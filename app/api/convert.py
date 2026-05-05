# -*- coding: utf-8 -*-
"""
PDF转换API接口

提供PDF到Markdown的纯转换功能（不进行脱敏处理）。
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional
import tempfile
import os
import logging

from app.services.pdf_converter import PDFConverter
from app.services.image_extractor import ImageExtractor
from app.utils.helpers import is_valid_pdf, get_file_extension
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/convert",
    tags=["convert"],
    responses={404: {"description": "Not found"}}
)


class ConvertResponse(BaseModel):
    """PDF转换响应模型"""
    filename: str
    markdown_content: str
    images_count: int
    images: List[dict] = []
    message: str


@router.post(
    "",
    response_model=ConvertResponse,
    summary="PDF转Markdown",
    description="将PDF文件转换为Markdown格式，不进行数据脱敏"
)
async def convert_pdf_to_markdown(
    file: UploadFile = File(..., description="PDF文件"),
    extract_images: bool = True,
    extract_tables: bool = True
):
    """
    将PDF转换为Markdown格式
    
    仅进行格式转换，不进行数据脱敏处理。
    
    Args:
        file: 上传的PDF文件
        extract_images: 是否提取图片
        extract_tables: 是否提取表格
        
    Returns:
        ConvertResponse: 转换结果，包含Markdown内容
        
    Raises:
        HTTPException: 文件格式错误或转换失败
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
        
        # 3. 保存临时文件
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            temp_file.write(file_content)
            temp_file_path = temp_file.name
        
        logger.info(f"开始转换PDF: {file.filename} ({file_size} 字节)")
        
        # 4. 初始化转换器
        image_extractor = None
        if extract_images:
            image_extractor = ImageExtractor(output_base_dir=settings.CONVERTED_DIR)
        
        pdf_converter = PDFConverter(image_extractor=image_extractor)
        
        # 5. 执行转换
        markdown_content, images_info = pdf_converter.convert_to_markdown(
            pdf_path=temp_file_path,
            doc_id=None,  # 不保存到数据库，不需要doc_id
            extract_images=extract_images,
            extract_tables=extract_tables
        )
        
        # 6. 构建响应
        response = ConvertResponse(
            filename=file.filename,
            markdown_content=markdown_content,
            images_count=len(images_info),
            images=images_info,
            message="PDF转换成功"
        )
        
        logger.info(f"PDF转换完成: {file.filename}, 图片数: {len(images_info)}")
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"PDF转换失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PDF转换失败: {str(e)}"
        )
    finally:
        # 清理临时文件
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
                logger.debug(f"已删除临时文件: {temp_file_path}")
            except Exception as e:
                logger.warning(f"删除临时文件失败: {e}")


@router.get(
    "/status",
    summary="转换服务状态检查",
    description="检查PDF转换服务状态"
)
async def convert_status():
    """
    检查PDF转换服务状态
    
    Returns:
        dict: 服务状态信息
    """
    return {
        "status": "ready",
        "max_file_size": settings.MAX_FILE_SIZE,
        "max_file_size_mb": settings.MAX_FILE_SIZE / 1024 / 1024,
        "supported_formats": ["pdf"],
        "features": {
            "extract_images": True,
            "extract_tables": True,
            "preserve_layout": True
        }
    }
