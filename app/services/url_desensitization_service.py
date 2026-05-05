# -*- coding: utf-8 -*-
"""
URL脱敏映射服务

管理URL路径段的脱敏映射关系，实现跨文档一致脱敏。
"""

from typing import Dict, Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import desc
import logging
import re

from app.models.document import URLDesensitizationMap
from app.database import get_db

logger = logging.getLogger(__name__)


class URLDesensitizationService:
    """
    URL脱敏映射服务类
    
    管理URL路径段的脱敏映射关系，确保跨文档脱敏一致性。
    """
    
    # 映射表最大记录数
    MAX_RECORDS = 1000
    
    def __init__(self, db: Optional[Session] = None):
        """
        初始化URL脱敏映射服务
        
        Args:
            db: 数据库会话，如果为None则使用默认会话
        """
        self.db = db or next(get_db())
    
    def get_map(self, original_path_segment: str) -> Optional[URLDesensitizationMap]:
        """
        获取指定原始路径段的脱敏映射
        
        Args:
            original_path_segment: 原始路径段
            
        Returns:
            URLDesensitizationMap对象或None
        """
        try:
            return self.db.query(URLDesensitizationMap).filter(
                URLDesensitizationMap.original_path_segment == original_path_segment
            ).first()
        except Exception as e:
            logger.error(f"获取URL脱敏映射失败: {e}")
            return None
    
    def get_all_maps(self) -> List[URLDesensitizationMap]:
        """
        获取所有脱敏映射
        
        Returns:
            脱敏映射列表
        """
        try:
            return self.db.query(URLDesensitizationMap).all()
        except Exception as e:
            logger.error(f"获取所有URL脱敏映射失败: {e}")
            return []
    
    def add_map(self, original_path_segment: str, desensitized_path_segment: str) -> bool:
        """
        添加新的脱敏映射
        
        Args:
            original_path_segment: 原始路径段
            desensitized_path_segment: 脱敏后的路径段
            
        Returns:
            bool: 添加成功返回True，失败返回False
        """
        try:
            # 检查是否已存在
            existing_map = self.get_map(original_path_segment)
            if existing_map:
                logger.info(f"URL脱敏映射已存在: {original_path_segment}")
                return True
            
            # 检查记录数，超过限制则删除最旧的记录
            self._maintain_map_size()
            
            # 创建新映射
            new_map = URLDesensitizationMap(
                original_path_segment=original_path_segment,
                desensitized_path_segment=desensitized_path_segment
            )
            
            self.db.add(new_map)
            self.db.commit()
            logger.info(f"添加URL脱敏映射成功: {original_path_segment} -> {desensitized_path_segment}")
            return True
        except Exception as e:
            logger.error(f"添加URL脱敏映射失败: {e}")
            self.db.rollback()
            return False
    
    def add_maps_batch(self, mappings: Dict[str, str]) -> Dict[str, bool]:
        """
        批量添加脱敏映射
        
        Args:
            mappings: 原始路径段到脱敏路径段的映射字典
            
        Returns:
            Dict[str, bool]: 每个映射的添加结果
        """
        results = {}
        
        try:
            # 检查记录数，预留空间
            current_count = self.db.query(URLDesensitizationMap).count()
            if current_count + len(mappings) > self.MAX_RECORDS:
                # 需要删除的记录数
                delete_count = (current_count + len(mappings)) - self.MAX_RECORDS
                self._delete_oldest_records(delete_count)
            
            # 批量添加
            for original, desensitized in mappings.items():
                existing_map = self.get_map(original)
                if existing_map:
                    results[original] = True
                    continue
                
                new_map = URLDesensitizationMap(
                    original_path_segment=original,
                    desensitized_path_segment=desensitized
                )
                self.db.add(new_map)
                results[original] = True
            
            self.db.commit()
            logger.info(f"批量添加URL脱敏映射成功，处理 {len(results)} 条记录")
        except Exception as e:
            logger.error(f"批量添加URL脱敏映射失败: {e}")
            self.db.rollback()
            for original in mappings:
                results[original] = False
        
        return results
    
    def _maintain_map_size(self):
        """
        维护映射表大小，确保不超过最大记录数
        """
        try:
            current_count = self.db.query(URLDesensitizationMap).count()
            if current_count >= self.MAX_RECORDS:
                # 删除最旧的记录
                delete_count = current_count - self.MAX_RECORDS + 1
                self._delete_oldest_records(delete_count)
        except Exception as e:
            logger.error(f"维护URL脱敏映射表大小失败: {e}")
    
    def _delete_oldest_records(self, count: int):
        """
        删除最旧的记录
        
        Args:
            count: 删除记录数
        """
        try:
            # 按创建时间排序，删除最旧的记录
            oldest_records = self.db.query(URLDesensitizationMap).order_by(
                URLDesensitizationMap.created_at
            ).limit(count).all()
            
            for record in oldest_records:
                self.db.delete(record)
            
            self.db.commit()
            logger.info(f"删除最旧的URL脱敏映射记录: {len(oldest_records)} 条")
        except Exception as e:
            logger.error(f"删除最旧的URL脱敏映射记录失败: {e}")
            self.db.rollback()
    
    def extract_path_segments(self, url: str) -> List[str]:
        """
        从URL中提取路径段
        
        Args:
            url: URL字符串
            
        Returns:
            List[str]: 路径段列表
        """
        try:
            # 提取URL路径部分
            path_match = re.search(r'https?://[^/]+(/[^?#]*)', url)
            if not path_match:
                return []
            
            path = path_match.group(1)
            # 分割路径段，过滤空字符串
            segments = [segment for segment in path.split('/') if segment]
            return segments
        except Exception as e:
            logger.error(f"提取URL路径段失败: {e}")
            return []
    
    def get_existing_mappings_for_url(self, url: str) -> Dict[str, str]:
        """
        获取URL中已存在的路径段映射
        
        Args:
            url: URL字符串
            
        Returns:
            Dict[str, str]: 已存在的路径段映射
        """
        mappings = {}
        segments = self.extract_path_segments(url)
        
        for segment in segments:
            mapping = self.get_map(segment)
            if mapping:
                mappings[segment] = mapping.desensitized_path_segment
        
        return mappings
    
    def close(self):
        """
        关闭数据库会话
        """
        if self.db:
            try:
                self.db.close()
            except Exception as e:
                logger.error(f"关闭数据库会话失败: {e}")


# 全局服务实例
_url_desensitization_service = None


def get_url_desensitization_service() -> URLDesensitizationService:
    """
    获取URL脱敏映射服务实例
    
    Returns:
        URLDesensitizationService实例
    """
    global _url_desensitization_service
    if _url_desensitization_service is None:
        _url_desensitization_service = URLDesensitizationService()
    return _url_desensitization_service
