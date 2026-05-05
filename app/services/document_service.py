# -*- coding: utf-8 -*-
"""
文档入库服务

实现完整的文档入库流程：上传→转换→脱敏→保存。
"""

import logging
import time
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentImage, Tag
from app.services.pdf_converter import PDFConverter
from app.services.image_extractor import ImageExtractor
from app.services.desensitizer import Desensitizer
from app.services.file_service import FileService
from app.utils.helpers import generate_uuid, get_file_extension, is_valid_pdf
from app.config import settings

logger = logging.getLogger(__name__)


class DocumentService:
    """文档入库服务类"""
    
    def __init__(
        self,
        db: Session,
        pdf_converter: Optional[PDFConverter] = None,
        desensitizer: Optional[Desensitizer] = None,
        file_service: Optional[FileService] = None
    ):
        """
        初始化文档服务
        
        Args:
            db: 数据库会话
            pdf_converter: PDF转换服务（可选，自动创建）
            desensitizer: 脱敏服务（可选，自动创建）
            file_service: 文件服务（可选，自动创建）
        """
        self.db = db
        
        # 初始化服务
        if pdf_converter is None:
            image_extractor = ImageExtractor(output_base_dir=settings.CONVERTED_DIR)
            self.pdf_converter = PDFConverter(image_extractor=image_extractor)
        else:
            self.pdf_converter = pdf_converter
        
        if desensitizer is None:
            self.desensitizer = Desensitizer()
        else:
            self.desensitizer = desensitizer
        
        if file_service is None:
            self.file_service = FileService()
        else:
            self.file_service = file_service
    
    def process_document(
        self,
        pdf_path: str,
        original_filename: str,
        extract_images: bool = True,
        extract_tables: bool = True,
        use_regex: bool = True,
        use_llm: bool = True,
        tags: Optional[List[str]] = None
    ) -> Dict:
        """
        处理文档入库流程
        
        完整流程：
        1. 验证PDF文件
        2. 转换PDF为Markdown（含图片提取）
        3. 数据脱敏
        4. 保存MD文件和图片
        5. 写入数据库记录
        
        Args:
            pdf_path: PDF文件路径
            original_filename: 原始文件名
            extract_images: 是否提取图片
            extract_tables: 是否提取表格
            use_regex: 是否使用正则脱敏
            use_llm: 是否使用LLM脱敏
            tags: 标签列表（可选）
            
        Returns:
            dict: 处理结果，包含文档信息和处理状态
            
        Raises:
            ValueError: 文件格式不正确
            IOError: 文件处理失败
        """
        try:
            # 1. 验证文件
            if not Path(pdf_path).exists():
                raise FileNotFoundError(f"PDF文件不存在: {pdf_path}")
            
            if not is_valid_pdf(original_filename):
                raise ValueError(f"文件格式不正确，仅支持PDF: {original_filename}")
            
            # 2. 生成文档ID
            doc_id = generate_uuid()
            logger.info(f"开始处理文档: {original_filename} (ID: {doc_id})")
            
            # 3. PDF转换
            logger.info("步骤1: PDF转换为Markdown...")
            markdown_content, images_info = self.pdf_converter.convert_to_markdown(
                pdf_path=pdf_path,
                doc_id=doc_id,
                extract_images=extract_images,
                extract_tables=extract_tables
            )
            
            logger.info(f"PDF转换完成，提取图片: {len(images_info)} 张")
            
            # 4. 数据脱敏
            logger.info("步骤2: 数据脱敏处理...")
            
            # 记录脱敏开始时间
            desensitize_start_time = time.time()
            
            desensitize_result = self.desensitizer.desensitize_sync(
                text=markdown_content,
                use_regex=use_regex,
                use_llm=use_llm
            )
            
            desensitized_content = desensitize_result['desensitized_text']
            is_desensitized = desensitize_result.get('llm_success', False) or use_regex
            
            # 如果启用了LLM脱敏但脱敏失败，抛出异常阻止保存未脱敏文档
            if use_llm and not desensitize_result.get('llm_success', False):
                error_msg = desensitize_result.get('error', '未知错误')
                raise ValueError(
                    f"LLM脱敏失败，无法保存未脱敏文档。错误信息: {error_msg}。"
                    f"请检查网络连接或LLM服务配置后重试。"
                )
            
            # 计算脱敏总耗时
            desensitize_total_time = time.time() - desensitize_start_time
            
            # 记录完整的脱敏过程日志
            from app.utils.llm_logger import get_llm_logger
            llm_logger = get_llm_logger()
            llm_logger.log_desensitization(
                original_text=markdown_content,
                desensitized_text=desensitized_content,
                result=desensitize_result,
                processing_time=desensitize_total_time
            )
            
            logger.info(f"脱敏完成，方法: {desensitize_result.get('method', 'unknown')}，总耗时: {desensitize_total_time:.2f}s")
            
            # 5. 保存文件
            logger.info("步骤3: 保存文件...")
            
            # 对文件名进行脱敏处理
            original_stem = Path(original_filename).stem
            logger.debug(f"原始文件名: {original_stem}")
            
            # 使用相同的脱敏器对文件名进行脱敏
            desensitized_filename_result = self.desensitizer.desensitize_sync(
                text=original_stem,
                use_regex=True,
                use_llm=False  # 文件名脱敏只用正则，避免过度处理
            )
            
            desensitized_stem = desensitized_filename_result.get('desensitized_text', original_stem)
            # 清理文件名中不适合的字符
            desensitized_stem = self._clean_filename(desensitized_stem)
            
            md_filename = f"{desensitized_stem}.md"
            logger.info(f"文件名脱敏: {original_stem} → {desensitized_stem}")
            
            md_file_path, md_filename = self.file_service.save_markdown_sync(
                content=desensitized_content,
                doc_id=doc_id,
                filename=md_filename
            )
            
            # 6. 获取文件大小和预览
            file_size = self.file_service.get_file_size(md_file_path)
            content_preview = self.file_service.get_content_preview(desensitized_content)
            
            # 7. 创建数据库记录
            logger.info("步骤4: 写入数据库...")
            document = Document(
                id=doc_id,
                filename=md_filename,
                original_filename=original_filename,
                file_path=md_file_path,
                file_size=file_size,
                content_preview=content_preview,
                full_content=desensitized_content,
                images_count=len(images_info),
                is_desensitized=is_desensitized
            )
            
            self.db.add(document)
            
            # 8. 保存图片记录
            if images_info:
                for img_info in images_info:
                    image_record = DocumentImage(
                        document_id=doc_id,
                        filename=img_info['filename'],
                        file_path=img_info['path'],
                        page_number=img_info.get('page'),
                        image_index=img_info.get('index'),
                        file_size=img_info.get('size', 0)
                    )
                    self.db.add(image_record)
            
            # 9. 添加标签（在提交前添加，确保文档已存在）
            if tags:
                logger.info(f"步骤5: 添加标签...")
                valid_tags = [t.strip() for t in tags if t.strip()]
                for tag_name in valid_tags:
                    # 查找或创建标签
                    tag = self.db.query(Tag).filter(Tag.name == tag_name).first()
                    if not tag:
                        tag = Tag(name=tag_name)
                        self.db.add(tag)
                        self.db.flush()  # 刷新以获取tag.id
                    
                    # 添加关联（如果不存在）
                    if tag not in document.tags:
                        document.tags.append(tag)
                
                logger.info(f"已添加 {len(valid_tags)} 个标签: {valid_tags}")
            
            # 10. 自动提取漏洞等级并打标签
            try:
                from app.services.vulnerability_level_service import VulnerabilityLevelService
                level_service = VulnerabilityLevelService(db=self.db)
                extracted_level = level_service.extract_and_tag_document(document)
                if extracted_level:
                    logger.info(f"自动提取并添加漏洞等级标签: {extracted_level}")
            except Exception as e:
                logger.warning(f"自动提取漏洞等级失败（不影响文档保存）: {e}")
            
            # 11. 提交事务
            self.db.commit()
            self.db.refresh(document)
            
            logger.info(f"文档入库完成: {doc_id}")
            
            return {
                "document_id": doc_id,
                "filename": md_filename,
                "original_filename": original_filename,
                "file_path": md_file_path,
                "file_size": file_size,
                "images_count": len(images_info),
                "is_desensitized": is_desensitized,
                "desensitize_stats": desensitize_result.get('regex_stats', {}),
                "status": "success",
                "message": "文档处理完成"
            }
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"文档处理失败: {e}", exc_info=True)
            raise
    
    def get_document(self, doc_id: str) -> Optional[Document]:
        """
        获取文档
        
        Args:
            doc_id: 文档ID
            
        Returns:
            Document: 文档对象，不存在返回None
        """
        return self.db.query(Document).filter(Document.id == doc_id).first()
    
    def check_duplicate_by_filename(self, original_filename: str) -> Optional[Document]:
        """
        根据原始文件名检查文档是否已存在
        
        Args:
            original_filename: 原始PDF文件名
            
        Returns:
            Document: 如果文件已存在，返回已存在的文档对象；否则返回None
        """
        try:
            from sqlalchemy import func
            
            # 根据原始文件名精确匹配（不区分大小写）
            # 使用LOWER函数确保不区分大小写（兼容MySQL）
            document = (
                self.db.query(Document)
                .filter(func.lower(Document.original_filename) == func.lower(original_filename))
                .first()
            )
            
            if document:
                logger.info(f"发现重复文件: {original_filename} (已存在文档ID: {document.id})")
            
            return document
            
        except Exception as e:
            logger.error(f"检查文件重复失败: {e}", exc_info=True)
            return None
    
    def delete_document(self, doc_id: str) -> bool:
        """
        删除文档
        
        包括：
        - 删除数据库记录（级联删除图片和标签关联）
        - 删除文件系统中的文件
        
        Args:
            doc_id: 文档ID
            
        Returns:
            bool: 删除是否成功
        """
        try:
            document = self.get_document(doc_id)
            if not document:
                logger.warning(f"文档不存在: {doc_id}")
                return False
            
            # 删除文件
            self.file_service.delete_document_files(doc_id)
            
            # 删除数据库记录（级联删除关联数据）
            self.db.delete(document)
            self.db.commit()
            
            logger.info(f"文档已删除: {doc_id}")
            return True
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"删除文档失败: {e}", exc_info=True)
            return False
    
    def add_tag_to_document(self, doc_id: str, tag_name: str) -> bool:
        """
        为文档添加标签
        
        Args:
            doc_id: 文档ID
            tag_name: 标签名称
            
        Returns:
            bool: 操作是否成功
        """
        try:
            document = self.get_document(doc_id)
            if not document:
                return False
            
            # 查找或创建标签
            tag = self.db.query(Tag).filter(Tag.name == tag_name).first()
            if not tag:
                tag = Tag(name=tag_name)
                self.db.add(tag)
                self.db.flush()
            
            # 添加关联（如果不存在）
            if tag not in document.tags:
                document.tags.append(tag)
                self.db.commit()
                logger.info(f"已为文档 {doc_id} 添加标签: {tag_name}")
                return True
            
            return True
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"添加标签失败: {e}", exc_info=True)
            return False
    
    def remove_tag_from_document(self, doc_id: str, tag_name: str) -> bool:
        """
        从文档移除标签
        
        Args:
            doc_id: 文档ID
            tag_name: 标签名称
            
        Returns:
            bool: 操作是否成功
        """
        try:
            document = self.get_document(doc_id)
            if not document:
                return False
            
            tag = self.db.query(Tag).filter(Tag.name == tag_name).first()
            if tag and tag in document.tags:
                document.tags.remove(tag)
                self.db.commit()
                logger.info(f"已从文档 {doc_id} 移除标签: {tag_name}")
                return True
            
            return True
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"移除标签失败: {e}", exc_info=True)
            return False
    
    def _clean_filename(self, filename: str) -> str:
        """
        清理文件名，移除不适合文件系统的字符
        
        Args:
            filename: 原始文件名
            
        Returns:
            str: 清理后的文件名
        """
        # 移除Windows文件系统不支持的字符
        invalid_chars = r'[<>:"/\\|?*]'
        cleaned = re.sub(invalid_chars, '_', filename)
        
        # 移除多余的空格和特殊字符
        cleaned = re.sub(r'\s+', '_', cleaned)  # 多个空格替换为一个下划线
        cleaned = re.sub(r'_+', '_', cleaned)   # 多个下划线合并为一个
        
        # 移除开头和结尾的下划线或点号
        cleaned = cleaned.strip('._')
        
        # 限制文件名长度（不包含扩展名）
        if len(cleaned) > 100:
            cleaned = cleaned[:100]
        
        # 如果清理后为空，使用默认名称
        if not cleaned:
            cleaned = "desensitized_document"
        
        return cleaned