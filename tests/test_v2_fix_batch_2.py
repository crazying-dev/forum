"""V2 第二批线上问题修复验收测试（契约先行）。

覆盖 4 个线上反馈问题：
  P1 个人主页「发布的帖子」永远卡在「加载中...」
     —— UserView.vue / SearchView.vue 使用了未 import 的 nextTick / resolveAvatars，
        执行到 await nextTick() 抛 ReferenceError，后续 loadPosts() 不再执行。
  P2 出生日期改为 V1 组件样式（年-月-日：年份带 ± 步进 + 月/日输入框，存库 YYYYMMDD）
  P3 「无限年换算」点「换算」无反应
     —— AfterBody.js 分两个 IIFE，wuxianToCE / wuxianYearLabel 定义在 Part 1 且未经
        __yoyoApp 导出，Part 2 的 initWuxianConverter 调用即 ReferenceError。
  P4 Nginx 反向代理后后端日志拿不到真实客户端 IP（全是 127.0.0.1）
     —— app.py 的 ProxyFix 被注释掉；已启用并补上带真实 IP 的访问日志。
  P5 资料页展示生日/年龄（照 V1：用户名下方，生日蛋糕图标 + 保密/xx 岁）
     —— UserView.vue 新增 ageDisplay（兼容 YYYYMMDD 算周岁 / 纯数字），
        main.css 新增 .user-profile-meta / .user-meta-item 样式。
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CSS = (ROOT / "static" / "css" / "main.css").read_text(encoding="utf-8")
JS = (ROOT / "static" / "js" / "AfterBody.js").read_text(encoding="utf-8")
APP_PY = (ROOT / "app.py").read_text(encoding="utf-8")
USER_API = (ROOT / "api" / "user" / "__init__.py").read_text(encoding="utf-8")

VUE_SRC = ROOT / "frontend" / "src"
USER_VUE = (VUE_SRC / "views" / "UserView.vue").read_text(encoding="utf-8")
SEARCH_VUE = (VUE_SRC / "views" / "SearchView.vue").read_text(encoding="utf-8")

# Vue / utils 中会被视图使用、必须显式 import 的名字
# （漏 import 时 esbuild 不会报错，但运行到该行会抛 ReferenceError）
MUST_IMPORT = [
    "nextTick", "computed", "onMounted", "ref", "watch", "onBeforeUnmount",
    "apiFetch", "esc", "fmtTime", "toast", "avatarHtml", "resolveAvatars",
    "getCurrentUser", "categoryLabel", "renderMarkdown", "enhanceContent",
]


def _imported_names(src: str) -> set:
    """收集文件内所有 import 语句中的具名导入。"""
    names = set()
    for m in re.finditer(r"^\s*import\s+(.+?)\s+from\s+['\"][^'\"]+['\"]", src, re.M | re.S):
        block = m.group(1)
        braces = re.search(r"\{([^}]*)\}", block)
        if braces:
            for part in braces.group(1).split(","):
                name = part.split(" as ")[-1].strip()
                if name:
                    names.add(name)
        else:
            names.add(block.strip().split(" as ")[-1].strip())
    return names


def _locally_declared(src: str) -> set:
    """收集文件内本地声明的名字（function / const / let / var），避免误判。"""
    names = set()
    for m in re.finditer(r"(?:function|const|let|var)\s+([A-Za-z_$][\w$]*)", src):
        names.add(m.group(1))
    return names


def _missing_imports(src: str) -> list:
    imported = _imported_names(src)
    local = _locally_declared(src)
    missing = []
    for name in MUST_IMPORT:
        if re.search(r"\b" + name + r"\b", src) and name not in imported and name not in local:
            missing.append(name)
    return missing


# ── P1 帖子未加载：缺失 import 导致 ReferenceError ──
def test_p1_user_view_imports_next_tick_and_resolve_avatars():
    imported = _imported_names(USER_VUE)
    assert "nextTick" in imported, "UserView.vue 使用 nextTick 但未从 vue 导入（load() 会抛 ReferenceError，帖子列表永远加载中）"
    assert "resolveAvatars" in imported, "UserView.vue 未从 utils.js 导入 resolveAvatars"
    # 用法仍在（回归防护：函数被删掉时此测试也应有意义）
    assert re.search(r"await nextTick\(\)", USER_VUE), "UserView.vue 未在渲染后 nextTick"
    assert "resolveAvatars(document)" in USER_VUE, "UserView.vue 未在渲染后解析 data-src 头像"


def test_p1_search_view_imports_next_tick():
    assert "nextTick" in _imported_names(SEARCH_VUE), \
        "SearchView.vue 使用 nextTick 但未导入（搜索结果头像不会加载）"


def test_p1_all_views_have_no_missing_imports():
    missing = {}
    for path in (VUE_SRC / "views").glob("*.vue"):
        bad = _missing_imports(path.read_text(encoding="utf-8"))
        if bad:
            missing[path.name] = bad
    assert not missing, f"以下视图使用了未导入的标识符（运行时会 ReferenceError）: {missing}"


# ── P2 生日选择器：V1 组件样式（年-月-日） ──
def test_p2_birthday_picker_markup_and_style():
    # 结构：年 ± 步进 + 年/月/日 输入框
    assert 'class="birthday-picker"' in USER_VUE, "编辑资料弹窗缺少 V1 风格的 .birthday-picker"
    assert 'class="bp-year"' in USER_VUE and 'class="bp-month"' in USER_VUE \
        and 'class="bp-day"' in USER_VUE, "出生日期选择器缺少 年/月/日 输入框"
    assert USER_VUE.count('class="bp-arrow"') == 2, "年份需要 上一年/下一年 两个步进按钮"
    assert re.search(r"function bpYearStep\s*\(", USER_VUE), "缺少年份 ± 步进逻辑 bpYearStep"
    # 不再使用原生日期控件（改为 V1 的年-月-日 组件）
    assert 'type="date"' not in USER_VUE, "出生日期仍在用原生 input[type=date]，未换成 V1 组件"
    # 样式（含年份切换过渡）
    assert ".birthday-picker" in CSS, "main.css 缺少 .birthday-picker 样式"
    assert ".birthday-picker .bp-year" in CSS and ".birthday-picker .bp-month" in CSS, \
        "main.css 缺少 年/月 输入框样式"
    assert ".bp-year-anim" in CSS, "main.css 缺少年份切换过渡样式 .bp-year-anim"


def test_p2_birthday_saved_as_v1_yyyymmdd():
    # V1 组件存库格式为 YYYYMMDD（在线库 users.age 列兼容）
    assert re.search(r"function bpDateValue\s*\(", USER_VUE), "缺少选择器取值函数 bpDateValue"
    assert re.search(r"function parseAgeToYmd\s*\(", USER_VUE), "缺少已有生日的解析函数（兼容存量格式）"
    assert re.search(r"padStart\(4, '0'\)", USER_VUE), "bpDateValue 未补零成 YYYYMMDD"
    # 兼容存量：YYYYMMDD / YYYY-MM-DD / YYYY/MM/DD
    assert re.search(r"\^\\d\{8\}\$", USER_VUE), "未兼容存量 YYYYMMDD 生日"
    # 后端放行 8 位 YYYYMMDD
    assert 're.fullmatch(r"\\d{8}", age_raw)' in USER_API, "API 未放行 YYYYMMDD 格式的 age"


# ── P3 无限年换算：跨 IIFE 调用未定义 ──
def test_p3_wuxian_helpers_exported_and_destructured():
    assert "wuxianToCE: wuxianToCE" in JS and "wuxianYearLabel: wuxianYearLabel" in JS, \
        "window.__yoyoApp 未导出 wuxianToCE / wuxianYearLabel（Part 2 调用即 ReferenceError）"
    assert re.search(r"\bvar\s+wuxianToCE\s*=\s*app\.wuxianToCE", JS), \
        "Part 2 未从 __yoyoApp 取用 wuxianToCE"
    assert re.search(r"wuxianYearLabel\s*=\s*app\.wuxianYearLabel", JS), \
        "Part 2 未从 __yoyoApp 取用 wuxianYearLabel"
    # 换算按钮仍绑定 click（不是只靠 input 实时换算）
    assert re.search(r"convert\.addEventListener\('click'", JS), "换算按钮未绑定 click 处理"
    assert "#wuxianConvert" not in JS and 'el(\'wuxianConvert\')' in JS, "换算按钮 id 取值异常"


def test_p3_strip_markdown_also_exported():
    # 同类隐患：Part 2 的 postItemHtml 也引用了 Part 1 的 stripMarkdown
    assert "stripMarkdown: stripMarkdown" in JS, "__yoyoApp 未导出 stripMarkdown"
    assert re.search(r"stripMarkdown\s*=\s*app\.stripMarkdown", JS), \
        "Part 2 未从 __yoyoApp 取用 stripMarkdown"


# ── P4 Nginx 代理后的真实客户端 IP ──
def test_p4_proxy_fix_enabled():
    # 必须是真正生效的一行，而不是注释
    active = [ln for ln in APP_PY.splitlines()
              if "ProxyFix(" in ln and not ln.strip().startswith("#")]
    assert active, "app.py 未启用 ProxyFix（Nginx 代理后 remote_addr 恒为 127.0.0.1）"
    assert re.search(r"ProxyFix\(app\.wsgi_app,\s*x_for=1", APP_PY), \
        "ProxyFix 未配置 x_for=1（只信任最近一跳代理，避免伪造头被采信）"
    assert "TRUST_PROXY" in APP_PY, "缺少 TRUST_PROXY 开关（便于无代理环境关闭）"


def test_p4_access_log_contains_real_client_ip():
    assert "[access] ip=" in APP_PY, "访问日志未打印真实客户端 IP"
    assert "werkzeug.proxy_fix.orig" in APP_PY, \
        "访问日志未区分直连方（peer），无法确认请求经代理转发"
    assert "after_request" in APP_PY and "before_request" in APP_PY, "访问日志钩子未注册"


# ── P5 资料页展示生日/年龄（照 V1 显示在用户名下方） ──
def test_p5_profile_shows_age_meta_item():
    # 模板：用户名下方一行 user-profile-meta，内含生日蛋糕图标 + 年龄
    assert 'class="user-profile-meta"' in USER_VUE, "资料页缺少用户名下方的 .user-profile-meta 行"
    assert 'class="user-meta-item"' in USER_VUE, "资料页缺少 .user-meta-item 元信息项"
    assert "fa-birthday-cake" in USER_VUE, "年龄未使用 V1 的生日蛋糕图标 fa-birthday-cake"
    assert re.search(r"\{\{\s*ageDisplay\s*\}\}", USER_VUE), "未渲染 ageDisplay 年龄文本"
    # 位置：应排在名称之后、统计行之前（用户名下方）
    assert USER_VUE.index("user-profile-meta") < USER_VUE.index('class="user-profile-stats"'), \
        ".user-profile-meta 应在用户名（名称）下方、统计行之前"


def test_p5_age_display_matches_v1_logic():
    assert re.search(r"const\s+ageDisplay\s*=\s*computed\(", USER_VUE), "缺少年龄展示计算属性 ageDisplay"
    # YYYYMMDD：按今天算周岁（月份/日期未到则减一），与 V1 __profileAgeDisplay 一致
    assert re.search(r"now\.getFullYear\(\)\s*-\s*dt\.getFullYear\(\)", USER_VUE), \
        "年龄未按年份差计算"
    assert re.search(r"now\.getMonth\(\)\s*-\s*dt\.getMonth\(\)", USER_VUE), \
        "年龄未考虑月份（未到生日不应进位）"
    assert re.search(r"now\.getDate\(\)\s*<\s*dt\.getDate\(\)", USER_VUE), \
        "年龄未考虑日期（当月未到生日不应进位）"
    # 空 / 非法 → 保密，与 V1 一致
    assert "'保密'" in USER_VUE, "年龄缺省值不是「保密」"


def test_p5_age_meta_styles_present():
    assert ".user-profile-meta" in CSS, "main.css 缺少 .user-profile-meta 样式"
    assert ".user-meta-item" in CSS, "main.css 缺少 .user-meta-item 样式"
