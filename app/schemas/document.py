# -*- coding: utf-8 -*-
"""
文档相关的Pydantic数据模型

定义API请求和响应的数据结构。
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime
from app.models.document import DownloadType


# ==================== 基础模型 ====================

class DocumentImageBase(BaseModel):
    """图片基础模型"""
    filename: str = Field(..., description="图片文件名")
    file_path: str = Field(..., description="图片存储路径")
    page_number: Optional[int] = Field(None, description="所在PDF页码")
    image_index: Optional[int] = Field(None, description="页内图片序号")
    file_size: Optional[int] = Field(None, description="图片大小(字节)")


class DocumentImageCreate(DocumentImageBase):
    """创建图片记录"""
    document_id: str = Field(..., description="关联文档ID")


class DocumentImageResponse(DocumentImageBase):
    """图片响应模型"""
    id: int
    document_id: str
    created_at: datetime
    
    class Config:
        from_attributes = True


# ==================== 文档模型 ====================

class DocumentBase(BaseModel):
    """文档基础模型"""
    filename: str = Field(..., max_length=255, description="MD文件名")
    original_filename: str = Field(..., max_length=255, description="原始PDF文件名")
    file_path: str = Field(..., max_length=500, description="MD文件存储路径")
    file_size: Optional[int] = Field(None, description="文件大小(字节)")
    content_preview: Optional[str] = Field(None, description="内容预览(前500字)")
    full_content: Optional[str] = Field(None, description="完整内容")
    is_desensitized: bool = Field(True, description="是否已脱敏")


class DocumentCreate(DocumentBase):
    """创建文档请求模型"""
    pass


class DocumentUpdate(BaseModel):
    """更新文档请求模型"""
    filename: Optional[str] = Field(None, max_length=255)
    content_preview: Optional[str] = None
    full_content: Optional[str] = None
    is_desensitized: Optional[bool] = None


class DocumentResponse(DocumentBase):
    """文档响应模型"""
    id: str
    images_count: int
    created_at: datetime
    updated_at: datetime
    images: List[DocumentImageResponse] = []
    tags: List[str] = []
    
    class Config:
        from_attributes = True


class DocumentListResponse(BaseModel):
    """文档列表响应模型"""
    id: str
    filename: str
    original_filename: str
    file_size: Optional[int]
    content_preview: Optional[str]
    images_count: int
    is_desensitized: bool
    created_at: datetime
    updated_at: datetime
    tags: List[str] = []
    
    class Config:
        from_attributes = True


# ==================== 标签模型 ====================

class TagBase(BaseModel):
    """标签基础模型"""
    name: str = Field(..., max_length=100, description="标签名称")
    
    @validator('name')
    def validate_name(cls, v):
        """验证标签名称"""
        if not v or not v.strip():
            raise ValueError('标签名称不能为空')
        return v.strip()


class TagCreate(TagBase):
    """创建标签请求模型"""
    pass


class TagResponse(TagBase):
    """标签响应模型"""
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True


# ==================== 上传模型 ====================

class DocumentUploadResponse(BaseModel):
    """文档上传响应模型"""
    document_id: str = Field(..., description="文档ID", alias="id")
    filename: str = Field(..., description="MD文件名")
    original_filename: str = Field(..., description="原始PDF文件名")
    file_size: int = Field(..., description="文件大小(字节)")
    images_count: int = Field(..., description="关联图片数量")
    is_desensitized: bool = Field(..., description="是否已脱敏")
    created_at: datetime = Field(..., description="创建时间")
    message: str = Field(..., description="处理结果消息")
    tags: List[str] = Field(default_factory=list, description="文档标签列表")
    
    class Config:
        populate_by_name = True  # 允许使用alias和字段名


class BatchUploadItem(BaseModel):
    """批量上传单个文件结果"""
    filename: str = Field(..., description="文件名")
    status: str = Field(..., description="状态：success/duplicate/error")
    message: str = Field(..., description="处理消息")
    document_id: Optional[str] = Field(None, description="文档ID（成功时）")
    error: Optional[str] = Field(None, description="错误信息（失败时）")
    existing_document_id: Optional[str] = Field(None, description="已存在文档ID（重复时）")


class BatchUploadResponse(BaseModel):
    """批量上传响应模型"""
    total: int = Field(..., description="总文件数")
    success: int = Field(..., description="成功数量")
    duplicate: int = Field(..., description="重复数量")
    failed: int = Field(..., description="失败数量")
    skipped: int = Field(..., description="跳过数量（非PDF文件）")
    items: List[BatchUploadItem] = Field(..., description="处理结果列表")
    message: str = Field(..., description="处理结果消息")


# ==================== 查询模型 ====================

class DocumentQueryParams(BaseModel):
    """文档查询参数模型"""
    keyword: Optional[str] = Field(None, description="关键词（全文搜索）")
    filename: Optional[str] = Field(None, description="文件名（模糊匹配）")
    start_date: Optional[datetime] = Field(None, description="开始时间")
    end_date: Optional[datetime] = Field(None, description="结束时间")
    tags: Optional[List[str]] = Field(None, description="标签列表")
    is_desensitized: Optional[bool] = Field(None, description="是否已脱敏")
    page: int = Field(1, ge=1, description="页码")
    page_size: int = Field(20, ge=1, le=1000, description="每页数量")
    sort_by: str = Field("created_at", description="排序字段")
    sort_order: str = Field("desc", pattern="^(asc|desc)$", description="排序方向")
    
    class Config:
        json_schema_extra = {
            "example": {
                "keyword": "安全",
                "filename": "报告",
                "page": 1,
                "page_size": 20,
                "sort_by": "created_at",
                "sort_order": "desc"
            }
        }


class DocumentQueryResponse(BaseModel):
    """文档查询响应模型"""
    total: int = Field(..., description="总记录数")
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页数量")
    total_pages: int = Field(..., description="总页数")
    items: List[DocumentListResponse] = Field(..., description="文档列表")


# ==================== 下载模型 ====================

class DownloadRequest(BaseModel):
    """下载请求模型"""
    document_ids: List[str] = Field(..., min_items=1, description="文档ID列表")
    include_images: bool = Field(True, description="是否包含图片")
    
    @validator('document_ids')
    def validate_document_ids(cls, v):
        """验证文档ID列表"""
        if not v:
            raise ValueError('文档ID列表不能为空')
        return v


class DownloadLogResponse(BaseModel):
    """下载记录响应模型"""
    id: int
    document_id: str
    download_type: DownloadType
    include_images: bool
    download_time: datetime
    
    class Config:
        from_attributes = True
