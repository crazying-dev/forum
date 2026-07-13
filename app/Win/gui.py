#!/usr/bin/env python3
"""
妖精论坛管理员可视化界面（Windows）- PyQt6版
"""

import sys
import os
import json
import logging
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QLineEdit, QComboBox, QProgressBar,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QPlainTextEdit, QGroupBox, QMessageBox, QInputDialog, QSplitter,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject
from PyQt6.QtGui import QFont, QColor, QIcon

APP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP_DIR)
CONFIG_FILE = os.path.join(APP_DIR, "config.bin")
LOGO_FILE = os.path.join(APP_DIR, "logo.png")

LOG_DIR = os.path.join(APP_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, f"admin_{datetime.now().strftime('%Y%m%d')}.log")


def decrypt_config(data):
    return ''.join([chr((b - 1) % 256) for b in data])


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return None
    try:
        with open(CONFIG_FILE, "rb") as f:
            encrypted = f.read()
        decrypted = decrypt_config(encrypted)
        return json.loads(decrypted)
    except Exception:
        return None


class WorkerSignals(QObject):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)


class Worker(QThread):

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
            self.signals.finished.emit(result)
        except Exception as e:
            self.signals.error.emit(str(e))


class AdminGUI(QMainWindow):

    def __init__(self, config):
        super().__init__()
        self.setWindowTitle("妖精论坛管理控制台")
        self.resize(1050, 680)
        self.setMinimumSize(900, 550)
        if os.path.exists(LOGO_FILE):
            self.setWindowIcon(QIcon(LOGO_FILE))

        self.config = config
        self._workers = []

        self._setup_logging()
        self._log("INFO", "管理控制台启动")

        self._init_api()
        self._build_ui()
        self._refresh_all()

    def _setup_logging(self):
        self.logger = logging.getLogger("admin_gui")
        self.logger.setLevel(logging.DEBUG)
        fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        self.logger.addHandler(fh)

    def _init_api(self):
        try:
            from api_client import AdminAPIClient
            base_url = self.config.get('apiUrl', 'admin.forum.crazying-dev.top')
            admin_id = self.config.get('adminId')
            admin_token = self.config.get('adminToken')
            self.api = AdminAPIClient(base_url, admin_id, admin_token)
            self._log("INFO", f"API客户端已初始化: {base_url}")
        except ImportError as e:
            self._log("ERROR", f"加载API客户端失败: {e}")
            QMessageBox.critical(self, "错误", f"加载API客户端失败:\n{e}")
            sys.exit(1)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 4)

        self.notebook = QTabWidget()
        layout.addWidget(self.notebook)

        self._build_dashboard_tab()
        self._build_reports_tab()
        self._build_users_tab()
        self._build_admins_tab()
        self._build_posts_tab()
        self._build_log_tab()

        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("color: #6b7280;")
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(180)
        self.progress_bar.setValue(100)
        self.statusBar().addWidget(self.status_label)
        self.statusBar().addPermanentWidget(self.progress_bar)

    def _refresh_all(self):
        self._load_users()
        self._load_stats()
        self._load_reports()

    def _set_progress(self, value, text=""):
        self.progress_bar.setValue(value)
        if text:
            self.status_label.setText(text)

    def _log(self, level, message):
        getattr(self.logger, level.lower(), self.logger.info)(message)
        if hasattr(self, "log_text"):
            ts = datetime.now().strftime("%H:%M:%S")
            color_map = {
                "ERROR": "#f38ba8",
                "WARNING": "#f9e2af",
                "INFO": "#a6e3a1",
                "DEBUG": "#89b4fa",
            }
            color = color_map.get(level, "#cdd6f4")
            self.log_text.appendHtml(
                f'<span style="color:{color}">[{ts}] {level} {message}</span>'
            )

    def _run_async(self, fn, on_success=None, on_error=None, loading_text="加载中..."):
        self._set_progress(0, loading_text)
        self._log("DEBUG", f"开始: {loading_text}")

        worker = Worker(fn)
        self._workers.append(worker)

        def on_finish(result):
            if worker in self._workers:
                self._workers.remove(worker)
            self._set_progress(100, "就绪")
            self._log("INFO", f"完成: {loading_text}")
            if on_success:
                on_success(result)

        def on_err(err):
            if worker in self._workers:
                self._workers.remove(worker)
            self._set_progress(100, f"错误: {err[:40]}")
            self._log("ERROR", f"{loading_text} 失败: {err}")
            if on_error:
                on_error(err)
            else:
                QMessageBox.critical(self, "错误", err)

        worker.signals.finished.connect(on_finish)
        worker.signals.error.connect(on_err)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _create_table(self, parent, headers):
        table = QTableWidget()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        return table

    def _populate_table(self, table, items, col_map, status_col=None, status_type=None):
        table.setRowCount(0)
        for item in items:
            row = table.rowCount()
            table.insertRow(row)
            for source_key, col in col_map.items():
                val = item.get(source_key, "")
                cell_color = None
                if col == status_col and status_type:
                    if status_type == "banned":
                        val = "是" if val == 1 else "否"
                        if val == "是":
                            cell_color = QColor("#ef4444")
                    elif status_type == "report":
                        val = "已处理" if val == 1 else "待处理"
                        cell_color = QColor("#9ca3af") if val == "已处理" else QColor("#f59e0b")
                if isinstance(val, str) and len(val) > 50:
                    val = val[:50] + "..."
                cell = QTableWidgetItem(str(val) if val is not None else "")
                if cell_color:
                    cell.setForeground(cell_color)
                table.setItem(row, col, cell)
        table.resizeColumnsToContents()

    def _build_dashboard_tab(self):
        frame = QWidget()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 16, 16, 16)

        title = QLabel("数据概览")
        title.setFont(QFont("微软雅黑", 16, QFont.Weight.Bold))
        layout.addWidget(title)
        layout.addSpacing(16)

        stats_layout = QHBoxLayout()
        self.stat_labels = {}
        labels = [("users", "用户总数"), ("posts", "帖子总数"), ("comments", "评论总数"),
                  ("pending_reports", "待处理举报"), ("banned_users", "已封禁用户")]
        for key, text in labels:
            group = QGroupBox(text)
            gl = QVBoxLayout(group)
            lbl = QLabel("-")
            lbl.setFont(QFont("微软雅黑", 24, QFont.Weight.Bold))
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            gl.addWidget(lbl)
            stats_layout.addWidget(group)
            self.stat_labels[key] = lbl
        layout.addLayout(stats_layout)

        layout.addSpacing(16)
        btn = QPushButton("刷新数据")
        btn.clicked.connect(self._load_stats)
        layout.addWidget(btn)
        layout.addStretch()

        self.notebook.addTab(frame, "仪表盘")

    def _load_stats(self):
        self._run_async(
            lambda: self.api.get_stats(),
            on_success=self._update_stats,
            loading_text="加载统计数据...",
        )

    def _update_stats(self, stats):
        if stats:
            for key, lbl in self.stat_labels.items():
                lbl.setText(str(stats.get(key, 0)))
        else:
            QMessageBox.warning(self, "警告", "获取统计数据失败")

    def _build_reports_tab(self):
        frame = QWidget()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 8, 8, 8)

        toolbar = QHBoxLayout()
        for text, handler in [("刷新", self._load_reports),
                              ("标记已处理", self._resolve_report),
                              ("查看帖子详情", self._view_report_post),
                              ("删除被举报帖子", self._delete_report_post)]:
            btn = QPushButton(text)
            btn.clicked.connect(handler)
            toolbar.addWidget(btn)

        toolbar.addSpacing(16)
        toolbar.addWidget(QLabel("筛选:"))
        self.report_filter = QComboBox()
        self.report_filter.addItems(["全部", "待处理", "已处理"])
        self.report_filter.currentTextChanged.connect(lambda: self._load_reports())
        toolbar.addWidget(self.report_filter)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        headers = ["ID", "帖子ID", "帖子标题", "举报人", "原因", "状态", "时间"]
        self.report_table = self._create_table(frame, headers)
        layout.addWidget(self.report_table)

        self.notebook.addTab(frame, "举报管理")

    def _load_reports(self):
        filt = self.report_filter.currentText()
        status = {"待处理": 0, "已处理": 1}.get(filt)
        self._run_async(
            lambda: self.api.list_reports(status),
            on_success=lambda r: self._populate_table(self.report_table, r or [], {
                "id": 0, "post_id": 1, "post_title": 2,
                "reporter_name": 3, "reason": 4,
                "status": 5, "created_at": 6,
            }, status_col=5, status_type="report"),
            loading_text="加载举报列表...",
        )

    def _get_selected_report(self):
        row = self.report_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "提示", "请先选择一条举报记录")
            return None
        return {
            "id": self.report_table.item(row, 0).text(),
            "post_id": self.report_table.item(row, 1).text(),
            "post_title": self.report_table.item(row, 2).text(),
            "status": self.report_table.item(row, 5).text(),
        }

    def _resolve_report(self):
        report = self._get_selected_report()
        if not report:
            return
        if QMessageBox.question(self, "确认",
                f"确认将举报 #{report['id']} 标记为已处理?") != QMessageBox.StandardButton.Yes:
            return
        self._log("INFO", f"标记举报 #{report['id']} 为已处理")
        self._run_async(
            lambda: self.api.resolve_report(int(report["id"])),
            on_success=lambda ok: (
                QMessageBox.information(self,
                    "成功" if ok else "失败",
                    "举报已标记为已处理" if ok else "操作失败"),
                self._load_reports(),
            ),
            loading_text="处理中...",
        )

    def _view_report_post(self):
        report = self._get_selected_report()
        if not report:
            return
        self.notebook.setCurrentWidget(self.posts_tab)
        self.post_id_input.setText(str(report["post_id"]))
        self._show_post_detail(report["post_id"])

    def _delete_report_post(self):
        report = self._get_selected_report()
        if not report:
            return
        if QMessageBox.question(self, "确认",
                f"确认删除帖子 '{report['post_title']}'?") != QMessageBox.StandardButton.Yes:
            return
        self._log("WARNING", f"删除举报帖子 #{report['post_id']} (举报#{report['id']})")

        def worker():
            result = self.api.delete_post(report["post_id"])
            ok = result is not None
            msg = "帖子已删除" if ok else "删除失败"
            if ok and report["status"] == "待处理":
                self.api.resolve_report(int(report["id"]))
            return ok, msg

        self._run_async(worker, on_success=lambda res: (
            QMessageBox.information(self, "成功" if res[0] else "失败", res[1]),
            self._load_reports(),
        ), loading_text="删除中...")

    def _build_users_tab(self):
        frame = QWidget()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 8, 8, 8)

        toolbar = QHBoxLayout()
        for text, handler in [("全部用户", self._load_users),
                              ("搜索用户", self._search_user),
                              ("修改信息", self._edit_user),
                              ("封禁", self._ban_user),
                              ("解封", self._unban_user)]:
            btn = QPushButton(text)
            btn.clicked.connect(handler)
            toolbar.addWidget(btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        headers = ["用户ID", "用户名", "邮箱", "VIP", "封禁", "年龄", "最后登录"]
        self.user_table = self._create_table(frame, headers)
        layout.addWidget(self.user_table)

        self.notebook.addTab(frame, "用户管理")

    def _load_users(self):
        self._run_async(
            lambda: self.api.list_users(),
            on_success=lambda u: self._populate_table(self.user_table, u or [], {
                "id": 0, "name": 1, "email": 2,
                "vip": 3, "is_banned": 4, "age": 5, "last_login": 6,
            }, status_col=4, status_type="banned"),
            loading_text="加载用户列表...",
        )

    def _search_user(self):
        text, ok = QInputDialog.getText(self, "搜索用户", "输入用户ID或用户名:")
        if not ok or not text.strip():
            return
        self._run_async(
            lambda: self.api.find_user_smart(text.strip()),
            on_success=lambda u: (
                QMessageBox.information(self, "信息", "未找到用户") if not u else
                self._populate_table(self.user_table, u, {
                    "id": 0, "name": 1, "email": 2,
                    "vip": 3, "is_banned": 4, "age": 5, "last_login": 6,
                }, status_col=4, status_type="banned")
            ),
            loading_text="搜索中...",
        )

    def _get_selected_user(self):
        row = self.user_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "提示", "请先选择一个用户")
            return None
        return {
            "id": self.user_table.item(row, 0).text(),
            "name": self.user_table.item(row, 1).text(),
        }

    def _edit_user(self):
        user = self._get_selected_user()
        if not user:
            return
        fields = ["name", "avatar", "email", "gender", "age", "intro", "vip", "password", "is_banned"]
        key, ok = QInputDialog.getItem(
            self, "修改用户",
            f"已选择: {user['name']}\n选择修改字段:", fields, 0, False)
        if not ok or not key:
            return
        value, ok = QInputDialog.getText(self, "修改用户", f"将 {user['name']} 的 {key} 修改为:")
        if not ok:
            return
        if QMessageBox.question(self, "确认",
                f"确认将 {user['name']} 的 {key} 修改为: {value}?") != QMessageBox.StandardButton.Yes:
            return
        self._log("INFO", f"修改用户 {user['name']}({user['id']}): {key}={value}")
        self._run_async(
            lambda: self.api.update_user(user["id"], key, value),
            on_success=lambda ok_val: (
                QMessageBox.information(self,
                    "成功" if ok_val else "失败",
                    "用户数据已更新" if ok_val else "更新未生效"),
                self._load_users(),
            ),
            loading_text="更新中...",
        )

    def _ban_user(self):
        user = self._get_selected_user()
        if not user:
            return
        if QMessageBox.question(self, "确认",
                f"确认封禁用户 {user['name']} ({user['id']})?") != QMessageBox.StandardButton.Yes:
            return
        self._log("WARNING", f"封禁用户 {user['name']}({user['id']})")
        self._run_async(
            lambda: self.api.ban_user(user["id"]),
            on_success=lambda ok_val: (
                QMessageBox.information(self,
                    "成功" if ok_val else "失败",
                    "用户已被封禁" if ok_val else "操作失败"),
                self._load_users(),
            ),
            loading_text="处理中...",
        )

    def _unban_user(self):
        user = self._get_selected_user()
        if not user:
            return
        if QMessageBox.question(self, "确认",
                f"确认解封用户 {user['name']} ({user['id']})?") != QMessageBox.StandardButton.Yes:
            return
        self._log("INFO", f"解封用户 {user['name']}({user['id']})")
        self._run_async(
            lambda: self.api.unban_user(user["id"]),
            on_success=lambda ok_val: (
                QMessageBox.information(self,
                    "成功" if ok_val else "失败",
                    "用户已被解封" if ok_val else "操作失败"),
                self._load_users(),
            ),
            loading_text="处理中...",
        )

    def _build_posts_tab(self):
        self.posts_tab = QWidget()
        layout = QVBoxLayout(self.posts_tab)
        layout.setContentsMargins(8, 8, 8, 8)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("帖子ID:"))
        self.post_id_input = QLineEdit()
        toolbar.addWidget(self.post_id_input)
        for text, handler in [("查看详情", self._view_post),
                              ("删除帖子", self._delete_post),
                              ("查看评论", self._view_post_comments),
                              ("删除评论", self._delete_comment)]:
            btn = QPushButton(text)
            btn.clicked.connect(handler)
            toolbar.addWidget(btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        splitter = QSplitter(Qt.Orientation.Vertical)

        detail_group = QGroupBox("帖子详情")
        dl = QVBoxLayout(detail_group)
        self.post_detail_text = QPlainTextEdit()
        self.post_detail_text.setReadOnly(True)
        self.post_detail_text.setFont(QFont("Consolas", 10))
        self.post_detail_text.setStyleSheet("background-color: #f5f5f7;")
        dl.addWidget(self.post_detail_text)
        splitter.addWidget(detail_group)

        comments_group = QGroupBox("评论列表")
        cl = QVBoxLayout(comments_group)
        self.comment_table = self._create_table(comments_group,
            ["评论ID", "用户名", "状态", "内容", "时间"])
        cl.addWidget(self.comment_table)
        splitter.addWidget(comments_group)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter)

        self.current_post_id = None
        self.notebook.addTab(self.posts_tab, "帖子管理")

    def _view_post(self):
        post_id = self.post_id_input.text().strip()
        if not post_id:
            QMessageBox.warning(self, "提示", "请输入帖子ID")
            return
        self._show_post_detail(post_id)

    def _show_post_detail(self, post_id):
        self.current_post_id = post_id

        def worker():
            post = self.api.get_post_detail(post_id)
            comments = self.api.get_post_comments(post_id) if post else []
            return post, comments

        def on_success(res):
            post, comments = res
            if not post:
                QMessageBox.information(self, "信息", "帖子不存在")
                return
            self._display_post_detail(post)
            self._populate_table(self.comment_table, comments, {
                "id": 0, "user_name": 1, "status": 2,
                "content": 3, "created_at": 4,
            }, status_col=2, status_type="report")

        self._run_async(worker, on_success=on_success, loading_text="加载帖子详情...")

    def _display_post_detail(self, post):
        status_str = "正常" if post["status"] == 1 else "已删除"
        lines = [
            f"帖子ID:   {post['id']}", f"标题:     {post['title']}",
            f"作者:     {post['user_name']} ({post['user_id']})", f"分类:     {post['category']}",
            f"状态:     {status_str}", f"点赞:     {post['likes']}  浏览: {post['views']}",
            f"创建时间: {post['created_at']}", f"更新时间: {post['updated_at']}",
            f"{'-' * 50}", f"内容:", post["content"],
        ]
        self.post_detail_text.setPlainText("\n".join(lines))

    def _delete_post(self):
        post_id = self.post_id_input.text().strip() or self.current_post_id
        if not post_id:
            QMessageBox.warning(self, "提示", "请输入帖子ID")
            return
        if QMessageBox.question(self, "确认", f"确认删除帖子 {post_id}?") != QMessageBox.StandardButton.Yes:
            return
        self._log("WARNING", f"删除帖子 #{post_id}")
        self._run_async(
            lambda: self.api.delete_post(post_id),
            on_success=lambda res: QMessageBox.information(
                self, "成功" if res is not None else "失败",
                "帖子已删除" if res is not None else "删除失败"),
            loading_text="删除中...",
        )

    def _view_post_comments(self):
        post_id = self.post_id_input.text().strip() or self.current_post_id
        if not post_id:
            QMessageBox.warning(self, "提示", "请输入帖子ID")
            return
        self._show_post_detail(post_id)

    def _delete_comment(self):
        row = self.comment_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "提示", "请先选择一条评论")
            return
        comment_id = self.comment_table.item(row, 0).text()
        if QMessageBox.question(self, "确认", f"确认删除评论 {comment_id}?") != QMessageBox.StandardButton.Yes:
            return
        self._log("WARNING", f"删除评论 #{comment_id}")

        def worker():
            ok = self.api.delete_comment(comment_id) is not None
            comments = self.api.get_post_comments(self.current_post_id) if ok and self.current_post_id else []
            return ok, "评论已删除" if ok else "删除失败", comments

        def on_success(res):
            ok, msg, comments = res
            if ok and self.current_post_id:
                self._populate_table(self.comment_table, comments, {
                    "id": 0, "user_name": 1, "status": 2,
                    "content": 3, "created_at": 4,
                }, status_col=2, status_type="report")
            QMessageBox.information(self, "成功" if ok else "失败", msg)

        self._run_async(worker, on_success=on_success, loading_text="删除中...")

    def _build_admins_tab(self):
        frame = QWidget()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 8, 8, 8)

        if self.config:
            admin_id = self.config.get("adminId", "")
            token_display = "*" * len(self.config.get("adminToken", ""))
            api_url = self.config.get("apiUrl", "admin.forum.crazying-dev.top")

            group = QGroupBox("当前管理员")
            gl = QGridLayout(group)
            gl.setContentsMargins(12, 12, 12, 12)

            lbl_key1 = QLabel("API地址:")
            lbl_key1.setFont(QFont("微软雅黑", 10, QFont.Weight.Bold))
            lbl_val1 = QLabel(api_url)
            lbl_val1.setFont(QFont("微软雅黑", 10))
            gl.addWidget(lbl_key1, 0, 0)
            gl.addWidget(lbl_val1, 0, 1)

            lbl_key2 = QLabel("管理员ID:")
            lbl_key2.setFont(QFont("微软雅黑", 10, QFont.Weight.Bold))
            lbl_val2 = QLabel(admin_id)
            lbl_val2.setFont(QFont("微软雅黑", 10))
            gl.addWidget(lbl_key2, 1, 0)
            gl.addWidget(lbl_val2, 1, 1)

            lbl_key3 = QLabel("管理员令牌:")
            lbl_key3.setFont(QFont("微软雅黑", 10, QFont.Weight.Bold))
            lbl_val3 = QLabel(token_display)
            lbl_val3.setFont(QFont("Consolas", 10))
            lbl_val3.setStyleSheet("color: #ef4444;")
            gl.addWidget(lbl_key3, 2, 0)
            gl.addWidget(lbl_val3, 2, 1)

            lbl_hint = QLabel("配置文件: config.bin")
            lbl_hint.setFont(QFont("微软雅黑", 8))
            lbl_hint.setStyleSheet("color: #6b7280;")
            gl.addWidget(lbl_hint, 3, 0, 1, 2)

            layout.addWidget(group)
        else:
            lbl = QLabel("未找到配置文件 config.bin")
            lbl.setFont(QFont("微软雅黑", 12))
            lbl.setStyleSheet("color: #ef4444;")
            layout.addWidget(lbl)

        layout.addStretch()
        self.notebook.addTab(frame, "管理员")

    def _build_log_tab(self):
        frame = QWidget()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 8, 8, 8)

        toolbar = QHBoxLayout()
        btn_clear = QPushButton("清空日志")
        btn_clear.clicked.connect(self._clear_log)
        toolbar.addWidget(btn_clear)

        btn_open = QPushButton("打开日志目录")
        btn_open.clicked.connect(self._open_log_dir)
        toolbar.addWidget(btn_open)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 10))
        self.log_text.setStyleSheet("""
            QPlainTextEdit {
                background-color: #1e1e2e;
                color: #cdd6f4;
            }
        """)
        layout.addWidget(self.log_text)

        self.notebook.addTab(frame, "日志")

    def _clear_log(self):
        self.log_text.clear()

    def _open_log_dir(self):
        os.startfile(LOG_DIR)


def main():
    app = QApplication(sys.argv)
    if os.path.exists(LOGO_FILE):
        app.setWindowIcon(QIcon(LOGO_FILE))

    if not os.path.exists(CONFIG_FILE):
        QMessageBox.critical(None, "配置错误",
            f"未找到配置文件\n\n{CONFIG_FILE}\n\n请找管理员生成配置文件。")
        sys.exit(1)

    config = load_config()
    if not config:
        QMessageBox.critical(None, "配置错误",
            f"配置文件解密失败\n\n{CONFIG_FILE}\n\n请检查配置文件是否正确。")
        sys.exit(1)

    window = AdminGUI(config)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()