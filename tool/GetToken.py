"""兼容旧导入路径：tool.GetToken.GetToken。

实际算法在 api/encrypt.py 中实现（md5 + HMAC-SHA256），这里只做转发。
"""
from api.encrypt import GetToken, SECRET_KEY  # noqa: F401

__all__ = ["GetToken", "SECRET_KEY"]
