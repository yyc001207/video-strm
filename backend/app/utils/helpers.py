"""通用工具函数。"""

import re

_WINDOWS_UNSAFE = re.compile(r'[\\/:*?"<>|\r\n\t]')


def sanitize_filename(name: str) -> str:
    """清洗文件名/路径段：移除文件系统非法字符与首尾空白/点。

    仅按段清洗，保留 ``/`` 路径分隔符（调用方在拆分后再拼接）。
    空结果返回 ``_``，避免产生空段。
    """
    cleaned = _WINDOWS_UNSAFE.sub("", str(name))
    cleaned = cleaned.strip().strip(".")
    return cleaned or "_"
