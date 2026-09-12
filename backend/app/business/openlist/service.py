"""OpenList 业务层：全局配置、预设、任务、执行管理、任务历史、配置播种。"""

from __future__ import annotations

import asyncio
import re
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.business.openlist import dir_cache
from app.business.openlist.execution_engine import run_generation, set_semaphore_size
from app.business.openlist.openlist_api import OpenListAPI
from app.business.openlist.schema import (
    OpenListConfigUpdate,
    OpenListDirExecutionBatchCreate,
    OpenListExecutionBatchCreate,
    OpenListExecutionCreate,
    OpenListServerCreate,
    OpenListServerUpdate,
    OpenListTaskCreate,
    OpenListTaskUpdate,
)
from app.business.openlist.task_status_manager import TaskStatusManager
from app.core.exceptions import BadRequestException, NotFoundException
from app.core.logger import logger
from app.core.models import (
    OpenListConfig,
    OpenListExecution,
    OpenListLog,
    OpenListServer,
    OpenListServerDir,
    OpenListTask,
)
from app.core.settings import settings

# 用户提供的默认 OpenList 服务器配置（可通过全局配置页修改）
DEFAULT_VIDEO_FORMATS = "mp4,mkv,avi,wmv,flv,mov,webm,ts"
DEFAULT_SUBTITLE_FORMATS = "srt,ass,ssa,sub,vtt"
DEFAULT_MAX_CONCURRENT = 1
DEFAULT_PAUSE_COUNT = 50
DEFAULT_PAUSE_TIME = "0,3,5"


def parse_pause_times(raw: Optional[str]) -> list[int]:
    """解析暂停时间（秒，逗号分隔）为整数列表。

    过滤非数字项；空列表或全部为 0 表示不限流（返回空列表）。
    """
    if not raw:
        return []
    values = []
    for part in str(raw).split(","):
        part = part.strip()
        if not part:
            continue
        try:
            values.append(int(part))
        except (ValueError, TypeError):
            continue
    if not values or all(v == 0 for v in values):
        return []
    return values


def execution_to_dict(execution: OpenListExecution, task: Optional[OpenListTask] = None) -> dict:
    """序列化执行记录；任务执行（无快照）时回退任务配置的处理路径/输出目录。"""
    process_path = execution.process_path or (task.process_path if task else "") or ""
    output_dir = execution.output_dir or (task.output_dir if task else "") or ""
    return {
        "id": execution.id,
        "task_id": execution.task_id,
        "task_name": execution.task_name,
        "process_path": process_path,
        "output_dir": output_dir,
        "server_id": execution.server_id,
        "server_name": execution.server_name,
        "status": execution.status,
        "video_success_count": execution.video_success_count,
        "video_total_count": execution.video_total_count,
        "subtitle_success_count": execution.subtitle_success_count,
        "subtitle_total_count": execution.subtitle_total_count,
        "is_incremental": execution.is_incremental,
        "is_force": execution.is_force,
        "strm_only": execution.strm_only,
        "strip_series": execution.strip_series,
        "duration_seconds": execution.duration_seconds,
        "log_path": execution.log_path,
        "started_time": execution.started_time.isoformat(sep=" ") if execution.started_time else None,
        "finished_time": execution.finished_time.isoformat(sep=" ") if execution.finished_time else None,
        "created_time": execution.created_time.isoformat(sep=" ") if execution.created_time else None,
    }


def task_to_dict(task: OpenListTask, last_execution: Optional[OpenListExecution] = None, server: Optional[OpenListServer] = None) -> dict:
    return {
        "id": task.id,
        "server_id": task.server_id,
        "server_url": server.server_url if server else "",
        "server_name": server.name if server else None,
        "name": task.name,
        "output_dir": task.output_dir,
        "process_path": task.process_path,
        "pause_count": task.pause_count,
        "pause_time": task.pause_time,
        "created_time": task.created_time.isoformat(sep=" ") if task.created_time else None,
        "updated_time": task.updated_time.isoformat(sep=" ") if task.updated_time else None,
        "last_execution": execution_to_dict(last_execution) if last_execution else None,
    }


async def _load_task_servers(db: AsyncSession, tasks: list[OpenListTask]) -> dict[int, OpenListServer]:
    """批量加载任务关联的服务器（server_id -> server）。"""
    server_ids = {t.server_id for t in tasks if t.server_id}
    if not server_ids:
        return {}
    result = await db.execute(select(OpenListServer).where(OpenListServer.id.in_(server_ids)))
    return {s.id: s for s in result.scalars()}


# ---------- 服务器配置 ----------

def server_to_dict(server: OpenListServer, parent_dirs: Optional[list[str]] = None) -> dict:
    return {
        "id": server.id,
        "name": server.name,
        "server_url": server.server_url,
        "parent_dirs": parent_dirs or [],
        "is_active": server.is_active,
        "has_token": bool(server.token),
    }


async def _load_server_dirs(db: AsyncSession, server_ids: list[int]) -> dict[int, list[str]]:
    """按服务器批量加载父级目录列表（不含已删除）。"""
    if not server_ids:
        return {}
    result = await db.execute(
        select(OpenListServerDir.server_id, OpenListServerDir.path)
        .where(
            OpenListServerDir.server_id.in_(server_ids),
            OpenListServerDir.is_deleted == False,  # noqa: E712
        )
        .order_by(OpenListServerDir.id)
    )
    mapping: dict[int, list[str]] = {}
    for row in result.all():
        # row: (server_id, path)
        mapping.setdefault(row[0], []).append(row[1])
    return mapping


async def list_servers(db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(OpenListServer)
        .where(OpenListServer.is_deleted == False)  # noqa: E712
        .order_by(OpenListServer.id)
    )
    servers = list(result.scalars())
    dirs_map = await _load_server_dirs(db, [s.id for s in servers])
    return [server_to_dict(s, dirs_map.get(s.id)) for s in servers]


async def get_server(db: AsyncSession, server_id: int) -> OpenListServer:
    server = await db.get(OpenListServer, server_id)
    if server is None or server.is_deleted:
        raise NotFoundException("服务器不存在")
    return server


_ILLEGAL_PATH_CHARS = set('<>:"|?*\\')


def _normalize_parent_dirs(raw: Optional[list[str]]) -> list[str]:
    """规范化父级目录：去空白、自动补 / 前缀、合并重复斜杠、去尾斜杠、去重（保持顺序）。

    用户可不写 /（如 ``emby/音乐``），统一存为 ``/emby/音乐``。
    """
    if not raw:
        return []
    seen: list[str] = []
    for item in raw:
        path = (item or "").strip()
        if not path:
            continue
        if not path.startswith("/"):
            path = "/" + path
        path = re.sub(r"/{2,}", "/", path).rstrip("/") or "/"
        if path not in seen:
            seen.append(path)
    return seen


def _validate_dir_format(path: str) -> str:
    """父级目录格式校验：无 .. 、无非法字符、无控制字符（/ 前缀由规范化阶段自动补全）。"""
    if not path:
        raise BadRequestException("父级目录不能为空")
    if ".." in path.split("/"):
        raise BadRequestException(f"父级目录不允许包含 ..：{path}")
    if any(ord(c) < 32 for c in path):
        raise BadRequestException(f"父级目录不允许包含控制字符：{path}")
    if any(c in _ILLEGAL_PATH_CHARS for c in path):
        raise BadRequestException(f"父级目录包含非法字符 <>:\"|?*\\：{path}")
    return path


async def _get_verify_ssl(db: AsyncSession) -> bool:
    """是否校验 SSL 证书：全局配置 disable_ssl_verify=True 时不校验（verify=False）。"""
    config = await _load_config(db)
    return not config.disable_ssl_verify


async def _validate_parent_dir_api(api: OpenListAPI, path: str) -> None:
    """目录有效性校验：存在性 + 读权限（list_files）+ 写权限（mkdir 临时目录后删除）。"""
    try:
        await api.list_files(path)
    except Exception as exc:
        raise BadRequestException(f"目录校验失败（{path}）：{exc}（目录不存在或无读取权限）")
    temp_path = f"{path.rstrip('/')}/.video-strm-verify-{uuid4().hex[:8]}"
    try:
        await api.create_dir(temp_path)
    except Exception as exc:
        raise BadRequestException(f"目录无写权限（{path} 下无法创建目录）：{exc}")
    try:
        await api.remove_path(temp_path)
    except Exception:
        logger.warning(f"清理校验临时目录失败（可手动删除）：{temp_path}")


async def _validate_parent_dirs(server_url: str, token: Optional[str], paths: list[str], verify_ssl: bool) -> None:
    """逐目录执行存在性 + 读写权限校验（格式校验由调用方先行完成）。"""
    if not paths:
        return
    api = OpenListAPI(server_url, token or "", verify_ssl=verify_ssl)
    for path in paths:
        await _validate_parent_dir_api(api, path)


async def _fetch_dirs(server: OpenListServer, path: str, verify_ssl: bool) -> list[dict]:
    """拉取指定路径下的一级子目录（仅 is_dir），条目含名称/路径/最后修改时间。

    存储的子目录 path 统一去掉前导 /（与父级目录拼接用）；调 OpenList API 时补回 / 前缀。
    """
    api = OpenListAPI(server.server_url, server.token or "", verify_ssl=verify_ssl)
    result = await api.list_files(f"/{path.lstrip('/')}")
    content = result.get("content") or []
    children = []
    for item in content:
        if not item.get("is_dir", False):
            continue
        name = item.get("name", "")
        item_path = item.get("path", "").strip("/") or f"{path.strip('/')}/{name}".strip("/")
        children.append({"name": name, "path": item_path, "modified": _format_modified(item.get("modified"))})
    return children


def _format_modified(ts) -> Optional[str]:
    """OpenList 返回的 modified 为毫秒时间戳，统一转 ISO 字符串；异常返回 None。"""
    if isinstance(ts, (int, float)) and ts:
        try:
            return datetime.fromtimestamp(ts / 1000).isoformat(sep=" ")
        except Exception:
            return None
    if isinstance(ts, str) and ts:
        return ts
    return None


async def list_server_dirs(db: AsyncSession, server_id: int, path: Optional[str] = None, refresh: bool = False) -> list[dict]:
    """查询服务器某路径下的一级子目录：缓存优先，miss / 过期 / refresh 时回源拉取并写缓存。

    path 缺省时回退到该服务器的第一个父级目录。
    缓存键统一去掉首尾斜杠规范化（/media/a/b 与 media/a/b 命中同一缓存）。
    """
    server = await get_server(db, server_id)
    dirs_map = await _load_server_dirs(db, [server.id])
    target = path or (dirs_map.get(server.id) or [None])[0] or "/"
    cache_key = target.strip("/") or "/"
    if not refresh:
        cached = dir_cache.get_cached(server.id, cache_key)
        if cached is not None:
            return cached
    verify_ssl = await _get_verify_ssl(db)
    children = await _fetch_dirs(server, target, verify_ssl)
    dir_cache.set_cache(server.id, cache_key, children)
    return children


async def _precache_server_dirs(db: AsyncSession, server_id: int, paths: list[str]) -> None:
    """校验通过后为每个父级目录建立一级子目录缓存（失败不影响保存，查询时按需回源）。"""
    for path in paths:
        try:
            await list_server_dirs(db, server_id, path, refresh=True)
        except Exception:
            pass


async def refresh_server_dirs_recursive(
    db: AsyncSession,
    server_id: int,
    path: Optional[str] = None,
    max_depth: int = 6,
    max_dirs: int = 500,
) -> dict:
    """递归刷新目录缓存：从指定路径（默认第一个父级目录）起逐层强制回源并覆盖缓存。

    - 同层并发拉取（信号量限流），已缓存层也强制刷新，保证数据时效
    - max_depth / max_dirs 限制请求量，防止超大目录树打爆服务器
    """
    server = await get_server(db, server_id)
    dirs_map = await _load_server_dirs(db, [server.id])
    root = path or (dirs_map.get(server.id) or [None])[0] or "/"
    sem = asyncio.Semaphore(8)

    async def fetch(dir_path: str) -> list[dict]:
        async with sem:
            return await list_server_dirs(db, server.id, dir_path, refresh=True)

    queue: deque = deque([(root, 0)])
    scanned = 0
    total_dirs = 0
    while queue and scanned < max_dirs:
        level_items = [queue.popleft() for _ in range(len(queue))]
        results = await asyncio.gather(*(fetch(p) for p, _ in level_items), return_exceptions=True)
        next_level: list[tuple[str, int]] = []
        for (dir_path, level), children in zip(level_items, results):
            if isinstance(children, Exception):
                continue
            scanned += 1
            total_dirs += len(children)
            if level + 1 <= max_depth:
                next_level.extend((child["path"], level + 1) for child in children)
        queue.extend(next_level)
    return {"count": total_dirs, "scanned": scanned, "root": root}


async def search_server_dirs(
    db: AsyncSession,
    server_id: int,
    path: str,
    keyword: str,
    depth: int = 3,
    limit: int = 50,
) -> list[dict]:
    """按关键字逐层搜索目录（BFS，缓存优先、层内并发拉取）。

    - 每层复用 list_server_dirs（已缓存层不重复请求服务器）
    - 同层目录并发拉取（信号量限流），避免串行请求导致整体超时
    - depth 限制下钻层数、MAX_SCAN 限制总扫描目录数，避免请求量爆炸
    """
    server = await get_server(db, server_id)
    kw = (keyword or "").strip().lower()
    if not kw:
        return []
    dirs_map = await _load_server_dirs(db, [server.id])
    root = path or (dirs_map.get(server.id) or [None])[0] or "/"

    matches: list[dict] = []
    current_level: list[str] = [root]
    scanned = 0
    MAX_SCAN = 300
    CONCURRENCY = 8
    sem = asyncio.Semaphore(CONCURRENCY)

    async def fetch_dirs(dir_path: str) -> list[dict]:
        async with sem:
            return await list_server_dirs(db, server.id, dir_path)

    for _ in range(depth):
        if not current_level or len(matches) >= limit or scanned >= MAX_SCAN:
            break
        batch = current_level[: MAX_SCAN - scanned]
        results = await asyncio.gather(*(fetch_dirs(d) for d in batch), return_exceptions=True)
        next_level: list[str] = []
        for children in results:
            if isinstance(children, Exception):
                continue
            scanned += 1
            for child in children:
                if kw in child["name"].lower():
                    matches.append(child)
                    if len(matches) >= limit:
                        break
                next_level.append(child["path"])
            if len(matches) >= limit:
                break
        current_level = next_level
    return matches


async def create_server(db: AsyncSession, data: OpenListServerCreate) -> dict:
    parent_dirs = _normalize_parent_dirs(data.parent_dirs)
    # 格式校验始终执行（本地可判定，不依赖服务器）；存在性/读写校验可跳过
    for path in parent_dirs:
        _validate_dir_format(path)
    if not data.skip_validation:
        verify_ssl = await _get_verify_ssl(db)
        await _validate_parent_dirs(data.server_url, data.token or None, parent_dirs, verify_ssl)
    server = OpenListServer(name=data.name, server_url=data.server_url, token=data.token or None)
    db.add(server)
    await db.flush()
    for path in parent_dirs:
        db.add(OpenListServerDir(server_id=server.id, path=path))
    await db.commit()
    await db.refresh(server)
    if parent_dirs:
        await _precache_server_dirs(db, server.id, parent_dirs)
    return server_to_dict(server, parent_dirs)


async def update_server(db: AsyncSession, server_id: int, data: OpenListServerUpdate) -> dict:
    server = await get_server(db, server_id)
    if data.name is not None:
        server.name = data.name
    if data.server_url is not None:
        server.server_url = data.server_url
    if data.token:
        server.token = data.token
    if data.is_active is not None:
        server.is_active = data.is_active

    new_dirs: Optional[list[str]] = None
    if data.parent_dirs is not None:
        new_dirs = _normalize_parent_dirs(data.parent_dirs)
        # 格式校验始终执行；存在性/读写校验可跳过
        for path in new_dirs:
            _validate_dir_format(path)
        if not data.skip_validation:
            verify_ssl = await _get_verify_ssl(db)
            await _validate_parent_dirs(server.server_url, server.token, new_dirs, verify_ssl)

    await db.commit()
    await db.refresh(server)
    # 配置变化后缓存可能失效，清空该服务器缓存；下次查询按需回源
    dir_cache.clear_server(server.id)

    if new_dirs is not None:
        old = await db.execute(
            select(OpenListServerDir).where(
                OpenListServerDir.server_id == server.id,
                OpenListServerDir.is_deleted == False,  # noqa: E712
            )
        )
        for row in old.scalars():
            row.is_deleted = True
        for path in new_dirs:
            db.add(OpenListServerDir(server_id=server.id, path=path))
        await db.commit()
        if new_dirs:
            await _precache_server_dirs(db, server.id, new_dirs)
        return server_to_dict(server, new_dirs)

    dirs_map = await _load_server_dirs(db, [server.id])
    return server_to_dict(server, dirs_map.get(server.id))


async def delete_server(db: AsyncSession, server_id: int) -> None:
    server = await get_server(db, server_id)
    server.is_deleted = True
    result = await db.execute(
        select(OpenListServerDir).where(
            OpenListServerDir.server_id == server_id,
            OpenListServerDir.is_deleted == False,  # noqa: E712
        )
    )
    for row in result.scalars():
        row.is_deleted = True
    await db.commit()
    dir_cache.clear_server(server_id)


async def add_server_parent_dirs(
    db: AsyncSession,
    server_id: int,
    parent_dirs: list[str],
    skip_validation: bool = False,
) -> dict:
    """快速追加父级目录：仅校验/新增传入的目录，不影响已有目录（含历史跳过校验保存的）。"""
    server = await get_server(db, server_id)
    new_dirs = _normalize_parent_dirs(parent_dirs)
    existing = (await _load_server_dirs(db, [server.id])).get(server.id) or []
    # 只处理真正新增的目录：已存在的目录不再重复校验/添加
    added = [p for p in new_dirs if p not in existing]
    for path in added:
        _validate_dir_format(path)
    if not skip_validation:
        verify_ssl = await _get_verify_ssl(db)
        await _validate_parent_dirs(server.server_url, server.token, added, verify_ssl)
    for path in added:
        db.add(OpenListServerDir(server_id=server.id, path=path))
    await db.commit()
    if added:
        await _precache_server_dirs(db, server.id, added)
    dirs_map = await _load_server_dirs(db, [server.id])
    return server_to_dict(server, dirs_map.get(server.id))


# ---------- 全局配置 ----------

async def _load_config(db: AsyncSession) -> OpenListConfig:
    config = await db.scalar(select(OpenListConfig).where(OpenListConfig.is_deleted == False))  # noqa: E712
    if config is None:
        config = OpenListConfig(
            server_url="", video_formats=DEFAULT_VIDEO_FORMATS,
            subtitle_formats=DEFAULT_SUBTITLE_FORMATS, max_concurrent=DEFAULT_MAX_CONCURRENT,
            pause_count=DEFAULT_PAUSE_COUNT, pause_time=DEFAULT_PAUSE_TIME,
        )
        db.add(config)
        await db.commit()
        await db.refresh(config)
    return config


async def get_config(db: AsyncSession) -> dict:
    """读取全局配置：返回服务器列表（不含 token 明文）+ 视频/字幕格式 + 并发度 + 限流 + SSL 开关。"""
    config = await _load_config(db)
    servers = await list_servers(db)
    return {
        "id": config.id,
        "servers": servers,
        "video_formats": config.video_formats or "",
        "subtitle_formats": config.subtitle_formats or "",
        "max_concurrent": config.max_concurrent or DEFAULT_MAX_CONCURRENT,
        "pause_count": config.pause_count or DEFAULT_PAUSE_COUNT,
        "pause_time": config.pause_time or DEFAULT_PAUSE_TIME,
        "disable_ssl_verify": config.disable_ssl_verify,
        "log_to_db": config.log_to_db,
        "output_dir_prefix": config.output_dir_prefix or "",
    }


async def update_config(db: AsyncSession, data: OpenListConfigUpdate) -> dict:
    """保存全局配置（视频/字幕格式 + 并发度 + 限流 + SSL 开关 + 输出前缀）；更新后调整并发信号量。"""
    config = await _load_config(db)
    if data.video_formats is not None:
        config.video_formats = data.video_formats
    if data.subtitle_formats is not None:
        config.subtitle_formats = data.subtitle_formats
    if data.max_concurrent is not None:
        config.max_concurrent = data.max_concurrent
    if data.pause_count is not None:
        config.pause_count = data.pause_count
    if data.pause_time is not None:
        config.pause_time = data.pause_time
    if data.disable_ssl_verify is not None:
        config.disable_ssl_verify = data.disable_ssl_verify
    if data.log_to_db is not None:
        config.log_to_db = data.log_to_db
    if data.output_dir_prefix is not None:
        config.output_dir_prefix = data.output_dir_prefix.strip() or None
    await db.commit()
    await db.refresh(config)
    set_semaphore_size(config.max_concurrent or DEFAULT_MAX_CONCURRENT)
    return await get_config(db)


async def get_config_for_run(db: AsyncSession, server_id: Optional[int] = None) -> dict:
    """构建 STRM 生成器所需的 camelCase 全局配置字典（含服务器信息）。

    优先按 server_id 取指定服务器的 url/token；未指定时回退取第一条启用服务器。
    限流参数（pauseCount/pauseTime）作为全局默认，任务级可在 run_generation 覆盖。
    """
    config = await _load_config(db)
    if server_id is not None:
        server = await db.scalar(
            select(OpenListServer).where(
                OpenListServer.id == server_id,
                OpenListServer.is_deleted == False,  # noqa: E712
                OpenListServer.is_active == True,  # noqa: E712
            )
        )
        if server is None:
            raise BadRequestException("所选服务器不存在或已停用")
    else:
        server = await db.scalar(
            select(OpenListServer)
            .where(OpenListServer.is_deleted == False, OpenListServer.is_active == True)  # noqa: E712
            .order_by(OpenListServer.id)
        )
        if server is None:
            raise BadRequestException("未配置可用的 OpenList 服务器")
    if not server.server_url:
        raise BadRequestException("未配置 OpenList 服务器地址")
    if not server.token:
        raise BadRequestException("未配置 OpenList Token")
    return {
        "baseUrl": server.server_url,
        "token": server.token,
        "videoExtensions": [e.strip() for e in (config.video_formats or "").split(",") if e.strip()],
        "subtitleExtensions": [e.strip() for e in (config.subtitle_formats or "").split(",") if e.strip()],
        "pauseCount": config.pause_count or DEFAULT_PAUSE_COUNT,
        "pauseTime": config.pause_time or DEFAULT_PAUSE_TIME,
        # disable_ssl_verify=True 时禁用验证（verify=False）；默认 False=校验
        "verifySsl": not config.disable_ssl_verify,
        "logToDb": config.log_to_db,
    }


# ---------- 任务 ----------

async def list_tasks(db: AsyncSession, keyword: Optional[str] = None, server_id: Optional[int] = None) -> tuple[list[dict], int]:
    stmt = select(OpenListTask).where(OpenListTask.is_deleted == False)  # noqa: E712
    if keyword:
        stmt = stmt.where(OpenListTask.name.like(f"%{keyword}%"))
    if server_id is not None:
        stmt = stmt.where(OpenListTask.server_id == server_id)
    total = await db.scalar(select(func.count(OpenListTask.id)).where(stmt.whereclause)) or 0
    result = await db.execute(
        stmt.order_by(OpenListTask.created_time.desc(), OpenListTask.id.desc())
    )
    tasks = list(result.scalars())
    last_execs = await _last_executions(db, [t.id for t in tasks])
    servers = await _load_task_servers(db, tasks)
    return [task_to_dict(t, last_execs.get(t.id), servers.get(t.server_id)) for t in tasks], total


async def _last_executions(db: AsyncSession, task_ids: list[int]) -> dict[int, OpenListExecution]:
    if not task_ids:
        return {}
    result = await db.execute(
        select(OpenListExecution)
        .where(OpenListExecution.task_id.in_(task_ids), OpenListExecution.is_deleted == False)  # noqa: E712
        .order_by(OpenListExecution.started_time.desc(), OpenListExecution.id.desc())
    )
    last: dict[int, OpenListExecution] = {}
    for ex in result.scalars():
        if ex.task_id not in last:
            last[ex.task_id] = ex
    return last


async def get_task(db: AsyncSession, task_id: int) -> OpenListTask:
    task = await db.get(OpenListTask, task_id)
    if task is None or task.is_deleted:
        raise NotFoundException("任务不存在")
    return task


async def create_task(db: AsyncSession, data: OpenListTaskCreate) -> dict:
    server = await get_server(db, data.server_id)
    task = OpenListTask(
        server_id=server.id,
        name=data.name,
        output_dir=data.output_dir,
        process_path=data.process_path,
        pause_count=data.pause_count,
        pause_time=data.pause_time,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task_to_dict(task, server=server)


async def update_task(db: AsyncSession, task_id: int, data: OpenListTaskUpdate) -> dict:
    task = await get_task(db, task_id)
    if data.name is not None:
        task.name = data.name
    if data.output_dir is not None:
        task.output_dir = data.output_dir
    if data.process_path is not None:
        task.process_path = data.process_path
    if data.pause_count is not None:
        task.pause_count = data.pause_count
    if data.pause_time is not None:
        task.pause_time = data.pause_time
    if data.server_id is not None:
        await get_server(db, data.server_id)
        task.server_id = data.server_id
    await db.commit()
    await db.refresh(task)
    server = await get_server(db, task.server_id) if task.server_id else None
    return task_to_dict(task, server=server)


async def delete_task(db: AsyncSession, task_id: int) -> None:
    task = await get_task(db, task_id)
    task.is_deleted = True
    await db.commit()


async def batch_delete_tasks(db: AsyncSession, ids: list[int]) -> None:
    """批量删除任务：先校验全部存在，再整体软删除，任一不存在则整体拒绝。"""
    if not ids:
        return
    result = await db.execute(
        select(OpenListTask).where(OpenListTask.id.in_(ids), OpenListTask.is_deleted == False)  # noqa: E712
    )
    tasks = {t.id: t for t in result.scalars()}
    missing = [i for i in ids if i not in tasks]
    if missing:
        raise NotFoundException(f"任务不存在: {missing}")
    for task in tasks.values():
        task.is_deleted = True
    await db.commit()


async def copy_task(db: AsyncSession, task_id: int) -> dict:
    task = await get_task(db, task_id)
    copy = OpenListTask(
        server_id=task.server_id,
        name=f"{task.name} - 副本",
        output_dir=task.output_dir,
        process_path=task.process_path,
        pause_count=task.pause_count,
        pause_time=task.pause_time,
    )
    db.add(copy)
    await db.commit()
    await db.refresh(copy)
    server = await get_server(db, copy.server_id) if copy.server_id else None
    return task_to_dict(copy, server=server)


# ---------- 执行管理 ----------

async def create_execution(db: AsyncSession, data: OpenListExecutionCreate) -> dict:
    """创建执行记录（仅落库，不启动后台）。返回 execution_id 供前端先连日志。"""
    task = await get_task(db, data.task_id)
    server = await get_server(db, data.server_id)
    if task.server_id is not None and task.server_id != server.id:
        raise BadRequestException("任务与所选服务器不匹配，请选择任务所属服务器执行")
    execution = OpenListExecution(
        task_id=task.id,
        task_name=task.name,
        server_id=server.id,
        server_name=server.name,
        status="running",
        is_incremental=data.is_incremental,
        is_force=data.is_force,
        strm_only=data.strm_only,
        strip_series=data.strip_series,
        started_time=datetime.now(),
    )
    db.add(execution)
    await db.commit()
    await db.refresh(execution)
    TaskStatusManager.clear(str(task.id))
    return execution_to_dict(execution)


async def batch_create_executions(db: AsyncSession, data: OpenListExecutionBatchCreate) -> list[dict]:
    """批量创建执行记录（同一服务器，多个任务），仅落库不启动。

    前端先拿到全部 execution_id 后逐条连接日志、再逐条启动，保证日志不遗漏。
    """
    await get_server(db, data.server_id)
    server_name = (await get_server(db, data.server_id)).name
    created: list[OpenListExecution] = []
    for item in data.tasks:
        task = await get_task(db, item.task_id)
        if task.server_id is not None and task.server_id != data.server_id:
            raise BadRequestException(f"任务「{task.name}」与所选服务器不匹配，请选择任务所属服务器执行")
        execution = OpenListExecution(
            task_id=task.id,
            task_name=task.name,
            server_id=data.server_id,
            server_name=server_name,
            status="running",
            is_incremental=item.is_incremental,
            is_force=item.is_force,
            strm_only=item.strm_only,
            strip_series=item.strip_series,
            started_time=datetime.now(),
        )
        db.add(execution)
        created.append(execution)
    # 整体提交：任一任务不存在则全部回滚，避免遗留孤儿 running 记录
    await db.commit()
    for execution in created:
        await db.refresh(execution)
        TaskStatusManager.clear(str(execution.task_id))
    return [execution_to_dict(e) for e in created]


async def batch_create_dir_executions(db: AsyncSession, data: OpenListDirExecutionBatchCreate) -> list[dict]:
    """批量创建目录执行记录（同一服务器，多个目录），仅落库不启动。

    与任务执行不同：不创建/关联任务记录，execution.task_id 固定为 0，
    执行参数（process_path/output_dir）以快照冗余存储，取消键使用 execution_id。
    """
    server = await get_server(db, data.server_id)
    created: list[OpenListExecution] = []
    for item in data.dirs:
        execution = OpenListExecution(
            task_id=0,
            task_name=Path(item.path).name or item.path,
            process_path=item.path,
            output_dir=item.output_dir,
            server_id=server.id,
            server_name=server.name,
            status="running",
            is_incremental=data.is_incremental,
            is_force=data.is_force,
            strm_only=data.strm_only,
            started_time=datetime.now(),
        )
        db.add(execution)
        created.append(execution)
    await db.commit()
    for execution in created:
        await db.refresh(execution)
        TaskStatusManager.clear(str(execution.id))
    return [execution_to_dict(e) for e in created]


async def start_execution(db: AsyncSession, execution_id: int, task_id: int, server_id: int) -> dict:
    """启动已创建的执行记录：校验记录存在且仍为 running，按 server_id 加载配置后拉起后台任务。

    只有处于 running 且尚未被启动过的记录才能启动；重复调用直接报错，防止
    前端并发/重复点击导致同一执行被启动多次。
    目录执行（task_id=0）使用 process_path/output_dir 快照启动，不查任务表。
    """
    execution = await db.get(OpenListExecution, execution_id)
    if execution is None or execution.is_deleted:
        raise NotFoundException("执行记录不存在")
    if execution.task_id != task_id:
        raise BadRequestException("执行记录与任务不匹配")
    if execution.status != "running":
        raise BadRequestException("执行记录不可启动，当前状态: " + execution.status)

    global_config = await get_config_for_run(db, server_id)

    if execution.process_path:
        # 目录执行：快照路径 + 取消键为 execution_id
        process_path = execution.process_path
        output_dir = execution.output_dir or ""
        pause_count: Optional[int] = None
        pause_time: Optional[str] = None
        cancel_key = str(execution.id)
    else:
        task = await get_task(db, task_id)
        if task.server_id is not None and task.server_id != server_id:
            raise BadRequestException("任务与所选服务器不匹配，请选择任务所属服务器执行")
        process_path = task.process_path
        output_dir = task.output_dir
        pause_count = task.pause_count
        pause_time = task.pause_time
        cancel_key = None

    # 防重复启动：以 status 为唯一启动标记，先置为启动中再提交
    execution.started_time = datetime.now()
    await db.commit()

    asyncio.create_task(
        run_generation(
            execution_id=execution.id,
            task_id=task_id,
            output_dir=output_dir,
            process_path=process_path,
            is_force=execution.is_force,
            global_config=global_config,
            pause_count=pause_count,
            pause_time=pause_time,
            strm_only=execution.strm_only,
            strip_series=execution.strip_series,
            cancel_key=cancel_key,
        )
    )
    return execution_to_dict(execution)


async def cancel_execution(db: AsyncSession, execution_id: int) -> dict:
    execution = await db.get(OpenListExecution, execution_id)
    if execution is None or execution.is_deleted:
        raise NotFoundException("执行记录不存在")
    if execution.status != "running":
        return {"cancelled": False, "status": execution.status}
    # 目录执行（task_id=0）以 execution_id 为取消键，任务执行使用 task_id
    cancel_key = str(execution.id) if execution.task_id == 0 else str(execution.task_id)
    TaskStatusManager.cancel(cancel_key)
    return {"cancelled": True, "status": "cancelled"}


# ---------- 任务历史 ----------

async def list_executions(
    db: AsyncSession,
    task_id: Optional[int] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict], int]:
    stmt = select(OpenListExecution).where(OpenListExecution.is_deleted == False)  # noqa: E712
    if task_id is not None:
        stmt = stmt.where(OpenListExecution.task_id == task_id)
    if status:
        stmt = stmt.where(OpenListExecution.status == status)
    total = await db.scalar(select(func.count(OpenListExecution.id)).where(stmt.whereclause)) or 0
    result = await db.execute(
        stmt.order_by(OpenListExecution.started_time.desc(), OpenListExecution.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    executions = list(result.scalars())
    # 任务执行记录无路径快照：批量回退任务配置的处理路径/输出目录
    task_ids = {ex.task_id for ex in executions if ex.task_id and not ex.process_path}
    tasks: dict[int, OpenListTask] = {}
    if task_ids:
        task_result = await db.execute(select(OpenListTask).where(OpenListTask.id.in_(task_ids)))
        tasks = {t.id: t for t in task_result.scalars()}
    return [execution_to_dict(ex, tasks.get(ex.task_id)) for ex in executions], total


async def history_summary(db: AsyncSession, server_id: Optional[int] = None) -> list[dict]:
    """默认视图：每个任务最近一次执行 + 目录执行（task_id=0）最近一次执行（可按服务器筛选）。"""
    stmt = select(OpenListTask).where(OpenListTask.is_deleted == False)  # noqa: E712
    if server_id is not None:
        stmt = stmt.where(OpenListTask.server_id == server_id)
    result = await db.execute(stmt.order_by(OpenListTask.created_time.desc(), OpenListTask.id.desc()))
    tasks = list(result.scalars())
    task_ids = [t.id for t in tasks]
    last = await _last_executions(db, task_ids)
    items = [
        {
            "task_id": t.id,
            "task_name": t.name,
            "output_dir": t.output_dir,
            "process_path": t.process_path,
            "execution": execution_to_dict(last[t.id]) if t.id in last else None,
        }
        for t in tasks
    ]
    # 目录执行（task_id=0）：聚合展示最近一次，点击详情查看全部目录执行记录
    last_dir_execution = await db.scalar(
        select(OpenListExecution)
        .where(OpenListExecution.task_id == 0, OpenListExecution.is_deleted == False)  # noqa: E712
        .order_by(OpenListExecution.started_time.desc(), OpenListExecution.id.desc())
        .limit(1)
    )
    if last_dir_execution is not None:
        items.insert(
            0,
            {
                "task_id": 0,
                "task_name": "目录执行",
                "output_dir": last_dir_execution.output_dir or "",
                "process_path": last_dir_execution.process_path or "",
                "execution": execution_to_dict(last_dir_execution),
            },
        )
    return items


_LOG_LINE_RE = re.compile(r"^\[([^\]]*)\] \[([A-Z]+)\] (.*)$", re.DOTALL)


def _read_log_file(execution_id: int, offset: int = 0, limit: int = 200) -> Optional[list[dict]]:
    """读取执行日志文件（execution_{id}.log），按 offset/limit 分页。

    行格式 `[ts] [LEVEL] message` → {log_level, content, created_time}。
    文件不存在/不可读返回 None（调用方回退 DB）。
    """
    path = Path(settings.openlist_log_dir) / f"execution_{execution_id}.log"
    try:
        if not path.is_file():
            return None
        with open(path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except Exception:
        return None
    items = []
    for line in lines[offset : offset + limit]:
        m = _LOG_LINE_RE.match(line)
        if not m:
            continue
        ts, level, message = m.group(1), m.group(2).lower(), m.group(3)
        items.append(
            {
                "log_level": level,
                "content": message,
                "created_time": ts or None,
            }
        )
    return items


def _log_file_total(execution_id: int) -> Optional[int]:
    """读取日志文件行数；文件缺失返回 None。"""
    path = Path(settings.openlist_log_dir) / f"execution_{execution_id}.log"
    try:
        if not path.is_file():
            return None
        with open(path, "r", encoding="utf-8") as f:
            return sum(1 for _ in f)
    except Exception:
        return None


async def get_execution_detail(db: AsyncSession, execution_id: int) -> dict:
    execution = await db.get(OpenListExecution, execution_id)
    if execution is None or execution.is_deleted:
        raise NotFoundException("执行记录不存在")
    # 优先读日志文件（文件是唯一权威源）；文件缺失回退 DB（兼容旧数据）
    file_logs = _read_log_file(execution_id, 0, 500)
    if file_logs is not None:
        return {
            "execution": execution_to_dict(execution),
            "logs": [{"id": i + 1, **item} for i, item in enumerate(file_logs)],
        }
    logs = await db.execute(
        select(OpenListLog)
        .where(OpenListLog.execution_id == execution_id)
        .order_by(OpenListLog.id)
        .limit(500)
    )
    return {
        "execution": execution_to_dict(execution),
        "logs": [
            {
                "id": log.id,
                "log_level": log.log_level,
                "content": log.content,
                "created_time": log.created_time.isoformat(sep=" ") if log.created_time else None,
            }
            for log in logs.scalars()
        ],
    }


async def list_execution_logs(
    db: AsyncSession, execution_id: int, page: int = 1, page_size: int = 200
) -> tuple[list[dict], int]:
    # 优先读日志文件分页；文件缺失回退 DB（兼容旧数据）
    offset = (page - 1) * page_size
    file_logs = _read_log_file(execution_id, offset, page_size)
    if file_logs is not None:
        total = _log_file_total(execution_id) or 0
        return [{"id": offset + i + 1, **item} for i, item in enumerate(file_logs)], total
    stmt = select(OpenListLog).where(OpenListLog.execution_id == execution_id)
    total = await db.scalar(select(func.count(OpenListLog.id)).where(stmt.whereclause)) or 0
    result = await db.execute(stmt.order_by(OpenListLog.id).offset(offset).limit(page_size))
    return [
        {
            "id": log.id,
            "log_level": log.log_level,
            "content": log.content,
            "created_time": log.created_time.isoformat(sep=" ") if log.created_time else None,
        }
        for log in result.scalars()
    ], total


async def get_recent_log_lines(execution_id: int, limit: int = 200) -> list[dict]:
    """WebSocket 重连时回放最近的日志帧（优先读文件末尾）。"""
    # 文件为主：读取末尾 limit 行（tail 语义）
    path = Path(settings.openlist_log_dir) / f"execution_{execution_id}.log"
    try:
        if path.is_file():
            with open(path, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()
            tail = lines[-limit:]
            frames = []
            for line in tail:
                m = _LOG_LINE_RE.match(line)
                if not m:
                    continue
                ts, level, message = m.group(1), m.group(2).lower(), m.group(3)
                frames.append({"type": "log", "level": level, "message": message, "ts": ts or None})
            return frames
    except Exception:
        pass
    # 文件缺失回退 DB
    try:
        from app.core.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(OpenListLog)
                .where(OpenListLog.execution_id == execution_id)
                .order_by(OpenListLog.id.desc())
                .limit(limit)
            )
            logs = list(result.scalars())[::-1]
            return [
                {
                    "type": "log",
                    "level": log.log_level,
                    "message": log.content,
                    "ts": log.created_time.isoformat(sep=" ") if log.created_time else None,
                }
                for log in logs
            ]
    except Exception:
        return []


# ---------- 播种 ----------

async def seed_default_openlist_config(db: AsyncSession) -> bool:
    """幂等插入默认 OpenList 全局配置（视频/字幕格式 + 并发度）。不预置任何服务器。"""
    changed = False
    config = await db.scalar(select(OpenListConfig).where(OpenListConfig.is_deleted == False))  # noqa: E712
    if config is None:
        config = OpenListConfig(
            server_url="",
            video_formats=DEFAULT_VIDEO_FORMATS,
            subtitle_formats=DEFAULT_SUBTITLE_FORMATS,
            max_concurrent=DEFAULT_MAX_CONCURRENT,
            pause_count=DEFAULT_PAUSE_COUNT,
            pause_time=DEFAULT_PAUSE_TIME,
        )
        db.add(config)
        changed = True
    if changed:
        await db.commit()
    return changed
