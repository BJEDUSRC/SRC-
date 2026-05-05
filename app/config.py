"""
应用配置模块

使用pydantic-settings管理配置，支持从环境变量和.env文件加载。
"""

from pydantic_settings import BaseSettings
from typing import Optional, List
from pathlib import Path


class Settings(BaseSettings):
    """应用配置类"""
    
    # 应用配置
    APP_NAME: str = "SRC脱敏标注数据管理系统"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    # 数据库配置
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str
    DB_NAME: str = "src_data"
    
    # LLM配置
    LLM_PROVIDER: str = "openai"  # openai, qwen
    LLM_MODEL: str = "gpt-4o-mini"  # 支持任何符合OpenAI接口的模型
    LLM_API_KEY: Optional[str] = None  # 如果为空，从环境变量OPENAI_API_KEY读取
    LLM_API_BASE: Optional[str] = None  # 如果为空，从环境变量OPENAI_BASE_URL读取
    
    # 脱敏配置
    SHOW_LLM_THINKING_PROCESS: bool = False  # 是否在脱敏输出中包含LLM的思考过程
    
    # 文件存储配置
    UPLOAD_DIR: str = "./uploads"
    CONVERTED_DIR: str = "./converted"
    MAX_FILE_SIZE: int = 100 * 1024 * 1024  # 100MB
    
    # 安全配置
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:8000"
    
    # 服务器配置
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    @property
    def database_url(self) -> str:
        """
        生成数据库连接URL
        
        Returns:
            MySQL连接字符串
        """
        return f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"
    
    @property
    def allowed_origins_list(self) -> List[str]:
        """
        解析允许的跨域源列表
        
        Returns:
            跨域源列表
        """
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",")]
    
    def ensure_directories(self) -> None:
        """
        确保必要的目录存在
        """
        directories = [
            self.UPLOAD_DIR,
            self.CONVERTED_DIR,
            f"{self.CONVERTED_DIR}/images",
            "database",
            "logs"
        ]
        
        for directory in directories:
            Path(directory).mkdir(parents=True, exist_ok=True)
    
    class Config:
        """Pydantic配置"""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# 全局配置实例
settings = Settings()
