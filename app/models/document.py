# -*- coding: utf-8 -*-
"""
文档相关数据库模型

定义Document、DocumentImage、Tag等ORM模型。
"""

from sqlalchemy import (
    Column, String, BigInteger, DateTime, Boolean, Text, Integer, 
    ForeignKey, Table, Enum
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
from app.utils.helpers import generate_uuid
import enum


# 下载类型枚举
class DownloadType(str, enum.Enum):
    """下载类型枚举"""
    SINGLE = "single"
    BATCH = "batch"


# 文档-标签关联表（多对多关系）
document_tags = Table(
    'document_tags',
    Base.metadata,
    Column('document_id', String(36), ForeignKey('documents.id', ondelete='CASCADE'), primary_key=True),
    Column('tag_id', BigInteger, ForeignKey('tags.id', ondelete='CASCADE'), primary_key=True)
)


class Document(Base):
    """
    文档模型
    
    存储PDF转换后的Markdown文档信息。
    """
    __tablename__ = 'documents'
    
    id = Column(String(36), primary_key=True, default=generate_uuid, comment='文档UUID')
    filename = Column(String(255), nullable=False, comment='MD文件名')
    original_filename = Column(String(255), nullable=False, comment='原始PDF文件名')
    file_path = Column(String(500), nullable=False, comment='MD文件存储路径')
    file_size = Column(BigInteger, comment='文件大小(字节)')
    content_preview = Column(Text, comment='内容预览(前500字)')
    full_content = Column(Text, comment='完整内容(用于全文搜索)')
    images_count = Column(Integer, default=0, comment='关联图片数量')
    is_desensitized = Column(Boolean, default=True, comment='是否已脱敏')
    created_at = Column(DateTime, default=func.now(), comment='创建时间')
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), comment='更新时间')
    
    # 关联关系
    images = relationship(
        "DocumentImage", 
        back_populates="document", 
        cascade="all, delete-orphan",
        lazy="dynamic"
    )
    tags = relationship(
        "Tag", 
        secondary=document_tags, 
        back_populates="documents",
        lazy="dynamic"
    )
    download_logs = relationship(
        "DownloadLog",
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="dynamic"
    )
    
    def __repr__(self) -> str:
        return f"<Document(id={self.id}, filename={self.filename})>"


class DocumentImage(Base):
    """
    文档图片模型
    
    存储从PDF中提取的图片信息。
    """
    __tablename__ = 'document_images'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    document_id = Column(
        String(36), 
        ForeignKey('documents.id', ondelete='CASCADE'), 
        nullable=False,
        comment='关联文档ID'
    )
    filename = Column(String(255), nullable=False, comment='图片文件名')
    file_path = Column(String(500), nullable=False, comment='图片存储路径')
    page_number = Column(Integer, comment='所在PDF页码')
    image_index = Column(Integer, comment='页内图片序号')
    file_size = Column(BigInteger, comment='图片大小(字节)')
    created_at = Column(DateTime, default=func.now(), comment='创建时间')
    
    # 关联关系
    document = relationship("Document", back_populates="images")
    
    def __repr__(self) -> str:
        return f"<DocumentImage(id={self.id}, filename={self.filename}, page={self.page_number})>"


class Tag(Base):
    """
    标签模型
    
    用于文档分类和标记。
    """
    __tablename__ = 'tags'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False, comment='标签名称')
    created_at = Column(DateTime, default=func.now(), comment='创建时间')
    
    # 关联关系
    documents = relationship(
        "Document", 
        secondary=document_tags, 
        back_populates="tags",
        lazy="dynamic"
    )
    
    def __repr__(self) -> str:
        return f"<Tag(id={self.id}, name={self.name})>"


class DownloadLog(Base):
    """
    下载记录模型
    
    记录文档下载历史。
    """
    __tablename__ = 'download_logs'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    document_id = Column(
        String(36),
        ForeignKey('documents.id', ondelete='CASCADE'),
        nullable=False,
        comment='关联文档ID'
    )
    download_type = Column(
        Enum(DownloadType, native_enum=False, length=10, create_constraint=False),
        default=DownloadType.SINGLE,
        comment='下载类型'
    )
    include_images = Column(Boolean, default=True, comment='是否包含图片')
    download_time = Column(DateTime, default=func.now(), comment='下载时间')
    
    # 关联关系
    document = relationship("Document", back_populates="download_logs")
    
    def __repr__(self) -> str:
        return f"<DownloadLog(id={self.id}, document_id={self.document_id}, type={self.download_type})>"


class URLDesensitizationMap(Base):
    """
    URL脱敏映射表
    
    记录URL路径段的脱敏映射关系，用于跨文档一致脱敏。
    最大存储1000条记录，按先进先出原则更新。
    """
    __tablename__ = 'url_desensitization_maps'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    original_path_segment = Column(String(100), unique=True, nullable=False, comment='原始路径段')
    desensitized_path_segment = Column(String(100), nullable=False, comment='脱敏后的路径段')
    created_at = Column(DateTime, default=func.now(), comment='创建时间')
    
    def __repr__(self) -> str:
        return f"<URLDesensitizationMap(id={self.id}, original={self.original_path_segment}, desensitized={self.desensitized_path_segment})>"
