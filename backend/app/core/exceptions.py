class NavlyException(Exception):
    def __init__(self, msg: str = "error", code: int = 400):
        self.msg = msg
        self.code = code


class BadRequestException(NavlyException):
    def __init__(self, msg: str = "参数错误"):
        super().__init__(msg, code=400)


class UnauthorizedException(NavlyException):
    def __init__(self, msg: str = "未认证"):
        super().__init__(msg, code=401)


class ForbiddenException(NavlyException):
    def __init__(self, msg: str = "无权限"):
        super().__init__(msg, code=403)


class NotFoundException(NavlyException):
    def __init__(self, msg: str = "资源不存在"):
        super().__init__(msg, code=404)


class PayloadTooLargeException(NavlyException):
    def __init__(self, msg: str = "请求体过大"):
        super().__init__(msg, code=413)


class RateLimitException(NavlyException):
    def __init__(self, msg: str = "请求过多"):
        super().__init__(msg, code=429)
