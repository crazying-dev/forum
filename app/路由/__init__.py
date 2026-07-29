"""Blueprint 注册。"""
from flask import Flask


def 注册路由(app: Flask):
	"""注册所有路由蓝图。"""
	from app.路由.页面 import 页面蓝图
	from app.路由.认证 import 认证蓝图
	from app.路由.用户 import 用户蓝图
	from app.路由.帖子 import 帖子蓝图
	from app.路由.评论 import 评论蓝图
	from app.路由.世界 import 世界蓝图
	from app.路由.搜索 import 搜索蓝图

	app.register_blueprint(页面蓝图)
	app.register_blueprint(认证蓝图)
	app.register_blueprint(用户蓝图)
	app.register_blueprint(帖子蓝图)
	app.register_blueprint(评论蓝图)
	app.register_blueprint(世界蓝图)
	app.register_blueprint(搜索蓝图)