from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # SQLite（本地部署，无需 MySQL/Redis）
    sqlite_path: str = "./data/video_strm.db"

    # OpenList：执行日志文件目录（独立于数据库目录存放）
    openlist_log_dir: str = "./openlist_logs"

    # CORS（本地开发前端默认 5173；本地部署可放宽为 * 或指定端口）
    allowed_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
