# -*- coding: utf-8 -*-
"""Live2D 桌宠：LPK 下载 / 解包 / 归一化（本次仅实现资源准备，不含渲染）。

对外只暴露两个名字：

    from app.live2d import Live2DProvider, LPKError
"""

from __future__ import annotations

from .provider import LPKError, Live2DProvider

__all__ = ["Live2DProvider", "LPKError"]
