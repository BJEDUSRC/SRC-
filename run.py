"""
应用启动脚本

使用uvicorn启动FastAPI应用。
"""

import uvicorn
from app.config import settings


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,  # 开发环境启用热重载
        log_level="debug" if settings.DEBUG else "info",
        access_log=True,
    )
