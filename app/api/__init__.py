# -*- coding: utf-8 -*-
"""
API路由包

导出所有API路由。
"""

from app.api import upload, query, download, convert, desensitize_api, web

__all__ = [
    "upload",
    "query",
    "download",
    "convert",
    "desensitize_api",
    "web",
]
