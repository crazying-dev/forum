# -*- coding: utf-8 -*-
"""后端接口层（唯一出网入口）。

* 基于 ``requests.Session``，自己管理 Cookie（token / ID）并持久化到 :mod:`app.session_store`
* 响应解析「宽松」：部分接口（如 ``/api/posts``）不返回 ``success`` 字段，
  只要 HTTP < 400 且能解出 JSON 就当作成功；错误文案优先取 ``message``
* 所有阻塞调用通过 :func:`run_async` 丢到 QThreadPool，回调在 **主线程** 执行
"""

from __future__ import annotations

import json as _json
import threading
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import requests
from PyQt6.QtCore import QObject, QRunnable, QThreadPool, QTimer, pyqtSignal

from . import constants, logger, session_store

_log = logger.get_logger("api")

NET_ERROR_TEXT = "网络错误，请检查网络连接后重试"
REQUEST_FAILED_TEXT = "请求失败"
PARSE_ERROR_TEXT = "响应解析失败"


# ────────────────────────── 响应包装 ──────────────────────────


class Result:
    """统一的接口返回包装。"""

    __slots__ = ("status", "data", "error", "url")

    def __init__(self, status: int = 0, data: Any = None,
                 error: str | None = None, url: str = "") -> None:
        self.status = status
        self.data = data
        self.error = error
        self.url = url

    @property
    def ok(self) -> bool:
        if self.error:
            return False
        if self.status and self.status >= 400:
            return False
        if self.data is None:
            return False
        if isinstance(self.data, dict) and self.data.get("success") is False:
            return False
        return True

    @property
    def message(self) -> str:
        data = self.data
        if isinstance(data, dict):
            for key in ("message", "error", "msg", "detail"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        if self.ok:
            return ""
        if self.error:
            return str(self.error)
        if self.status == 401:
            return "请先登录"
        if self.status == 403:
            return "没有权限"
        if self.status == 404:
            return "内容不存在或已被删除"
        if self.status == 429:
            return "操作过于频繁，请稍后再试"
        if self.status and self.status >= 500:
            return "服务器开小差了，请稍后再试"
        if self.status and self.status >= 400:
            return "请求失败（HTTP %s）" % self.status
        return REQUEST_FAILED_TEXT

    @property
    def is_unauthorized(self) -> bool:
        return self.status == 401

    def get(self, key: str, default: Any = None) -> Any:
        if isinstance(self.data, dict):
            return self.data.get(key, default)
        return default

    def rows(self, key: str) -> list:
        value = self.get(key)
        return value if isinstance(value, list) else []

    def __repr__(self) -> str:  # pragma: no cover
        return "<Result %s ok=%s>" % (self.status, self.ok)


# ────────────────────────── 异步执行 ──────────────────────────


class _TaskSignals(QObject):
    done = pyqtSignal(object)
    failed = pyqtSignal(str)


class _Task(QRunnable):
    def __init__(self, fn: Callable[[], Any]) -> None:
        super().__init__()
        self._fn = fn
        self.signals = _TaskSignals()
        self.setAutoDelete(True)

    def run(self) -> None:  # pragma: no cover - 线程内执行
        try:
            value = self._fn()
        except Exception as exc:  # noqa: BLE001
            _log.error("异步任务异常：%s", exc, exc_info=True)
            try:
                self.signals.failed.emit(str(exc))
            except RuntimeError:
                pass
            return
        try:
            self.signals.done.emit(value)
        except RuntimeError:
            # 解释器退出阶段信号对象可能已被回收
            pass


_alive: set = set()


def run_async(fn: Callable[[], Any], on_success: Callable | None = None,
              on_error: Callable | None = None, label: str = "") -> None:
    """在线程池里执行 ``fn``，回调在主线程。"""
    task = _Task(fn)
    _alive.add(task)

    def _cleanup(*_args) -> None:
        # 延迟丢弃引用：排队中的信号投递完成前不能释放 _Task.signals，
        # 否则会报 "wrapped C/C++ object of type _TaskSignals has been deleted"。
        QTimer.singleShot(100, lambda t=task: _alive.discard(t))

    if on_success is not None:
        task.signals.done.connect(on_success)
    task.signals.done.connect(_cleanup)
    if on_error is not None:
        task.signals.failed.connect(on_error)
    else:
        task.signals.failed.connect(
            lambda msg, _l=label: _log.error("[%s] %s", _l or "异步请求", msg))
    task.signals.failed.connect(_cleanup)
    QThreadPool.globalInstance().start(task)


def wait_for_pending(timeout_ms: int = 5000) -> None:
    """退出前等后台请求收尾，避免工作线程在解释器销毁时写已释放对象。"""
    try:
        pool = QThreadPool.globalInstance()
        pool.clear()
        pool.waitForDone(max(int(timeout_ms), 0))
    except Exception:
        pass


# ────────────────────────── 接口层 ──────────────────────────


class ForumApi:
    """妖精论坛后端接口封装。"""

    def __init__(self, base_url: str | None = None,
                 store: session_store.SessionStore | None = None,
                 timeout: tuple[int, int] = (10, 25)) -> None:
        self.base = (base_url or constants.BASE_URL).rstrip("/")
        self.store = store if store is not None else session_store.SessionStore()
        self._timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": constants.CLIENT_UA,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })
        self._lock = threading.RLock()
        self._user: dict | None = self.store.user
        self._unauth_listeners: list[Callable[[], None]] = []
        self._restore_cookies()

    # ── Cookie / 登录状态 ──
    def _host(self) -> str:
        try:
            return urlparse(self.base).hostname or ""
        except Exception:
            return ""

    def _restore_cookies(self) -> None:
        host = self._host()
        if not host:
            return
        for name, value in self.store.cookies.items():
            try:
                self.session.cookies.set(name, value, domain=host, path="/")
            except Exception:
                pass

    def _collect_cookies(self) -> dict[str, str]:
        out: dict[str, str] = {}
        try:
            for cookie in self.session.cookies:
                if cookie.name in session_store.COOKIE_NAMES and cookie.value:
                    out.setdefault(cookie.name, cookie.value)
        except Exception:
            pass
        return out

    def persist(self) -> None:
        self.store.save(self._collect_cookies(), self._user or None)

    @property
    def user(self) -> dict | None:
        return dict(self._user) if self._user else None

    @property
    def user_id(self) -> str:
        return str((self._user or {}).get("id") or "")

    @property
    def is_logged_in(self) -> bool:
        return bool(self._user) or self.store.has_credentials

    def set_user(self, user: dict | None, *, persist: bool = True) -> None:
        self._user = user or None
        if user and user.get("name"):
            self.store.save(None, user, last_name=str(user.get("name")))
        elif persist:
            self.store.save(None, self._user)

    def clear_login(self) -> None:
        self._user = None
        self.store.clear()
        try:
            self.session.cookies.clear()
        except Exception:
            pass

    def add_unauthorized_listener(self, fn: Callable[[], None]) -> None:
        if fn not in self._unauth_listeners:
            self._unauth_listeners.append(fn)

    def _notify_unauthorized(self) -> None:
        for fn in list(self._unauth_listeners):
            try:
                fn()
            except Exception:
                pass

    # ── 底层请求 ──
    def _url(self, path: str) -> str:
        if str(path).startswith(("http://", "https://")):
            return path
        return self.base + "/" + str(path).lstrip("/")

    def request(self, method: str, path: str, *, params: dict | None = None,
                json_body: Any = None, data: Any = None, files: Any = None,
                headers: dict | None = None, timeout: tuple[int, int] | None = None,
                retries: int = 2, notify_401: bool = True) -> Result:
        url = self._url(path)
        method = method.upper()
        request_headers = dict(headers or {})
        if json_body is not None and "Content-Type" not in request_headers:
            request_headers["Content-Type"] = "application/json; charset=utf-8"
        last_error = ""
        for attempt in range(retries + 1):
            try:
                response = self.session.request(
                    method, url, params=params, json=json_body,
                    data=data, files=files, headers=request_headers,
                    timeout=timeout or self._timeout,
                )
            except requests.exceptions.Timeout:
                last_error = "请求超时，请稍后重试"
                if method == "GET" and attempt < retries:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                break
            except requests.exceptions.SSLError as exc:
                last_error = "安全连接失败：%s" % exc
                break
            except requests.exceptions.ConnectionError as exc:
                last_error = NET_ERROR_TEXT
                _log.debug("连接失败（%s）：%s", url, exc)
                if attempt < retries:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                break
            except requests.RequestException as exc:
                last_error = NET_ERROR_TEXT
                _log.debug("请求异常（%s）：%s", url, exc)
                break

            status = response.status_code
            parsed: Any = None
            text = ""
            try:
                text = response.text
            except Exception:
                text = ""
            if text:
                try:
                    parsed = _json.loads(text)
                except ValueError:
                    parsed = None
            # 同步 Cookie → 本地凭证
            try:
                self._sync_cookies()
            except Exception:
                pass
            if status == 401 and notify_401:
                self._user = None
                self.store.save(self._collect_cookies(), None)
                self._notify_unauthorized()
            if parsed is None and status < 400 and text.strip():
                return Result(status, None, PARSE_ERROR_TEXT, url)
            return Result(status, parsed, None, url)
        return Result(0, None, last_error or NET_ERROR_TEXT, url)

    def _sync_cookies(self) -> None:
        cookies = self._collect_cookies()
        if cookies and cookies != self.store.cookies:
            self.store.save(cookies, self._user)

    def get(self, path: str, **params) -> Result:
        clean = {k: v for k, v in params.items() if v is not None and v != ""}
        return self.request("GET", path, params=clean or None)

    def post(self, path: str, payload: Any = None, **kw) -> Result:
        return self.request("POST", path, json_body=payload, **kw)

    def put(self, path: str, payload: Any = None, **kw) -> Result:
        return self.request("PUT", path, json_body=payload, **kw)

    def run(self, fn: Callable[[], Any], on_success: Callable | None = None,
            on_error: Callable | None = None, label: str = "") -> None:
        """把一次接口调用丢到后台线程。"""
        run_async(fn, on_success=on_success, on_error=on_error, label=label)

    # ─────────────── 认证 ───────────────
    def login(self, password: str, name: str = "", email: str = "") -> Result:
        payload: dict[str, Any] = {"password": password}
        if name:
            payload["name"] = name
        if email:
            payload["email"] = email
        result = self.post("/api/user/login", payload)
        if result.ok:
            user = result.get("user")
            self.set_user(user if isinstance(user, dict) else None,
                          persist=True)
            if not self.store.token:
                # 服务端会把 token 也放进响应体，供不方便自动保存 Cookie 的客户端使用
                token = result.get("Token")
                if token:
                    self.store.save({"token": str(token),
                                     "ID": str((user or {}).get("id") or "")},
                                    user)
        return result

    def logout(self) -> Result:
        result = self.post("/api/user/logout", {})
        self.clear_login()
        return result

    def register(self, name: str, email: str, password: str, code: str) -> Result:
        result = self.post("/api/user/register", {
            "name": name, "email": email, "password": password, "code": code})
        if result.ok:
            user = result.get("user")
            if not isinstance(user, dict):
                info = self.me()
                user = info.get("user")
            self.set_user(user if isinstance(user, dict) else None, persist=True)
            self.store.save(None, self._user, last_name=name)
        return result

    def send_register_code(self, email: str) -> Result:
        return self.post("/api/email/send-register-code", {"email": email})

    def send_verify_code(self) -> Result:
        return self.post("/api/email/send-verify-code", {})

    def verify_code_email(self, code: str) -> Result:
        result = self.post("/api/email/verify-code-email", {"code": code})
        if result.ok:
            self.me()
        return result

    def send_reset_code(self, email: str) -> Result:
        return self.post("/api/email/send-code-reset-password", {"email": email})

    def reset_password_by_code(self, email: str, code: str, password: str) -> Result:
        return self.post("/api/email/reset-password-by-code",
                         {"email": email, "code": code, "password": password})

    def send_change_password_code(self) -> Result:
        return self.post("/api/email/send-change-password-code", {})

    def change_password(self, new_password: str, code: str = "",
                        old_password: str = "") -> Result:
        payload: dict[str, Any] = {"new_password": new_password}
        if code:
            payload["code"] = code
        if old_password:
            payload["old_password"] = old_password
        result = self.post("/api/user/password", payload)
        if result.ok:
            # 服务端改密后会清掉 Cookie，本地也同步退出
            self.clear_login()
        return result

    def send_change_email_old_code(self) -> Result:
        return self.post("/api/email/send-change-email-old-code", {})

    def send_change_email_code(self, new_email: str) -> Result:
        return self.post("/api/email/send-change-email-code", {"email": new_email})

    def change_email(self, old_code: str, new_email: str, new_code: str) -> Result:
        result = self.post("/api/user/email", {
            "old_code": old_code, "email": new_email, "code": new_code})
        if result.ok:
            user = result.get("user")
            if isinstance(user, dict):
                self.set_user(user)
        return result

    # ─────────────── 用户 ───────────────
    def me(self) -> Result:
        result = self.get("/api/user/info")
        if result.ok:
            user = result.get("user")
            if isinstance(user, dict):
                self.set_user(user)
        return result

    def update_profile(self, **fields) -> Result:
        result = self.put("/api/user/info", fields)
        if result.ok:
            user = result.get("user")
            if isinstance(user, dict):
                self.set_user(user)
            else:
                self.me()
        return result

    def get_user(self, user_id: str) -> Result:
        """按 ID 查公开资料（注意：与 :attr:`user` 属性区分，历史命名的坑）。"""
        return self.get("/api/user/%s" % user_id)

    def follow(self, user_id: str) -> Result:
        return self.post("/api/user/%s/follow" % user_id, {})

    def following(self, user_id: str, page: int = 1, page_size: int = 20) -> Result:
        return self.get("/api/user/%s/following" % user_id,
                        page=page, page_size=page_size)

    def followers(self, user_id: str, page: int = 1, page_size: int = 20) -> Result:
        return self.get("/api/user/%s/followers" % user_id,
                        page=page, page_size=page_size)

    def user_posts(self, user_id: str, page: int = 1, page_size: int = 20) -> Result:
        return self.get("/api/user/%s/posts" % user_id,
                        page=page, page_size=page_size)

    def user_favorites(self, user_id: str, page: int = 1,
                       page_size: int = 20) -> Result:
        return self.get("/api/user/%s/favorites" % user_id,
                        page=page, page_size=page_size)

    def user_comments(self, user_id: str, page: int = 1,
                      page_size: int = 20) -> Result:
        return self.get("/api/user/%s/comments" % user_id,
                        page=page, page_size=page_size)

    def my_replies(self, page: int = 1, page_size: int = 20) -> Result:
        return self.get("/api/users/me/replies", page=page, page_size=page_size)

    def upload_avatar(self, file_path: str | Path) -> Result:
        path = Path(file_path)
        try:
            handle = open(path, "rb")
        except OSError as exc:
            return Result(0, None, "无法读取文件：%s" % exc)
        try:
            result = self.request(
                "POST", "/api/user/avatar/upload",
                files={"avatar": (path.name, handle, "application/octet-stream")},
                timeout=(15, 90), retries=0,
            )
        finally:
            try:
                handle.close()
            except Exception:
                pass
        if result.ok:
            avatar = result.get("avatar")
            if avatar and self._user:
                self._user = dict(self._user)
                self._user["avatar"] = avatar
                self.store.save(None, self._user)
        return result

    # ─────────────── 帖子 ───────────────
    def posts(self, page: int = 1, page_size: int = constants.PAGE_SIZE,
              category: str | None = None, sort: str | None = None) -> Result:
        return self.get("/api/posts", page=page, page_size=page_size,
                        category=category, sort=sort)

    def random_posts(self, limit: int = 200) -> Result:
        return self.get("/api/posts/random", limit=limit)

    def get_post(self, post_id: str) -> Result:
        """帖子详情（注意：与通用 ``post(path, payload)`` 区分）。"""
        return self.get("/api/posts/%s" % post_id)

    def create_post(self, title: str, content: str, category: str = "general") -> Result:
        return self.post("/api/posts/create", {
            "title": title, "content": content, "category": category})

    def like_post(self, post_id: str) -> Result:
        return self.post("/api/posts/%s/like" % post_id, {})

    def favorite_post(self, post_id: str) -> Result:
        return self.post("/api/posts/%s/favorite" % post_id, {})

    def report_post(self, post_id: str, reason: str, detail: str = "") -> Result:
        return self.post("/api/posts/%s/report" % post_id,
                         {"reason": reason, "detail": detail})

    def delete_post(self, post_id: str) -> Result:
        return self.post("/api/posts/%s/delete" % post_id, {})

    # ─────────────── 评论 ───────────────
    def comments(self, post_id: str, page: int = 1, page_size: int = 50) -> Result:
        return self.get("/api/posts/%s/comments" % post_id,
                        page=page, page_size=page_size)

    def create_comment(self, post_id: str, content: str,
                       parent_id: str | None = None) -> Result:
        payload: dict[str, Any] = {"content": content}
        if parent_id:
            payload["parent_id"] = parent_id
        return self.post("/api/posts/%s/comments/create" % post_id, payload)

    def like_comment(self, comment_id: str) -> Result:
        return self.post("/api/comments/%s/like" % comment_id, {})

    def delete_comment(self, comment_id: str) -> Result:
        return self.post("/api/comments/%s/delete" % comment_id, {})

    def report_comment(self, comment_id: str, reason: str, detail: str = "") -> Result:
        return self.post("/api/comments/%s/report" % comment_id,
                         {"reason": reason, "detail": detail})

    # ─────────────── 搜索 ───────────────
    def search(self, keyword: str, page: int = 1, page_size: int = 20,
               type_: str = "both") -> Result:
        return self.get("/api/search", k=keyword, page=page,
                        page_size=page_size, type=type_)

    # ─────────────── 世界频道 ───────────────
    def world_all(self) -> Result:
        return self.get("/api/world/ALL")

    def world_send(self, content: str, parent_id: str | None = None) -> Result:
        payload: dict[str, Any] = {"content": content}
        if parent_id:
            payload["parent_id"] = parent_id
        return self.post("/api/world/Send", payload)

    # ─────────────── 杂项 ───────────────
    def easter_egg(self) -> Result:
        return self.get(constants.EASTER_EGG_PATH)

    def huiguan(self) -> Result:
        return self.get("/api/huiguan")

    def report_bug(self, title: str, detail: str, steps: str = "",
                   contact: str = "", page_url: str = "") -> Result:
        return self.post("/api/report-bug", {
            "title": title, "detail": detail, "steps": steps,
                "contact": contact, "page_url": page_url or constants.BASE_URL,
        })
    def healthz(self) -> Result:
        return self.get("/healthz")

    def self_check(self) -> bool:
        """启动时的连通性探测（失败不打扰用户）。"""
        result = self.healthz()
        return bool(result.ok and (result.get("ok") or result.get("service")))

    # ─────────────── 通用网络工具 ───────────────
    def fetch_text(self, url: str, timeout: tuple[int, int] = (5, 8)) -> str:
        """取纯文本（每日一言）。"""
        try:
            response = requests.get(url, timeout=timeout,
                                    headers={"Accept": "text/plain",
                                             "User-Agent": constants.CLIENT_UA})
            if response.status_code >= 400:
                return ""
            return response.text.strip()
        except Exception:
            return ""

    def fetch_json(self, url: str, timeout: tuple[int, int] = (5, 8)) -> Any:
        try:
            response = requests.get(url, timeout=timeout,
                                    headers={"User-Agent": constants.CLIENT_UA})
            if response.status_code >= 400:
                return None
            return response.json()
        except Exception:
            return None

    def download(self, url: str, dest: str | Path, *,
                 on_progress: Callable[[int, int], None] | None = None,
                 timeout: tuple[int, int] = (10, 180)) -> Result:
        """流式下载到本地（先写 .part，完成后再替换）。"""
        target = Path(dest)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".part")
        full_url = self._url(url)
        try:
            with self.session.get(full_url, stream=True,
                                  timeout=timeout) as response:
                if response.status_code >= 400:
                    return Result(response.status_code, None,
                                  "下载失败（HTTP %s）" % response.status_code,
                                  full_url)
                total = int(response.headers.get("Content-Length") or 0)
                done = 0
                with open(tmp, "wb") as fh:
                    for chunk in response.iter_content(chunk_size=65536):
                        if not chunk:
                            continue
                        fh.write(chunk)
                        done += len(chunk)
                        if on_progress is not None:
                            try:
                                on_progress(done, total)
                            except Exception:
                                pass
            tmp.replace(target)
            return Result(200, {"path": str(target), "size": done}, None, full_url)
        except Exception as exc:  # noqa: BLE001
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass
            return Result(0, None, "%s（%s）" % (NET_ERROR_TEXT, exc), full_url)


_api: ForumApi | None = None


def api() -> ForumApi:
    """全局单例。"""
    global _api
    if _api is None:
        _api = ForumApi()
    return _api
