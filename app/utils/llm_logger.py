# -*- coding: utf-8 -*-
"""
LLM对话日志记录器

专门记录大模型的输入输出对话，用于调试和监控脱敏效果。
"""

import logging
import json
import os
from datetime import datetime
from typing import Dict, Any, Optional
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.config import settings


class LLMConversationLogger:
    """LLM对话日志记录器"""
    
    def __init__(self, log_file: str = "llm_conversations.log", max_content_length: int = 1000):
        """
        初始化LLM对话日志记录器
        
        Args:
            log_file: 日志文件名
            max_content_length: 单条内容最大记录长度（避免日志文件过大）
        """
        self.max_content_length = max_content_length
        
        # 确保日志目录存在
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        self.log_file_path = log_dir / log_file
        
        # 创建专门的日志器
        self.logger = logging.getLogger("llm_conversation")
        self.logger.setLevel(logging.INFO)
        
        # 避免重复添加处理器
        if not self.logger.handlers:
            # 创建文件处理器（带轮转）
            file_handler = RotatingFileHandler(
                self.log_file_path,
                maxBytes=50*1024*1024,  # 50MB
                backupCount=5,
                encoding='utf-8'
            )
            
            # 创建格式器
            formatter = logging.Formatter(
                '%(asctime)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            file_handler.setFormatter(formatter)
            
            self.logger.addHandler(file_handler)
            
            # 防止向上传播到根日志器
            self.logger.propagate = False
    
    def _truncate_content(self, content: str) -> str:
        """
        截断过长的内容
        
        Args:
            content: 原始内容
            
        Returns:
            截断后的内容
        """
        if len(content) <= self.max_content_length:
            return content
        
        # 截断并添加省略号
        truncated = content[:self.max_content_length - 50]
        return f"{truncated}...\n\n[内容已截断，原长度: {len(content)} 字符]"
    
    def log_conversation(
        self,
        input_text: str,
        output_text: Optional[str] = None,
        success: bool = True,
        tokens_used: int = 0,
        method: str = "unknown",
        error_message: Optional[str] = None,
        model: Optional[str] = None,
        processing_time: Optional[float] = None,
        extra_info: Optional[Dict[str, Any]] = None
    ):
        """
        记录LLM对话
        
        Args:
            input_text: 输入给LLM的文本
            output_text: LLM的输出文本
            success: 是否成功
            tokens_used: 使用的token数量
            method: 使用的方法（如：llm, llm+regex等）
            error_message: 错误信息（如有）
            model: 使用的模型名称
            processing_time: 处理时间（秒）
            extra_info: 额外信息
        """
        
        # 构建对话记录
        conversation_record = {
            "timestamp": datetime.now().isoformat(),
            "success": success,
            "method": method,
            "model": model or getattr(settings, 'LLM_MODEL', 'unknown'),
            "tokens_used": tokens_used,
            "processing_time_seconds": processing_time,
            "input_length": len(input_text),
            "output_length": len(output_text) if output_text else 0,
            "input_text": self._truncate_content(input_text),
            "output_text": self._truncate_content(output_text) if output_text else None,
            "error": error_message,
            "extra": extra_info or {}
        }
        
        # 转换为JSON字符串（格式化输出）
        try:
            record_json = json.dumps(conversation_record, ensure_ascii=False, indent=2)
        except Exception as e:
            # 如果JSON序列化失败，使用简单格式
            record_json = f"JSON序列化失败: {e}\n原始记录: {str(conversation_record)}"
        
        # 记录日志
        log_level = logging.INFO if success else logging.WARNING
        status = "SUCCESS" if success else "FAILED"
        
        log_message = f"""
{'='*80}
LLM对话记录 - {status}
{'='*80}
{record_json}
{'='*80}
"""
        
        self.logger.log(log_level, log_message)
    
    def log_desensitization(
        self,
        original_text: str,
        desensitized_text: Optional[str],
        result: Dict[str, Any],
        processing_time: Optional[float] = None
    ):
        """
        专门记录脱敏对话
        
        Args:
            original_text: 原始文本
            desensitized_text: 脱敏后文本
            result: 脱敏结果字典
            processing_time: 处理时间
        """
        
        # 分析脱敏效果
        input_preview = original_text[:200] + "..." if len(original_text) > 200 else original_text
        output_preview = (desensitized_text[:200] + "...") if desensitized_text and len(desensitized_text) > 200 else desensitized_text
        
        # 检查敏感信息是否被脱敏（简单检查）
        potential_sensitive = ["手机", "电话", "邮箱", "@", "学校", "公司", "http", "IP", "备案"]
        sensitivity_check = {
            "input_has_sensitive": any(keyword in original_text for keyword in potential_sensitive),
            "output_has_sensitive": any(keyword in (desensitized_text or "") for keyword in potential_sensitive) if desensitized_text else False
        }
        
        extra_info = {
            "desensitization_stats": result.get('regex_stats', {}),
            "input_preview": input_preview,
            "output_preview": output_preview,
            "sensitivity_analysis": sensitivity_check,
            "text_length_change": {
                "original": len(original_text),
                "desensitized": len(desensitized_text) if desensitized_text else 0,
                "change_ratio": round((len(desensitized_text) / len(original_text) if desensitized_text and original_text else 0), 2)
            }
        }
        
        self.log_conversation(
            input_text=original_text,
            output_text=desensitized_text,
            success=result.get('llm_success', False),
            tokens_used=result.get('llm_tokens', 0),
            method=result.get('method', 'unknown'),
            error_message=result.get('error'),
            processing_time=processing_time,
            extra_info=extra_info
        )
    
    def get_log_stats(self) -> Dict[str, Any]:
        """
        获取日志统计信息
        
        Returns:
            日志统计信息
        """
        stats = {
            "log_file": str(self.log_file_path),
            "file_exists": self.log_file_path.exists(),
            "file_size_mb": 0,
            "total_conversations": 0,
            "successful_conversations": 0
        }
        
        if self.log_file_path.exists():
            stats["file_size_mb"] = round(self.log_file_path.stat().st_size / (1024 * 1024), 2)
            
            try:
                # 简单统计（读取最后几行）
                with open(self.log_file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    stats["total_conversations"] = content.count("LLM对话记录")
                    stats["successful_conversations"] = content.count("SUCCESS")
            except Exception as e:
                stats["read_error"] = str(e)
        
        return stats


# 全局单例实例
_llm_logger = None


def get_llm_logger() -> LLMConversationLogger:
    """
    获取LLM对话日志记录器的全局实例
    
    Returns:
        LLMConversationLogger实例
    """
    global _llm_logger
    if _llm_logger is None:
        _llm_logger = LLMConversationLogger()
    return _llm_logger