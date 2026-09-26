妖精论坛 · Windows 客户端
=========================

本安装包会把客户端安装到：
    %LOCALAPPDATA%\CrForum

你的账号、配置、头像缓存、Live2D 模型等数据保存在：
    %USERPROFILE%\.Cr\forum
（卸载时默认保留，如需清除请用 uninstall.cmd /purge）
安装完成后的效果：
  * 开始菜单出现「妖精论坛客户端」快捷方式
  * 「添加/删除程序」中出现卸载入口
  * 注入注册表 Crforum:// 链接（例如 Crforum://post/PS... 可直接唤起客户端）
  * 客户端内置自动更新（「设置 → 启动与更新 → 检查更新」）

不需要管理员权限；所有写入都在当前用户下。

手动卸载：
    运行 %LOCALAPPDATA%\CrForum\uninstall.cmd

安全提示：客户端仅访问官网后端，不会上传本地文件；
Live2D 模型仅在首次使用时从官网下载一次并缓存到本地。
