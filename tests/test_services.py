"""
核心服务测试模块

测试PDF转换、图片提取、LLM服务和数据脱敏等核心功能。
"""

import pytest
import os
import asyncio
from pathlib import Path

from app.services.image_extractor import ImageExtractor
from app.services.pdf_converter import PDFConverter
from app.services.llm_service import LLMService
from app.services.desensitizer import Desensitizer
from app.config import settings


class TestImageExtractor:
    """图片提取器测试"""
    
    def test_generate_md_image_ref(self):
        """测试Markdown图片引用生成"""
        image_info = {
            "path": "images/doc1/test_p1_img1.png",
            "page": 1,
            "index": 1
        }
        
        ref = ImageExtractor.generate_md_image_ref(image_info)
        assert ref == "![图片1-1](images/doc1/test_p1_img1.png)"
        
        # 测试自定义alt文本
        ref = ImageExtractor.generate_md_image_ref(image_info, "测试图片")
        assert ref == "![测试图片](images/doc1/test_p1_img1.png)"


class TestPDFConverter:
    """PDF转换器测试"""
    
    def test_table_to_markdown(self):
        """测试表格转Markdown"""
        table = [
            ["姓名", "年龄", "城市"],
            ["张三", "25", "北京"],
            ["李四", "30", "上海"]
        ]
        
        md = PDFConverter.table_to_markdown(table)
        
        assert "姓名" in md
        assert "张三" in md
        assert "|" in md
        assert "---" in md
    
    def test_empty_table(self):
        """测试空表格"""
        md = PDFConverter.table_to_markdown([])
        assert md == ""
        
        md = PDFConverter.table_to_markdown([[]])
        assert md == ""


class TestDesensitizer:
    """数据脱敏测试"""
    
    def test_regex_desensitize_ip(self):
        """测试IP地址脱敏"""
        desensitizer = Desensitizer(enable_llm=False)  # 仅使用正则，不初始化LLM
        
        text = "服务器IP是192.168.1.100，备用IP是10.0.0.1"
        result, stats = desensitizer._regex_desensitize(text)
        
        assert "192.168.***.***" in result
        assert "10.0.***.***" in result
        assert stats.get("ip", 0) == 2
    
    def test_regex_desensitize_phone(self):
        """测试手机号脱敏"""
        desensitizer = Desensitizer(enable_llm=False)
        
        text = "联系电话：13812345678，备用：13987654321"
        result, stats = desensitizer._regex_desensitize(text)
        
        assert "138****5678" in result
        assert "139****4321" in result
        assert stats.get("phone", 0) == 2
    
    def test_regex_desensitize_id_card(self):
        """测试身份证号脱敏"""
        desensitizer = Desensitizer(enable_llm=False)
        
        text = "身份证号：110101199001011234"
        result, stats = desensitizer._regex_desensitize(text)
        
        assert "110101********1234" in result
        assert stats.get("id_card", 0) == 1
    
    def test_regex_desensitize_email(self):
        """测试邮箱脱敏"""
        desensitizer = Desensitizer(enable_llm=False)
        
        text = "邮箱：user@example.com"
        result, stats = desensitizer._regex_desensitize(text)
        
        assert "u***@example.com" in result
        assert stats.get("email", 0) == 1
    
    def test_validate_desensitization(self):
        """测试脱敏验证"""
        desensitizer = Desensitizer(enable_llm=False)
        
        original = "IP: 192.168.1.100, 手机: 13812345678"
        desensitized = "IP: 192.168.***.***,手机: 138****5678"
        
        result = desensitizer.validate_desensitization(original, desensitized)
        
        assert result["is_safe"] == True
        assert len(result["remaining_sensitive"]) == 0


class TestLLMService:
    """LLM服务测试"""
    
    def test_split_text_by_tokens(self):
        """测试文本分割"""
        llm_service = LLMService()
        
        text = "这是一段测试文本。" * 1000  # 创建长文本
        chunks = llm_service.split_text_by_tokens(text, max_tokens=500)
        
        assert len(chunks) > 1
        assert all(len(chunk) <= 700 for chunk in chunks)  # 考虑overlap
    
    def test_get_token_count(self):
        """测试token计数"""
        llm_service = LLMService()
        
        # 中文文本
        chinese_text = "这是一段中文测试文本"
        count = llm_service.get_token_count(chinese_text)
        assert count > 0
        
        # 英文文本
        english_text = "This is an English test text"
        count = llm_service.get_token_count(english_text)
        assert count > 0


# 集成测试（需要实际的LLM API）
@pytest.mark.asyncio
@pytest.mark.skipif(
    not settings.LLM_API_KEY or settings.LLM_API_KEY == "your_api_key_here",
    reason="需要有效的LLM API密钥"
)
class TestIntegration:
    """集成测试（需要真实API）"""
    
    async def test_full_desensitize_flow(self):
        """测试完整脱敏流程"""
        desensitizer = Desensitizer()
        
        text = """
        姓名：张三
        手机：13812345678
        身份证：110101199001011234
        地址：北京市朝阳区建国路100号
        IP：192.168.1.100
        """
        
        result = await desensitizer.desensitize(text, use_regex=True, use_llm=True)
        
        assert result["regex_stats"]["phone"] >= 1
        assert result["regex_stats"]["id_card"] >= 1
        assert result["regex_stats"]["ip"] >= 1
        assert result["llm_success"] == True
        
        # 验证脱敏效果
        validation = desensitizer.validate_desensitization(
            text,
            result["desensitized_text"]
        )
        
        assert validation["is_safe"] == True


class TestURLDesensitizationService:
    """URL脱敏映射服务测试"""
    
    def test_extract_path_segments(self):
        """测试URL路径段提取"""
        from app.services.url_desensitization_service import get_url_desensitization_service
        
        service = get_url_desensitization_service()
        
        # 测试标准URL
        url = "http://www.baidu.com/sousou/api/v1/users"
        segments = service.extract_path_segments(url)
        assert segments == ["sousou", "api", "v1", "users"]
        
        # 测试带查询参数的URL
        url = "https://example.com/path1/path2?param=value"
        segments = service.extract_path_segments(url)
        assert segments == ["path1", "path2"]
        
        # 测试根路径
        url = "https://example.com/"
        segments = service.extract_path_segments(url)
        assert segments == []
    
    def test_add_and_get_map(self):
        """测试添加和获取映射"""
        from app.services.url_desensitization_service import get_url_desensitization_service
        
        service = get_url_desensitization_service()
        
        # 添加映射
        result = service.add_map("sousou", "bccbcc")
        assert result == True
        
        # 获取映射
        mapping = service.get_map("sousou")
        assert mapping is not None
        assert mapping.original_path_segment == "sousou"
        assert mapping.desensitized_path_segment == "bccbcc"
    
    def test_get_existing_mappings_for_url(self):
        """测试获取URL中已存在的映射"""
        from app.services.url_desensitization_service import get_url_desensitization_service
        
        service = get_url_desensitization_service()
        
        # 先添加一些映射
        service.add_map("sousou", "bccbcc")
        service.add_map("api", "xyzxyz")
        
        # 测试包含已映射路径段的URL
        url = "http://www.baidu.com/sousou/api/v1/users"
        mappings = service.get_existing_mappings_for_url(url)
        assert "sousou" in mappings
        assert "api" in mappings
        assert mappings["sousou"] == "bccbcc"
        assert mappings["api"] == "xyzxyz"
        
        # 测试不包含已映射路径段的URL
        url = "http://www.baidu.com/search/v2/users"
        mappings = service.get_existing_mappings_for_url(url)
        assert len(mappings) == 0


# 集成测试（需要实际的LLM API）
@pytest.mark.asyncio
@pytest.mark.skipif(
    not settings.LLM_API_KEY or settings.LLM_API_KEY == "your_api_key_here",
    reason="需要有效的LLM API密钥"
)
class TestURLDesensitizationIntegration:
    """URL脱敏映射集成测试（需要真实API）"""
    
    async def test_cross_document_url_consistency(self):
        """测试跨文档URL脱敏一致性"""
        from app.services.desensitizer import Desensitizer
        from app.services.url_desensitization_service import get_url_desensitization_service
        
        desensitizer = Desensitizer()
        url_service = get_url_desensitization_service()
        
        # 清理测试数据
        try:
            # 清空现有映射
            mappings = url_service.get_all_maps()
            for mapping in mappings:
                url_service.db.delete(mapping)
            url_service.db.commit()
        except:
            pass
        
        # 第一个文档：包含URL
        doc1_text = "测试URL：http://www.baidu.com/sousou/api/v1/users?id=123"
        result1 = await desensitizer.desensitize(doc1_text, use_llm=True)
        
        assert result1["llm_success"] == True
        desensitized_doc1 = result1["desensitized_text"]
        
        # 第二个文档：包含相同的URL路径段
        doc2_text = "另一个测试：http://www.example.com/sousou/api/v2/products"
        result2 = await desensitizer.desensitize(doc2_text, use_llm=True)
        
        assert result2["llm_success"] == True
        desensitized_doc2 = result2["desensitized_text"]
        
        # 验证两个文档中的相同路径段被脱敏为相同的值
        # 提取脱敏后的路径段
        from app.services.url_desensitization_service import get_url_desensitization_service
        service = get_url_desensitization_service()
        
        # 获取已保存的映射
        sousou_mapping = service.get_map("sousou")
        api_mapping = service.get_map("api")
        
        assert sousou_mapping is not None
        assert api_mapping is not None
        
        # 验证映射在两个文档中都被使用
        assert sousou_mapping.desensitized_path_segment in desensitized_doc1
        assert sousou_mapping.desensitized_path_segment in desensitized_doc2
        assert api_mapping.desensitized_path_segment in desensitized_doc1
        assert api_mapping.desensitized_path_segment in desensitized_doc2


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "-s"])
