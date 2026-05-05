"""
日志配置模块

统一管理应用日志格式和输出。
"""

import logging
from logging.handlers import RotatingFileHandler
import sys
from pathlib import Path
from app.config import settings


def setup_logging() -> logging.Logger:
    """
    配置应用日志系统
    
    - 开发环境：输出到控制台，级别为DEBUG
    - 生产环境：输出到文件和控制台，级别为INFO
    - 使用轮转文件处理器，单文件最大10MB，保留5个备份
    
    Returns:
        logging.Logger: 配置好的日志记录器
    """
    # 创建日志记录器
    logger = logging.getLogger("src_data_manage")
    
    # 设置日志级别
    log_level = logging.DEBUG if settings.DEBUG else logging.INFO
    logger.setLevel(log_level)
    
    # 如果已经有处理器，不重复添加
    if logger.handlers:
        return logger
    
    # 日志格式
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 文件处理器（生产环境或明确要求）
    if not settings.DEBUG:
        # 确保日志目录存在
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        # 应用日志
        file_handler = RotatingFileHandler(
            'logs/app.log',
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        # 错误日志（单独文件）
        error_handler = RotatingFileHandler(
            'logs/error.log',
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)
        logger.addHandler(error_handler)
    
    # 防止日志向上传播
    logger.propagate = False
    
    return logger


# 获取日志记录器的便捷函数
def get_logger(name: str) -> logging.Logger:
    """
    获取指定名称的日志记录器
    
    Args:
        name: 日志记录器名称，通常使用模块名
        
    Returns:
        logging.Logger: 日志记录器实例
        
    Example:
        ```python
        from app.utils.logger import get_logger
        
        logger = get_logger(__name__)
        logger.info("处理文档开始")
        ```
    """
    return logging.getLogger(f"src_data_manage.{name}")
