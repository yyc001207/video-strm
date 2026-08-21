"""OpenList 业务层：全局配置、预设、任务、执行管理、任务历史、配置播种。"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.business.openlist.execution_engine import run_generation, set_semaphore_size
from app.business.openlist.schema import (
    OpenListConfigUpdate,
    OpenListExecutionBatchCreate,
    OpenListExecutionCreate,
    OpenListPresetCreate,
    OpenListPresetUpdate,
    OpenListServerCreate,
    OpenListServerUpdate,
    OpenListTaskCreate,
    OpenListTaskUpdate,
)
from app.business.openlist.task_status_manager import TaskStatusManager
from app.core.exceptions import BadRequestException, NotFoundException
from app.core.models import (
    OpenListConfig,
    OpenListExecution,
    OpenListLog,
    OpenListPreset,
    OpenListServer,
    OpenListTask,
)
from app.core.settings import settings

# 用户提供的默认 OpenList 服务器配置（可通过全局配置页修改）
DEFAULT_SERVER_URL = "http://192.168.199.238:5244"
DEFAULT_TOKEN = "openlist-1395546b-a0b2-48ba-9b56-bc495bdb7f32XikIcYkGh4WcY6MLBWuDwaRT20ryKWqXH9F81rX6rRKMGZuEnZhwQXnRstzmt7yH"
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


def execution_to_dict(execution: OpenListExecution) -> dict:
    return {
        "id": execution.id,
        "task_id": execution.task_id,
        "task_name": execution.task_name,
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
        "duration_seconds": execution.duration_seconds,
        "log_path": execution.log_path,
        "started_time": execution.started_time.isoformat(sep=" ") if execution.started_time else None,
        "finished_time": execution.finished_time.isoformat(sep=" ") if execution.finished_time else None,
        "created_time": execution.created_time.isoformat(sep=" ") if execution.created_time else None,
    }


def task_to_dict(task: OpenListTask, last_execution: Optional[OpenListExecution] = None) -> dict:
    return {
        "id": task.id,
        "name": task.name,
        "output_dir": task.output_dir,
        "process_path": task.process_path,
        "pause_count": task.pause_count,
        "pause_time": task.pause_time,
        "created_time": task.created_time.isoformat(sep=" ") if task.created_time else None,
        "updated_time": task.updated_time.isoformat(sep=" ") if task.updated_time else None,
        "last_execution": execution_to_dict(last_execution) if last_execution else None,
    }


# ---------- 服务器配置 ----------

def server_to_dict(server: OpenListServer) -> dict:
    return {
        "id": server.id,
        "name": server.name,
        "server_url": server.server_url,
        "is_active": server.is_active,
        "has_token": bool(server.token),
    }


async def list_servers(db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(OpenListServer)
        .where(OpenListServer.is_deleted == False)  # noqa: E712
        .order_by(OpenListServer.id)
    )
    return [server_to_dict(s) for s in result.scalars()]


async def get_server(db: AsyncSession, server_id: int) -> OpenListServer:
    server = await db.get(OpenListServer, server_id)
    if server is None or server.is_deleted:
        raise NotFoundException("服务器不存在")
    return server


async def create_server(db: AsyncSession, data: OpenListServerCreate) -> dict:
    server = OpenListServer(name=data.name, server_url=data.server_url, token=data.token or None)
    db.add(server)
    await db.commit()
    await db.refresh(server)
    return server_to_dict(server)


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
    await db.commit()
    await db.refresh(server)
    return server_to_dict(server)


async def delete_server(db: AsyncSession, server_id: int) -> None:
    server = await get_server(db, server_id)
    server.is_deleted = True
    await db.commit()


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
        "process_path_prefix": config.process_path_prefix or "",
        "output_dir_prefix": config.output_dir_prefix or "",
    }


async def update_config(db: AsyncSession, data: OpenListConfigUpdate) -> dict:
    """保存全局配置（视频/字幕格式 + 并发度 + 限流 + SSL 开关 + 前缀）；更新后调整并发信号量。"""
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
    if data.process_path_prefix is not None:
        config.process_path_prefix = data.process_path_prefix.strip() or None
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


# ---------- 预设 ----------

async def list_presets(db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(OpenListPreset)
        .where(OpenListPreset.is_deleted == False)  # noqa: E712
        .order_by(OpenListPreset.sort_order, OpenListPreset.id)
    )
    return [
        {
            "id": p.id,
            "name": p.name,
            "preset_path": p.preset_path,
            "sort_order": p.sort_order,
            "created_time": p.created_time.isoformat(sep=" ") if p.created_time else None,
        }
        for p in result.scalars()
    ]


async def create_preset(db: AsyncSession, data: OpenListPresetCreate) -> dict:
    preset = OpenListPreset(name=data.name, preset_path=data.preset_path, sort_order=data.sort_order)
    db.add(preset)
    await db.commit()
    await db.refresh(preset)
    return {
        "id": preset.id,
        "name": preset.name,
        "preset_path": preset.preset_path,
        "sort_order": preset.sort_order,
    }


async def update_preset(db: AsyncSession, preset_id: int, data: OpenListPresetUpdate) -> dict:
    preset = await db.get(OpenListPreset, preset_id)
    if preset is None or preset.is_deleted:
        raise NotFoundException("预设不存在")
    if data.name is not None:
        preset.name = data.name
    if data.preset_path is not None:
        preset.preset_path = data.preset_path
    if data.sort_order is not None:
        preset.sort_order = data.sort_order
    await db.commit()
    await db.refresh(preset)
    return {"id": preset.id, "name": preset.name, "preset_path": preset.preset_path, "sort_order": preset.sort_order}


async def delete_preset(db: AsyncSession, preset_id: int) -> None:
    preset = await db.get(OpenListPreset, preset_id)
    if preset is None or preset.is_deleted:
        raise NotFoundException("预设不存在")
    preset.is_deleted = True
    await db.commit()


async def batch_delete_presets(db: AsyncSession, ids: list[int]) -> None:
    """批量删除预设：先校验全部存在，再整体软删除，任一不存在则整体拒绝。"""
    if not ids:
        return
    result = await db.execute(
        select(OpenListPreset).where(OpenListPreset.id.in_(ids), OpenListPreset.is_deleted == False)  # noqa: E712
    )
    presets = {p.id: p for p in result.scalars()}
    missing = [i for i in ids if i not in presets]
    if missing:
        raise NotFoundException(f"预设不存在: {missing}")
    for preset in presets.values():
        preset.is_deleted = True
    await db.commit()


async def reorder_presets(db: AsyncSession, ids: list[int]) -> None:
    presets = await db.execute(select(OpenListPreset).where(OpenListPreset.id.in_(ids)))
    by_id = {p.id: p for p in presets.scalars()}
    for order, preset_id in enumerate(ids):
        preset = by_id.get(preset_id)
        if preset is not None:
            preset.sort_order = order
    await db.commit()


# ---------- 任务 ----------

async def list_tasks(db: AsyncSession, keyword: Optional[str] = None) -> tuple[list[dict], int]:
    stmt = select(OpenListTask).where(OpenListTask.is_deleted == False)  # noqa: E712
    if keyword:
        stmt = stmt.where(OpenListTask.name.like(f"%{keyword}%"))
    total = await db.scalar(select(func.count(OpenListTask.id)).where(stmt.whereclause)) or 0
    result = await db.execute(
        stmt.order_by(OpenListTask.created_time.desc(), OpenListTask.id.desc())
    )
    tasks = list(result.scalars())
    last_execs = await _last_executions(db, [t.id for t in tasks])
    return [task_to_dict(t, last_execs.get(t.id)) for t in tasks], total


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
    task = OpenListTask(
        name=data.name,
        output_dir=data.output_dir,
        process_path=data.process_path,
        pause_count=data.pause_count,
        pause_time=data.pause_time,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task_to_dict(task)


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
    await db.commit()
    await db.refresh(task)
    return task_to_dict(task)


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
        name=f"{task.name} - 副本",
        output_dir=task.output_dir,
        process_path=task.process_path,
        pause_count=task.pause_count,
        pause_time=task.pause_time,
    )
    db.add(copy)
    await db.commit()
    await db.refresh(copy)
    return task_to_dict(copy)


# ---------- 执行管理 ----------

async def create_execution(db: AsyncSession, data: OpenListExecutionCreate) -> dict:
    """创建执行记录（仅落库，不启动后台）。返回 execution_id 供前端先连日志。"""
    task = await get_task(db, data.task_id)
    server = await get_server(db, data.server_id)
    execution = OpenListExecution(
        task_id=task.id,
        task_name=task.name,
        server_id=server.id,
        server_name=server.name,
        status="running",
        is_incremental=data.is_incremental,
        is_force=data.is_force,
        strm_only=data.strm_only,
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
        execution = OpenListExecution(
            task_id=task.id,
            task_name=task.name,
            server_id=data.server_id,
            server_name=server_name,
            status="running",
            is_incremental=item.is_incremental,
            is_force=item.is_force,
            strm_only=item.strm_only,
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


async def start_execution(db: AsyncSession, execution_id: int, task_id: int, server_id: int) -> dict:
    """启动已创建的执行记录：校验记录存在且仍为 running，按 server_id 加载配置后拉起后台任务。

    只有处于 running 且尚未被启动过的记录才能启动；重复调用直接报错，防止
    前端并发/重复点击导致同一执行被启动多次。
    """
    execution = await db.get(OpenListExecution, execution_id)
    if execution is None or execution.is_deleted:
        raise NotFoundException("执行记录不存在")
    if execution.task_id != task_id:
        raise BadRequestException("执行记录与任务不匹配")
    if execution.status != "running":
        raise BadRequestException("执行记录不可启动，当前状态: " + execution.status)

    task = await get_task(db, task_id)
    global_config = await get_config_for_run(db, server_id)

    # 防重复启动：以 status 为唯一启动标记，先置为启动中再提交
    execution.started_time = datetime.now()
    await db.commit()

    asyncio.create_task(
        run_generation(
            execution_id=execution.id,
            task_id=task.id,
            output_dir=task.output_dir,
            process_path=task.process_path,
            is_force=execution.is_force,
            global_config=global_config,
            pause_count=task.pause_count,
            pause_time=task.pause_time,
            strm_only=execution.strm_only,
        )
    )
    return execution_to_dict(execution)


async def cancel_execution(db: AsyncSession, execution_id: int) -> dict:
    execution = await db.get(OpenListExecution, execution_id)
    if execution is None or execution.is_deleted:
        raise NotFoundException("执行记录不存在")
    if execution.status != "running":
        return {"cancelled": False, "status": execution.status}
    TaskStatusManager.cancel(str(execution.task_id))
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
    return [execution_to_dict(ex) for ex in result.scalars()], total


async def history_summary(db: AsyncSession) -> list[dict]:
    """默认视图：每个任务最近一次执行。"""
    result = await db.execute(
        select(OpenListTask)
        .where(OpenListTask.is_deleted == False)  # noqa: E712
        .order_by(OpenListTask.created_time.desc(), OpenListTask.id.desc())
    )
    tasks = list(result.scalars())
    task_ids = [t.id for t in tasks]
    last = await _last_executions(db, task_ids)
    return [
        {
            "task_id": t.id,
            "task_name": t.name,
            "output_dir": t.output_dir,
            "process_path": t.process_path,
            "execution": execution_to_dict(last[t.id]) if t.id in last else None,
        }
        for t in tasks
    ]


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
    """幂等插入默认 OpenList 全局配置（视频/字幕格式 + 并发度）与默认服务器。"""
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
    server = await db.scalar(
        select(OpenListServer).where(OpenListServer.is_deleted == False).order_by(OpenListServer.id)  # noqa: E712
    )
    if server is None:
        db.add(
            OpenListServer(
                name="默认服务器",
                server_url=DEFAULT_SERVER_URL,
                token=DEFAULT_TOKEN,
                is_active=True,
            )
        )
        changed = True
    if changed:
        await db.commit()
    return changed
