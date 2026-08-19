"""video-strm 测试环境：SQLite 文件库（每测试重建表，数据隔离）。

用法（在 backend/ 下）：
    python -m pytest -v
"""

import sys
from pathlib import Path

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.main as main_app  # noqa: E402
from app.core import database as db_module  # noqa: E402
from app.core import models  # noqa: E402, F401   # 注册全部模型到 Base

TEST_DB = Path(__file__).resolve().parent / ".test-data" / "test.db"


@pytest_asyncio.fixture(scope="session", autouse=True)
async def prepare_environment():
    TEST_DB.parent.mkdir(parents=True, exist_ok=True)
    # NullPool：pytest-asyncio 每个测试独立事件循环，池化连接跨循环复用会报错
    engine = create_async_engine(f"sqlite+aiosqlite:///{TEST_DB}", poolclass=NullPool)
    session = async_sessionmaker(bind=engine, expire_on_commit=False)
    db_module.engine = engine
    db_module.AsyncSessionLocal = session
    yield
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def reset_db():
    """每个测试前重建全部表，保证用例间数据隔离。"""
    async with db_module.engine.begin() as conn:
        await conn.run_sync(db_module.Base.metadata.drop_all)
        await conn.run_sync(db_module.Base.metadata.create_all)
    yield


@pytest_asyncio.fixture
async def client():
    """带 lifespan（自动建表 + seed 默认全局配置）的异步测试客户端。"""
    transport = ASGITransport(app=main_app.app)
    async with main_app.app.router.lifespan_context(main_app.app):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
