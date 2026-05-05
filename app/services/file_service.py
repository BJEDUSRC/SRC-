# -*- coding: utf-8 -*-
"""
文件存储服务

负责MD文件和图片文件的保存、读取、删除等操作。
"""

import aiofiles
from pathlib import Path
from typing import List, Optional, Tuple
import logging
import shutil

from app.config import settings
from app.utils.helpers import get_safe_file_path, truncate_text

logger = logging.getLogger(__name__)


class FileService:
    """文件存储服务类"""
    
    def __init__(self, base_dir: Optional[str] = None):
        """
        初始化文件服务
        
        Args:
            base_dir: 基础存储目录，默认使用配置中的CONVERTED_DIR
        """
        self.base_dir = Path(base_dir or settings.CONVERTED_DIR)
        self.images_dir = self.base_dir / "images"
        
        # 确保目录存在
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)
    
    def get_document_dir(self, doc_id: str) -> Path:
        """
        获取文档专属目录
        
        Args:
            doc_id: 文档ID
            
        Returns:
            Path: 文档目录路径
        """
        doc_dir = self.base_dir / doc_id
        doc_dir.mkdir(parents=True, exist_ok=True)
        return doc_dir
    
    def get_image_dir(self, doc_id: str) -> Path:
        """
        获取文档图片目录
        
        Args:
            doc_id: 文档ID
            
        Returns:
            Path: 图片目录路径
        """
        img_dir = self.images_dir / doc_id
        img_dir.mkdir(parents=True, exist_ok=True)
        return img_dir
    
    async def save_markdown(
        self, 
        content: str, 
        doc_id: str,
        filename: Optional[str] = None
    ) -> Tuple[str, str]:
        """
        保存Markdown文件
        
        Args:
            content: Markdown内容
            doc_id: 文档ID
            filename: 文件名（可选，默认使用doc_id.md）
            
        Returns:
            tuple: (文件完整路径, 相对文件名)
            
        Raises:
            IOError: 文件保存失败
        """
        try:
            doc_dir = self.get_document_dir(doc_id)
            filename = filename or f"{doc_id}.md"
            file_path = doc_dir / filename
            
            # 异步写入文件
            async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
                await f.write(content)
            
            logger.info(f"Markdown文件已保存: {file_path}")
            return str(file_path), filename
            
        except Exception as e:
            logger.error(f"保存Markdown文件失败: {e}", exc_info=True)
            raise IOError(f"保存Markdown文件失败: {e}")
    
    def save_markdown_sync(
        self, 
        content: str, 
        doc_id: str,
        filename: Optional[str] = None
    ) -> Tuple[str, str]:
        """
        同步保存Markdown文件
        
        Args:
            content: Markdown内容
            doc_id: 文档ID
            filename: 文件名（可选）
            
        Returns:
            tuple: (文件完整路径, 相对文件名)
        """
        try:
            doc_dir = self.get_document_dir(doc_id)
            filename = filename or f"{doc_id}.md"
            file_path = doc_dir / filename
            
            # 同步写入文件
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            logger.info(f"Markdown文件已保存: {file_path}")
            return str(file_path), filename
            
        except Exception as e:
            logger.error(f"保存Markdown文件失败: {e}", exc_info=True)
            raise IOError(f"保存Markdown文件失败: {e}")
    
    async def read_markdown(self, file_path: str) -> str:
        """
        读取Markdown文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            str: 文件内容
            
        Raises:
            FileNotFoundError: 文件不存在
            IOError: 文件读取失败
        """
        try:
            path = Path(file_path)
            if not path.exists():
                raise FileNotFoundError(f"文件不存在: {file_path}")
            
            async with aiofiles.open(path, 'r', encoding='utf-8') as f:
                content = await f.read()
            
            return content
            
        except FileNotFoundError:
            raise
        except Exception as e:
            logger.error(f"读取Markdown文件失败: {e}", exc_info=True)
            raise IOError(f"读取Markdown文件失败: {e}")
    
    def read_markdown_sync(self, file_path: str) -> str:
        """
        同步读取Markdown文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            str: 文件内容
        """
        try:
            path = Path(file_path)
            if not path.exists():
                raise FileNotFoundError(f"文件不存在: {file_path}")
            
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            return content
            
        except FileNotFoundError:
            raise
        except Exception as e:
            logger.error(f"读取Markdown文件失败: {e}", exc_info=True)
            raise IOError(f"读取Markdown文件失败: {e}")
    
    def get_file_size(self, file_path: str) -> int:
        """
        获取文件大小
        
        Args:
            file_path: 文件路径
            
        Returns:
            int: 文件大小（字节）
        """
        try:
            return Path(file_path).stat().st_size
        except Exception as e:
            logger.warning(f"获取文件大小失败: {e}")
            return 0
    
    def delete_document_files(self, doc_id: str) -> bool:
        """
        删除文档及其关联的所有文件
        
        包括：
        - Markdown文件
        - 所有关联的图片文件
        - 文档目录
        
        Args:
            doc_id: 文档ID
            
        Returns:
            bool: 删除是否成功
        """
        try:
            # 删除文档目录（包含MD文件）
            doc_dir = self.get_document_dir(doc_id)
            if doc_dir.exists():
                shutil.rmtree(doc_dir)
                logger.info(f"已删除文档目录: {doc_dir}")
            
            # 删除图片目录
            img_dir = self.get_image_dir(doc_id)
            if img_dir.exists():
                shutil.rmtree(img_dir)
                logger.info(f"已删除图片目录: {img_dir}")
            
            return True
            
        except Exception as e:
            logger.error(f"删除文档文件失败: {e}", exc_info=True)
            return False
    
    def delete_image_file(self, image_path: str) -> bool:
        """
        删除单个图片文件
        
        Args:
            image_path: 图片文件路径
            
        Returns:
            bool: 删除是否成功
        """
        try:
            path = Path(image_path)
            if path.exists():
                path.unlink()
                logger.info(f"已删除图片文件: {image_path}")
                return True
            return False
            
        except Exception as e:
            logger.error(f"删除图片文件失败: {e}", exc_info=True)
            return False
    
    def list_document_images(self, doc_id: str) -> List[Path]:
        """
        列出文档的所有图片文件
        
        Args:
            doc_id: 文档ID
            
        Returns:
            List[Path]: 图片文件路径列表
        """
        try:
            img_dir = self.get_image_dir(doc_id)
            if not img_dir.exists():
                return []
            
            # 返回所有图片文件
            image_files = [
                f for f in img_dir.iterdir() 
                if f.is_file() and f.suffix.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
            ]
            
            return sorted(image_files)
            
        except Exception as e:
            logger.error(f"列出图片文件失败: {e}", exc_info=True)
            return []
    
    def get_content_preview(self, content: str, max_length: int = 500) -> str:
        """
        生成内容预览
        
        Args:
            content: 完整内容
            max_length: 最大长度
            
        Returns:
            str: 预览文本
        """
        return truncate_text(content, max_length)
    
    def validate_file_path(self, file_path: str) -> bool:
        """
        验证文件路径是否安全（防止路径穿越攻击）
        
        Args:
            file_path: 文件路径
            
        Returns:
            bool: 路径是否安全
        """
        try:
            path = Path(file_path).resolve()
            base_path = self.base_dir.resolve()
            
            # 检查路径是否在基础目录内
            return str(path).startswith(str(base_path))
            
        except Exception:
            return False
