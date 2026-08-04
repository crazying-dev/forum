# -*- coding: utf-8 -*-
"""邮箱验证工具。

  邮箱格式正则校验 + 临时邮箱域名检测（调用 mail-checker API）。
  API：https://mail-checker.unknownmp.de5.net/api/v1/verify/domain/{domain}
"""
import re
import time
import requests
from threading import Lock

# 邮箱格式正则（RFC 5322 简化版）
EMAIL_REGEX = re.compile(
	r'^[a-zA-Z0-9.!#$%&\'*+/=?^_{|}~-]+'
	r'@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?'
	r'(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$'
)

# 域名检测缓存
_domain_lock = Lock()
_domain_cache = {}       # {domain: (is_disposable, cached_at)}
_CACHE_TTL = 3600        # 缓存 1 小时

CHECK_API = 'https://mail-checker.unknownmp.de5.net/api/v1/verify/domain/{}'


def _check_domain(domain):
	"""检测域名是否为临时邮箱（带缓存）。

	Returns:
		True  — 是临时邮箱（应拒绝）
		False — 正常邮箱（允许）
	"""
	now = time.time()
	with _domain_lock:
		cached = _domain_cache.get(domain)
		if cached and now - cached[1] < _CACHE_TTL:
			return cached[0]

	try:
		resp = requests.get(CHECK_API.format(domain), timeout=5)
		if resp.status_code == 200:
			data = resp.json()
			is_disposable = data.get('is_disposable', False)
	except Exception as e:
		print(f"[EMAIL] API 检测失败 {domain}: {e}")
		is_disposable = False  # API 不可用时不阻断

	with _domain_lock:
		_domain_cache[domain] = (is_disposable, now)

	return is_disposable


def validate_email(email):
	"""校验邮箱格式并检测临时邮箱域名。

    Args:
        email: 邮箱地址

    Returns:
        (valid: bool, error_msg: str)
        - (True, '') — 校验通过
        - (False, msg) — 格式错误或域名被阻止
    """
	if not email or not isinstance(email, str):
		return False, '请输入邮箱地址'

	email = email.strip().lower()

	if not EMAIL_REGEX.match(email):
		return False, '邮箱格式不正确'

	parts = email.split('@')
	if len(parts) != 2:
		return False, '邮箱格式不正确'

	domain = parts[1]

	if _check_domain(domain):
		return False, '不支持的邮箱服务商，请使用其他邮箱'

	return True, ''