"""页面路由。"""
from flask import Blueprint, render_template, redirect, request, jsonify
from flask_login import current_user
from api import database as db
from api import config
import json
import random
import uuid
from flask_cors import cross_origin
from main.main import base, app

页面蓝图 = Blueprint('pages', __name__)


@页面蓝图.route('/login')
def login_page():
	if current_user.is_authenticated:
		return redirect('/')
	return render_template(base, page_template='auth.html')


@页面蓝图.route('/')
def index_page():
	return render_template(base, page_template='index.html')


@页面蓝图.route('/privacy')
def privacy_page():
	return render_template(base, page_template='privacy.html')


@页面蓝图.route('/verify-email')
def verify_email_page():
	token = request.args.get('token', '')
	if token:
		token_info = db.get_verify_token(token, 'email_verify')
		if token_info:
			db.update_user_email_verified(token_info['user_id'])
			db.delete_verify_token(token)
			return render_template(base, page_template='verify_success.html')
		else:
			return render_template(base, page_template='verify_failed.html')
	return render_template(base, page_template='auth.html')


@页面蓝图.route('/reset-password')
def reset_password_page():
	token = request.args.get('token', '')
	if token:
		token_info = db.get_verify_token(token, 'password_reset')
		if token_info:
			return render_template(base, page_template='auth.html')
		else:
			return render_template(base, page_template='verify_failed.html')
	return render_template(base, page_template='auth.html')


@页面蓝图.route('/WIKI')
def WIKI():
	return render_template(base, page_template='WIKI/WIKI.html')


@页面蓝图.route("/World")
def World():
	return render_template(base, page_template='World.html')


@页面蓝图.route('/WIKI/GuanFang')
def WIKIGuanFang():
	return render_template(base, page_template='WIKI/GuanFang/GuanFang.html')


@页面蓝图.route('/WIKI/Personal')
def WIKIPersonal():
	return render_template(base, page_template='WIKI/Personal/Personal.html')


@页面蓝图.route('/WIKI/Personal/mouse')
def WIKIPersonalMouse():
	return render_template(base, page_template='WIKI/Personal/mouse/mouse.html')


@页面蓝图.route('/WIKI/Personal/mouse/Liunx')
def WIKIPersonalMouseLiunx():
	return render_template(base, page_template='WIKI/Personal/mouse/Liunx.html')


@页面蓝图.route('/forum')
def forum_page():
	return render_template(base, page_template='forum.html')


@页面蓝图.route('/post/create')
def post_create_page():
	return render_template(base, page_template='post_create.html')


@页面蓝图.route('/WIKI/Personal/Live2D')
def WIKIPersonalLive2D():
	return render_template(base, page_template='WIKI/Personal/Live2D.html')


@页面蓝图.route('/users/<ID>')
def users_page(ID):
	UserInfo = db.get_user_by_id(ID)
	if not UserInfo:
		return "No this user", 401
	return render_template(base, page_template='UserPersonalinfo.html')


@页面蓝图.route('/huiguan')
def huiguan_page():
	return render_template(base, page_template='huiguan.html')


@页面蓝图.route('/api/huiguan')
def api_huiguan_list():
	try:
		with app.open_resource("huiguan.json", "r", encoding="utf-8") as f:
			data = json.load(f)
		return jsonify({
			'success': True,
			'list': data
		})
	except Exception as e:
		print(f"[ERROR] /api/huiguan: {e}")
		return jsonify({'success': False, 'message': '服务器内部错误'}), 500


@页面蓝图.route('/favicon.ico')
def favicon():
	return redirect(config.Image_father_URL + '/favicon.png')


@页面蓝图.route('/Easter-Egg')
def EasterEgg():
	try:
		with app.open_resource("EasterEgg/1.json", "r", encoding="utf-8") as f:
			data = random.choice(json.load(f))
		return jsonify(data)
	except Exception as e:
		print(f"[ERROR] /Easter-Egg: {e}")
		return jsonify({"error": "服务器内部错误"}), 500


@页面蓝图.route('/search')
def search_page():
	return render_template(base, page_template='search.html')


@页面蓝图.route('/post/<post_id>')
def page_post_detail(post_id):
	return render_template(base, page_template='post_detail.html')


@页面蓝图.route('/rss.xml')
def RSS():
	return ""


@页面蓝图.route('/QQ/redirect')
def QQ_redirect():
	return redirect("https://qm.qq.com/q/bLxr68HnUI")


@页面蓝图.route("/INFO/")
@页面蓝图.route("/INFO")
@cross_origin(origins="men.umrca.com")
def INFO():
	return random.choice(["妖精论坛——一个充满神秘色彩的封闭区域，在此处，你会与聚灵而生的妖精，亦或者得到某种机遇而打开修行之路的人类，展开全新的相遇"])


@页面蓝图.route('/api/users/avatar/navifox/', methods=['GET'])
@cross_origin(origins="")
def navifox_avatar():
	return ""


@页面蓝图.route("/TheDoorOfBings/UUID4/")
def TheDoorOfBings_UUID():
	return jsonify([str(uuid.uuid4())])
