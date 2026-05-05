# -*- coding: utf-8 -*-
"""
文档查询API接口

提供文档查询、全文搜索、详情获取等功能。
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
import logging

from app.database import get_db
from app.schemas.document import (
    DocumentQueryParams,
    DocumentQueryResponse,
    DocumentResponse,
    DocumentListResponse
)
from app.services.query_service import QueryService
from app.models.document import Document
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class BatchDeleteRequest(BaseModel):
    """批量删除请求模型"""
    document_ids: List[str]

router = APIRouter(
    prefix="/api/v1/documents",
    tags=["documents"],
    responses={404: {"description": "Not found"}}
)


def _convert_document_to_response(doc: Document) -> DocumentListResponse:
    """
    将文档模型转换为响应模型
    
    Args:
        doc: Document模型实例
        
    Returns:
        DocumentListResponse: 响应模型
    """
    # 获取标签名称列表
    tag_names = []
    if hasattr(doc, 'tags'):
        if hasattr(doc.tags, 'all'):
            tag_names = [tag.name for tag in doc.tags.all()]
        elif isinstance(doc.tags, list):
            tag_names = [tag.name for tag in doc.tags]
    
    return DocumentListResponse(
        id=doc.id,
        filename=doc.filename,
        original_filename=doc.original_filename,
        file_size=doc.file_size,
        content_preview=doc.content_preview,
        images_count=doc.images_count,
        is_desensitized=doc.is_desensitized,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        tags=tag_names
    )


def _build_query_response(result: dict) -> DocumentQueryResponse:
    """
    构建查询响应
    
    Args:
        result: 查询结果字典
        
    Returns:
        DocumentQueryResponse: 查询响应
    """
    items = [_convert_document_to_response(doc) for doc in result['items']]
    
    return DocumentQueryResponse(
        total=result['total'],
        page=result['page'],
        page_size=result['page_size'],
        total_pages=result['total_pages'],
        items=items
    )


@router.get(
    "/",
    response_model=DocumentQueryResponse,
    summary="查询文档列表",
    description="支持多种查询条件：关键词全文搜索、文件名、时间范围、标签、分页排序"
)
async def query_documents(
    keyword: Optional[str] = Query(None, description="关键词（全文搜索）"),
    filename: Optional[str] = Query(None, description="文件名（模糊匹配）"),
    start_date: Optional[datetime] = Query(None, description="开始时间"),
    end_date: Optional[datetime] = Query(None, description="结束时间"),
    tags: Optional[str] = Query(None, description="标签列表（逗号分隔）"),
    is_desensitized: Optional[bool] = Query(None, description="是否已脱敏"),
    vulnerability_level: Optional[str] = Query(None, description="漏洞等级（严重/高危/中危/其他）"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=1000, description="每页数量"),
    sort_by: str = Query("created_at", description="排序字段"),
    sort_order: str = Query("desc", regex="^(asc|desc)$", description="排序方向"),
    db: Session = Depends(get_db)
):
    """
    查询文档列表
    
    支持多种查询条件组合：
    - 关键词全文搜索（基于MySQL FULLTEXT）
    - 文件名模糊匹配
    - 时间范围查询
    - 标签筛选（支持多个标签，AND关系）
    - 脱敏状态筛选
    - 分页和排序
    
    Args:
        keyword: 关键词（全文搜索）
        filename: 文件名（模糊匹配）
        start_date: 开始时间（ISO格式）
        end_date: 结束时间（ISO格式）
        tags: 标签列表（逗号分隔，如：tag1,tag2）
        is_desensitized: 是否已脱敏
        page: 页码（从1开始）
        page_size: 每页数量（1-1000）
        sort_by: 排序字段（created_at, updated_at, filename, file_size, images_count）
        sort_order: 排序方向（asc/desc）
        db: 数据库会话
        
    Returns:
        DocumentQueryResponse: 查询结果，包含总数、分页信息和文档列表
        
    Example:
        ```
        GET /api/v1/documents/?keyword=安全&page=1&page_size=20
        GET /api/v1/documents/?filename=报告&tags=漏洞,安全&start_date=2026-01-01
        ```
    """
    try:
        # 解析标签列表
        tag_list = None
        if tags:
            tag_list = [tag.strip() for tag in tags.split(',') if tag.strip()]
        
        # 创建查询服务并执行查询
        query_service = QueryService(db=db)
        result = query_service.search_documents(
            keyword=keyword,
            filename=filename,
            start_date=start_date,
            end_date=end_date,
            tags=tag_list,
            is_desensitized=is_desensitized,
            vulnerability_level=vulnerability_level,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order
        )
        
        return _build_query_response(result)
        
    except Exception as e:
        logger.error(f"查询文档列表失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查询失败: {str(e)}"
        )


@router.get(
    "/search",
    response_model=DocumentQueryResponse,
    summary="全文搜索",
    description="基于MySQL FULLTEXT索引进行全文搜索（支持中文分词）"
)
async def fulltext_search(
    q: str = Query(..., description="搜索关键词"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=1000, description="每页数量"),
    db: Session = Depends(get_db)
):
    """
    全文搜索
    
    使用MySQL的FULLTEXT索引进行全文搜索，支持中文分词（ngram）。
    搜索范围包括文档的完整内容。
    
    Args:
        q: 搜索关键词
        page: 页码（从1开始）
        page_size: 每页数量（1-1000）
        db: 数据库会话
        
    Returns:
        DocumentQueryResponse: 搜索结果
        
    Example:
        ```
        GET /api/v1/documents/search?q=安全漏洞&page=1
        ```
    """
    try:
        if not q or not q.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="搜索关键词不能为空"
            )
        
        # 创建查询服务并执行全文搜索
        query_service = QueryService(db=db)
        result = query_service.search_documents(
            keyword=q.strip(),
            page=page,
            page_size=page_size,
            sort_by='created_at',
            sort_order='desc'
        )
        
        return _build_query_response(result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"全文搜索失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"搜索失败: {str(e)}"
        )


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="获取文档详情",
    description="根据文档ID获取完整文档信息，包括图片和标签"
)
async def get_document(
    document_id: str,
    db: Session = Depends(get_db)
):
    """
    获取文档详情
    
    根据文档ID获取完整的文档信息，包括：
    - 文档基本信息
    - 关联的图片列表
    - 关联的标签列表
    
    Args:
        document_id: 文档ID（UUID）
        db: 数据库会话
        
    Returns:
        DocumentResponse: 文档详情
        
    Raises:
        HTTPException: 文档不存在时返回404
    """
    try:
        query_service = QueryService(db=db)
        document = query_service.get_document_by_id(document_id)
        
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"文档不存在: {document_id}"
            )
        
        # 获取图片列表
        from app.schemas.document import DocumentImageResponse
        if hasattr(document.images, 'all'):
            images_list = document.images.all()
        else:
            images_list = document.images
        
        images = [
            DocumentImageResponse(
                id=img.id,
                document_id=img.document_id,
                filename=img.filename,
                file_path=img.file_path,
                page_number=img.page_number,
                image_index=img.image_index,
                file_size=img.file_size,
                created_at=img.created_at
            )
            for img in images_list
        ]
        
        # 获取标签列表
        if hasattr(document.tags, 'all'):
            tag_names = [tag.name for tag in document.tags.all()]
        else:
            tag_names = []
        
        return DocumentResponse(
            id=document.id,
            filename=document.filename,
            original_filename=document.original_filename,
            file_path=document.file_path,
            file_size=document.file_size,
            content_preview=document.content_preview,
            full_content=document.full_content,
            images_count=document.images_count,
            is_desensitized=document.is_desensitized,
            created_at=document.created_at,
            updated_at=document.updated_at,
            images=images,
            tags=tag_names
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取文档详情失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取文档详情失败: {str(e)}"
        )


@router.delete(
    "/{document_id}",
    summary="删除文档",
    description="删除指定ID的文档及其关联的文件和数据"
)
async def delete_document(
    document_id: str,
    db: Session = Depends(get_db)
):
    """
    删除文档
    
    删除文档及其关联的：
    - Markdown文件
    - 图片文件
    - 数据库记录（文档、图片、标签关联）
    
    Args:
        document_id: 文档ID
        db: 数据库会话
        
    Returns:
        删除结果
        
    Raises:
        HTTPException: 文档不存在或删除失败
    """
    try:
        query_service = QueryService(db=db)
        success = query_service.delete_document(document_id)
        
        return {
            "success": True,
            "message": f"文档删除成功",
            "document_id": document_id
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"删除文档失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除文档失败: {str(e)}"
        )


@router.post(
    "/batch-delete",
    summary="批量删除文档",
    description="批量删除多个文档及其关联的文件和数据"
)
async def batch_delete_documents(
    request: BatchDeleteRequest,
    db: Session = Depends(get_db)
):
    """
    批量删除文档
    
    Args:
        request: 批量删除请求，包含文档ID列表
        db: 数据库会话
        
    Returns:
        批量删除结果统计
    """
    try:
        if not request.document_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="文档ID列表不能为空"
            )
        
        query_service = QueryService(db=db)
        result = query_service.batch_delete_documents(request.document_ids)
        
        return {
            "success": True,
            "message": f"批量删除完成：成功 {result['success']} 个，失败 {result['failed']} 个",
            "result": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"批量删除文档失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"批量删除失败: {str(e)}"
        )
