"""
数据库连接和会话管理模块

使用SQLAlchemy管理MySQL数据库连接池和会话。
"""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import QueuePool
from app.config import settings
import logging
import sqlalchemy

logger = logging.getLogger(__name__)

# 创建数据库引擎
engine = create_engine(
    settings.database_url,
    poolclass=QueuePool,
    pool_size=10,  # 连接池大小
    max_overflow=20,  # 最大溢出连接数
    pool_pre_ping=True,  # 连接前测试连接有效性
    pool_recycle=3600,  # 连接回收时间（秒）
    echo=settings.DEBUG,  # 开发环境打印SQL
    connect_args={
        "charset": "utf8mb4",
        "connect_timeout": 10,
    }
)

# 创建会话工厂
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# 创建ORM基类
Base = declarative_base()


def get_db():
    """
    获取数据库会话依赖
    
    用于FastAPI依赖注入，自动管理会话生命周期。
    
    Yields:
        Session: 数据库会话对象
        
    Example:
        ```python
        @router.get("/documents")
        def get_documents(db: Session = Depends(get_db)):
            return db.query(Document).all()
        ```
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """
    初始化数据库
    
    创建所有表结构。注意：生产环境应使用Alembic迁移。
    """
    try:
        # 导入所有模型以确保它们被注册
        from app.models import document  # noqa: F401
        
        logger.info("开始创建数据库表...")
        # 使用SQLAlchemy创建所有表结构
        Base.metadata.create_all(bind=engine)
        logger.info("数据库表创建成功，模型已注册")
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}", exc_info=True)
        raise


def check_db_connection() -> bool:
    """
    检查数据库连接是否正常
    
    Returns:
        bool: 连接正常返回True，否则返回False
    """
    try:
        # 尝试执行简单查询
        with engine.connect() as conn:
            conn.execute(sqlalchemy.text("SELECT 1"))
        logger.info("数据库连接正常")
        return True
    except Exception as e:
        logger.error(f"数据库连接失败: {e}", exc_info=True)
        return False


# 监听连接事件（可选：用于调试）
@event.listens_for(engine, "connect")
def receive_connect(dbapi_conn, connection_record):
    """连接建立时的回调"""
    if settings.DEBUG:
        logger.debug("数据库连接已建立")


@event.listens_for(engine, "checkout")
def receive_checkout(dbapi_conn, connection_record, connection_proxy):
    """从连接池取出连接时的回调"""
    if settings.DEBUG:
        logger.debug("从连接池获取连接")
