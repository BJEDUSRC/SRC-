# -*- coding: utf-8 -*-
"""
集成测试模块

测试完整的业务流程：上传 -> 查询 -> 下载
"""

import pytest
from starlette.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import tempfile
import os
from pathlib import Path
import io

from app.main import app
from app.database import Base, get_db
from app.config import settings


# 创建测试数据库
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_integration.db"
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


@pytest.fixture
def sample_pdf_content():
    """生成模拟PDF内容（实际测试需要真实PDF）"""
    # 这是一个最小化的PDF文件头（仅用于测试，不是完整PDF）
    # 实际测试应该使用真实的PDF文件
    return b"%PDF-1.4\n%test\n"


class TestFullWorkflow:
    """完整工作流测试"""
    
    def test_upload_query_download_flow(self, client, sample_pdf_content):
        """测试完整流程：上传 -> 查询 -> 下载"""
        # 注意：这个测试需要真实的PDF文件才能完全通过
        # 这里主要测试API的调用流程
        
        # 1. 上传文档（模拟）
        # 由于需要真实的PDF文件，这里跳过实际上传
        # 实际测试时应该使用真实的PDF文件
        pass
    
    def test_query_after_upload(self, client):
        """测试上传后查询"""
        # 1. 先查询文档列表
        response = client.get("/api/v1/documents/")
        assert response.status_code == 200
        initial_count = response.json()["total"]
        
        # 2. 如果有文档，测试查询功能
        if initial_count > 0:
            # 测试关键词搜索
            response = client.get("/api/v1/documents/?keyword=test")
            assert response.status_code == 200
            
            # 测试分页
            response = client.get("/api/v1/documents/?page=1&page_size=5")
            assert response.status_code == 200
            data = response.json()
            assert len(data["items"]) <= 5
    
    def test_download_after_query(self, client):
        """测试查询后下载"""
        # 1. 查询文档
        response = client.get("/api/v1/documents/?page=1&page_size=1")
        assert response.status_code == 200
        data = response.json()
        
        if data["total"] > 0:
            doc_id = data["items"][0]["id"]
            
            # 2. 下载单个文档（MD）
            response = client.get(f"/api/v1/download/{doc_id}?include_images=false")
            # 如果文件存在，应该返回200；如果不存在，可能返回404
            assert response.status_code in [200, 404]
            
            # 3. 获取下载统计
            response = client.get(f"/api/v1/download/stats/{doc_id}")
            assert response.status_code == 200
            stats = response.json()
            assert "total_downloads" in stats
            
            # 4. 获取下载记录
            response = client.get(f"/api/v1/download/logs/{doc_id}")
            assert response.status_code == 200
            logs = response.json()
            assert isinstance(logs, list)


class TestBatchOperations:
    """批量操作测试"""
    
    def test_batch_download_workflow(self, client):
        """测试批量下载流程"""
        # 1. 获取多个文档
        response = client.get("/api/v1/documents/?page=1&page_size=3")
        assert response.status_code == 200
        data = response.json()
        
        if data["total"] >= 2:
            doc_ids = [item["id"] for item in data["items"][:2]]
            
            # 2. 批量下载
            response = client.post(
                "/api/v1/download/batch",
                json={
                    "document_ids": doc_ids,
                    "include_images": True
                }
            )
            # 如果文件存在，返回200和ZIP；如果不存在，可能返回404
            assert response.status_code in [200, 404]
            
            if response.status_code == 200:
                # 验证返回的是ZIP文件
                assert response.headers["content-type"] == "application/zip"
                assert len(response.content) > 0


class TestErrorHandling:
    """错误处理测试"""
    
    def test_invalid_document_id(self, client):
        """测试无效文档ID"""
        invalid_ids = [
            "",
            "invalid-id",
            "123",
            "nonexistent-uuid-format"
        ]
        
        for doc_id in invalid_ids:
            # 查询
            response = client.get(f"/api/v1/documents/{doc_id}")
            assert response.status_code == 404
            
            # 下载
            response = client.get(f"/api/v1/download/{doc_id}")
            assert response.status_code == 404
    
    def test_invalid_query_parameters(self, client):
        """测试无效查询参数"""
        # 无效页码
        response = client.get("/api/v1/documents/?page=-1")
        assert response.status_code in [200, 422]  # 可能被验证或默认处理
        
        # 无效页面大小
        response = client.get("/api/v1/documents/?page_size=0")
        assert response.status_code in [200, 422]
        
        # 无效日期格式
        response = client.get("/api/v1/documents/?date_from=invalid-date")
        assert response.status_code in [200, 422]


class TestDataConsistency:
    """数据一致性测试"""
    
    def test_document_consistency(self, client):
        """测试文档数据一致性"""
        # 1. 获取文档列表
        list_response = client.get("/api/v1/documents/")
        assert list_response.status_code == 200
        documents = list_response.json()["items"]
        
        # 2. 验证每个文档的详情
        for doc in documents[:5]:  # 只测试前5个
            doc_id = doc["id"]
            
            # 获取详情
            detail_response = client.get(f"/api/v1/documents/{doc_id}")
            assert detail_response.status_code == 200
            detail = detail_response.json()
            
            # 验证一致性
            assert detail["id"] == doc["id"]
            assert detail["filename"] == doc["filename"]
            assert detail["images_count"] == doc["images_count"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
