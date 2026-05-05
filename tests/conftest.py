# -*- coding: utf-8 -*-
"""
Pytest配置文件

提供共享的fixtures和测试配置。
"""

import pytest
import os
import tempfile
from pathlib import Path


@pytest.fixture(scope="session")
def test_data_dir():
    """创建测试数据目录"""
    temp_dir = tempfile.mkdtemp(prefix="src_test_")
    yield Path(temp_dir)
    # 清理（如果需要）
    # import shutil
    # shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture(scope="session")
def test_config():
    """测试配置"""
    return {
        "test_db_url": "sqlite:///./test.db",
        "test_upload_dir": "./test_uploads",
        "test_converted_dir": "./test_converted",
    }


# 配置pytest
def pytest_configure(config):
    """Pytest配置钩子"""
    config.addinivalue_line(
        "markers", "integration: 标记为集成测试"
    )
    config.addinivalue_line(
        "markers", "slow: 标记为慢速测试"
    )
    config.addinivalue_line(
        "markers", "requires_llm: 需要LLM API的测试"
    )
