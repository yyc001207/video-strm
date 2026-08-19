"""日志工具：应用级 logger 与 STRM 生成 logger。

``get_strm_logger()`` 返回 ``strm`` 命名空间的 logger；执行引擎会为单次执行
创建 ``strm.{execution_id}`` 子 logger 并挂接实时广播 + 落库 Handler，
``propagate=False`` 避免重复打到根 ``strm`` logger。
"""

import logging

_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

_app_logger = logging.getLogger("navly")
_strm_logger = logging.getLogger("strm")


def _ensure_stream(logger_: logging.Logger):
    if not any(isinstance(h, logging.StreamHandler) for h in logger_.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(_formatter)
        logger_.addHandler(handler)


for _logger in (_app_logger, _strm_logger):
    _logger.setLevel(logging.INFO)
    _logger.propagate = False
    _ensure_stream(_logger)


def get_strm_logger() -> logging.Logger:
    """返回 STRM 生成的共享 logger（未绑定单次执行时使用）。"""
    return _strm_logger


logger = _app_logger
