"""
通用工具函数模块

提供项目中常用的辅助函数。
"""

from pathlib import Path
import uuid
from typing import Tuple
import hashlib
from datetime import datetime


def generate_uuid() -> str:
    """
    生成UUID字符串
    
    Returns:
        str: UUID字符串
    """
    return str(uuid.uuid4())


def get_safe_filename(original_filename: str, prefix: str = "") -> str:
    """
    生成安全的文件名
    
    使用UUID避免文件名冲突和路径穿越攻击。
    
    Args:
        original_filename: 原始文件名
        prefix: 文件名前缀（可选）
        
    Returns:
        str: 安全的文件名
        
    Example:
        >>> get_safe_filename("report.pdf", "doc")
        'doc_a1b2c3d4-e5f6-7890-abcd-ef1234567890.pdf'
    """
    ext = Path(original_filename).suffix.lower()
    file_id = generate_uuid()
    
    if prefix:
        return f"{prefix}_{file_id}{ext}"
    return f"{file_id}{ext}"


def get_safe_file_path(base_dir: str, original_filename: str, prefix: str = "") -> Tuple[str, str]:
    """
    生成安全的文件保存路径
    
    Args:
        base_dir: 基础目录
        original_filename: 原始文件名
        prefix: 文件名前缀（可选）
        
    Returns:
        tuple: (完整绝对路径, 相对文件名)
        
    Raises:
        ValueError: 如果生成的路径不在base_dir内（路径穿越攻击）
    """
    base_path = Path(base_dir).resolve()
    filename = get_safe_filename(original_filename, prefix)
    file_path = base_path / filename
    
    # 安全检查：确保文件路径在基础目录内
    if not str(file_path).startswith(str(base_path)):
        raise ValueError("检测到非法的文件路径")
    
    return str(file_path), filename


def calculate_file_hash(file_path: str, algorithm: str = "sha256") -> str:
    """
    计算文件哈希值
    
    用于文件去重和完整性校验。
    
    Args:
        file_path: 文件路径
        algorithm: 哈希算法（md5, sha1, sha256等）
        
    Returns:
        str: 文件哈希值（十六进制字符串）
        
    Example:
        >>> calculate_file_hash("document.pdf")
        'a1b2c3d4e5f67890...'
    """
    hash_obj = hashlib.new(algorithm)
    
    with open(file_path, 'rb') as f:
        # 分块读取，避免大文件占用过多内存
        while chunk := f.read(8192):
            hash_obj.update(chunk)
    
    return hash_obj.hexdigest()


def format_file_size(size_bytes: int) -> str:
    """
    格式化文件大小为可读字符串
    
    Args:
        size_bytes: 文件大小（字节）
        
    Returns:
        str: 格式化后的大小字符串
        
    Example:
        >>> format_file_size(1024)
        '1.00 KB'
        >>> format_file_size(1048576)
        '1.00 MB'
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


def get_file_extension(filename: str) -> str:
    """
    获取文件扩展名（小写，不含点）
    
    Args:
        filename: 文件名
        
    Returns:
        str: 扩展名
        
    Example:
        >>> get_file_extension("report.PDF")
        'pdf'
    """
    return Path(filename).suffix.lower().lstrip('.')


def is_valid_pdf(filename: str) -> bool:
    """
    检查文件名是否为PDF格式
    
    Args:
        filename: 文件名
        
    Returns:
        bool: 是否为PDF文件
    """
    return get_file_extension(filename) == 'pdf'


def truncate_text(text: str, max_length: int = 500, suffix: str = "...") -> str:
    """
    截断文本到指定长度
    
    Args:
        text: 原始文本
        max_length: 最大长度
        suffix: 截断后缀
        
    Returns:
        str: 截断后的文本
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def get_current_timestamp() -> str:
    """
    获取当前时间戳字符串
    
    Returns:
        str: ISO格式的时间戳
        
    Example:
        >>> get_current_timestamp()
        '2026-01-22T15:30:45'
    """
    return datetime.now().isoformat()
