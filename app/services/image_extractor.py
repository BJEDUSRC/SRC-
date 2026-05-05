"""
图片提取服务模块

从PDF文档中提取图片，保存到指定目录，并生成Markdown引用。
"""

import fitz  # PyMuPDF
from PIL import Image
import io
import os
from pathlib import Path
from typing import List, Dict, Optional
import logging

from app.utils.logger import get_logger

logger = get_logger(__name__)


class ImageExtractor:
    """
    PDF图片提取服务类
    
    负责从PDF文档中提取所有嵌入的图片，按规范命名并保存。
    """
    
    def __init__(self, output_base_dir: str):
        """
        初始化图片提取器
        
        Args:
            output_base_dir: 图片保存的基础目录路径
        """
        self.output_base_dir = output_base_dir
        
    def extract_images(self, pdf_path: str, doc_id: str) -> List[Dict[str, any]]:
        """
        从PDF中提取所有图片
        
        Args:
            pdf_path: PDF文件的绝对路径
            doc_id: 文档唯一标识符（用于创建图片子目录）
            
        Returns:
            图片信息列表，每个元素包含:
            {
                "path": "相对路径",
                "page": 页码,
                "index": 页内序号,
                "filename": 文件名,
                "size": 文件大小(字节)
            }
            
        Raises:
            FileNotFoundError: PDF文件不存在
            Exception: PDF处理失败
        """
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF文件不存在: {pdf_path}")
        
        try:
            doc = fitz.open(pdf_path)
            images = []
            
            # 创建文档专属图片目录
            image_dir = os.path.join(self.output_base_dir, "images", doc_id)
            os.makedirs(image_dir, exist_ok=True)
            
            logger.info(f"开始从PDF提取图片: {pdf_path}")
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                image_list = page.get_images()
                
                if not image_list:
                    continue
                
                logger.debug(f"第 {page_num + 1} 页发现 {len(image_list)} 张图片")
                
                for img_index, img in enumerate(image_list, 1):
                    try:
                        # 提取图片
                        xref = img[0]
                        base_image = doc.extract_image(xref)
                        image_bytes = base_image["image"]
                        image_ext = base_image["ext"]
                        
                        # 生成标准文件名: {原文件名}_p{页码}_img{序号}.{扩展名}
                        pdf_basename = Path(pdf_path).stem
                        filename = f"{pdf_basename}_p{page_num + 1}_img{img_index}.{image_ext}"
                        image_path = os.path.join(image_dir, filename)
                        
                        # 保存图片
                        with open(image_path, "wb", encoding=None) as f:
                            f.write(image_bytes)
                        
                        # 获取文件大小
                        file_size = os.path.getsize(image_path)
                        
                        # 记录相对路径（用于MD引用）
                        relative_path = f"images/{doc_id}/{filename}"
                        
                        images.append({
                            "path": relative_path,
                            "page": page_num + 1,
                            "index": img_index,
                            "filename": filename,
                            "size": file_size
                        })
                        
                        logger.debug(f"提取图片: {filename} ({file_size} bytes)")
                        
                    except Exception as e:
                        logger.warning(f"提取第 {page_num + 1} 页第 {img_index} 张图片失败: {e}")
                        continue
            
            doc.close()
            logger.info(f"PDF图片提取完成，共提取 {len(images)} 张图片")
            
            return images
            
        except Exception as e:
            logger.error(f"PDF图片提取失败: {pdf_path}", exc_info=True)
            raise
    
    @staticmethod
    def generate_md_image_ref(image_info: Dict[str, any], alt_text: Optional[str] = None) -> str:
        """
        生成Markdown格式的图片引用
        
        Args:
            image_info: 图片信息字典（必须包含 path 键）
            alt_text: 图片替代文本，如果为None则自动生成
            
        Returns:
            Markdown格式的图片引用字符串
            
        Example:
            >>> info = {"path": "images/doc1/img1.png", "page": 1, "index": 1}
            >>> generate_md_image_ref(info)
            '![图片1-1](images/doc1/img1.png)'
        """
        if not alt_text:
            alt_text = f"图片{image_info['page']}-{image_info['index']}"
        
        return f"![{alt_text}]({image_info['path']})"
    
    @staticmethod
    def optimize_image(image_path: str, max_width: int = 1200, quality: int = 85) -> None:
        """
        优化图片大小（可选功能）
        
        对过大的图片进行压缩，减少存储空间。
        
        Args:
            image_path: 图片文件路径
            max_width: 最大宽度（像素）
            quality: JPEG质量（1-100）
            
        Raises:
            Exception: 图片处理失败
        """
        try:
            with Image.open(image_path) as img:
                # 如果图片宽度超过最大宽度，进行缩放
                if img.width > max_width:
                    ratio = max_width / img.width
                    new_height = int(img.height * ratio)
                    img = img.resize((max_width, new_height), Image.LANCZOS)
                    
                    # 保存优化后的图片
                    if img.format == 'PNG':
                        img.save(image_path, 'PNG', optimize=True)
                    else:
                        img.save(image_path, 'JPEG', quality=quality, optimize=True)
                    
                    logger.debug(f"图片已优化: {image_path}")
                    
        except Exception as e:
            logger.warning(f"图片优化失败: {image_path}, 错误: {e}")
    
    def extract_and_optimize(
        self, 
        pdf_path: str, 
        doc_id: str,
        optimize: bool = False,
        max_width: int = 1200
    ) -> List[Dict[str, any]]:
        """
        提取图片并可选地进行优化
        
        Args:
            pdf_path: PDF文件路径
            doc_id: 文档ID
            optimize: 是否优化图片
            max_width: 优化时的最大宽度
            
        Returns:
            图片信息列表
        """
        images = self.extract_images(pdf_path, doc_id)
        
        if optimize:
            logger.info("开始优化图片...")
            for img_info in images:
                full_path = os.path.join(self.output_base_dir, img_info['path'])
                try:
                    self.optimize_image(full_path, max_width=max_width)
                    # 更新文件大小
                    img_info['size'] = os.path.getsize(full_path)
                except Exception as e:
                    logger.warning(f"优化图片失败: {img_info['filename']}, {e}")
        
        return images
