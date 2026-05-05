"""
FastAPI应用主入口

创建和配置FastAPI应用实例，注册路由、中间件和异常处理器。
"""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
# 暂时注释掉slowapi，避免.env编码问题（第二阶段再启用）
# from slowapi import Limiter, _rate_limit_exceeded_handler
# from slowapi.util import get_remote_address
# from slowapi.errors import RateLimitExceeded
from contextlib import asynccontextmanager
import logging
import sys

from app.config import settings
from app.database import check_db_connection, init_db
from app.utils.logger import setup_logging

# 设置日志
logger = setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理
    
    在应用启动时执行初始化，关闭时执行清理。
    """
    # 启动时执行
    logger.info(f"启动 {settings.APP_NAME} v{settings.APP_VERSION}")
    
    # 确保必要的目录存在
    settings.ensure_directories()
    logger.info("已创建必要的目录")
    
    # 检查数据库连接
    if not check_db_connection():
        logger.error("数据库连接失败，应用无法启动")
        sys.exit(1)
    
    # 初始化数据库表（仅开发环境，生产环境使用Alembic）
    if settings.DEBUG:
        try:
            init_db()
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}")
            sys.exit(1)
    
    logger.info("应用启动完成")
    
    try:
        yield
    finally:
        # 关闭时执行
        try:
            logger.info("应用正在关闭...")
            # 这里可以添加清理逻辑，如关闭数据库连接池等
            # 注意：CancelledError 是正常的关闭流程，不需要特殊处理
        except Exception as e:
            # 捕获关闭时的异常，避免影响正常关闭流程
            logger.debug(f"关闭过程中的异常（可忽略）: {e}")


# 创建FastAPI应用实例
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="基于大模型的SRC脱敏标注数据管理系统，用于PDF文档的智能转换、数据脱敏和管理",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan
)

# 配置CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 配置速率限制（暂时禁用，避免.env编码问题）
# limiter = Limiter(
#     key_func=get_remote_address,
#     default_limits=["100/minute"],
#     storage_uri="memory://",
#     enabled=True,
#     headers_enabled=True,
#     swallow_errors=False
# )
# app.state.limiter = limiter
# app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# 挂载静态文件目录（如果目录存在）
import os
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


# 全局异常处理器
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    全局异常处理器
    
    捕获所有未处理的异常，返回统一的错误响应。
    """
    logger.error(f"未处理的异常: {exc}", exc_info=True)
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "code": 500,
            "message": "服务器内部错误",
            "detail": str(exc) if settings.DEBUG else "请联系管理员"
        }
    )


# 健康检查端点
@app.get(
    "/health",
    tags=["system"],
    summary="健康检查",
    description="检查应用和数据库服务是否正常"
)
async def health_check():
    """
    健康检查接口
    
    Returns:
        dict: 包含服务状态的响应
    """
    db_status = check_db_connection()
    
    return {
        "status": "healthy" if db_status else "unhealthy",
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "database": "connected" if db_status else "disconnected"
    }


# API文档重定向（方便用户访问）
@app.get("/api/docs", include_in_schema=False)
async def api_docs_redirect():
    """重定向到API文档页面"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/docs")


# 注册Web页面路由
from app.api import web
app.include_router(web.router)

# 注册API路由
from app.api import upload, query, download, convert, desensitize_api, vulnerability_level_api
app.include_router(upload.router)
app.include_router(query.router)
app.include_router(download.router)
app.include_router(convert.router)
app.include_router(desensitize_api.router)
app.include_router(vulnerability_level_api.router)
