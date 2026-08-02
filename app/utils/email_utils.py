# -*- coding: utf-8 -*-
"""邮箱验证工具。

  邮箱格式正则校验 + 域名黑名单。
  黑名单文件：/root/db/MailBreak.json
  格式：{"blocked": ["tempmail.com", "disposable.org"]}
"""
import os
import re
import json
from threading import Lock

# 邮箱格式正则（RFC 5322 简化版）
EMAIL_REGEX = re.compile(
	r'^[a-zA-Z0-9.!#$%&\'*+/=?^_{|}~-]+'
	r'@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?'
	r'(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$'
)

BLACKLIST_PATH = '/root/db/MailBreak.json'
_lock = Lock()
_blacklist = None


def _load_blacklist():
	"""加载邮箱域名黑名单（懒加载 + 缓存）。"""
	global _blacklist
	with _lock:
		if _blacklist is not None:
			return _blacklist
		try:
			os.makedirs(os.path.dirname(BLACKLIST_PATH), exist_ok=True)
			if os.path.exists(BLACKLIST_PATH):
				with open(BLACKLIST_PATH, 'r', encoding='utf-8') as f:
					data = json.load(f)
					_blacklist = set(data.get('blocked', []))
			else:
				_save_blacklist(set())
				_blacklist = set()
			print(f"[EMAIL] 域名黑名单已加载: {len(_blacklist)} 个")
		except Exception as e:
			print(f"[EMAIL] 加载黑名单失败: {e}")
			_blacklist = set()
	return _blacklist


def _save_blacklist(domains):
	"""保存黑名单到 JSON 文件。"""
	try:
		os.makedirs(os.path.dirname(BLACKLIST_PATH), exist_ok=True)
		with open(BLACKLIST_PATH, 'w', encoding='utf-8') as f:
			json.dump({'blocked': sorted(domains)}, f, ensure_ascii=False, indent=2)
	except Exception as e:
		print(f"[EMAIL] 保存黑名单失败: {e}")


def validate_email(email):
	"""校验邮箱格式并检查域名黑名单。

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

	# 提取域名部分
	parts = email.split('@')
	if len(parts) != 2:
		return False, '邮箱格式不正确'

	domain = parts[1]

	# 检查黑名单
	blacklist = _load_blacklist()
	for blocked in blacklist:
		if domain == blocked or domain.endswith('.' + blocked):
			return False, '不支持的邮箱服务商，请使用其他邮箱'

	return True, ''