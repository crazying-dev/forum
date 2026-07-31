# -*- coding: utf-8 -*-
"""IP 安全防护模块。

检测恶意 IP：
  1. 访问危险路径（.git/.env/常见漏洞扫描路径等）
  2. 请求频率过高
  3. 命中 /root/db/forum_IP.json 黑名单
检测到恶意行为后写入黑名单，黑名单内 IP 直接返回 500。
"""
import os
import re
import json
import time
from threading import Lock
from flask import request, jsonify

# ── IP 黑名单 JSON 文件 ─────────────────────────────────

IP_LIST_PATH = '/root/db/forum_IP.json'
_ip_lock = Lock()
_ip_blacklist = set()
_ip_blacklist_loaded = False


def _load_blacklist():
	"""加载 IP 黑名单 JSON 文件。"""
	global _ip_blacklist, _ip_blacklist_loaded
	with _ip_lock:
		if _ip_blacklist_loaded:
			return
		try:
			os.makedirs(os.path.dirname(IP_LIST_PATH), exist_ok=True)
			if os.path.exists(IP_LIST_PATH):
				with open(IP_LIST_PATH, 'r', encoding='utf-8') as f:
					data = json.load(f)
					_ip_blacklist = set(data.get('blocked', []))
			else:
				_save_blacklist()
			_ip_blacklist_loaded = True
			print(f"[SECURITY] IP 黑名单已加载: {len(_ip_blacklist)} 个")
		except Exception as e:
			print(f"[SECURITY] 加载黑名单失败: {e}")


def _save_blacklist():
	"""保存 IP 黑名单到 JSON 文件。"""
	try:
		os.makedirs(os.path.dirname(IP_LIST_PATH), exist_ok=True)
		data = {
			'blocked': sorted(_ip_blacklist),
			'updated': time.strftime('%Y-%m-%d %H:%M:%S')
		}
		with open(IP_LIST_PATH, 'w', encoding='utf-8') as f:
			json.dump(data, f, ensure_ascii=False, indent=2)
	except Exception as e:
		print(f"[SECURITY] 保存黑名单失败: {e}")


def _is_ip_blocked(client_ip):
	"""检查 IP 是否在黑名单中。"""
	return client_ip in _ip_blacklist


def _add_ip_to_blacklist(client_ip, reason):
	"""将 IP 加入黑名单并写入文件。"""
	with _ip_lock:
		if client_ip in _ip_blacklist:
			return
		_ip_blacklist.add(client_ip)
		_save_blacklist()
	print(f"[SECURITY] IP 已加入黑名单: {client_ip} ({reason})")




# ── 危险路径模式 ──────────────────────────────────────────

_MALICIOUS_PATTERNS = [
	# 版本控制
	r'\.git(/|$)',
	r'\.svn(/|$)',
	r'\.hg(/|$)',

	# 敏感配置文件
	r'\.env(\.|$)',
	r'\.aws(/|$)',
	r'\.htaccess',
	r'\.htpasswd',
	r'wp-config\.php',
	r'config\.(inc\.)?php',
	r'web\.config',
	r'application\.properties',
	r'application\.yml',

	# 常见攻击面板
	r'wp-admin(/|$)',
	r'wp-login\.php',
	r'wp-content(/|$)',
	r'wp-includes(/|$)',
	r'xmlrpc\.php',
	r'phpmyadmin(/|$)',
	r'phpMyAdmin(/|$)',
	r'pma(/|$)',
	r'PMA(/|$)',
	r'admin(/|$)',
	r'administrator(/|$)',
	r'manager(/|$)',

	# 数据备份泄露
	r'backup\.(sql|zip|tar|gz)',
	r'dump\.(sql|zip)',
	r'database\.(sql|zip)',
	r'\.sql$',
	r'\.bz2$',

	# 常见漏洞扫描
	r'nmaplowercheck',
	r'actuator(/|$)',
	r'swagger',
	r'api-docs',
	r'cgi-bin(/|$)',
	r'console(/|$)',
	r'jmx-console',
	r'web-console',

	# 路径穿越
	r'\.\./',
	r'\.\.%2f',
	r'\.\.%252f',

	# 敏感文件
	r'\.DS_Store',
	r'Thumbs\.db',
	r'id_rsa',
	r'id_dsa',
	r'known_hosts',

	# 常见攻击 Payload
	r'/etc/passwd',
	r'/etc/shadow',
	r'cmd\.exe',
	r'powershell',

	# 其他风险路径
	r'/.well-known/security\.txt',
	r'vendor(/|$)',
	r'node_modules(/|$)',
	r'Dockerfile',
	r'docker-compose',
]

_compiled_patterns = [re.compile(p, re.IGNORECASE) for p in _MALICIOUS_PATTERNS]


# ── 频率追踪 ──────────────────────────────────────────────

_freq_lock = Lock()
_freq_store = {}     # {ip: [timestamps]}
_freq_cleanup_at = 0  # 上次清理时间

# 全局频率阈值（所有请求，不论路径）
GLOBAL_MAX_REQUESTS = 120   # 每窗口最大请求数
GLOBAL_WINDOW = 60          # 窗口时长（秒）


def _cleanup_freq(now):
	"""定期清理过期记录。"""
	global _freq_cleanup_at
	if now - _freq_cleanup_at < 300:  # 每 5 分钟清一次
		return
	_freq_cleanup_at = now
	cutoff = now - GLOBAL_WINDOW
	stale = [ip for ip, ts_list in _freq_store.items()
	         if not any(t > cutoff for t in ts_list)]
	for ip in stale:
		_freq_store.pop(ip, None)


def _report_ip(client_ip, reason):
	"""记录恶意 IP：写日志 + 首次时通过宝塔 API 封禁。"""
	log_path = '/root/IP.txt'
	entry = f"{client_ip}  # {time.strftime('%Y-%m-%d %H:%M:%S')}  {reason}"
	try:
		os.makedirs(os.path.dirname(log_path), exist_ok=True)

		existing = set()
		if os.path.exists(log_path):
			with open(log_path, 'r', encoding='utf-8') as f:
				for line in f:
					line = line.strip()
					if line:
						existing.add(line.split('#')[0].strip())

		if client_ip not in existing:
			with open(log_path, 'a', encoding='utf-8') as f:
				f.write(entry + '\n')
			print(f"[SECURITY] 恶意 IP 已记录: {entry}")

			# 加入黑名单
			_add_ip_to_blacklist(client_ip, reason)
	except Exception as e:
		print(f"[SECURITY] 写入 IP 日志失败: {e}")


# ── 检测函数 ──────────────────────────────────────────────

def detect_malicious():
	"""检测当前请求是否为恶意访问。

	在 before_request 中调用。如果检测到恶意行为，
	记录 IP 并返回一个 404/403 响应阻断请求。

	Returns:
	"""
	_load_blacklist()
	client_ip = request.remote_addr or 'unknown'
	path = request.path or ''
	now = time.time()

	# ── 0. 黑名单优先检测 ──
	if _is_ip_blocked(client_ip):
		return jsonify({'error': 'Internal Server Error'}), 500

	# ── 1. 危险路径检测 ──
	for pattern in _compiled_patterns:
		if pattern.search(path):
			_report_ip(client_ip, f"恶意路径: {path}")
			# 返回 404 迷惑攻击者（不要返回 403 暴露防护细节）
			return jsonify({'error': 'Not Found'}), 404

	# ── 2. 全局频率检测 ──
	with _freq_lock:
		_cleanup_freq(now)
		ts_list = _freq_store.get(client_ip, [])
		ts_list = [t for t in ts_list if t > now - GLOBAL_WINDOW]
		ts_list.append(now)
		_freq_store[client_ip] = ts_list

		if len(ts_list) > GLOBAL_MAX_REQUESTS:
			_report_ip(client_ip,
			           f"频率过高: {len(ts_list)} req/{GLOBAL_WINDOW}s")
			return jsonify({'error': 'Too Many Requests'}), 429

	return None