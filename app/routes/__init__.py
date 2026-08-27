"""Blueprint 注册。"""
from flask import Flask


def register_routes(app: Flask):
	"""注册所有路由蓝图。"""
	from app.routes.pages import pages_bp
	from app.routes.auth import auth_bp
	from app.routes.users import users_bp
	from app.routes.posts import posts_bp
	from app.routes.comments import comments_bp
	from app.routes.world import world_bp
	from app.routes.search import search_bp
	from app.routes.bug import bug_bp
	from app.routes.vote import vote_bp

	app.register_blueprint(pages_bp)
	app.register_blueprint(auth_bp)
	app.register_blueprint(users_bp)
	app.register_blueprint(posts_bp)
	app.register_blueprint(comments_bp)
	app.register_blueprint(world_bp)
	app.register_blueprint(search_bp)
	app.register_blueprint(bug_bp)
	app.register_blueprint(vote_bp)