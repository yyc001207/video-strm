"""OpenList 目录缓存：按 (server_id, path) 缓存一级子目录列表。

策略：单进程内存缓存（本地部署为单 uvicorn worker）。
- 缓存条目：{"name", "path", "modified"}（名称/路径/最后修改时间，来源 OpenList list_files）
- 缓存优先：命中且未过期直接返回；miss / 过期才回源拉取
- 过期清理：读取时懒清理过期条目；写入时顺带清扫过期条目，避免无效数据占用
- 手动刷新：refresh=True 回源并覆盖缓存
"""

import time
from typing import Any, Dict, List, Optional

TTL_SECONDS = 300  # 缓存有效期（秒）

# key: f"{server_id}:{path}" -> {"items": list[dict], "ts": float}
_cache: Dict[str, Dict[str, Any]] = {}
_cache_size = 0
_MAX_CACHE_SIZE = 500  # 条目上限，超出时清理最旧的一半，防止无限增长


def _key(server_id: int, path: str) -> str:
    return f"{server_id}:{path}"


def get_cached(server_id: int, path: str) -> Optional[List[dict]]:
    """命中且未过期返回子目录列表；过期条目直接删除并返回 None。"""
    key = _key(server_id, path)
    entry = _cache.get(key)
    if entry is None:
        return None
    if time.time() - entry["ts"] > TTL_SECONDS:
        del _cache[key]
        _shrink()
        return None
    return entry["items"]


def set_cache(server_id: int, path: str, items: List[dict]) -> None:
    global _cache_size
    key = _key(server_id, path)
    if key not in _cache:
        _cache_size += 1
    _cache[key] = {"items": items, "ts": time.time()}
    _shrink()


def _shrink() -> None:
    """过期/超量清理：删除全部过期条目；仍超上限时删除最旧的一半。"""
    global _cache_size
    now = time.time()
    expired = [k for k, v in _cache.items() if now - v["ts"] > TTL_SECONDS]
    for key in expired:
        del _cache[key]
        _cache_size -= 1
    if _cache_size > _MAX_CACHE_SIZE:
        # 按写入时间排序后删除最旧的一半
        ordered = sorted(_cache.items(), key=lambda kv: kv[1]["ts"])
        for key, _ in ordered[: _cache_size // 2]:
            del _cache[key]
            _cache_size -= 1


def clear_server(server_id: int) -> None:
    """服务器配置变更（更新/删除）后清空该服务器的全部目录缓存。"""
    global _cache_size
    prefix = f"{server_id}:"
    for key in [k for k in _cache if k.startswith(prefix)]:
        del _cache[key]
        _cache_size -= 1


def clear_all() -> None:
    global _cache_size
    _cache.clear()
    _cache_size = 0
