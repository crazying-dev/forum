"""Flask 扩展注册。"""
import os

from flask_cors import CORS
from flask_login import LoginManager
from flask import Flask
from app.config import *


def register_extensions(app: Flask):
	"""注册所有 Flask 扩展。"""
	_allowed_origins = os.getenv('CORS_ORIGINS', '').split(',')
	_allowed_origins = [o.strip() for o in _allowed_origins if o.strip()]
	CORS(app, origins=_allowed_origins or True)

	login_manager = LoginManager()
	login_manager.init_app(app)
	return login_manager, _allowed_origins
