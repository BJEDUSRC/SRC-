# -*- coding: utf-8 -*-
"""
安全测试模块

测试SQL注入、XSS、文件上传安全等。
"""

import pytest
from starlette.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import Base, get_db


# 创建测试数据库
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_security.db"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db_session():
    """创建测试数据库会话"""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session):
    """创建测试客户端"""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    test_client = TestClient(app)
    yield test_client
    
    app.dependency_overrides.clear()


class TestSQLInjection:
    """SQL注入测试"""
    
    def test_sql_injection_in_keyword(self, client):
        """测试关键词搜索中的SQL注入"""
        sql_payloads = [
            "'; DROP TABLE documents; --",
            "' OR '1'='1",
            "1' UNION SELECT * FROM documents --",
            "'; DELETE FROM documents; --"
        ]
        
        for payload in sql_payloads:
            response = client.get(f"/api/v1/documents/?keyword={payload}")
            # 应该正常处理，不会执行SQL注入
            assert response.status_code in [200, 400, 422]
            # 验证数据库表仍然存在（通过查询验证）
            check_response = client.get("/api/v1/documents/")
            assert check_response.status_code == 200
    
    def test_sql_injection_in_filename(self, client):
        """测试文件名搜索中的SQL注入"""
        sql_payloads = [
            "'; DROP TABLE documents; --",
            "' OR '1'='1"
        ]
        
        for payload in sql_payloads:
            response = client.get(f"/api/v1/documents/?filename={payload}")
            assert response.status_code in [200, 400, 422]
    
    def test_sql_injection_in_document_id(self, client):
        """测试文档ID中的SQL注入"""
        sql_payloads = [
            "'; DROP TABLE documents; --",
            "1' OR '1'='1",
            "1' UNION SELECT * FROM documents --"
        ]
        
        for payload in sql_payloads:
            # 查询
            response = client.get(f"/api/v1/documents/{payload}")
            assert response.status_code == 404  # 无效ID应该返回404
            
            # 下载
            response = client.get(f"/api/v1/download/{payload}")
            assert response.status_code == 404


class TestXSS:
    """XSS攻击测试"""
    
    def test_xss_in_keyword(self, client):
        """测试关键词中的XSS"""
        xss_payloads = [
            "<script>alert('XSS')</script>",
            "<img src=x onerror=alert('XSS')>",
            "javascript:alert('XSS')",
            "<svg onload=alert('XSS')>"
        ]
        
        for payload in xss_payloads:
            response = client.get(f"/api/v1/documents/?keyword={payload}")
            # API应该正常处理，不会执行脚本
            assert response.status_code in [200, 400, 422]
            # 验证响应中没有未转义的脚本标签
            if response.status_code == 200:
                content = response.text
                assert "<script>" not in content or "&lt;script&gt;" in content
    
    def test_xss_in_filename(self, client):
        """测试文件名中的XSS"""
        xss_payloads = [
            "<script>alert('XSS')</script>.pdf",
            "test<script>.pdf"
        ]
        
        for payload in xss_payloads:
            response = client.get(f"/api/v1/documents/?filename={payload}")
            assert response.status_code in [200, 400, 422]


class TestFileUploadSecurity:
    """文件上传安全测试"""
    
    def test_upload_non_pdf_file(self, client):
        """测试上传非PDF文件"""
        # 尝试上传可执行文件
        malicious_files = [
            ("test.exe", b"MZ\x90\x00", "application/x-msdownload"),
            ("test.php", b"<?php echo 'hack'; ?>", "application/x-php"),
            ("test.sh", b"#!/bin/bash\necho 'hack'", "application/x-sh"),
            ("test.js", b"alert('hack')", "application/javascript"),
        ]
        
        for filename, content, content_type in malicious_files:
            response = client.post(
                "/api/v1/upload",
                files={"file": (filename, content, content_type)}
            )
            # 应该拒绝非PDF文件
            assert response.status_code in [400, 422]
    
    def test_upload_large_file(self, client):
        """测试上传超大文件"""
        # 创建一个大的假文件（例如100MB）
        large_content = b"0" * (100 * 1024 * 1024)  # 100MB
        large_file = ("large.pdf", large_content, "application/pdf")
        
        response = client.post(
            "/api/v1/upload",
            files={"file": large_file}
        )
        # 应该被大小限制拒绝
        assert response.status_code in [400, 413, 422]
    
    def test_upload_path_traversal(self, client):
        """测试路径遍历攻击"""
        path_traversal_names = [
            "../../../etc/passwd.pdf",
            "..\\..\\..\\windows\\system32\\config\\sam.pdf",
            "....//....//etc/passwd.pdf"
        ]
        
        for filename in path_traversal_names:
            test_file = (filename, b"%PDF-1.4", "application/pdf")
            response = client.post(
                "/api/v1/upload",
                files={"file": test_file}
            )
            # 应该被路径验证拒绝或安全处理
            assert response.status_code in [400, 422, 500]


class TestInputValidation:
    """输入验证测试"""
    
    def test_invalid_date_format(self, client):
        """测试无效日期格式"""
        invalid_dates = [
            "2026-13-45",  # 无效月份和日期
            "not-a-date",
            "2026/01/01",  # 错误的分隔符
            "01-01-2026",  # 错误的顺序
        ]
        
        for date in invalid_dates:
            response = client.get(f"/api/v1/documents/?date_from={date}")
            assert response.status_code in [200, 400, 422]
    
    def test_negative_pagination(self, client):
        """测试负数分页参数"""
        response = client.get("/api/v1/documents/?page=-1&page_size=-10")
        # 应该被验证拒绝或使用默认值
        assert response.status_code in [200, 422]
    
    def test_extremely_large_pagination(self, client):
        """测试极大的分页参数"""
        response = client.get("/api/v1/documents/?page=999999&page_size=999999")
        # 应该被限制或使用默认值
        assert response.status_code in [200, 422]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
