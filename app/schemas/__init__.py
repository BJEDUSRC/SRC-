# -*- coding: utf-8 -*-
"""
Pydantic数据模型包

导出所有schemas。
"""

from app.schemas.document import (
    # 图片模型
    DocumentImageBase,
    DocumentImageCreate,
    DocumentImageResponse,
    
    # 文档模型
    DocumentBase,
    DocumentCreate,
    DocumentUpdate,
    DocumentResponse,
    DocumentListResponse,
    
    # 标签模型
    TagBase,
    TagCreate,
    TagResponse,
    
    # 上传模型
    DocumentUploadResponse,
    
    # 查询模型
    DocumentQueryParams,
    DocumentQueryResponse,
    
    # 下载模型
    DownloadRequest,
    DownloadLogResponse,
)

__all__ = [
    "DocumentImageBase",
    "DocumentImageCreate",
    "DocumentImageResponse",
    "DocumentBase",
    "DocumentCreate",
    "DocumentUpdate",
    "DocumentResponse",
    "DocumentListResponse",
    "TagBase",
    "TagCreate",
    "TagResponse",
    "DocumentUploadResponse",
    "DocumentQueryParams",
    "DocumentQueryResponse",
    "DownloadRequest",
    "DownloadLogResponse",
]
