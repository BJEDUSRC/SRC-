# -*- coding: utf-8 -*-
"""
API接口测试模块

测试FastAPI端点的功能。
"""

import pytest
from starlette.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import tempfile
import os
from pathlib import Path

from app.main import app
from app.database import Base, get_db
from app.config import settings


# 创建测试数据库
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
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


@pytest.fixture(scope="function")
def test_pdf_file():
    """创建测试PDF文件（模拟）"""
    # 注意：实际测试需要真实的PDF文件
    # 这里返回一个路径，实际使用时需要提供真实的PDF文件
    return None


class TestHealthCheck:
    """健康检查测试"""
    
    def test_health_check(self, client):
        """测试健康检查端点"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "app_name" in data


class TestUploadAPI:
    """上传API测试"""
    
    def test_upload_without_file(self, client):
        """测试无文件上传"""
        response = client.post("/api/v1/upload")
        assert response.status_code == 422  # 验证错误
    
    def test_upload_invalid_file_type(self, client):
        """测试无效文件类型"""
        # 创建一个非PDF文件
        test_file = ("test.txt", b"test content", "text/plain")
        response = client.post(
            "/api/v1/upload",
            files={"file": test_file}
        )
        assert response.status_code == 400
    
    def test_upload_empty_file(self, client):
        """测试空文件上传"""
        test_file = ("empty.pdf", b"", "application/pdf")
        response = client.post(
            "/api/v1/upload",
            files={"file": test_file}
        )
        # 应该返回错误或拒绝空文件
        assert response.status_code in [400, 422]


class TestQueryAPI:
    """查询API测试"""
    
    def test_query_all_documents(self, client):
        """测试查询所有文档"""
        response = client.get("/api/v1/documents/")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert isinstance(data["items"], list)
    
    def test_query_with_pagination(self, client):
        """测试分页查询"""
        response = client.get("/api/v1/documents/?page=1&page_size=10")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) <= 10
    
    def test_query_with_keyword(self, client):
        """测试关键词搜索"""
        response = client.get("/api/v1/documents/?keyword=test")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
    
    def test_query_with_date_range(self, client):
        """测试日期范围查询"""
        response = client.get(
            "/api/v1/documents/?date_from=2026-01-01&date_to=2026-12-31"
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
    
    def test_query_nonexistent_document(self, client):
        """测试查询不存在的文档"""
        response = client.get("/api/v1/documents/nonexistent-id")
        assert response.status_code == 404


class TestDownloadAPI:
    """下载API测试"""
    
    def test_download_nonexistent_document(self, client):
        """测试下载不存在的文档"""
        response = client.get("/api/v1/download/nonexistent-id")
        assert response.status_code == 404
    
    def test_batch_download_empty_list(self, client):
        """测试批量下载空列表"""
        response = client.post(
            "/api/v1/download/batch",
            json={"document_ids": [], "include_images": True}
        )
        # 应该返回错误或空响应
        assert response.status_code in [400, 404]
    
    def test_batch_download_invalid_ids(self, client):
        """测试批量下载无效ID"""
        response = client.post(
            "/api/v1/download/batch",
            json={"document_ids": ["invalid-id-1", "invalid-id-2"], "include_images": True}
        )
        # 应该返回404或空ZIP
        assert response.status_code in [404, 200]
    
    def test_download_stats_nonexistent(self, client):
        """测试获取不存在文档的统计"""
        response = client.get("/api/v1/download/stats/nonexistent-id")
        assert response.status_code == 200  # 应该返回0统计
        data = response.json()
        assert data["total_downloads"] == 0
    
    def test_download_logs_nonexistent(self, client):
        """测试获取不存在文档的下载记录"""
        response = client.get("/api/v1/download/logs/nonexistent-id")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0


class TestWebPages:
    """Web页面测试"""
    
    def test_index_page(self, client):
        """测试首页"""
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    
    def test_upload_page(self, client):
        """测试上传页面"""
        response = client.get("/upload")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    
    def test_query_page(self, client):
        """测试查询页面"""
        response = client.get("/query")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    
    def test_download_page(self, client):
        """测试下载管理页面"""
        response = client.get("/download")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
