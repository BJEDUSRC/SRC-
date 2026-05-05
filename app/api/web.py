# -*- coding: utf-8 -*-
"""
Web 页面路由

提供前端页面的路由处理
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

# 创建路由器
router = APIRouter(tags=["Web"])

# 模板目录
templates_dir = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


@router.get("/", response_class=HTMLResponse, summary="首页")
async def index(request: Request):
    """
    系统首页
    
    显示系统概览、统计数据和最近文档
    """
    return templates.TemplateResponse(
        "index.html",
        {"request": request}
    )


@router.get("/upload", response_class=HTMLResponse, summary="上传页面")
async def upload_page(request: Request):
    """
    文档上传页面
    
    提供PDF文件上传功能
    """
    return templates.TemplateResponse(
        "upload.html",
        {"request": request}
    )


@router.get("/query", response_class=HTMLResponse, summary="查询页面")
async def query_page(request: Request):
    """
    文档查询页面
    
    提供文档搜索和筛选功能
    """
    return templates.TemplateResponse(
        "query.html",
        {"request": request}
    )


@router.get("/download", response_class=HTMLResponse, summary="下载页面")
async def download_page(request: Request):
    """
    下载管理页面
    
    提供文档下载和下载记录管理功能
    """
    return templates.TemplateResponse(
        "download.html",
        {"request": request}
    )


@router.get("/convert", response_class=HTMLResponse, summary="PDF转换页面")
async def convert_page(request: Request):
    """
    PDF转换页面
    
    提供PDF到Markdown的纯转换功能（不脱敏）
    """
    return templates.TemplateResponse(
        "convert.html",
        {"request": request}
    )


@router.get("/desensitize", response_class=HTMLResponse, summary="数据脱敏页面")
async def desensitize_page(request: Request):
    """
    数据脱敏页面
    
    提供纯文本数据脱敏功能
    """
    return templates.TemplateResponse(
        "desensitize.html",
        {"request": request}
    )
