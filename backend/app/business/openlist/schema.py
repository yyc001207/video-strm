"""OpenList 模块 Pydantic 模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------- 全局配置 ----------

class OpenListConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    video_formats: Optional[str] = Field(default=None, max_length=512)
    subtitle_formats: Optional[str] = Field(default=None, max_length=512)
    max_concurrent: Optional[int] = Field(default=None, ge=1, le=100)
    pause_count: Optional[int] = Field(default=None, ge=1, le=100000)
    pause_time: Optional[str] = Field(default=None, max_length=512)
    disable_ssl_verify: Optional[bool] = None
    log_to_db: Optional[bool] = None
    process_path_prefix: Optional[str] = Field(default=None, max_length=128)
    output_dir_prefix: Optional[str] = Field(default=None, max_length=128)


class OpenListConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    video_formats: Optional[str] = None
    subtitle_formats: Optional[str] = None
    max_concurrent: int = 1
    pause_count: int = 50
    pause_time: str = "0,3,5"
    disable_ssl_verify: bool = False
    log_to_db: bool = False
    process_path_prefix: Optional[str] = None
    output_dir_prefix: Optional[str] = None
    created_time: Optional[datetime] = None
    updated_time: Optional[datetime] = None


# ---------- 服务器 ----------

class OpenListServerCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, max_length=128)
    server_url: str = Field(..., min_length=1, max_length=512)
    token: Optional[str] = Field(default=None, max_length=512)


class OpenListServerUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, max_length=128)
    server_url: Optional[str] = Field(default=None, min_length=1, max_length=512)
    token: Optional[str] = Field(default=None, max_length=512)
    is_active: Optional[bool] = None


class OpenListServerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: Optional[str] = None
    server_url: str
    is_active: bool = True
    has_token: bool = False
    created_time: Optional[datetime] = None
    updated_time: Optional[datetime] = None


# ---------- 预设 ----------

class OpenListPresetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=128)
    preset_path: str = Field(..., min_length=1, max_length=512)
    sort_order: int = Field(default=0)


class OpenListPresetUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    preset_path: Optional[str] = Field(default=None, min_length=1, max_length=512)
    sort_order: Optional[int] = None


class OpenListPresetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    preset_path: str
    sort_order: int
    created_time: Optional[datetime] = None
    updated_time: Optional[datetime] = None


# ---------- 任务 ----------

class OpenListTaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=128)
    output_dir: str = Field(..., min_length=1, max_length=512)
    process_path: str = Field(..., min_length=1, max_length=512)
    pause_count: Optional[int] = Field(default=None, ge=1, le=100000)
    pause_time: Optional[str] = Field(default=None, max_length=512)


class OpenListTaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    output_dir: Optional[str] = Field(default=None, min_length=1, max_length=512)
    process_path: Optional[str] = Field(default=None, min_length=1, max_length=512)
    pause_count: Optional[int] = Field(default=None, ge=1, le=100000)
    pause_time: Optional[str] = Field(default=None, max_length=512)


class OpenListTaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    output_dir: str
    process_path: str
    pause_count: Optional[int] = None
    pause_time: Optional[str] = None
    created_time: Optional[datetime] = None
    updated_time: Optional[datetime] = None


class OpenListBatchDeleteRequest(BaseModel):
    """批量删除请求（预设/任务通用）。"""

    model_config = ConfigDict(extra="forbid")

    ids: list[int] = Field(..., min_length=1, max_length=200)


# ---------- 执行 ----------

class OpenListBatchTask(BaseModel):
    """批量执行中的单个任务参数。"""

    model_config = ConfigDict(extra="forbid")

    task_id: int
    is_incremental: bool = True
    is_force: bool = False
    strm_only: bool = False


class OpenListExecutionCreate(BaseModel):
    """创建执行记录（仅落库，不启动后台任务）。"""

    model_config = ConfigDict(extra="forbid")

    task_id: int
    server_id: int
    is_incremental: bool = True
    is_force: bool = False
    strm_only: bool = False


class OpenListExecutionBatchCreate(BaseModel):
    """批量创建执行记录（同一服务器，多个任务，仅落库不启动）。"""

    model_config = ConfigDict(extra="forbid")

    server_id: int
    tasks: list[OpenListBatchTask] = Field(..., min_length=1, max_length=50)


class OpenListExecutionStart(BaseModel):
    """启动已创建的执行记录（前端先建再连再启动，保证日志不遗漏）。"""

    model_config = ConfigDict(extra="forbid")

    execution_id: int
    task_id: int
    server_id: int


class OpenListExecutionCancel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution_id: int


class OpenListExecutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    task_name: str
    server_id: Optional[int] = None
    server_name: Optional[str] = None
    status: str
    video_success_count: int = 0
    video_total_count: int = 0
    subtitle_success_count: int = 0
    subtitle_total_count: int = 0
    is_incremental: bool = True
    is_force: bool = False
    strm_only: bool = False
    duration_seconds: Optional[int] = None
    log_path: Optional[str] = None
    started_time: Optional[datetime] = None
    finished_time: Optional[datetime] = None
    created_time: Optional[datetime] = None


class OpenListLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    execution_id: int
    log_level: str
    content: str
    metadata_: Optional[dict] = None
    created_time: Optional[datetime] = None
