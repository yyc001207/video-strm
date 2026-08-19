from typing import Any, Optional


def success_response(
    data: Any = None,
    msg: str = "success",
    code: int = 200,
    total: Optional[int] = None,
) -> dict:
    result: dict = {"code": code, "msg": msg, "data": data}
    if total is not None:
        result["total"] = total
    return result


def error_response(msg: str = "error", code: int = 400, data: Any = None) -> dict:
    return {"code": code, "msg": msg, "data": data}
