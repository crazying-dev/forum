# -*- coding: utf-8 -*-
"""妖精论坛 Windows 桌面客户端。

模块划分：

* :mod:`app.paths`      —— 程序/资源/数据目录解析
* :mod:`app.crypto`     —— 字符串混淆与本地凭证加解密（纯标准库）
* :mod:`app.constants`  —— 全局常量（后端地址、分区表、限值、资源路径）
* :mod:`app.logger`     —— 日志（文件 + Qt 视图双通道）
* :mod:`app.config`     —— 本地配置（~/.Cr/forum/config.json）
* :mod:`app.yearmode`   —— 无限年/公元年换算与时间格式
* :mod:`app.theme`      —— 主题色板与 QSS
* :mod:`app.api`        —— 后端 HTTP 接口层
* :mod:`app.session_store` —— 登录凭证持久化
* :mod:`app.shell`      —— 主窗口外壳（导航 / 顶栏 / 世界面板）
* :mod:`app.pages`      —— 各业务页面
* :mod:`app.widgets`    —— 可复用组件
* :mod:`app.live2d`     —— Live2D 桌宠（原生渲染）
"""

__all__ = ["__version__"]

__version__ = "1.2.4"
