# -*- coding: utf-8 -*-
"""邮箱验证工具。

  邮箱格式正则校验 + 临时邮箱域名检测（调用 mail-checker API）。
  API：https://mail-checker.unknownmp.de5.net/api/v1/verify/domain/{domain}
"""
import re
import time
from collections import OrderedDict
import requests
from threading import Lock

# 邮箱格式正则（RFC 5322 简化版）
EMAIL_REGEX = re.compile(
	r'^[a-zA-Z0-9.!#$%&\'*+/=?^_{|}~-]+'
	r'@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?'
	r'(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$'
)

# 域名检测缓存：使用 OrderedDict 实现 LRU，限制容量
_domain_lock = Lock()
_domain_cache = OrderedDict()  # {domain: (is_disposable, cached_at)}
_CACHE_TTL = 3600              # 缓存 1 小时
_MAX_CACHE_SIZE = 5000         # 最大缓存条目（限制内存上限）
_LAST_DOMAIN_CLEANUP = 0.0     # 上次清理过期条目的时间戳

CHECK_API = 'https://mail-checker.unknownmp.de5.net/api/v1/verify/domain/{}'


def _cleanup_domain_cache(now):
	"""主动清理过期条目（按 TTL），并裁剪超过容量上限的条目（LRU 淘汰）。"""
	global _LAST_DOMAIN_CLEANUP
	# 最多 60 秒清一次，避免每次加锁扫字典
	if now - _LAST_DOMAIN_CLEANUP < 60:
		return
	_LAST_DOMAIN_CLEANUP = now
	cutoff = now - _CACHE_TTL
	# 先移除过期
	stale = [k for k, (_, ts) in _domain_cache.items() if ts < cutoff]
	for k in stale:
		_domain_cache.pop(k, None)
	# 再按 LRU 裁剪容量（末尾是最新，popitem(last=False) 淘汰最旧）
	while len(_domain_cache) > _MAX_CACHE_SIZE:
		_domain_cache.popitem(last=False)


def _check_domain(domain):
	"""检测域名是否为临时邮箱（带缓存 + TTL + LRU 上限）。

	Returns:
		True  — 是临时邮箱（应拒绝）
		False — 正常邮箱（允许）
	"""
	now = time.time()
	with _domain_lock:
		_cleanup_domain_cache(now)
		cached = _domain_cache.get(domain)
		if cached and now - cached[1] < _CACHE_TTL:
			# 命中：移到末尾（LRU 标记为最新）
			_domain_cache.move_to_end(domain)
			return cached[0]
		# 过期或不存在：删除可能存在的过期旧条目
		_domain_cache.pop(domain, None)

	try:
		resp = requests.get(CHECK_API.format(domain), timeout=5)
		if resp.status_code == 200:
			data = resp.json()
			is_disposable = data.get('is_disposable', False)
		else:
			is_disposable = False
	except Exception as e:
		print(f"[EMAIL] API 检测失败 {domain}: {e}")
		is_disposable = False  # API 不可用时不阻断

	with _domain_lock:
		# 写缓存（末尾 = 最新）
		_domain_cache[domain] = (is_disposable, now)
		# 写完再裁剪一次，保证不爆上限
		while len(_domain_cache) > _MAX_CACHE_SIZE:
			_domain_cache.popitem(last=False)

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