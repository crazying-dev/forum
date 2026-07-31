# -*- coding: utf-8 -*-
"""IP 安全防护模块。

检测恶意 IP：
  1. 访问危险路径（.git/.env/常见漏洞扫描路径等）
  2. 请求频率过高
检测到恶意行为后：
  - 写入 /root/IP.txt 日志
  - 通过 iptables 封禁 IP
"""
import os
import re
import time
import subprocess
import threading
from threading import Lock
from flask import request, jsonify

# ── 命令行封禁 ──────────────────────────────────────────

_blocked_cache = {}      # {ip: timestamp} 避免重复封禁
_BLOCK_COOLDOWN = 600    # 同一 IP 10 分钟内不重复

# 可通过环境变量自定义封禁命令，默认用 iptables
BLOCK_CMD = os.getenv('BLOCK_CMD', 'iptables -A INPUT -s {ip} -j DROP -m comment --comment "{reason}"')


def _block_ip(client_ip, reason):
	"""通过命令行封禁 IP。"""
	now = time.time()
	if now - _blocked_cache.get(client_ip, 0) < _BLOCK_COOLDOWN:
		return
	_blocked_cache[client_ip] = now

	cmd = BLOCK_CMD.format(ip=client_ip, reason=reason)
	try:
		result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
		if result.returncode == 0:
			print(f"[SECURITY] iptables 封禁 {client_ip} OK")
		else:
			print(f"[SECURITY] iptables 失败 {client_ip}: {result.stderr.strip()}")
	except subprocess.TimeoutExpired:
		print(f"[SECURITY] iptables 超时 {client_ip}")
	except Exception as e:
		print(f"[SECURITY] iptables 异常 {client_ip}: {e}")




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

			# 通过宝塔 API 封禁 IP
			_block_ip(client_ip, reason)
	except Exception as e:
		print(f"[SECURITY] 写入 IP 日志失败: {e}")


# ── 检测函数 ──────────────────────────────────────────────

def detect_malicious():
	"""检测当前请求是否为恶意访问。

	在 before_request 中调用。如果检测到恶意行为，
	记录 IP 并返回一个 404/403 响应阻断请求。

	Returns:
		None（安全）或 Flask Response（需立即返回阻断）
	"""
	client_ip = request.remote_addr or 'unknown'
	path = request.path or ''
	now = time.time()

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