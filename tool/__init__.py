"""工具模块 — 对外保持原有 GetToken/GETIP 名字的导入兼容。

实际实现移到 api/encrypt.py 中（按项目约束：加密逻辑必须放 api/ 目录下）。
本文件只做 re-export，保证 `from tool import *` / `from tool.GetToken import GetToken` 仍然可用。
"""
# 转发给 api.encrypt 的统一实现（md5+hmac 算法，与原代码一致）
from api.encrypt import GetToken  # noqa: F401


def GETIP(IP):
    """原函数占位，用于上报访问 IP，后续接入黑名单/日志系统再完善。"""
    # TODO: 接入安全模块，写入 IP 日志 / 触发风控
    return True


__all__ = ["GetToken", "GETIP"]
