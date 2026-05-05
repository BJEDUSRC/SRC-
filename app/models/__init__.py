# -*- coding: utf-8 -*-
"""
数据库模型包

导出所有ORM模型。
"""

from app.models.document import (
    Document,
    DocumentImage,
    Tag,
    DownloadLog,
    DownloadType,
    document_tags
)

__all__ = [
    "Document",
    "DocumentImage",
    "Tag",
    "DownloadLog",
    "DownloadType",
    "document_tags",
]
