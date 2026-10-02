# -*- coding: utf-8 -*-
"""Markdown 渲染：基于 Qt 自带的 CommonMark 解析器（QTextDocument.setMarkdown）。

三端口径统一（与 Web 的 marked、Android 的 MarkdownBody 一致）：

* **不渲染 HTML 语法** —— GitHub 方言再叠加 ``MarkdownNoHTML``：不加这个标志
  Qt 会把 ``<div>hi</div>`` 直接吞成 ``hi``（等于悄悄解析了 HTML），叠上之后
  正文里的 HTML 标签按字面文字展示；
* **单换行即换行** —— Qt 走 CommonMark 口径，段落内的单个换行会被合并成空格
  （``line1\\nline2`` → ``line1 line2``）。这里用 :func:`apply_hard_breaks`
  预处理成硬换行（行尾两个空格），与网页端 marked 的 ``breaks: true`` 对齐。

* 样式通过 :func:`app.theme.document_css` 注入，与整体主题保持一致
* 外链不直接打开，发 :attr:`MarkdownView.link_clicked` 交给上层做安全确认
* 内嵌远端图片走 :mod:`app.widgets.images` 缓存；首次渲染不阻塞，
  下载完成后自动重渲染（保留滚动位置）
"""

from __future__ import annotations

from PyQt6.QtCore import QTimer, QUrl, Qt, pyqtSignal
from PyQt6.QtGui import QImage, QTextDocument
from PyQt6.QtWidgets import QFrame, QTextBrowser, QWidget

from .. import constants, logger, theme

_log = logger.get_logger("markdown")

# 代码围栏前缀（三个反引号 / 三个波浪线）：内部原样保留，不补硬换行
_FENCE_PREFIXES = ("```", "~~~")


def _markdown_features():
    """GitHub 方言（表格 / 删除线）+ 关闭 HTML 解析；不支持时返回 None。"""
    try:
        features = QTextDocument.MarkdownFeature.MarkdownDialectGitHub
    except AttributeError:
        return None
    no_html = getattr(QTextDocument.MarkdownFeature, "MarkdownNoHTML", None)
    if no_html is not None:
        # Qt 把 MarkdownNoHTML 定义为 0x20 | MarkdownDialectCommonMark，按位或即可叠加
        features = features | no_html
    return features


def apply_hard_breaks(text: str) -> str:
    """把「单换行」转成 Markdown 硬换行（行尾两个空格）。

    Qt 的 CommonMark 解析器会让段落内的单个换行退化成空格，而三端口径是
    「单换行即换行」（网页端 marked 配的 breaks: true），因此这里做等价预处理。

    代码围栏（三个反引号 / 三个波浪线）内部原样保留；空行与已以两个空格
    结尾的行不动（幂等）。
    """
    if not text or "\n" not in text:
        return text
    out = []
    fence = None
    for line in text.split("\n"):
        stripped = line.lstrip()
        marker = stripped[:3] if stripped.startswith(_FENCE_PREFIXES) else None
        if fence is not None:
            out.append(line)
            if marker == fence:
                fence = None
            continue
        if marker is not None:
            fence = marker
            out.append(line)
            continue
        if line.strip() and not line.endswith("  "):
            out.append(line + "  ")
        else:
            out.append(line)
    return "\n".join(out)


def set_document_markdown(document: QTextDocument, text: str) -> None:
    """把 Markdown 写入 QTextDocument（自动降级到默认方言）。"""
    prepared = apply_hard_breaks(text or "")
    features = _markdown_features()
    try:
        if features is not None:
            document.setMarkdown(prepared, features)
        else:
            document.setMarkdown(prepared)
    except TypeError:
        document.setMarkdown(prepared)


def markdown_to_html(text: str, mode: str | None = None) -> str:
    """仅供内部调用的 Markdown → HTML（供 tooltip 等场景使用）。"""
    document = QTextDocument()
    document.setDefaultStyleSheet(theme.document_css(mode))
    set_document_markdown(document, text)
    return document.toHtml()


class MarkdownView(QTextBrowser):
    """只读 Markdown 视图（帖子正文 / 评论内容 / 发帖预览）。"""

    link_clicked = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None, *, min_height: int = 0,
                 max_height: int = 0) -> None:
        super().__init__(parent)
        self.setObjectName("MarkdownView")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.setReadOnly(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction |
            Qt.TextInteractionFlag.LinksAccessibleByMouse)
        self.document().setDocumentMargin(4)
        self.document().setBaseUrl(QUrl(constants.BASE_URL + "/"))
        self._source = ""
        self._mode = None
        self._requested: set[str] = set()
        self._rerender_scheduled = False
        self._min_height = int(min_height)
        self._max_height = int(max_height)
        if self._min_height:
            self.setMinimumHeight(self._min_height)
        if self._max_height:
            self.setMaximumHeight(self._max_height)
        self.anchorClicked.connect(self._on_anchor)
        self._apply_style()

    # ── 样式 ──
    def _apply_style(self) -> None:
        self.document().setDefaultStyleSheet(theme.document_css(self._mode))

    def reload_theme(self) -> None:
        """主题切换后重渲染。"""
        self._apply_style()
        self.set_markdown(self._source)

    # ── 内容 ──
    def source(self) -> str:
        return self._source

    def set_markdown(self, text: str) -> None:
        self._source = text or ""
        self._requested.clear()
        set_document_markdown(self.document(), self._source)
        self._resize_to_content()

    def set_raw_text(self, text: str) -> None:
        """纯文本（不做 Markdown 解析）。"""
        self._source = ""
        self.setPlainText(text or "")

    def _resize_to_content(self) -> None:
        if not self._max_height:
            return
        try:
            height = int(self.document().size().height()) + 12
        except Exception:
            return
        self.setFixedHeight(min(max(height, self._min_height or 24), self._max_height))

    # ── 链接 ──
    def _on_anchor(self, url: QUrl) -> None:
        href = url.toString()
        if href:
            self.link_clicked.emit(href)

    # ── 图片资源 ──
    def loadResource(self, type_, name):  # noqa: N802
        try:
            is_image = int(type_) == int(QTextDocument.ResourceType.ImageResource.value)
        except Exception:
            is_image = False
        if is_image:
            try:
                raw = name.toString() if hasattr(name, "toString") else str(name)
            except Exception:
                raw = ""
            if raw:
                from .images import image_cache
                absolute = constants.absolute(raw)
                pixmap = image_cache.cached_pixmap(absolute)
                if pixmap is not None and not pixmap.isNull():
                    return pixmap
                if absolute not in self._requested:
                    self._requested.add(absolute)
                    image_cache.fetch(absolute,
                                      on_ready=lambda _u, _p: self._schedule_rerender(),
                                      on_error=lambda _m: None)
                return QImage()
        return super().loadResource(type_, name)

    def _schedule_rerender(self) -> None:
        if self._rerender_scheduled:
            return
        self._rerender_scheduled = True

        def _do() -> None:
            self._rerender_scheduled = False
            if not self._source:
                return
            bar = self.verticalScrollBar()
            position = bar.value()
            set_document_markdown(self.document(), self._source)
            bar.setValue(position)

        QTimer.singleShot(0, _do)
