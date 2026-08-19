"""执行任务取消状态管理：进程内标记某个任务是否需要取消。

STRM 生成器在文件/目录之间轮询 ``is_cancelled``，实现取消的半实时响应。
新一次执行开始前必须调用 ``clear`` 复位，避免沿用上一次的取消标记。
"""

from typing import Dict


class TaskStatusManager:
    _cancel_flags: Dict[str, bool] = {}

    @classmethod
    def is_cancelled(cls, task_id: str) -> bool:
        return cls._cancel_flags.get(str(task_id), False)

    @classmethod
    def cancel(cls, task_id: str) -> None:
        cls._cancel_flags[str(task_id)] = True

    @classmethod
    def clear(cls, task_id: str) -> None:
        cls._cancel_flags.pop(str(task_id), None)


task_status_manager = TaskStatusManager()
