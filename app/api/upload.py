# -*- coding: utf-8 -*-
"""
文档上传API接口

提供PDF文件上传和入库功能。
"""

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status, Form
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Optional, List
import tempfile
import os
import logging

from app.database import get_db
from app.schemas.document import DocumentUploadResponse, BatchUploadResponse, BatchUploadItem
from app.services.document_service import DocumentService
from app.services.pdf_converter import PDFConverter
from app.services.image_extractor import ImageExtractor
from app.services.desensitizer import Desensitizer
from app.services.file_service import FileService
from app.utils.helpers import is_valid_pdf, get_file_extension
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/upload",
    tags=["upload"],
    responses={404: {"description": "Not found"}}
)


@router.post(
    "/",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="上传PDF文档",
    description="上传PDF文件，自动转换为Markdown并进行数据脱敏"
)
async def upload_document(
    file: UploadFile = File(..., description="PDF文件"),
    extract_images: bool = Form(True),
    extract_tables: bool = Form(True),
    desensitize: bool = Form(True, description="是否启用脱敏"),
    tags: Optional[str] = Form(None, description="标签列表，逗号分隔"),
    db: Session = Depends(get_db)
):
    """
    上传PDF文档并处理入库
    
    完整流程：
    1. 验证文件格式
    2. 保存临时文件
    3. 调用文档服务处理（转换→脱敏→保存）
    4. 清理临时文件
    
    Args:
        file: 上传的PDF文件
        extract_images: 是否提取图片
        extract_tables: 是否提取表格
        desensitize: 是否启用LLM智能脱敏
        tags: 标签列表，逗号分隔（如：tag1,tag2,tag3）
        db: 数据库会话
        
    Returns:
        DocumentUploadResponse: 上传结果
        
    Raises:
        HTTPException: 文件格式错误或处理失败
    """
    temp_file_path = None
    
    try:
        # 1. 验证文件格式
        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="文件名不能为空"
            )
        
        if not is_valid_pdf(file.filename):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"不支持的文件格式，仅支持PDF文件。当前文件: {get_file_extension(file.filename)}"
            )
        
        # 2. 验证文件大小
        file_content = await file.read()
        file_size = len(file_content)
        
        if file_size > settings.MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"文件大小超过限制: {settings.MAX_FILE_SIZE / 1024 / 1024:.0f}MB"
            )
        
        if file_size == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="文件为空"
            )
        
        logger.info(f"收到上传文件: {file.filename} ({file_size} 字节)")
        
        # 3. 检查LLM服务是否可用（如果启用了脱敏）
        if desensitize:
            try:
                # 尝试初始化脱敏服务来检查LLM是否可用
                test_desensitizer = Desensitizer()
                if not test_desensitizer.enable_llm or test_desensitizer.chain is None:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="LLM脱敏服务不可用，无法上传文档。请检查LLM服务配置（LLM_API_KEY和LLM_API_BASE）或网络连接后重试。"
                    )
            except ValueError as e:
                # Desensitizer初始化失败（LLM不可用）
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"LLM脱敏服务不可用，无法上传文档。错误信息: {str(e)}。请检查LLM服务配置后重试。"
                )
            except Exception as e:
                logger.error(f"检查LLM服务状态失败: {e}", exc_info=True)
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"无法检查LLM服务状态: {str(e)}。请稍后重试。"
                )
        
        # 4. 检查文件是否已存在（根据原始文件名，在保存临时文件之前检查）
        from app.services.document_service import DocumentService
        temp_document_service = DocumentService(db=db)
        existing_document = temp_document_service.check_duplicate_by_filename(file.filename)
        
        if existing_document:
            # 获取已存在文档的标签信息
            tag_names = []
            if hasattr(existing_document, 'tags'):
                if hasattr(existing_document.tags, 'all'):
                    tag_names = [tag.name for tag in existing_document.tags.all()]
                elif isinstance(existing_document.tags, list):
                    tag_names = [tag.name for tag in existing_document.tags]
            
            # 构建错误信息，包含已存在文档的详细信息
            error_detail = {
                "message": f"文件 '{file.filename}' 已存在",
                "existing_document": {
                    "id": existing_document.id,
                    "filename": existing_document.filename,
                    "original_filename": existing_document.original_filename,
                    "file_size": existing_document.file_size,
                    "images_count": existing_document.images_count,
                    "is_desensitized": existing_document.is_desensitized,
                    "created_at": existing_document.created_at.isoformat() if existing_document.created_at else None,
                    "tags": tag_names
                },
                "suggestion": "如需上传新版本，请先删除已存在的文档，或使用不同的文件名。"
            }
            
            # 注意：此时还没有创建临时文件，所以不需要清理
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=error_detail
            )
        
        # 5. 保存临时文件（在确认文件不重复后）
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            temp_file.write(file_content)
            temp_file_path = temp_file.name
        
        # 6. 解析标签列表
        tag_list = None
        if tags:
            tag_list = [tag.strip() for tag in tags.split(',') if tag.strip()]
            logger.info(f"解析到 {len(tag_list)} 个标签: {tag_list}")
        
        # 7. 初始化服务
        image_extractor = ImageExtractor(output_base_dir=settings.CONVERTED_DIR)
        pdf_converter = PDFConverter(image_extractor=image_extractor)
        desensitizer = Desensitizer()
        file_service = FileService()
        
        document_service = DocumentService(
            db=db,
            pdf_converter=pdf_converter,
            desensitizer=desensitizer,
            file_service=file_service
        )
        
        # 8. 处理文档（使用LLM脱敏）
        result = document_service.process_document(
            pdf_path=temp_file_path,
            original_filename=file.filename,
            extract_images=extract_images,
            extract_tables=extract_tables,
            use_regex=False,  # 不使用正则
            use_llm=desensitize,  # 根据desensitize参数决定是否使用LLM
            tags=tag_list
        )
        
        # 9. 获取文档标签
        document = document_service.get_document(result['document_id'])
        tag_names = []
        if document and hasattr(document, 'tags'):
            if hasattr(document.tags, 'all'):
                tag_names = [tag.name for tag in document.tags.all()]
            elif isinstance(document.tags, list):
                tag_names = [tag.name for tag in document.tags]
        
        # 10. 构建响应
        from datetime import datetime
        response = DocumentUploadResponse(
            id=result['document_id'],  # 使用alias
            document_id=result['document_id'],
            filename=result['filename'],
            original_filename=result['original_filename'],
            file_size=result['file_size'],
            images_count=result['images_count'],
            is_desensitized=result['is_desensitized'],
            created_at=datetime.now(),
            message=result['message'],
            tags=tag_names
        )
        
        logger.info(f"文档上传成功: {result['document_id']}, 标签: {tag_names}")
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"文档上传失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"文档处理失败: {str(e)}"
        )
    finally:
        # 清理临时文件
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
                logger.debug(f"已删除临时文件: {temp_file_path}")
            except Exception as e:
                logger.warning(f"删除临时文件失败: {e}")


@router.post(
    "/batch",
    response_model=BatchUploadResponse,
    status_code=status.HTTP_200_OK,
    summary="批量上传PDF文档",
    description="批量上传文件夹中的PDF文件，自动跳过重复文件和非PDF文件"
)
async def batch_upload_documents(
    files: List[UploadFile] = File(..., description="PDF文件列表"),
    extract_images: bool = Form(True),
    extract_tables: bool = Form(True),
    desensitize: bool = Form(True, description="是否启用LLM智能脱敏"),
    tags: Optional[str] = Form(None, description="标签列表，逗号分隔"),
    db: Session = Depends(get_db)
):
    """
    批量上传PDF文档
    
    处理流程：
    1. 筛选PDF文件（忽略非PDF文件）
    2. 检查每个文件是否重复
    3. 只处理不重复的PDF文件
    4. 返回处理结果统计
    
    Args:
        files: PDF文件列表
        extract_images: 是否提取图片
        extract_tables: 是否提取表格
        desensitize: 是否启用LLM智能脱敏
        tags: 标签列表，逗号分隔
        db: 数据库会话
        
    Returns:
        BatchUploadResponse: 批量上传结果
    """
    temp_file_paths = []
    results = []
    success_count = 0
    duplicate_count = 0
    failed_count = 0
    skipped_count = 0
    
    # 检查LLM服务是否可用（如果启用了脱敏）
    if desensitize:
        try:
            # 尝试初始化脱敏服务来检查LLM是否可用
            test_desensitizer = Desensitizer()
            if not test_desensitizer.enable_llm or test_desensitizer.chain is None:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="LLM脱敏服务不可用，无法批量上传文档。请检查LLM服务配置（LLM_API_KEY和LLM_API_BASE）或网络连接后重试。"
                )
        except ValueError as e:
            # Desensitizer初始化失败（LLM不可用）
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"LLM脱敏服务不可用，无法批量上传文档。错误信息: {str(e)}。请检查LLM服务配置后重试。"
            )
        except Exception as e:
            logger.error(f"检查LLM服务状态失败: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"无法检查LLM服务状态: {str(e)}。请稍后重试。"
            )
    
    # 初始化服务（复用）
    image_extractor = ImageExtractor(output_base_dir=settings.CONVERTED_DIR)
    pdf_converter = PDFConverter(image_extractor=image_extractor)
    desensitizer = Desensitizer()
    file_service = FileService()
    
    document_service = DocumentService(
        db=db,
        pdf_converter=pdf_converter,
        desensitizer=desensitizer,
        file_service=file_service
    )
    
    # 解析标签列表
    tag_list = None
    if tags:
        tag_list = [tag.strip() for tag in tags.split(',') if tag.strip()]
        logger.info(f"批量上传解析到 {len(tag_list)} 个标签: {tag_list}")
    
    # 处理每个文件
    for file in files:
        temp_file_path = None
        file_content = None
        try:
            # 提取纯文件名（去掉路径，只保留文件名）
            original_filename = file.filename
            if original_filename:
                # 使用 os.path.basename 提取文件名，去掉文件夹路径
                import os
                clean_filename = os.path.basename(original_filename)
            else:
                clean_filename = None
            
            # 1. 验证文件格式（只处理PDF文件）
            if not clean_filename:
                skipped_count += 1
                results.append(BatchUploadItem(
                    filename="未知文件",
                    status="skipped",
                    message="文件名为空"
                ))
                continue
            
            if not is_valid_pdf(clean_filename):
                skipped_count += 1
                results.append(BatchUploadItem(
                    filename=clean_filename,
                    status="skipped",
                    message=f"非PDF文件，已忽略（{get_file_extension(clean_filename)}）"
                ))
                continue
            
            # 2. 读取文件内容（只读取一次）
            file_content = await file.read()
            file_size = len(file_content)
            
            if file_size > settings.MAX_FILE_SIZE:
                failed_count += 1
                results.append(BatchUploadItem(
                    filename=clean_filename,
                    status="error",
                    message=f"文件大小超过限制: {settings.MAX_FILE_SIZE / 1024 / 1024:.0f}MB",
                    error=f"文件大小: {file_size / 1024 / 1024:.2f}MB"
                ))
                continue
            
            if file_size == 0:
                failed_count += 1
                results.append(BatchUploadItem(
                    filename=clean_filename,
                    status="error",
                    message="文件为空",
                    error="文件大小为0"
                ))
                continue
            
            # 3. 检查文件是否已存在（使用纯文件名）
            existing_document = document_service.check_duplicate_by_filename(clean_filename)
            
            if existing_document:
                duplicate_count += 1
                results.append(BatchUploadItem(
                    filename=clean_filename,
                    status="duplicate",
                    message=f"文件已存在（文档ID: {existing_document.id}）",
                    existing_document_id=existing_document.id
                ))
                continue  # 跳过重复文件，不进行处理
            
            # 4. 保存临时文件
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
                temp_file.write(file_content)
                temp_file_path = temp_file.name
                temp_file_paths.append(temp_file_path)
            
            logger.info(f"批量上传处理文件: {clean_filename} ({file_size} 字节) [原始路径: {original_filename}]")
            
            # 5. 处理文档（使用纯文件名）
            result = document_service.process_document(
                pdf_path=temp_file_path,
                original_filename=clean_filename,  # 使用纯文件名，不包含路径
                extract_images=extract_images,
                extract_tables=extract_tables,
                use_regex=False,  # 不使用正则
                use_llm=desensitize,  # 根据desensitize参数决定是否使用LLM
                tags=tag_list
            )
            
            success_count += 1
            results.append(BatchUploadItem(
                filename=clean_filename,
                status="success",
                message="上传成功",
                document_id=result['document_id']
            ))
            
            logger.info(f"批量上传成功: {clean_filename} (ID: {result['document_id']})")
            
        except Exception as e:
            failed_count += 1
            error_msg = str(e)
            clean_filename_for_error = clean_filename if 'clean_filename' in locals() else (file.filename if file.filename else "未知文件")
            logger.error(f"批量上传处理文件失败: {clean_filename_for_error}, 错误: {error_msg}", exc_info=True)
            results.append(BatchUploadItem(
                filename=clean_filename_for_error,
                status="error",
                message=f"处理失败: {error_msg}",
                error=error_msg
            ))
        finally:
            # 清理临时文件
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                    if temp_file_path in temp_file_paths:
                        temp_file_paths.remove(temp_file_path)
                except Exception as e:
                    logger.warning(f"删除临时文件失败: {temp_file_path}, {e}")
    
    # 构建响应
    total = len(files)
    pdf_total = total - skipped_count  # PDF文件总数
    message = f"批量上传完成：共 {total} 个文件，其中PDF文件 {pdf_total} 个。成功 {success_count} 个，重复 {duplicate_count} 个，失败 {failed_count} 个，跳过非PDF文件 {skipped_count} 个"
    
    logger.info(f"批量上传完成: 总数={total}, PDF文件={pdf_total}, 成功={success_count}, 重复={duplicate_count}, 失败={failed_count}, 跳过={skipped_count}")
    
    return BatchUploadResponse(
        total=total,
        success=success_count,
        duplicate=duplicate_count,
        failed=failed_count,
        skipped=skipped_count,
        items=results,
        message=message
    )


@router.get(
    "/status",
    summary="上传状态检查",
    description="检查上传服务状态"
)
async def upload_status():
    """
    检查上传服务状态
    
    Returns:
        dict: 服务状态信息
    """
    return {
        "status": "ready",
        "max_file_size": settings.MAX_FILE_SIZE,
        "max_file_size_mb": settings.MAX_FILE_SIZE / 1024 / 1024,
        "supported_formats": ["pdf"],
        "batch_upload": True
    }
