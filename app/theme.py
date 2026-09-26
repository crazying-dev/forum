# -*- coding: utf-8 -*-
"""主题：色板 / QSS / 文档 CSS。

色板照搬 Web 端 ``static/css/main.css`` 的 ``:root`` 与 ``.night-mode``，
半透明色已按底层背景预混为实色（Qt 控件默认不做透明度混合，实色更稳定）。
"""

from __future__ import annotations

from datetime import datetime

from . import constants, config

PRIMARY_RADIUS = 8

PALETTES: dict[str, dict[str, str]] = {
    constants.THEME_DAY: {
        "text_primary": "#1A2423",
        "text_secondary": "#2E4659",
        "text_tertiary": "#96A9A7",
        "text_light": "#E8EEED",
        "text_accent": "#579491",
        "text_muted": "#96A9A7",
        "bg_body": "#D8E6E4",
        "bg_header": "#E6EDEC",
        "bg_card": "#FFFFFF",
        "bg_input": "#F9FBFA",
        "bg_hover": "#F0F4F3",
        "bg_item_hover": "#F0F4F3",
        "bg_item_active": "#E9EEED",
        "bg_icon": "#E9EEED",
        "bg_icon_hover": "#D2DDDB",
        "bg_footer": "#6A8C89",
        "bg_secondary": "#FFFFFF",
        "border": "#E1E8E7",
        "border_divider": "#F0F4F3",
        "border_focus": "#6A8C89",
        "primary": "#6A8C89",
        "primary_hover": "#579491",
        "primary_text": "#FFFFFF",
        "danger": "#B4544F",
        "danger_hover": "#9E423D",
        "shadow": "rgba(58, 95, 107, 0.15)",
        "code_bg": "#F0F4F3",
        "mark_bg": "#FFF3C4",
    },
    constants.THEME_NIGHT: {
        "text_primary": "#E8EEED",
        "text_secondary": "#D8E6E4",
        "text_tertiary": "#84A8B9",
        "text_light": "#B4D2D8",
        "text_accent": "#B4D2D8",
        "text_muted": "#84A8B9",
        "bg_body": "#325A64",
        "bg_header": "#2F495B",
        "bg_card": "#1B2726",
        "bg_input": "#1F2F30",
        "bg_hover": "#2B3A3C",
        "bg_item_hover": "#2B3A3C",
        "bg_item_active": "#304143",
        "bg_icon": "#304143",
        "bg_icon_hover": "#455A61",
        "bg_footer": "#2E4659",
        "bg_secondary": "#1B2726",
        "border": "#2B3A3C",
        "border_divider": "#243435",
        "border_focus": "#84A8B9",
        "primary": "#84A8B9",
        "primary_hover": "#6A8C89",
        "primary_text": "#12211F",
        "danger": "#E78284",
        "danger_hover": "#D06B6D",
        "shadow": "rgba(0, 0, 0, 0.3)",
        "code_bg": "#243435",
        "mark_bg": "#4A4326",
    },
}


def resolve_mode(mode: str | None = None) -> str:
    """把配置里的 day/night/auto 解析为具体主题。

    ``auto`` 同 Web 端：本地时间 < 6 点或 ≥ 18 点为夜间。
    """
    if mode is None:
        try:
            mode = config.current().theme
        except Exception:
            mode = constants.THEME_AUTO
    mode = str(mode or constants.THEME_AUTO)
    if mode == constants.THEME_DAY:
        return constants.THEME_DAY
    if mode == constants.THEME_NIGHT:
        return constants.THEME_NIGHT
    hour = datetime.now().hour
    return constants.THEME_NIGHT if (hour < 6 or hour >= 18) else constants.THEME_DAY


def palette(mode: str | None = None) -> dict[str, str]:
    return PALETTES[resolve_mode(mode)]


def qss(mode: str | None = None) -> str:
    """生成全局 QSS。"""
    p = palette(mode)
    return _QSS_TEMPLATE.format(**p)


def document_css(mode: str | None = None) -> str:
    """给 QTextDocument（Markdown 渲染）用的 CSS。"""
    p = palette(mode)
    return _DOC_TEMPLATE.format(**p)


def restyle(widget) -> None:
    """动态属性变更后强制重算样式。"""
    try:
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()
    except Exception:
        pass


_QSS_TEMPLATE = """
* {{
    outline: 0;
}}
QWidget {{
    color: {text_primary};
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif;
    font-size: 13px;
}}
QMainWindow, QDialog, #Root {{
    background: {bg_body};
}}
QToolTip {{
    background: {bg_card};
    color: {text_primary};
    border: 1px solid {border};
    padding: 4px 8px;
    border-radius: 6px;
}}

/* ── 顶部栏 ── */
#TopBar {{
    background: {bg_header};
    border-bottom: 1px solid {border};
}}
#TopBarTitle {{
    font-size: 17px;
    font-weight: 700;
    color: {text_primary};
}}
#TopSearch {{
    background: {bg_input};
    border: 1px solid {border};
    border-radius: 16px;
    padding: 6px 14px;
    min-height: 20px;
}}
#TopSearch:focus {{
    border-color: {border_focus};
}}

/* ── 左侧导航栏 ── */
#SideNav {{
    background: {bg_header};
    border-right: 1px solid {border};
}}
#NavButton {{
    background: transparent;
    border: none;
    border-radius: {radius}px;
    color: {text_secondary};
    text-align: left;
    padding: 9px 10px;
    font-size: 13px;
}}
#NavButton:hover {{
    background: {bg_item_hover};
    color: {text_primary};
}}
#NavButton[active="true"] {{
    background: {bg_item_active};
    color: {primary};
    font-weight: 700;
}}
#SideHint {{
    color: {text_tertiary};
}}

/* ── 卡片 ── */
QFrame#Card, QFrame[class="card"] {{
    background: {bg_card};
    border: 1px solid {border};
    border-radius: 12px;
}}
QLabel#PageTitle {{
    font-size: 19px;
    font-weight: 700;
}}
QLabel#CardTitle {{
    font-size: 15px;
    font-weight: 700;
}}
QLabel[muted="true"] {{
    color: {text_tertiary};
}}

/* ── 帖子卡片 ── */
QFrame#PostCard {{
    background: {bg_card};
    border: 1px solid {border};
    border-radius: 12px;
}}
QFrame#PostCard:hover {{
    border-color: {border_focus};
}}
QLabel#PostTitle {{
    font-size: 15px;
    font-weight: 700;
    color: {text_primary};
}}
QLabel#PostSummary {{
    color: {text_secondary};
}}
QLabel#PostMeta {{
    color: {text_tertiary};
    font-size: 12px;
}}
QLabel#CategoryChip {{
    background: {primary};
    color: {primary_text};
    border-radius: 9px;
    padding: 1px 9px;
    font-size: 12px;
}}
QLabel#TitleChip {{
    background: {bg_icon};
    color: {primary};
    border-radius: 9px;
    padding: 1px 8px;
    font-size: 12px;
    font-weight: 700;
}}

/* ── 按钮 ── */
QPushButton {{
    background: {bg_input};
    color: {text_primary};
    border: 1px solid {border};
    border-radius: {radius}px;
    padding: 6px 14px;
    min-height: 18px;
}}
QPushButton:hover {{
    background: {bg_hover};
    border-color: {border_focus};
}}
QPushButton:pressed {{
    background: {bg_item_active};
}}
QPushButton:disabled {{
    color: {text_tertiary};
    background: {bg_item_hover};
}}
QPushButton[variant="primary"] {{
    background: {primary};
    color: {primary_text};
    border: 1px solid {primary};
    font-weight: 700;
}}
QPushButton[variant="primary"]:hover {{
    background: {primary_hover};
    border-color: {primary_hover};
}}
QPushButton[variant="danger"] {{
    background: transparent;
    color: {danger};
    border: 1px solid {danger};
}}
QPushButton[variant="danger"]:hover {{
    background: {bg_hover};
}}
QPushButton[variant="ghost"] {{
    background: transparent;
    border: none;
    color: {text_secondary};
    padding: 4px 8px;
}}
QPushButton[variant="ghost"]:hover {{
    background: {bg_item_hover};
    color: {text_primary};
}}
QPushButton[variant="chip"] {{
    background: {bg_icon};
    border: none;
    border-radius: 12px;
    padding: 4px 12px;
    color: {text_secondary};
}}
QPushButton[variant="chip"][active="true"] {{
    background: {primary};
    color: {primary_text};
    font-weight: 700;
}}

/* ── 输入控件 ── */
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDateEdit, QComboBox {{
    background: {bg_input};
    color: {text_primary};
    border: 1px solid {border};
    border-radius: {radius}px;
    padding: 6px 10px;
    selection-background-color: {primary};
    selection-color: {primary_text};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
QSpinBox:focus, QDateEdit:focus, QComboBox:focus {{
    border-color: {border_focus};
}}
QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {{
    color: {text_tertiary};
}}
QComboBox::drop-down {{
    border: none;
    width: 18px;
}}
QComboBox QAbstractItemView {{
    background: {bg_card};
    color: {text_primary};
    border: 1px solid {border};
    selection-background-color: {bg_item_active};
    selection-color: {text_primary};
    outline: 0;
}}

/* ── 列表 / 滚动区 ── */
QListWidget, QListView, QTreeWidget, QTableWidget {{
    background: transparent;
    border: none;
    outline: 0;
}}
QListWidget::item, QListView::item {{
    border-radius: {radius}px;
    padding: 6px 8px;
}}
QListWidget::item:hover, QListView::item:hover {{
    background: {bg_item_hover};
}}
QListWidget::item:selected, QListView::item:selected {{
    background: {bg_item_active};
    color: {text_primary};
}}
QScrollArea {{
    background: transparent;
    border: none;
}}
QScrollArea > QWidget > QWidget {{
    background: transparent;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {text_tertiary};
    border-radius: 4px;
    min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{
    background: {primary};
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {text_tertiary};
    border-radius: 4px;
    min-width: 28px;
}}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
    border: none;
    height: 0;
    width: 0;
}}

/* ── 标签页 ── */
QTabWidget::pane {{
    border: 1px solid {border};
    border-radius: {radius}px;
    top: -1px;
    background: {bg_card};
}}
QTabBar::tab {{
    background: transparent;
    color: {text_secondary};
    border: none;
    padding: 7px 14px;
    margin-right: 4px;
    border-top-left-radius: {radius}px;
    border-top-right-radius: {radius}px;
}}
QTabBar::tab:hover {{
    background: {bg_item_hover};
}}
QTabBar::tab:selected {{
    background: {bg_card};
    color: {primary};
    font-weight: 700;
    border: 1px solid {border};
    border-bottom-color: {bg_card};
}}

/* ── 菜单 ── */
QMenuBar {{
    background: {bg_header};
    color: {text_primary};
}}
QMenuBar::item:selected {{
    background: {bg_item_hover};
}}
QMenu {{
    background: {bg_card};
    color: {text_primary};
    border: 1px solid {border};
    border-radius: 10px;
    padding: 6px;
}}
QMenu::item {{
    padding: 6px 22px 6px 12px;
    border-radius: 6px;
}}
QMenu::item:selected {{
    background: {bg_item_active};
    color: {primary};
}}
QMenu::separator {{
    height: 1px;
    background: {border_divider};
    margin: 4px 6px;
}}

/* ── 其他 ── */
QCheckBox, QRadioButton {{
    color: {text_primary};
    spacing: 6px;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 15px;
    height: 15px;
    border: 1px solid {border_focus};
    background: {bg_input};
}}
QCheckBox::indicator {{
    border-radius: 4px;
}}
QRadioButton::indicator {{
    border-radius: 8px;
}}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: {primary};
    border-color: {primary};
}}
QProgressBar {{
    background: {bg_item_hover};
    border: none;
    border-radius: 5px;
    height: 8px;
    text-align: center;
    color: {text_secondary};
}}
QProgressBar::chunk {{
    background: {primary};
    border-radius: 5px;
}}
QSplitter::handle {{
    background: {border_divider};
}}
QSplitter::handle:horizontal {{
    width: 5px;
}}
QSplitter::handle:vertical {{
    height: 5px;
}}
QGroupBox {{
    border: 1px solid {border};
    border-radius: 10px;
    margin-top: 12px;
    padding-top: 12px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
    color: {text_secondary};
    font-weight: 700;
}}
QHeaderView::section {{
    background: {bg_item_hover};
    color: {text_secondary};
    border: none;
    border-right: 1px solid {border};
    padding: 5px 8px;
}}
QStatusBar {{
    background: {bg_header};
    color: {text_tertiary};
    border-top: 1px solid {border};
}}

/* ── 世界频道 ── */
#WorldPanel {{
    background: {bg_card};
    border-left: 1px solid {border};
}}
#WorldHeader {{
    color: {text_secondary};
    font-weight: 700;
}}
#WorldStatus {{
    color: {text_tertiary};
    font-size: 12px;
}}
#WorldStatus[state="online"] {{
    color: {primary};
}}
#WorldStatus[state="offline"] {{
    color: {danger};
}}
QFrame#WorldMsg {{
    background: transparent;
    border-radius: 10px;
}}
QFrame#WorldMsg[mine="true"] {{
    background: {bg_item_hover};
}}
QLabel#WorldName {{
    color: {text_accent};
    font-size: 12px;
    font-weight: 700;
}}
QLabel#WorldTime {{
    color: {text_tertiary};
    font-size: 11px;
}}
#WorldInput {{
    background: {bg_input};
    border: 1px solid {border};
    border-radius: 14px;
    padding: 6px 12px;
}}
#WorldResizer {{
    background: transparent;
}}
#WorldResizer:hover {{
    background: {bg_icon_hover};
}}

/* ── 评论 ── */
QFrame#CommentItem {{
    background: transparent;
    border: none;
    border-left: 2px solid {border_divider};
}}
QLabel#CommentFloor {{
    color: {text_tertiary};
    font-size: 11px;
}}

/* ── 提示 / 加载 ── */
#Toast {{
    background: {bg_card};
    color: {text_primary};
    border: 1px solid {border};
    border-radius: 10px;
    padding: 10px 18px;
}}
#EmptyHint {{
    color: {text_tertiary};
    padding: 28px 0;
}}
#LoadingHint {{
    color: {text_tertiary};
}}
QTextBrowser#MarkdownView {{
    background: transparent;
    border: none;
}}
#AvatarCircle {{
    background: {bg_icon};
    border-radius: 22px;
}}
#Divider {{
    background: {border_divider};
    max-height: 1px;
    min-height: 1px;
}}
"""

_QSS_TEMPLATE = _QSS_TEMPLATE.replace("{radius}", str(PRIMARY_RADIUS))

_DOC_TEMPLATE = """
body {{
    color: {text_primary};
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 14px;
    line-height: 1.7;
}}
h1 {{ font-size: 21px; margin: 14px 0 8px 0; }}
h2 {{ font-size: 18px; margin: 12px 0 7px 0; }}
h3 {{ font-size: 16px; margin: 10px 0 6px 0; }}
h4, h5, h6 {{ font-size: 14px; margin: 9px 0 5px 0; }}
p {{ margin: 6px 0; }}
a {{ color: {text_accent}; text-decoration: none; }}
code {{
    background: {code_bg};
    color: {danger};
    font-family: "Cascadia Mono", Consolas, "Courier New", monospace;
}}
pre {{
    background: {code_bg};
    color: {text_primary};
    padding: 10px;
    font-family: "Cascadia Mono", Consolas, "Courier New", monospace;
}}
blockquote {{
    border-left: 3px solid {primary};
    color: {text_secondary};
    margin: 8px 0 8px 4px;
    padding-left: 10px;
}}
table {{ border-collapse: collapse; }}
th, td {{ border: 1px solid {border}; padding: 5px 9px; }}
th {{ background: {bg_item_hover}; }}
hr {{ color: {border_divider}; }}
mark {{ background: {mark_bg}; color: {text_primary}; }}
img {{ max-width: 100%; }}
"""


def apply(app, mode: str | None = None) -> str:
    """给 QApplication 应用样式，返回实际生效的主题名。"""
    effective = resolve_mode(mode)
    app.setStyleSheet(qss(effective))
    return effective
