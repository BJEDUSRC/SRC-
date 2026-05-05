# -*- coding: utf-8 -*-
"""
文档下载API接口

提供单文件下载、批量下载等功能。
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, StreamingResponse, Response
from sqlalchemy.orm import Session
from typing import List, Union
import logging

from app.database import get_db
from app.schemas.document import DownloadRequest, DownloadLogResponse
from app.services.download_service import DownloadService
from app.models.document import DownloadLog, DownloadType

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/download",
    tags=["download"],
    responses={404: {"description": "Not found"}}
)


@router.get(
    "/{document_id}",
    summary="下载单个文档",
    description="根据文档ID下载文档，可选择是否包含图片"
)
async def download_document(
    document_id: str,
    include_images: bool = Query(True, description="是否包含图片"),
    db: Session = Depends(get_db)
):
    """
    下载单个文档
    
    如果包含图片，返回ZIP文件（包含MD文件和所有图片）；
    否则只返回MD文件。
    
    Args:
        document_id: 文档ID（UUID）
        include_images: 是否包含图片（默认True）
        db: 数据库会话
        
    Returns:
        Union[FileResponse, StreamingResponse]: 文件响应（MD文件或ZIP文件）
        
    Raises:
        HTTPException: 文档不存在时返回404
    """
    try:
        download_service = DownloadService(db=db)
        response = download_service.download_single(
            doc_id=document_id,
            include_images=include_images
        )
        
        if not response:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"文档不存在: {document_id}"
            )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"下载文档失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"下载失败: {str(e)}"
        )


@router.post(
    "/batch",
    summary="批量下载文档",
    description="批量下载多个文档，打包为ZIP文件"
)
async def download_batch(
    request: DownloadRequest,
    db: Session = Depends(get_db)
):
    """
    批量下载文档
    
    将多个文档打包为ZIP文件，每个文档在ZIP中保持独立的目录结构。
    
    Args:
        request: 下载请求，包含文档ID列表和是否包含图片
        db: 数据库会话
        
    Returns:
        StreamingResponse: ZIP文件流
        
    Raises:
        HTTPException: 文档不存在或下载失败时返回错误
    """
    try:
        download_service = DownloadService(db=db)
        response = await download_service.download_batch(
            doc_ids=request.document_ids,
            include_images=request.include_images
        )
        
        if not response:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="没有找到任何文档"
            )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"批量下载失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"批量下载失败: {str(e)}"
        )


@router.get(
    "/stats/{document_id}",
    summary="获取下载统计",
    description="获取指定文档的下载统计信息"
)
async def get_download_stats(
    document_id: str,
    db: Session = Depends(get_db)
):
    """
    获取文档下载统计
    
    返回文档的下载次数统计，包括：
    - 总下载次数
    - 单文件下载次数
    - 批量下载次数
    
    Args:
        document_id: 文档ID
        db: 数据库会话
        
    Returns:
        dict: 下载统计信息
    """
    try:
        download_service = DownloadService(db=db)
        stats = download_service.get_download_stats(document_id)
        return stats
    except Exception as e:
        logger.error(f"获取下载统计失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取统计失败: {str(e)}"
        )


@router.get(
    "/logs/{document_id}",
    response_model=List[DownloadLogResponse],
    summary="获取下载记录",
    description="获取指定文档的下载记录列表"
)
async def get_download_logs(
    document_id: str,
    limit: int = Query(50, ge=1, le=100, description="返回记录数"),
    db: Session = Depends(get_db)
):
    """
    获取文档下载记录
    
    返回指定文档的下载历史记录。
    
    Args:
        document_id: 文档ID
        limit: 返回记录数（默认50，最大100）
        db: 数据库会话
        
    Returns:
        List[DownloadLogResponse]: 下载记录列表
    """
    try:
        # 使用原始SQL查询避免SQLAlchemy枚举转换问题
        from sqlalchemy import text
        logs_raw = db.execute(
            text("""
                SELECT id, document_id, download_type, include_images, download_time
                FROM download_logs
                WHERE document_id = :document_id
                ORDER BY download_time DESC
                LIMIT :limit
            """),
            {"document_id": document_id, "limit": limit}
        ).fetchall()
        
        result = []
        for row in logs_raw:
            log_id, doc_id, download_type_raw, include_images, download_time = row
            
            # 转换为枚举对象（简化逻辑）
            download_type = _parse_download_type(download_type_raw)
            
            result.append(DownloadLogResponse(
                id=log_id,
                document_id=doc_id,
                download_type=download_type,
                include_images=include_images,
                download_time=download_time
            ))
        
        return result
    except Exception as e:
        logger.error(f"获取下载记录失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取下载记录失败: {str(e)}"
        )


def _parse_download_type(value) -> DownloadType:
    """
    解析下载类型枚举
    
    Args:
        value: 原始值（可能是枚举、字符串或其他类型）
        
    Returns:
        DownloadType: 下载类型枚举
    """
    if isinstance(value, DownloadType):
        return value
    
    # 转换为字符串并标准化
    type_str = str(value).lower().strip()
    
    # 映射表
    type_map = {
        'single': DownloadType.SINGLE,
        'batch': DownloadType.BATCH
    }
    
    return type_map.get(type_str, DownloadType.SINGLE)
