"""SQLite 异步数据库：启动时自动建表 + 种子数据（本地部署，无需 Alembic 迁移）。"""

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from app.core.settings import settings

# 确保 SQLite 文件所在目录存在
_db_path = Path(settings.sqlite_path)
_db_path.parent.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite+aiosqlite:///{settings.sqlite_path}"
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)
Base = declarative_base()


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    """建表并写入默认 OpenList 全局配置（幂等）。"""
    from app.core import models  # noqa: F401   # 注册全部模型到 Base
    from app.business.openlist.service import seed_default_openlist_config

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as session:
        await seed_default_openlist_config(session)
