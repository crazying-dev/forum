"""页面路由。"""
from flask import Blueprint, send_file, render_template, redirect, request, jsonify
from flask_login import current_user
from api import database as db
from api import config
import json
import random
import uuid
from flask_cors import cross_origin
from main.main import base, app

pages_bp = Blueprint('pages', __name__)


@pages_bp.route('/login')
def login_page():
	if current_user.is_authenticated:
		return redirect('/')
	return render_template(base, page_template='auth.html')


@pages_bp.route('/')
def index_page():
	return render_template(base, page_template='index.html')


@pages_bp.route('/privacy')
def privacy_page():
	return render_template(base, page_template='privacy.html')


@pages_bp.route('/verify-email')
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


@pages_bp.route('/reset-password')
def reset_password_page():
	token = request.args.get('token', '')
	if token:
		token_info = db.get_verify_token(token, 'password_reset')
		if token_info:
			return render_template(base, page_template='auth.html')
		else:
			return render_template(base, page_template='verify_failed.html')
	return render_template(base, page_template='auth.html')


@pages_bp.route('/WIKI')
def WIKI():
	return render_template(base, page_template='WIKI/WIKI.html')


@pages_bp.route("/World")
def World():
	return render_template(base, page_template='World.html')


@pages_bp.route('/WIKI/GuanFang')
def WIKIGuanFang():
	return render_template(base, page_template='WIKI/GuanFang/GuanFang.html')


@pages_bp.route('/WIKI/Personal')
def WIKIPersonal():
	return render_template(base, page_template='WIKI/Personal/Personal.html')


@pages_bp.route('/WIKI/Personal/mouse')
def WIKIPersonalMouse():
	return render_template(base, page_template='WIKI/Personal/mouse/mouse.html')


@pages_bp.route('/WIKI/Personal/mouse/Liunx')
def WIKIPersonalMouseLiunx():
	return render_template(base, page_template='WIKI/Personal/mouse/Liunx.html')


@pages_bp.route('/forum')
def forum_page():
	return render_template(base, page_template='forum.html')


@pages_bp.route('/post/create')
def post_create_page():
	return render_template(base, page_template='post_create.html')


@pages_bp.route('/WIKI/Personal/Live2D')
def WIKIPersonalLive2D():
	return render_template(base, page_template='WIKI/Personal/Live2D.html')


@pages_bp.route('/users/<ID>')
def users_page(ID):
	UserInfo = db.get_user_by_id(ID)
	if not UserInfo:
		return "No this user", 401
	return render_template(base, page_template='UserPersonalinfo.html')


@pages_bp.route('/api/huiguan')
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


@pages_bp.route('/favicon.ico')
def favicon():
	return redirect(config.Image_father_URL + '/favicon.png')


@pages_bp.route('/Easter-Egg')
def EasterEgg():
	try:
		with app.open_resource("EasterEgg/1.json", "r", encoding="utf-8") as f:
			data = random.choice(json.load(f))
		return jsonify(data)
	except Exception as e:
		print(f"[ERROR] /Easter-Egg: {e}")
		return jsonify({"error": "服务器内部错误"}), 500


@pages_bp.route('/search')
def search_page():
	return render_template(base, page_template='search.html')


@pages_bp.route('/post/<post_id>')
def page_post_detail(post_id):
	return render_template(base, page_template='post_detail.html')


@pages_bp.route('/rss.xml')
def RSS():
	return ""


@pages_bp.route('/QQ/redirect')
def QQ_redirect():
	return redirect("https://qm.qq.com/q/bLxr68HnUI")


@pages_bp.route("/INFO/")
@pages_bp.route("/INFO")
@cross_origin(origins="men.umrca.com")
def INFO():
	return random.choice(["妖精论坛——一个充满神秘色彩的封闭区域，在此处，你会与聚灵而生的妖精，亦或者得到某种机遇而打开修行之路的人类，展开全新的相遇"])


@pages_bp.route('/api/users/avatar/navifox/', methods=['GET'])
def navifox_avatar():
	return ""




@pages_bp.route('/manifest.json')
def manifest():
	return send_file(os.path.join(app.root_path), 'templates/PATH/manifest.json', mimetype='application/manifest+json')


@pages_bp.route('/sw.js')
def service_worker():
	return "// Service Worker\nself.addEventListener('fetch', function(e) {\n    e.respondWith(fetch(e.request));\n});\n", 200, {'Content-Type': 'application/javascript'}


@pages_bp.route("/TheDoorOfBings/UUID4/")
def TheDoorOfBings_UUID():
	return jsonify([str(uuid.uuid4())])

# /avatar/xxx.webp
@pages_bp.route('/avatar/<filename>')
def serve_avatar(filename):
	try:
		return send_file('/root/db/avatar/' + filename, mimetype='image/webp')
	except Exception:
		return '', 404
