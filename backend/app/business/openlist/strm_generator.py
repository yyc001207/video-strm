"""STRM 生成器：扫描 OpenList 云端目录，为视频生成 .strm 下载链接、下载字幕。

- 视频文件产出 ``.strm`` 文件（内容为 ``{base}/d/{quoted_path}`` 下载地址）
- 字幕文件直接下载到输出目录
- 增量模式（force=False）跳过已存在文件；强制模式（force=True）重新生成
- 不支持的格式（非视频/字幕扩展名）不处理，忽略的媒体/图片扩展名直接跳过
- 输出路径相对任务处理路径映射：``/test/tv/xxx.mkv`` -> 输出目录 ``/xxx.strm``
"""

import asyncio
import logging
import os
import random
import shutil
from pathlib import Path
from typing import Any, Dict, List, Set
from urllib.parse import quote

from app.business.openlist.openlist_api import OpenListAPI
from app.business.openlist.task_status_manager import TaskStatusManager
from app.core.logger import get_strm_logger
from app.utils.helpers import sanitize_filename


def parse_pause_times(raw) -> List[int]:
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


class STRMGenerator:
    def __init__(
        self,
        global_config: Dict[str, Any],
        task_config: Dict[str, Any],
        task_id: str = None,
        logger_: logging.Logger = None,
        api: OpenListAPI = None,
    ):
        self.logger = logger_ or get_strm_logger()
        self.task_id = str(task_id) if task_id is not None else None
        self.base_url = global_config["baseUrl"].rstrip("/")
        verify_ssl = bool(global_config.get("verifySsl", False))
        self.api = api or OpenListAPI(self.base_url, global_config["token"], logger_=self.logger, verify_ssl=verify_ssl)
        self.video_exts = self._normalize_exts(global_config.get("videoExtensions", []))
        self.subtitle_exts = self._normalize_exts(global_config.get("subtitleExtensions", []))
        self.output_dir = task_config.get("outputDir") or "./output"
        self.task_paths = self._normalize_task_paths(task_config)
        # 限流参数：任务级优先，为 NULL/空则回退全局配置；全 0 或空则不暂停
        raw_count = task_config.get("pauseCount")
        if raw_count is None:
            raw_count = global_config.get("pauseCount")
        try:
            self.pause_count = max(1, int(raw_count)) if raw_count else 0
        except (ValueError, TypeError):
            self.pause_count = 0
        raw_time = task_config.get("pauseTime") or global_config.get("pauseTime")
        self.pause_times = parse_pause_times(raw_time)
        self.stats = {
            "totalVideos": 0,
            "successVideos": 0,
            "errorVideos": 0,
            "totalSubtitles": 0,
            "successSubtitles": 0,
            "errorSubtitles": 0,
        }

    @staticmethod
    def _normalize_exts(raw) -> Set[str]:
        """扩展名统一转小写并补点，兼容 ``mp4``/``.mp4`` 两种写法。"""
        if isinstance(raw, str):
            raw = raw.split(",")
        exts = set()
        for item in raw or []:
            item = str(item).strip().lower()
            if not item:
                continue
            exts.add(item if item.startswith(".") else f".{item}")
        return exts

    @staticmethod
    def _normalize_task_paths(task_config: Dict[str, Any]) -> List[str]:
        """任务处理路径：兼容单行字符串与换行分隔的多路径。"""
        raw = task_config.get("taskPaths") or task_config.get("processPath") or ""
        if isinstance(raw, str):
            return [p.strip().strip("/") for p in raw.split("\n") if p.strip()]
        if isinstance(raw, (list, tuple)):
            return [str(p).strip().strip("/") for p in raw if str(p).strip()]
        return []

    def _sanitize_path(self, path: str) -> str:
        if not path or path == ".":
            return path
        parts = path.split("/")
        cleaned_parts = [sanitize_filename(p) for p in parts]
        return "/".join(cleaned_parts)

    def _get_download_url(self, file_path: str) -> str:
        clean_path = file_path.strip("/")
        return f"{self.base_url}/d/{quote(clean_path)}"

    def _build_output_dir(self, output_base: Path, relative_path: str) -> Path:
        relative_path = str(relative_path).replace("\\", "/").strip("./")
        if not relative_path or relative_path == ".":
            output_dir = output_base
        else:
            parts = relative_path.split("/")
            cleaned_parts = [sanitize_filename(p) for p in parts]
            cleaned_path = "/".join(cleaned_parts)
            output_dir = output_base / cleaned_path
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    def _cancelled(self) -> bool:
        if self.task_id:
            return TaskStatusManager.is_cancelled(self.task_id)
        return False

    def _get_output_path(self, item_path: str, base_path: str) -> str:
        item_path = item_path.strip("/")
        base_path = base_path.strip("/")
        if item_path.startswith(base_path):
            relative = item_path[len(base_path):].lstrip("/")
            if not relative:
                # 扫描路径与处理路径相同：对应输出根，清理时直接指向输出根
                return ""
            return relative
        return Path(item_path).name

    async def _process_file(self, item: Dict, current_path: str, output_base: Path, force: bool, strm_only: bool, base_path: str):
        name = item.get("name", "")
        file_ext = Path(name).suffix.lower()
        item_path = item.get("path") or f"{current_path}/{name}"
        item_path = item_path.strip("/")
        if self._cancelled():
            return
        output_relative = self._get_output_path(item_path, base_path)
        parent = Path(output_relative).parent
        output_dir_path = str(parent).replace("\\", "/") if str(parent) != "." else ""
        output_dir = self._build_output_dir(output_base, output_dir_path)

        if file_ext in self.video_exts:
            self.stats["totalVideos"] += 1
            try:
                strm_filename = self._sanitize_path(Path(name).stem) + ".strm"
                strm_path = output_dir / strm_filename
                if not force and strm_path.exists():
                    self.stats["successVideos"] += 1
                    self.logger.info(f"[{output_relative}] 跳过 STRM (已存在): {name}")
                    return
                output_dir.mkdir(parents=True, exist_ok=True)
                with open(strm_path, "w", encoding="utf-8") as f:
                    f.write(self._get_download_url(item_path))
                self.stats["successVideos"] += 1
                self.logger.info(f"[{output_relative}] 创建 STRM: {name}")
            except Exception as e:
                self.stats["errorVideos"] += 1
                self.logger.error(f"[{output_relative}] 创建 STRM 失败 {name}: {e}")
        elif file_ext in self.subtitle_exts:
            self.stats["totalSubtitles"] += 1
            try:
                subtitle_path = output_dir / name
                # strm_only 仅在强制生成时生效：已存在的字幕跳过下载，避免重复下载
                skip_existing = not force or (strm_only and force)
                if skip_existing and subtitle_path.exists():
                    self.stats["successSubtitles"] += 1
                    self.logger.info(f"[{output_relative}] 跳过字幕 (已存在): {name}")
                    return
                output_dir.mkdir(parents=True, exist_ok=True)
                success = await self.api.download_file("/" + item_path, str(subtitle_path), encode=False)
                if success:
                    self.stats["successSubtitles"] += 1
                    self.logger.info(f"[{output_relative}] 下载字幕: {name}")
                else:
                    self.stats["errorSubtitles"] += 1
                    self.logger.error(f"[{output_relative}] 下载字幕失败: {name}")
            except Exception as e:
                self.stats["errorSubtitles"] += 1
                self.logger.error(f"[{output_relative}] 下载字幕失败 {name}: {e}")

    IGNORE_EXTS = {".nfo", ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif", ".svg", ".ico", ".mp3"}

    async def _scan_and_process(self, scan_path: str, output_base: Path, force: bool, strm_only: bool, base_path: str, cloud_files: Set[str]):
        if self._cancelled():
            return
        try:
            result = await self.api.list_files("/" + scan_path)
            items = result.get("content") or []
        except Exception as e:
            self.logger.error(f"扫描失败 {scan_path}: {e}，清理本地残留")
            self._cleanup_current_dir(output_base, set(), base_path, scan_path, set())
            return
        cloud_dir_names = set()
        for item in items:
            if not item.get("is_dir", False):
                item_name = item.get("name", "")
                item_path = f"{scan_path}/{item_name}"
                relative_path = self._get_output_path(item_path, base_path)
                relative_path = self._sanitize_path(relative_path)
                file_ext = Path(relative_path).suffix.lower()
                if file_ext in self.video_exts:
                    relative_path = str(relative_path).rsplit(".", 1)[0] + ".strm"
                cloud_files.add(relative_path)
            else:
                dir_name = item.get("name", "")
                cloud_dir_names.add(self._sanitize_path(dir_name))
        for item in items:
            if item.get("is_dir", False):
                subdir_name = item.get("name", "")
                subdir_path = item.get("path", "").strip("/") or f"{scan_path}/{subdir_name}"
                sub_cloud_files = set()
                await self._scan_and_process(subdir_path, output_base, force, strm_only, base_path, sub_cloud_files)
                if sub_cloud_files:
                    cloud_files.update(sub_cloud_files)
        self._cleanup_current_dir(output_base, cloud_files, base_path, scan_path, cloud_dir_names)
        # 顺序处理文件（原为 asyncio.gather 并发）；每处理 pause_count 个文件限流暂停一次，
        # 随机暂停 pause_times 列表中的一个时间，控制对服务器的请求频率。
        files = [item for item in items if not item.get("is_dir", False)]
        count = 0
        for item in files:
            await self._process_file(item, scan_path, output_base, force, strm_only, base_path)
            count += 1
            if self.pause_times and self.pause_count > 0 and count % self.pause_count == 0:
                delay = random.choice(self.pause_times)
                self.logger.info(f"[限流] 已处理 {count} 个文件，暂停 {delay}s")
                await asyncio.sleep(delay)

    def _safe_remove_dir(self, target: Path, output_base: Path):
        """安全删除目录：先确认目标在输出根内，改名后再删除（同文件系统内原子性）。

        先 ``rename`` 到临时名可避免 rmtree 中途失败导致半删状态卡住原目录名；
        若 rename 失败（如目标被占用）则回退直接删除。任何失败都仅记录日志。
        """
        try:
            target_resolved = target.resolve()
            base_resolved = output_base.resolve()
            # 防越界：目标必须严格位于输出根之内，且不能是输出根本身
            if target_resolved == base_resolved or not target_resolved.is_relative_to(base_resolved):
                self.logger.error(f"拒绝删除越界路径: {target}")
                return
            trash = target_resolved.parent / f".trash-{target_resolved.name}"
            try:
                if trash.exists():
                    shutil.rmtree(str(trash))
                target_resolved.rename(trash)
                shutil.rmtree(str(trash))
            except Exception:
                # rename 失败（目标被占用等）时回退直接删除
                shutil.rmtree(str(target_resolved))
        except Exception as e:
            self.logger.error(f"删除目录失败 {target}: {e}")

    def _cleanup_current_dir(self, output_base: Path, cloud_files: Set[str], base_path: str, scan_path: str, cloud_dir_names: Set[str] = None):
        if self._cancelled():
            return
        output_relative = self._get_output_path(scan_path, base_path)
        output_relative = self._sanitize_path(output_relative)
        current_dir = output_base / output_relative
        try:
            current_resolved = current_dir.resolve()
            base_resolved = output_base.resolve()
        except Exception:
            return
        if not current_resolved.is_relative_to(base_resolved) or current_resolved == base_resolved:
            if output_relative:
                self.logger.error(f"清理路径越界，跳过: {current_dir}")
                return
        if not current_dir.exists():
            return
        current_depth = len(output_relative.split("/")) if output_relative else 0
        current_dir_files = set()
        for cf in cloud_files:
            cf_parts = cf.split("/")
            if len(cf_parts) > current_depth:
                prefix = "/".join(cf_parts[:current_depth])
                if current_depth == 0 or prefix == output_relative:
                    current_dir_files.add(cf)
        for local_file in current_dir.iterdir():
            if not local_file.is_file():
                continue
            try:
                relative_path = local_file.relative_to(output_base)
            except ValueError:
                continue
            relative_str = str(relative_path).replace("\\", "/")
            file_ext = Path(relative_str).suffix.lower()
            if file_ext in self.IGNORE_EXTS:
                continue
            if file_ext == ".strm":
                if relative_str in current_dir_files:
                    continue
                try:
                    local_file.unlink()
                    self.logger.info(f"删除已失效STRM: {relative_str}")
                except Exception as e:
                    self.logger.error(f"删除文件失败 {local_file}: {e}")
                continue
            if relative_str not in current_dir_files:
                try:
                    local_file.unlink()
                    self.logger.info(f"删除已失效文件: {relative_str}")
                except Exception as e:
                    self.logger.error(f"删除文件失败 {local_file}: {e}")
        if cloud_dir_names is not None:
            for local_item in current_dir.iterdir():
                if local_item.is_dir():
                    sanitized_name = self._sanitize_path(local_item.name)
                    if sanitized_name not in cloud_dir_names:
                        self._safe_remove_dir(local_item, output_base)
                        self.logger.info(f"删除已失效目录: {local_item}")

    def _cleanup_empty_dirs(self, output_base: Path):
        for dirpath, dirnames, filenames in os.walk(str(output_base), topdown=False):
            current = Path(dirpath)
            if current == output_base:
                continue
            try:
                if not any(current.iterdir()):
                    current.rmdir()
                    self.logger.info(f"清理空目录: {current}")
            except Exception as e:
                self.logger.error(f"清理空目录失败 {current}: {e}")

    async def execute(self, force: bool = False, strm_only: bool = False, cleanup: bool = True) -> Dict[str, Any]:
        if self.output_dir.startswith("/"):
            relative_path = self.output_dir.lstrip("/")
            output_path = Path.cwd() / "output" / relative_path
            output_path.mkdir(parents=True, exist_ok=True)
            self.output_dir = str(output_path)
        output_base = Path(self.output_dir)
        self.logger.info(f"开始执行，共 {len(self.task_paths)} 个路径")
        for task_path in self.task_paths:
            if self._cancelled():
                self.logger.info("任务已取消")
                break
            base_path = task_path.strip("/")
            cloud_files = set()
            await self._scan_and_process(task_path, output_base, force, strm_only, base_path, cloud_files)
        self._cleanup_empty_dirs(output_base)
        self.logger.info(f"完成: 视频 {self.stats['successVideos']}/{self.stats['totalVideos']}, 字幕 {self.stats['successSubtitles']}/{self.stats['totalSubtitles']}")
        return self.stats
