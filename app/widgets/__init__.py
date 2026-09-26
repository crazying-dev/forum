# -*- coding: utf-8 -*-
"""可复用组件层。

这里用 **显式导入**（而不是模块级 __getattr__ 懒加载）：后者与
``from . import <子模块>`` 结合会在导入期递归调用自身，导致
RecursionError（已踩过坑）。各子模块之间只依赖 ``..`` 兄弟包，无循环。
"""

from __future__ import annotations

from .comment import CommentItem, CommentList
from .common import (Card, CardTitle, Chip, Divider, ElidedLabel, EmptyHint, FlowLayout,
                     LoadingHint, Muted, ScrollPage, TitleLabel, UserLink,
                     button, chip, clear_layout, divider, ghost_button, hbox,
                     set_active, set_variant, vbox)
from .dialogs import (REPORT_REASONS, BaseDialog, BugReportDialog,
                      ExternalLinkDialog, ReportDialog, UserListDialog, confirm,
                      info_box)
from .images import AsyncImage, Avatar, avatar_cache, image_cache
from .markdown import MarkdownView, markdown_to_html
from .post_card import PostCard, with_author
from .toast import Toast, ToastManager, toast
from .update import (DownloadDialog, UpdateDialog, ask_update, check_and_prompt,
                     download_and_install, eta_text, progress_text)
from .world_panel import WorldMessage, WorldPanel

__all__ = [
    "Card", "CardTitle", "Chip", "Divider", "ElidedLabel", "EmptyHint", "FlowLayout",
    "LoadingHint", "Muted", "ScrollPage", "TitleLabel", "UserLink",
    "button", "chip", "clear_layout", "divider", "ghost_button", "hbox",
    "set_active", "set_variant", "vbox",
    "REPORT_REASONS", "BaseDialog", "BugReportDialog", "ExternalLinkDialog",
    "ReportDialog", "UserListDialog", "confirm", "info_box",
    "AsyncImage", "Avatar", "avatar_cache", "image_cache",
    "MarkdownView", "markdown_to_html",
    "PostCard", "with_author",
    "Toast", "ToastManager", "toast",
    "DownloadDialog", "UpdateDialog", "ask_update", "check_and_prompt",
    "download_and_install", "eta_text", "progress_text",
    "WorldMessage", "WorldPanel",
    "CommentItem", "CommentList",
]
