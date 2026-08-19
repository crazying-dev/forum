# -*- coding: utf-8 -*-
"""IP 安全防护模块。

检测恶意 IP：
  1. 访问危险路径（.git/.env/常见漏洞扫描路径等）
  2. 请求频率过高
  3. 命中 /root/db/forum_IP.json 黑名单
检测到恶意行为后写入黑名单，命中黑名单的 IP 从 [250,500,502,666,888] 中随机返回一个码。

持久化策略（写进文件为前提，异步 + 批量/定时）：
  - 每次封禁：先写入内存 set，**同时异步把这条 IP 追加写入 WAL 日志文件**（单行 append，
    必定落盘，不是只放内存等定时）。
  - 定时合并：每 30s 把 WAL + 内存快照合并到主 JSON（forum_IP.json 原子替换写盘），
    合并完成后清空 WAL。
  - 进程退出：强制合并一次。
  - 启动加载：先读主 JSON，再回放 WAL 日志里的所有 IP 补齐，避免崩溃时 WAL 还没收尾。

黑名单有效期：
  - 黑名单中的 IP 永久有效，不设过期。
"""
import os
import re
import json
import time
import random
import atexit
import threading
from threading import Lock
from flask import request, jsonify

# ── IP 黑名单文件路径 ────────────────────────────────────

IP_LIST_PATH = '/root/db/forum_IP.json'
IP_WAL_PATH = '/root/db/forum_IP.wal.log'

_ip_lock = Lock()
_wal_lock = Lock()
_ip_blacklist = set()
_ip_blacklist_loaded = False

# 合并（写主 JSON）的定时兜底间隔
_MERGE_INTERVAL_SECONDS = 30

# 后台定时合并线程
_merge_scheduler_thread = None
_merge_scheduler_started = False
_merge_worker_running = True


# ── WAL 追加写入（每条封禁必定落盘，不阻塞请求） ────────

def _wal_append_async(client_ip: str):
    """把一个 IP 异步 append 到 WAL 日志文件。
    即使 30s 内进程崩溃，下次启动也能从 WAL 回放回来。"""
    def _runner():
        try:
            os.makedirs(os.path.dirname(IP_WAL_PATH), exist_ok=True)
            # 写 WAL 是单行 append，持锁范围很小
            with _wal_lock:
                with open(IP_WAL_PATH, 'a', encoding='utf-8') as f:
                    f.write(client_ip.strip() + '\n')
        except Exception as e:
            print(f"[SECURITY] WAL 追加写入失败 ({client_ip}): {e}")
    t = threading.Thread(target=_runner, name='blacklist-wal-append', daemon=True)
    t.start()


# ── 主 JSON + WAL 合并（定时 + 退出触发） ────────────────

def _merge_wal_into_main(clear_wal_after: bool = True):
    """把当前内存 set + WAL 日志合并到主 JSON。
    合并采用原子替换写 tmp + os.replace。
    """
    try:
        os.makedirs(os.path.dirname(IP_LIST_PATH), exist_ok=True)
        # 1) 先把 WAL 中可能的增量（比如启动前崩溃遗留 / 并发 append）并入内存
        try:
            if os.path.exists(IP_WAL_PATH):
                with _wal_lock:
                    with open(IP_WAL_PATH, 'r', encoding='utf-8') as f:
                        lines = [ln.strip() for ln in f if ln.strip()]
                if lines:
                    with _ip_lock:
                        for ip in lines:
                            if ip:
                                _ip_blacklist.add(ip)
        except Exception as e:
            print(f"[SECURITY] 读取 WAL 增量失败: {e}")
            # 即使 WAL 读失败也继续，至少把内存快照写进去

        # 2) 写主 JSON 快照（原子替换）
        with _ip_lock:
            snapshot = sorted(list(_ip_blacklist))
        data = {
            'blocked': snapshot,
            'updated': time.strftime('%Y-%m-%d %H:%M:%S')
        }
        tmp_path = IP_LIST_PATH + '.tmp'
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, IP_LIST_PATH)

        # 3) 合并成功后清空 WAL
        if clear_wal_after:
            try:
                with _wal_lock:
                    if os.path.exists(IP_WAL_PATH):
                        os.remove(IP_WAL_PATH)
            except Exception as e:
                print(f"[SECURITY] 清空 WAL 失败: {e}")
    except Exception as e:
        print(f"[SECURITY] 合并黑名单到主文件失败: {e}")


def _merge_scheduler_loop():
    while _merge_worker_running:
        try:
            time.sleep(_MERGE_INTERVAL_SECONDS)
            _merge_wal_into_main(clear_wal_after=True)
        except Exception as e:
            print(f"[SECURITY] 定时合并黑名单异常: {e}")


def _ensure_merge_scheduler_started():
    global _merge_scheduler_started, _merge_scheduler_thread
    if _merge_scheduler_started:
        return
    with _wal_lock:
        if _merge_scheduler_started:
            return
        _merge_scheduler_thread = threading.Thread(
            target=_merge_scheduler_loop,
            name='blacklist-merge-scheduler',
            daemon=True,
        )
        _merge_scheduler_thread.start()
        atexit.register(_merge_on_exit)
        _merge_scheduler_started = True


def _merge_on_exit():
    global _merge_worker_running
    _merge_worker_running = False
    try:
        _merge_wal_into_main(clear_wal_after=True)
    except Exception:
        pass


# ── 加载（主 JSON + WAL 回放，保证重启不漏 IP） ─────────

def _load_blacklist():
    """加载 IP 黑名单。
    先读主 JSON，再回放 WAL 日志里的 IP 合并进来（永久有效，不做任何过期过滤/容量裁剪）。"""
    global _ip_blacklist, _ip_blacklist_loaded
    with _ip_lock:
        if _ip_blacklist_loaded:
            return
        try:
            os.makedirs(os.path.dirname(IP_LIST_PATH), exist_ok=True)
            os.makedirs(os.path.dirname(IP_WAL_PATH), exist_ok=True)
            merged = set()
            # 1) 主 JSON
            if os.path.exists(IP_LIST_PATH):
                with open(IP_LIST_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    blocked = data.get('blocked', []) or []
                    for ip in blocked:
                        if ip:
                            merged.add(ip)
            # 2) WAL 回放（上次崩溃遗留的增量）
            if os.path.exists(IP_WAL_PATH):
                with open(IP_WAL_PATH, 'r', encoding='utf-8') as f:
                    for ln in f:
                        ip = ln.strip()
                        if ip:
                            merged.add(ip)
            _ip_blacklist = merged
            # 首次加载就尝试合并一次（把 WAL 里的遗留增量正式合并进主 JSON）
            _ip_blacklist_loaded = True
            print(f"[SECURITY] IP 黑名单已加载: {len(_ip_blacklist)} 个")
        except Exception as e:
            print(f"[SECURITY] 加载黑名单失败: {e}")
    # 启动定时合并线程 + 先合并一次把刚才回放的 WAL 写进主 JSON
    _ensure_merge_scheduler_started()
    _merge_wal_into_main(clear_wal_after=True)


def _save_blacklist():
    """对外兼容接口：立即合并 + 落盘（主 JSON + 清空 WAL）。"""
    _merge_wal_into_main(clear_wal_after=True)


def _is_ip_blocked(client_ip):
    return client_ip in _ip_blacklist


def _add_ip_to_blacklist(client_ip, reason):
    """将 IP 加入黑名单：
      1) 先写内存 set（立即生效，命中黑名单直接拦截）
      2) 异步立刻 append 到 WAL 日志文件（每条必定落盘，不等定时）
      3) 30s 定时/退出时，WAL 合并进主 JSON 并清空。
    IP 永久有效，不做容量裁剪。
    """
    changed = False
    with _ip_lock:
        if client_ip not in _ip_blacklist:
            _ip_blacklist.add(client_ip)
            changed = True
    if changed:
        _ensure_merge_scheduler_started()
        _wal_append_async(client_ip)
    print(f"[SECURITY] IP 已加入黑名单: {client_ip} ({reason})")


# 封禁命中时使用的随机返回码池
_BAN_STATUS_POOL = (250, 500, 502, 666, 888)
_BAN_STATUS_POOL_LEN = len(_BAN_STATUS_POOL)


def _random_ban_status():
    return _BAN_STATUS_POOL[random.randrange(_BAN_STATUS_POOL_LEN)]






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
		return jsonify({'error': 'Internal Server Error'}), _random_ban_status()

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