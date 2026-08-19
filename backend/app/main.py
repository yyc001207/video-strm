"""video-strm API：OpenList 任务调度独立服务（本地部署，无登录/无 Redis/MySQL）。"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.settings import settings
from app.core.database import init_db
from app.core.exceptions import NavlyException
from app.utils.responses import success_response
from app.api import openlist


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="video-strm API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    msg = first.get("msg", "参数错误")
    return JSONResponse(
        status_code=200,
        content={"code": 400, "msg": msg, "data": None},
    )


@app.exception_handler(NavlyException)
async def navly_exception_handler(request: Request, exc: NavlyException):
    return JSONResponse(
        status_code=200,
        content={"code": exc.code, "msg": exc.msg, "data": None},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=200,
        content={"code": 500, "msg": "服务器内部错误", "data": None},
    )


app.include_router(openlist.router, prefix="/api/openlist", tags=["OpenList"])


@app.get("/api/health")
async def health_check():
    return success_response(data={"status": "ok"})


# 前端构建产物目录：backend/app/main.py → backend/frontend/dist（Docker 镜像内为 /app/frontend/dist）
DIST_DIR = Path(__file__).resolve().parents[1] / "frontend" / "dist"


def mount_frontend() -> None:
    """存在前端构建产物时托管静态资源并做 SPA 回退；本地纯后端开发（未构建前端）时自动跳过。"""

    if not DIST_DIR.is_dir():
        return

    assets_dir = DIST_DIR / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    index_file = DIST_DIR / "index.html"

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        # API / 文档路由未命中时保持 404，不返回前端页面
        if full_path.startswith("api/") or full_path in {"docs", "redoc", "openapi.json"}:
            raise HTTPException(status_code=404, detail="Not Found")
        target = (DIST_DIR / full_path).resolve()
        if full_path and target.is_file() and target.is_relative_to(DIST_DIR.resolve()):
            return FileResponse(target)
        if index_file.is_file():
            return FileResponse(index_file)
        raise HTTPException(status_code=404, detail="Not Found")


mount_frontend()
