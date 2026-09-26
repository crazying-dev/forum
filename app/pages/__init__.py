# -*- coding: utf-8 -*-
"""业务页面包。页面通过 :class:`app.shell.Shell` 的 ``navigate(route, **kwargs)`` 打开。

路由表（与 :data:`app.shell.ROUTES` 对应）：

==============  ==========================================
route           页面
==============  ==========================================
home           首页（最新 / 随机推荐 / 综合排序）
forum          论坛列表（分区 + 排序 + 分页）
post           帖子详情（需 ``post_id``）
post_create    发布帖子
search         搜索（需 ``keyword``）
user           用户主页（需 ``user_id``）
me             「我的」（资料 / 收藏 / 评论 / 改资料改密改邮箱）
world          世界频道独立页
wiki           WIKI 总览
wiki_official  WIKI·官方
wiki_personal  WIKI·个人
wiki_mouse     WIKI·鼠标
wiki_mouse_linux  WIKI·鼠标 Linux 版
auth           登录 / 注册 / 找回密码
download       下载（客户端安装包 / 发布页，按平台分组）
settings       设置（主题 / 年制 / 鼠标 / 桌宠 / 日志 / 关于）
privacy        隐私政策
huiguan        会馆列表
easter_egg     彩蛋 / 每日一言
==============  ==========================================
"""

from __future__ import annotations

__all__ = ["base", "home", "forum", "post_detail", "post_create", "search",
           "user", "profile", "world", "wiki", "auth", "download", "settings",
           "misc"]
