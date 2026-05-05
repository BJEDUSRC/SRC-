# -*- coding: utf-8 -*-
"""
文档查询服务

提供文档查询、全文搜索、组合查询等功能。
"""

from sqlalchemy import or_, and_, func, text
from sqlalchemy.orm import Session
from typing import Optional, List, Dict
from datetime import datetime, date
import logging
import os
from pathlib import Path

from app.models.document import Document, Tag, document_tags, DocumentImage, DownloadLog
from app.schemas.document import DocumentQueryParams
from app.config import settings

logger = logging.getLogger(__name__)


class QueryService:
    """
    文档查询服务
    
    提供多种查询方式：
    - 基础查询（文件名、时间范围、标签）
    - 全文搜索（MySQL FULLTEXT）
    - 组合查询（多条件AND组合）
    """
    
    def __init__(self, db: Session):
        """
        初始化查询服务
        
        Args:
            db: 数据库会话
        """
        self.db = db
    
    def search_documents(
        self,
        keyword: Optional[str] = None,
        filename: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        tags: Optional[List[str]] = None,
        is_desensitized: Optional[bool] = None,
        vulnerability_level: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = 'created_at',
        sort_order: str = 'desc'
    ) -> Dict:
        """
        搜索文档
        
        支持多种查询条件组合：
        - 关键词全文搜索
        - 文件名模糊匹配
        - 时间范围查询
        - 标签筛选
        - 脱敏状态筛选
        
        Args:
            keyword: 关键词（全文搜索）
            filename: 文件名（模糊匹配）
            start_date: 开始时间
            end_date: 结束时间
            tags: 标签列表
            is_desensitized: 是否已脱敏
            page: 页码（从1开始）
            page_size: 每页数量
            sort_by: 排序字段
            sort_order: 排序方向（asc/desc）
            
        Returns:
            dict: 包含总数、分页信息和文档列表的字典
        """
        try:
            # 构建基础查询
            query = self.db.query(Document)
            
            # 1. 关键词全文搜索
            if keyword and keyword.strip():
                keyword = keyword.strip()
                # 使用LIKE进行全文搜索（更通用，不依赖FULLTEXT索引）
                # 搜索范围包括：完整内容、预览内容、文件名
                query = query.filter(
                    or_(
                        Document.full_content.like(f"%{keyword}%"),
                        Document.content_preview.like(f"%{keyword}%"),
                        Document.filename.like(f"%{keyword}%"),
                        Document.original_filename.like(f"%{keyword}%")
                    )
                )
                logger.debug(f"全文搜索关键词: {keyword}")
            
            # 2. 文件名模糊匹配
            if filename and filename.strip():
                filename = filename.strip()
                query = query.filter(
                    or_(
                        Document.filename.like(f"%{filename}%"),
                        Document.original_filename.like(f"%{filename}%")
                    )
                )
                logger.debug(f"文件名搜索: {filename}")
            
            # 3. 时间范围查询
            if start_date:
                if isinstance(start_date, str):
                    start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                query = query.filter(Document.created_at >= start_date)
                logger.debug(f"开始时间: {start_date}")
            
            if end_date:
                if isinstance(end_date, str):
                    end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                # 结束时间包含当天，所以加一天
                if isinstance(end_date, datetime):
                    end_date = end_date.replace(hour=23, minute=59, second=59)
                query = query.filter(Document.created_at <= end_date)
                logger.debug(f"结束时间: {end_date}")
            
            # 4. 标签筛选
            if tags and len(tags) > 0:
                # 使用子查询找到包含所有指定标签的文档
                # 需要文档包含tags中的所有标签（AND关系）
                tag_objects = self.db.query(Tag).filter(Tag.name.in_(tags)).all()
                if tag_objects:
                    tag_ids = [tag.id for tag in tag_objects]
                    # 使用子查询：文档必须包含所有指定的标签
                    subquery = (
                        self.db.query(document_tags.c.document_id)
                        .filter(document_tags.c.tag_id.in_(tag_ids))
                        .group_by(document_tags.c.document_id)
                        .having(func.count(document_tags.c.tag_id) == len(tag_ids))
                        .subquery()
                    )
                    query = query.filter(Document.id.in_(
                        self.db.query(subquery.c.document_id)
                    ))
                    logger.debug(f"标签筛选: {tags}")
            
            # 5. 漏洞等级筛选
            if vulnerability_level and vulnerability_level.strip():
                level = vulnerability_level.strip()
                # 查找有该等级标签的文档
                level_tag = self.db.query(Tag).filter(Tag.name == level).first()
                if level_tag:
                    level_subquery = (
                        self.db.query(document_tags.c.document_id)
                        .filter(document_tags.c.tag_id == level_tag.id)
                    )
                    query = query.filter(Document.id.in_(level_subquery))
                    logger.debug(f"漏洞等级筛选: {level}")
            
            # 6. 脱敏状态筛选
            if is_desensitized is not None:
                query = query.filter(Document.is_desensitized == is_desensitized)
                logger.debug(f"脱敏状态: {is_desensitized}")
            
            # 7. 获取总数（在排序和分页之前）
            total = query.count()
            
            # 8. 排序
            # 支持的排序字段
            valid_sort_fields = ['created_at', 'updated_at', 'filename', 'file_size', 'images_count']
            if sort_by not in valid_sort_fields:
                sort_by = 'created_at'
                logger.warning(f"无效的排序字段，使用默认值: created_at")
            
            order_column = getattr(Document, sort_by)
            if sort_order.lower() == 'desc':
                query = query.order_by(order_column.desc())
            else:
                query = query.order_by(order_column.asc())
            
            # 9. 分页
            offset = (page - 1) * page_size
            items = query.offset(offset).limit(page_size).all()
            
            # 10. 加载关联数据（标签）
            for item in items:
                # 加载标签（如果还没有加载）
                if not hasattr(item, '_tags_loaded'):
                    item.tags  # 触发懒加载
                    item._tags_loaded = True
            
            # 11. 计算总页数
            total_pages = (total + page_size - 1) // page_size if total > 0 else 0
            
            logger.info(f"查询完成: 总数={total}, 页码={page}, 每页={page_size}, 返回={len(items)}条")
            
            return {
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "items": items
            }
            
        except Exception as e:
            logger.error(f"查询文档失败: {e}", exc_info=True)
            raise
    
    def get_document_by_id(self, doc_id: str) -> Optional[Document]:
        """
        根据ID获取文档详情
        
        Args:
            doc_id: 文档ID
            
        Returns:
            Document: 文档对象，不存在返回None
        """
        try:
            # 注意：Document.images 和 Document.tags 是 lazy="dynamic" 关系
            # 不能使用 joinedload，需要直接访问关系
            document = (
                self.db.query(Document)
                .filter(Document.id == doc_id)
                .first()
            )
            
            if document:
                logger.debug(f"获取文档成功: {doc_id}")
                # 预加载关联数据（通过访问关系触发懒加载）
                _ = list(document.images)  # 触发images懒加载
                _ = list(document.tags)   # 触发tags懒加载
            else:
                logger.warning(f"文档不存在: {doc_id}")
            
            return document
            
        except Exception as e:
            logger.error(f"获取文档失败: {e}", exc_info=True)
            raise
    
    def delete_document(self, document_id: str) -> bool:
        """
        删除文档及其关联的文件和数据
        
        Args:
            document_id: 文档ID
            
        Returns:
            bool: 删除是否成功
            
        Raises:
            ValueError: 文档不存在
            Exception: 删除失败
        """
        try:
            # 获取文档
            document = self.get_document_by_id(document_id)
            if not document:
                raise ValueError(f"文档不存在: {document_id}")
            
            logger.info(f"开始删除文档: {document.original_filename} (ID: {document_id})")
            
            # 1. 先删除关联的下载日志（避免枚举值不匹配问题）
            try:
                self.db.query(DownloadLog).filter(DownloadLog.document_id == document_id).delete(synchronize_session=False)
                logger.debug(f"已删除文档的下载日志")
            except Exception as e:
                logger.warning(f"删除下载日志失败（将继续删除文档）: {e}")
            
            # 2. 删除文件系统中的文件
            files_to_delete = []
            
            # Markdown文件
            if document.file_path:
                md_file_path = Path(document.file_path)
                if md_file_path.exists():
                    files_to_delete.append(md_file_path)
            
            # 图片文件
            if hasattr(document, 'images'):
                if hasattr(document.images, 'all'):
                    images_list = document.images.all()
                else:
                    images_list = document.images
                
                for img in images_list:
                    if img.file_path:
                        img_file_path = Path(img.file_path)
                        if img_file_path.exists():
                            files_to_delete.append(img_file_path)
            
            # 删除文件
            for file_path in files_to_delete:
                try:
                    file_path.unlink()
                    logger.debug(f"已删除文件: {file_path}")
                except Exception as e:
                    logger.warning(f"删除文件失败: {file_path}, 错误: {e}")
            
            # 删除文档文件夹（如果为空）
            if document.file_path:
                doc_dir = Path(document.file_path).parent
                if doc_dir.exists() and doc_dir.is_dir():
                    try:
                        # 只删除空文件夹
                        if not any(doc_dir.iterdir()):
                            doc_dir.rmdir()
                            logger.debug(f"已删除空文件夹: {doc_dir}")
                    except Exception as e:
                        logger.warning(f"删除文件夹失败: {doc_dir}, 错误: {e}")
            
            # 3. 删除数据库记录（级联删除会自动删除关联的images和tags）
            self.db.delete(document)
            self.db.commit()
            
            logger.info(f"文档删除成功: {document.original_filename} (ID: {document_id})")
            return True
            
        except ValueError:
            raise
        except Exception as e:
            self.db.rollback()
            logger.error(f"删除文档失败: {e}", exc_info=True)
            raise
    
    def batch_delete_documents(self, document_ids: List[str]) -> Dict[str, any]:
        """
        批量删除文档
        
        Args:
            document_ids: 文档ID列表
            
        Returns:
            dict: 删除结果统计
        """
        result = {
            "total": len(document_ids),
            "success": 0,
            "failed": 0,
            "errors": []
        }
        
        for doc_id in document_ids:
            try:
                self.delete_document(doc_id)
                result["success"] += 1
            except ValueError as e:
                result["failed"] += 1
                result["errors"].append({"document_id": doc_id, "error": str(e)})
                logger.warning(f"删除文档失败（不存在）: {doc_id}")
            except Exception as e:
                result["failed"] += 1
                result["errors"].append({"document_id": doc_id, "error": str(e)})
                logger.error(f"删除文档失败: {doc_id}, 错误: {e}")
        
        logger.info(f"批量删除完成: 总数={result['total']}, 成功={result['success']}, 失败={result['failed']}")
        return result
    
    def highlight_keyword(self, text: str, keyword: str, max_length: int = 200) -> str:
        """
        高亮关键词（简单实现）
        
        在文本中查找关键词，并在前后添加标记。
        如果文本太长，会截取包含关键词的部分。
        
        Args:
            text: 原始文本
            keyword: 关键词
            max_length: 最大返回长度
            
        Returns:
            str: 高亮后的文本片段
        """
        if not text or not keyword:
            return text[:max_length] if text else ""
        
        keyword_lower = keyword.lower()
        text_lower = text.lower()
        
        # 查找关键词位置
        index = text_lower.find(keyword_lower)
        
        if index == -1:
            # 未找到关键词，返回前max_length个字符
            return text[:max_length] + "..." if len(text) > max_length else text
        
        # 计算截取范围（关键词前后各取一些字符）
        start = max(0, index - max_length // 2)
        end = min(len(text), index + len(keyword) + max_length // 2)
        
        # 截取文本
        snippet = text[start:end]
        
        # 高亮关键词（使用Markdown格式）
        highlighted = snippet.replace(
            text[start + index - start:start + index - start + len(keyword)],
            f"**{text[start + index - start:start + index - start + len(keyword)]}**"
        )
        
        # 添加省略号
        if start > 0:
            highlighted = "..." + highlighted
        if end < len(text):
            highlighted = highlighted + "..."
        
        return highlighted
