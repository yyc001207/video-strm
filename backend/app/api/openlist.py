"""OpenList 路由：全局配置 / 预设 / 任务 / 执行管理 / 任务历史 / 实时日志（WebSocket）。

注意：FastAPI 按注册顺序匹配路径，``/presets/{preset_id}``、``/tasks/{task_id}``
等参数化路由必须排在 ``/presets/delete``、``/tasks/copy`` 等字面量路由之后，
否则 ``copy``/``delete`` 会被当作 id 解析而报 422。

实时日志下载端点返回纯文本，流式响应无 {code,msg,data} 包裹，供前端 blob 下载。
"""

from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.business.openlist import service
from app.business.openlist.schema import (
    OpenListBatchDeleteRequest,
    OpenListConfigUpdate,
    OpenListExecutionBatchCreate,
    OpenListExecutionCancel,
    OpenListExecutionCreate,
    OpenListExecutionStart,
    OpenListPresetCreate,
    OpenListPresetUpdate,
    OpenListServerCreate,
    OpenListServerUpdate,
    OpenListTaskCreate,
    OpenListTaskUpdate,
)
from app.core.database import get_db
from app.core.exceptions import BadRequestException, NotFoundException
from app.core.models import OpenListExecution, OpenListLog
from app.utils.responses import success_response
from app.websocket.manager import ws_manager

router = APIRouter()


# ---------- 全局配置 ----------

@router.get("/config", summary="OpenList 全局配置")
async def get_config(
    db: AsyncSession = Depends(get_db),
):
    return success_response(data=await service.get_config(db))


@router.post("/config", summary="保存 OpenList 全局配置")
async def update_config(
    data: OpenListConfigUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await service.update_config(db, data)
    return success_response(data=result)


# ---------- 服务器 ----------
# 字面量路由（delete）先于 /servers/{id} 注册

@router.get("/servers", summary="服务器配置列表")
async def list_servers(
    db: AsyncSession = Depends(get_db),
):
    return success_response(data={"list": await service.list_servers(db)})


@router.post("/servers", summary="创建服务器配置")
async def create_server(
    data: OpenListServerCreate,
    db: AsyncSession = Depends(get_db),
):
    return success_response(data=await service.create_server(db, data))


@router.post("/servers/delete", summary="删除服务器配置")
async def delete_server(
    payload: dict,
    db: AsyncSession = Depends(get_db),
):
    server_id = payload.get("id")
    if server_id is None:
        raise BadRequestException("缺少 id")
    await service.delete_server(db, server_id)
    return success_response(data=None)


@router.post("/servers/{server_id}", summary="更新服务器配置")
async def update_server(
    server_id: int,
    data: OpenListServerUpdate,
    db: AsyncSession = Depends(get_db),
):
    return success_response(data=await service.update_server(db, server_id, data))


# ---------- 预设 ----------
# 字面量路由（delete/reorder）先于 /presets/{preset_id} 注册

@router.get("/presets", summary="预设列表")
async def list_presets(
    db: AsyncSession = Depends(get_db),
):
    return success_response(data={"list": await service.list_presets(db)})


@router.post("/presets", summary="创建预设")
async def create_preset(
    data: OpenListPresetCreate,
    db: AsyncSession = Depends(get_db),
):
    return success_response(data=await service.create_preset(db, data))


@router.post("/presets/delete", summary="删除预设")
async def delete_preset(
    payload: dict,
    db: AsyncSession = Depends(get_db),
):
    preset_id = payload.get("id")
    if preset_id is None:
        raise BadRequestException("缺少 id")
    await service.delete_preset(db, preset_id)
    return success_response(data=None)


@router.post("/presets/batch-delete", summary="批量删除预设")
async def batch_delete_presets(
    data: OpenListBatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    await service.batch_delete_presets(db, data.ids)
    return success_response(data=None)


@router.post("/presets/reorder", summary="预设排序")
async def reorder_presets(
    payload: dict,
    db: AsyncSession = Depends(get_db),
):
    ids = payload.get("ids") or []
    await service.reorder_presets(db, [int(i) for i in ids])
    return success_response(data=None)


@router.post("/presets/{preset_id}", summary="更新预设")
async def update_preset(
    preset_id: int,
    data: OpenListPresetUpdate,
    db: AsyncSession = Depends(get_db),
):
    return success_response(data=await service.update_preset(db, preset_id, data))


# ---------- 任务 ----------
# 字面量路由（delete/copy）先于 /tasks/{task_id} 注册

@router.get("/tasks", summary="任务列表（含最近一次执行）")
async def list_tasks(
    keyword: Optional[str] = Query(default=None, max_length=128),
    db: AsyncSession = Depends(get_db),
):
    items, total = await service.list_tasks(db, keyword)
    return success_response(data={"list": items}, total=total)


@router.post("/tasks", summary="创建任务")
async def create_task(
    data: OpenListTaskCreate,
    db: AsyncSession = Depends(get_db),
):
    return success_response(data=await service.create_task(db, data))


@router.post("/tasks/delete", summary="删除任务")
async def delete_task(
    payload: dict,
    db: AsyncSession = Depends(get_db),
):
    task_id = payload.get("id")
    if task_id is None:
        raise BadRequestException("缺少 id")
    await service.delete_task(db, task_id)
    return success_response(data=None)


@router.post("/tasks/batch-delete", summary="批量删除任务")
async def batch_delete_tasks(
    data: OpenListBatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    await service.batch_delete_tasks(db, data.ids)
    return success_response(data=None)


@router.post("/tasks/copy", summary="复制任务")
async def copy_task(
    payload: dict,
    db: AsyncSession = Depends(get_db),
):
    task_id = payload.get("id")
    if task_id is None:
        raise BadRequestException("缺少 id")
    return success_response(data=await service.copy_task(db, task_id))


@router.get("/tasks/{task_id}", summary="任务详情")
async def get_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
):
    return success_response(data=await service.get_task(db, task_id))


@router.post("/tasks/{task_id}", summary="更新任务")
async def update_task(
    task_id: int,
    data: OpenListTaskUpdate,
    db: AsyncSession = Depends(get_db),
):
    return success_response(data=await service.update_task(db, task_id, data))


# ---------- 执行管理 ----------

@router.post("/executions", summary="创建执行记录（仅落库，不启动）")
async def create_execution(
    data: OpenListExecutionCreate,
    db: AsyncSession = Depends(get_db),
):
    return success_response(data=await service.create_execution(db, data))


@router.post("/executions/batch", summary="批量创建执行记录（同一服务器多任务，仅落库）")
async def batch_create_executions(
    data: OpenListExecutionBatchCreate,
    db: AsyncSession = Depends(get_db),
):
    results = await service.batch_create_executions(db, data)
    return success_response(data={"list": results})


@router.post("/executions/start", summary="启动已创建的执行记录")
async def start_execution(
    data: OpenListExecutionStart,
    db: AsyncSession = Depends(get_db),
):
    execution = await service.start_execution(db, data.execution_id, data.task_id, data.server_id)
    return success_response(data=execution)


@router.post("/executions/cancel", summary="取消任务执行")
async def cancel_execution(
    data: OpenListExecutionCancel,
    db: AsyncSession = Depends(get_db),
):
    return success_response(data=await service.cancel_execution(db, data.execution_id))


@router.get("/executions", summary="执行记录列表（分页）")
async def list_executions(
    task_id: Optional[int] = Query(default=None),
    status: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    items, total = await service.list_executions(db, task_id, status, page, pageSize)
    return success_response(data={"list": items}, total=total)


@router.get("/executions/{execution_id}", summary="执行详情 + 日志")
async def get_execution_detail(
    execution_id: int,
    db: AsyncSession = Depends(get_db),
):
    return success_response(data=await service.get_execution_detail(db, execution_id))


@router.get("/executions/{execution_id}/log-download", summary="下载执行日志文件")
async def download_execution_log(
    execution_id: int,
    db: AsyncSession = Depends(get_db),
):
    execution = await db.get(OpenListExecution, execution_id)
    if execution is None or execution.is_deleted:
        raise NotFoundException("执行记录不存在")
    file = Path(execution.log_path) if execution.log_path else None
    if file is None or not file.is_file():
        # 无日志文件时退化为从数据库行生成文本
        rows = await db.execute(
            select(OpenListLog).where(OpenListLog.execution_id == execution_id).order_by(OpenListLog.id)
        )
        lines = [
            f"[{log.created_time.strftime('%Y-%m-%d %H:%M:%S') if log.created_time else ''}] [{log.log_level.upper()}] {log.content}"
            for log in rows.scalars()
        ]
        content = "\n".join(lines) or "（无日志）"
        filename = f"execution_{execution_id}.log"
        return PlainTextResponse(
            content,
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
        )
    return FileResponse(
        file,
        media_type="text/plain",
        filename=f"execution_{execution_id}.log",
    )


# ---------- 任务历史 ----------

@router.get("/history", summary="任务历史（每个任务最近一次执行）")
async def history_summary(
    db: AsyncSession = Depends(get_db),
):
    return success_response(data={"list": await service.history_summary(db)})


@router.get("/history/task/{task_id}", summary="指定任务的全部执行记录")
async def history_by_task(
    task_id: int,
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    items, total = await service.list_executions(db, task_id=task_id, page=page, page_size=pageSize)
    return success_response(data={"list": items}, total=total)


@router.get("/history/{execution_id}/logs", summary="执行日志（分页）")
async def list_execution_logs(
    execution_id: int,
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    items, total = await service.list_execution_logs(db, execution_id, page, pageSize)
    return success_response(data={"list": items}, total=total)


# ---------- 实时日志（WebSocket） ----------

@router.websocket("/ws/{execution_id}")
async def execution_ws(websocket: WebSocket, execution_id: int):
    # 本地部署无鉴权：直接接受连接
    await ws_manager.connect(execution_id, websocket)
    recent = await service.get_recent_log_lines(execution_id, limit=200)
    await ws_manager.send_recent(execution_id, websocket, recent)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(execution_id, websocket)
