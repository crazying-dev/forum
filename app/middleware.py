"""中间件模块。"""
import time
import gzip
import hashlib as _hashlib
from io import BytesIO as _BytesIO
from flask import request


# ── 速率限制存储 ────────────────────────────────────────

_rate_limit_store = {}
_rate_limit_cleanup_at = 0  # 上次全量清理时间戳，避免每次都扫字典


def csrf_protect(request, app_config):
	"""对状态变更请求（POST/PUT/DELETE/PATCH）校验 Origin/Referer。"""
	if request.method in ('GET', 'HEAD', 'OPTIONS'):
		return
	_allowed_origins_set = set(app_config.get('allowed_origins', [])) if app_config.get('allowed_origins') else set()
	origin = request.headers.get('Origin') or ''
	referer = request.headers.get('Referer') or ''
	host = request.host_url.rstrip('/')

	def _is_allowed(url):
		if not url:
			return False
		if url.startswith(host) or url.rstrip('/') == host:
			return True
		for ao in _allowed_origins_set:
			if url.startswith(ao.rstrip('/')):
				return True
		return False

	if _is_allowed(origin) or _is_allowed(referer):
		return
	return {'success': False, 'message': '跨站请求已被拦截'}, 403


def rate_limit(key, max_count, window_seconds):
	"""简易速率限制。

	Args:
		key: 限流维度标识
		max_count: 窗口内最大请求次数
		window_seconds: 窗口时长（秒）
	Returns:
		True（超出限制）或 False（允许通过）
	"""
	global _rate_limit_store, _rate_limit_cleanup_at
	now = time.time()
	client_ip = request.remote_addr or 'unknown'
	rk = f"{key}:{client_ip}"
	bucket = _rate_limit_store.get(rk, [])
	bucket = [t for t in bucket if t > now - window_seconds]  # 过滤本窗口过期时间戳
	if len(bucket) >= max_count:
		return True
	bucket.append(now)
	_rate_limit_store[rk] = bucket

	# ── 定期清理：按"字典规模"或"按时间间隔"触发，避免无限增长 ──
	store_size = len(_rate_limit_store)
	need_cleanup = (
		store_size > 5000
		or (now - _rate_limit_cleanup_at) > 600  # 至少每 10 分钟清一次
	)
	if need_cleanup:
		_rate_limit_cleanup_at = now
		cutoff = now - max(window_seconds * 2, 3600)
		# 先 snapshot，再逐个判断是否删除，避免先 clear 导致遍历空字典的 BUG
		stale_keys = []
		for k, v in _rate_limit_store.items():
			if not any(t > cutoff for t in v):
				stale_keys.append(k)
		for k in stale_keys:
			del _rate_limit_store[k]
		# 如果清理后仍然过大，说明恶意流量多，直接硬截断
		if len(_rate_limit_store) > 20000:
			cutoff2 = now - max(window_seconds, 600)
			for k in list(_rate_limit_store.keys()):
				v = _rate_limit_store[k]
				v_clean = [t for t in v if t > cutoff2]
				if v_clean:
					_rate_limit_store[k] = v_clean
				else:
					del _rate_limit_store[k]
	return False


def performance_optimize(response, request):
	"""响应后处理：安全头、ETag 和 gzip 压缩。"""
	# ── 安全响应头 ──
	response.headers.setdefault('X-Content-Type-Options', 'nosniff')
	response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
	response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
	response.headers.setdefault('Permissions-Policy', 'geolocation=(), microphone=(), camera=(), payment=()')
	response.headers.setdefault('X-XSS-Protection', '1; mode=block')
	if request.is_secure or request.headers.get('x-forwarded-proto') == 'https':
		response.headers.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')

	# 只读一次响应体，避免 ETag + gzip 重复复制大对象
	resp_data = None
	if request.method == 'GET' and response.status_code == 200:
		content_type = response.content_type or ''
		if any(ct in content_type for ct in ('text/html', 'application/json', 'text/', 'application/javascript', 'image/svg+xml')):
			resp_data = response.get_data()

	# ETag
	if resp_data is not None and response.status_code == 200:
		content_type = response.content_type or ''
		if any(ct in content_type for ct in ('text/html', 'application/json')):
			if resp_data:
				etag = _hashlib.md5(resp_data).hexdigest()[:16]
				response.headers['ETag'] = f'"{etag}"'
				if response.headers.get('ETag') == request.headers.get('If-None-Match'):
					response.status_code = 304
					response.set_data(b'')
					response.headers['Content-Length'] = '0'
					response.headers.pop('Content-Encoding', None)
					return response

	# gzip 压缩（复用已读取的 resp_data）
	accept_encoding = request.headers.get('Accept-Encoding', '')
	if 'gzip' in accept_encoding and response.status_code < 500:
		content_type = response.content_type or ''
		if any(ct in content_type for ct in ('text/', 'application/json', 'application/javascript', 'image/svg+xml')):
			if resp_data is None:
				resp_data = response.get_data()
			if len(resp_data) > 500:
				buf = _BytesIO()
				with gzip.GzipFile(fileobj=buf, mode='wb', compresslevel=6) as f:
					f.write(resp_data)
				gz_data = buf.getvalue()
				buf.close()
				response.set_data(gz_data)
				response.headers['Content-Encoding'] = 'gzip'
				response.headers['Content-Length'] = len(gz_data)
				response.headers['Vary'] = 'Accept-Encoding'

	return response
