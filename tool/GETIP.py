"""兼容旧导入路径：tool.GETIP.GETIP。"""
from tool.__init__ import GETIP  # noqa: F401

__all__ = ["GETIP"]
