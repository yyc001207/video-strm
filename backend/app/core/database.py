"""SQLite 异步数据库：启动时自动建表 + 种子数据（本地部署，无需 Alembic 迁移）。"""

from pathlib import Path

from sqlalchemy import text
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


async def _ensure_config_columns() -> None:
    """轻量列级迁移：create_all 不会为已存在的表补列，这里用 PRAGMA 检查后 ALTER 补齐新字段。

    SQLite 支持 ADD COLUMN，追加可空列即可；新库由 create_all 直接建好，此函数自动跳过。
    """
    new_columns = {
        "process_path_prefix": "VARCHAR(128)",
        "output_dir_prefix": "VARCHAR(128)",
    }
    async with engine.begin() as conn:
        result = await conn.execute(text("PRAGMA table_info(open_list_config)"))
        existing = {row[1] for row in result}
        for column, ddl in new_columns.items():
            if column not in existing:
                await conn.execute(text(f"ALTER TABLE open_list_config ADD COLUMN {column} {ddl}"))


async def init_db() -> None:
    """建表、轻量迁移并写入默认 OpenList 全局配置（幂等）。"""
    from app.core import models  # noqa: F401   # 注册全部模型到 Base
    from app.business.openlist.service import seed_default_openlist_config

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _ensure_config_columns()
    async with AsyncSessionLocal() as session:
        await seed_default_openlist_config(session)
