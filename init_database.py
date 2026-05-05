"""
数据库初始化脚本

使用SQLAlchemy创建所有表结构，包括URL脱敏映射表。
"""

from app.database import init_db

if __name__ == "__main__":
    print("开始初始化数据库...")
    try:
        init_db()
        print("数据库初始化成功！")
    except Exception as e:
        print(f"数据库初始化失败: {e}")
