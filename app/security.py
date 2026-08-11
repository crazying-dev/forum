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

# 黑名单容量上限：超过后只保留内存中最新的一半，并持久化到文件
# （防止长期被扫描时 set 无限膨胀，超过 10 万条约占几 MB）
_MAX_BLACKLIST_SIZE = 100000


def _load_blacklist():
	"""加载 IP 黑名单 JSON 文件（加载时自动按容量上限截断，避免超大数据）。"""
	global _ip_blacklist, _ip_blacklist_loaded
	with _ip_lock:
		if _ip_blacklist_loaded:
			return
		try:
			os.makedirs(os.path.dirname(IP_LIST_PATH), exist_ok=True)
			if os.path.exists(IP_LIST_PATH):
				with open(IP_LIST_PATH, 'r', encoding='utf-8') as f:
					data = json.load(f)
					blocked = data.get('blocked', [])
					# 超过上限时只保留末尾（最新）的部分
					if len(blocked) > _MAX_BLACKLIST_SIZE:
						blocked = blocked[-_MAX_BLACKLIST_SIZE:]
					_ip_blacklist = set(blocked)
			else:
				_save_blacklist()
			_ip_blacklist_loaded = True
			print(f"[SECURITY] IP 黑名单已加载: {len(_ip_blacklist)} 个")
		except Exception as e:
			print(f"[SECURITY] 加载黑名单失败: {e}")


def _save_blacklist():
	"""保存 IP 黑名单到 JSON 文件（超过上限时裁剪后再写入）。"""
	try:
		os.makedirs(os.path.dirname(IP_LIST_PATH), exist_ok=True)
		blocked_list = list(_ip_blacklist)
		if len(blocked_list) > _MAX_BLACKLIST_SIZE:
			# 超量时随机截断一部分（set 无顺序概念，简单切片即可）
			blocked_list = blocked_list[-_MAX_BLACKLIST_SIZE:]
			_ip_blacklist.intersection_update(blocked_list)
		data = {
			'blocked': sorted(blocked_list),
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
	"""将 IP 加入黑名单并写入文件；超上限时先裁剪。"""
	with _ip_lock:
		if client_ip in _ip_blacklist:
			return
		_ip_blacklist.add(client_ip)
		if len(_ip_blacklist) > _MAX_BLACKLIST_SIZE:
			# 随机删除一批以回到上限（保持大约 80% 水位）
			trim_target = int(_MAX_BLACKLIST_SIZE * 0.8)
			extra = list(_ip_blacklist)[:len(_ip_blacklist) - trim_target]
			_ip_blacklist.difference_update(extra)
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
GLOBAL_MAX_REQUESTS = 300   # 每窗口最大请求数
GLOBAL_WINDOW = 60          # 窗口时长（秒）

# _freq_store 硬上限：超过后立刻清理（避免短时间被大量IP打爆内存）
_MAX_FREQ_STORE_SIZE = 50000


def _cleanup_freq(now):
	"""定期清理过期记录（按时间 + 按容量双重触发）。"""
	global _freq_cleanup_at
	store_size = len(_freq_store)
	need_clean = (
		(now - _freq_cleanup_at) >= 300  # 每 5 分钟必清一次
		or store_size > _MAX_FREQ_STORE_SIZE
	)
	if not need_clean:
		return
	_freq_cleanup_at = now
	cutoff = now - GLOBAL_WINDOW
	# 先删除完全过期的 IP
	stale = [ip for ip, ts_list in _freq_store.items()
	         if not any(t > cutoff for t in ts_list)]
	for ip in stale:
		_freq_store.pop(ip, None)
	# 如果仍然过大，说明窗口内活跃 IP 超多，再按 LRU 风格清理（保留有最近时间戳的）
	if len(_freq_store) > _MAX_FREQ_STORE_SIZE:
		cutoff2 = now - 30  # 近 30 秒有活动的保留
		stale2 = [ip for ip, ts_list in _freq_store.items()
		          if not any(t > cutoff2 for t in ts_list)]
		for ip in stale2:
			_freq_store.pop(ip, None)
		# 还大就粗暴砍一半
		if len(_freq_store) > _MAX_FREQ_STORE_SIZE:
			keys = list(_freq_store.keys())
			drop = keys[:len(keys) - _MAX_FREQ_STORE_SIZE]
			for ip in drop:
				_freq_store.pop(ip, None)


# ── 恶意 IP 日志写入去重缓存（避免每次都读整份日志文件） ──
_reported_ip_lock = Lock()
_reported_ip_set = set()   # 已写入日志的 IP，内存去重
_REPORTED_SET_MAX = 100000  # 上限，超过后重置并在下一次写入时从文件同步一次


def _ensure_reported_set_loaded(log_path):
	"""确保内存中 _reported_ip_set 已从文件同步（懒加载 + 超限重置）。"""
	global _reported_ip_set
	if len(_reported_ip_set) >= _REPORTED_SET_MAX:
		# 超过上限后重置，让下面重新从文件加载最新部分
		_reported_ip_set.clear()
	if _reported_ip_set:
		return  # 已有内容，无需每次都读文件
	try:
		if os.path.exists(log_path):
			# 只读取文件末尾的 _REPORTED_SET_MAX 行做去重（避免超日志文件时读爆内存）
			lines = []
			with open(log_path, 'r', encoding='utf-8') as f:
				# 简单倒推：按行迭代但只保留最后 N 行
				from collections import deque
				lines = deque(f, maxlen=_REPORTED_SET_MAX)
			for line in lines:
				line = line.strip()
				if line:
					ip = line.split('#')[0].strip()
					if ip:
						_reported_ip_set.add(ip)
	except Exception as e:
		print(f"[SECURITY] 加载 IP 日志去重缓存失败: {e}")


def _report_ip(client_ip, reason):
	"""记录恶意 IP：写日志 + 加入黑名单（用内存set去重，避免每次读全文件）。"""
	log_path = '/root/IP.txt'
	entry = f"{client_ip}  # {time.strftime('%Y-%m-%d %H:%M:%S')}  {reason}"
	try:
		os.makedirs(os.path.dirname(log_path), exist_ok=True)

		with _reported_ip_lock:
			_ensure_reported_set_loaded(log_path)
			already_written = client_ip in _reported_ip_set
			if not already_written:
				with open(log_path, 'a', encoding='utf-8') as f:
					f.write(entry + '\n')
				_reported_ip_set.add(client_ip)
				print(f"[SECURITY] 恶意 IP 已记录: {entry}")

		# 无论是否已在日志中，都要加入 JSON 黑名单
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