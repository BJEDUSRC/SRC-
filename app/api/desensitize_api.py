# -*- coding: utf-8 -*-
"""
数据脱敏API接口

提供纯文本数据脱敏功能。
"""

from fastapi import APIRouter, HTTPException, status, UploadFile, File, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Dict, Optional, List
import logging
import tempfile
import os

from app.services.desensitizer import Desensitizer
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/desensitize",
    tags=["desensitize"],
    responses={404: {"description": "Not found"}}
)

# 创建全局脱敏器实例（避免每次请求都初始化LLM）
_desensitizer: Optional[Desensitizer] = None


def get_desensitizer() -> Desensitizer:
    """获取或创建脱敏器实例"""
    global _desensitizer
    if _desensitizer is None:
        _desensitizer = Desensitizer(enable_llm=True, llm_priority=True)
    return _desensitizer


class DesensitizeRequest(BaseModel):
    """脱敏请求模型"""
    text: str = Field(..., description="需要脱敏的文本", min_length=1, max_length=100000)


class DesensitizeResponse(BaseModel):
    """脱敏响应模型"""
    desensitized_text: str = Field(..., description="脱敏后的文本")
    llm_tokens: int = Field(0, description="LLM使用的token数")
    llm_success: bool = Field(False, description="LLM脱敏是否成功")
    method: str = Field("none", description="使用的脱敏方法")


class AnalyzeRequest(BaseModel):
    """敏感信息分析请求模型"""
    text: str = Field(..., description="需要分析的文本", min_length=1, max_length=100000)


class AnalyzeResponse(BaseModel):
    """敏感信息分析响应模型"""
    total_sensitive_count: int = Field(0, description="敏感信息总数")
    sensitive_types: Dict[str, int] = Field(default_factory=dict, description="敏感信息类型统计")
    risk_level: str = Field("low", description="风险等级")
    recommendations: List[str] = Field(default_factory=list, description="处理建议")


class ValidateRequest(BaseModel):
    """脱敏验证请求模型"""
    original: str = Field(..., description="原始文本")
    desensitized: str = Field(..., description="脱敏后的文本")


class ValidateResponse(BaseModel):
    """脱敏验证响应模型"""
    is_safe: bool = Field(False, description="是否安全")
    security_level: str = Field("low", description="安全等级")
    remaining_sensitive: Dict[str, int] = Field(default_factory=dict, description="残留敏感信息")
    reduction_ratio: float = Field(0.0, description="文本缩减比例")
    total_issues: int = Field(0, description="问题总数")
    warnings: List[str] = Field(default_factory=list, description="警告信息")
    suggestions: List[str] = Field(default_factory=list, description="改进建议")


@router.post(
    "",
    response_model=DesensitizeResponse,
    summary="文本脱敏",
    description="对输入文本进行LLM智能脱敏处理"
)
async def desensitize_text(request: DesensitizeRequest):
    """
    对文本进行LLM智能脱敏处理
    
    Args:
        request: 脱敏请求，包含需要脱敏的文本
        
    Returns:
        DesensitizeResponse: 脱敏结果
        
    Raises:
        HTTPException: 脱敏处理失败
    """
    try:
        logger.info(f"开始文本脱敏，文本长度: {len(request.text)} 字符")
        
        desensitizer = get_desensitizer()
        
        # 执行脱敏（仅使用LLM）
        result = desensitizer.desensitize_sync(
            text=request.text,
            use_llm=True
        )
        
        response = DesensitizeResponse(
            desensitized_text=result.get("desensitized_text", request.text),
            llm_tokens=result.get("llm_tokens", 0),
            llm_success=result.get("llm_success", False),
            method=result.get("method", "none")
        )
        
        logger.info(f"文本脱敏完成，方法: {response.method}")
        
        return response
        
    except Exception as e:
        logger.error(f"文本脱敏失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"脱敏处理失败: {str(e)}"
        )


@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    summary="敏感信息分析",
    description="分析文本中的敏感信息分布（不进行脱敏）"
)
async def analyze_sensitive_info(request: AnalyzeRequest):
    """
    分析文本中的敏感信息
    
    仅进行分析统计，不修改原文本。
    
    Args:
        request: 分析请求
        
    Returns:
        AnalyzeResponse: 分析结果
        
    Raises:
        HTTPException: 分析失败
    """
    try:
        logger.info(f"开始敏感信息分析，文本长度: {len(request.text)} 字符")
        
        desensitizer = get_desensitizer()
        
        # 执行分析
        result = desensitizer.get_sensitive_info_summary(request.text)
        
        response = AnalyzeResponse(
            total_sensitive_count=result.get("total_sensitive_count", 0),
            sensitive_types=result.get("sensitive_types", {}),
            risk_level=result.get("risk_level", "low"),
            recommendations=result.get("recommendations", [])
        )
        
        logger.info(f"敏感信息分析完成，风险等级: {response.risk_level}")
        
        return response
        
    except Exception as e:
        logger.error(f"敏感信息分析失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"分析失败: {str(e)}"
        )


@router.post(
    "/validate",
    response_model=ValidateResponse,
    summary="验证脱敏效果",
    description="验证脱敏后的文本是否还存在敏感信息"
)
async def validate_desensitization(request: ValidateRequest):
    """
    验证脱敏效果
    
    检查脱敏后的文本中是否还存在敏感信息。
    
    Args:
        request: 验证请求，包含原始文本和脱敏后文本
        
    Returns:
        ValidateResponse: 验证结果
        
    Raises:
        HTTPException: 验证失败
    """
    try:
        logger.info("开始验证脱敏效果")
        
        desensitizer = get_desensitizer()
        
        # 执行验证
        result = desensitizer.validate_desensitization(
            original=request.original,
            desensitized=request.desensitized
        )
        
        response = ValidateResponse(
            is_safe=result.get("is_safe", False),
            security_level=result.get("security_level", "low"),
            remaining_sensitive=result.get("remaining_sensitive", {}),
            reduction_ratio=result.get("reduction_ratio", 0.0),
            total_issues=result.get("total_issues", 0),
            warnings=result.get("warnings", []),
            suggestions=result.get("suggestions", [])
        )
        
        logger.info(f"脱敏验证完成，安全等级: {response.security_level}")
        
        return response
        
    except Exception as e:
        logger.error(f"脱敏验证失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"验证失败: {str(e)}"
        )


@router.post(
    "/file",
    response_model=DesensitizeResponse,
    summary="MD文件脱敏",
    description="上传MD文件进行LLM智能脱敏处理"
)
async def desensitize_file(
    file: UploadFile = File(..., description="MD文件")
):
    """
    对MD文件进行LLM智能脱敏处理
    
    支持上传MD文件，读取内容后进行脱敏，返回脱敏后的文本。
    
    Args:
        file: 上传的MD文件
        
    Returns:
        DesensitizeResponse: 脱敏结果
        
    Raises:
        HTTPException: 文件格式错误或脱敏处理失败
    """
    temp_file_path = None
    
    try:
        # 1. 验证文件格式
        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="文件名不能为空"
            )
        
        # 检查是否为MD文件
        filename_lower = file.filename.lower()
        if not (filename_lower.endswith('.md') or filename_lower.endswith('.markdown')):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="仅支持MD或Markdown格式的文件"
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
        
        # 3. 读取文件内容
        try:
            # 尝试UTF-8编码
            text_content = file_content.decode('utf-8')
        except UnicodeDecodeError:
            try:
                # 尝试GBK编码（中文环境常见）
                text_content = file_content.decode('gbk')
            except UnicodeDecodeError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="文件编码不支持，请使用UTF-8或GBK编码"
                )
        
        logger.info(f"开始MD文件脱敏: {file.filename} ({file_size} 字节)")
        
        # 4. 执行脱敏（仅使用LLM）
        desensitizer = get_desensitizer()
        
        result = desensitizer.desensitize_sync(
            text=text_content,
            use_llm=True
        )
        
        response = DesensitizeResponse(
            desensitized_text=result.get("desensitized_text", text_content),
            llm_tokens=result.get("llm_tokens", 0),
            llm_success=result.get("llm_success", False),
            method=result.get("method", "none")
        )
        
        logger.info(f"MD文件脱敏完成: {file.filename}, 方法: {response.method}")
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"MD文件脱敏失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"文件脱敏处理失败: {str(e)}"
        )
    finally:
        # 清理临时文件（如果有）
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except Exception:
                pass


@router.get(
    "/status",
    summary="脱敏服务状态检查",
    description="检查脱敏服务状态"
)
async def desensitize_status():
    """
    检查脱敏服务状态
    
    Returns:
        dict: 服务状态信息
    """
    desensitizer = get_desensitizer()
    
    return {
        "status": "ready",
        "llm_enabled": desensitizer.enable_llm,
        "llm_available": desensitizer.chain is not None,
        "features": {
            "llm_desensitize": desensitizer.enable_llm,
            "sensitive_analysis": True,
            "validation": True,
            "file_upload": True
        },
        "note": "仅使用LLM智能脱敏"
    }
