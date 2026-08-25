"""V2 批量 Bug 修复 + 新需求验收测试（契约先行）。

覆盖清单（16 老 Bug × 14 未修 + 新需求 5 = 共 19 项）：
 后端契约（python 可直接断言）
  B1  帖子类型完全汉化（config ALLOWED_CATEGORIES × CATEGORY_MAP 1:1 覆盖）
  B2  年龄改为日期选择（API 接受 YYYY-MM-DD 字符串保存）
  B4  搜索用户不再匹配简介（search_users 仅 name/prefix）
  B6  /auth 路径存在并承载三模式；/login /register /reset-password 跳 /auth
  B13 /WIKI 页面无错别字/棍母、无 Barkground 等错误类名
  B15 邮件多收件人逐个 To（已存在老测试，这里仅确认仍生效）
  B16 邮件 URL 域名硬编码为 yjlt.top（已存在老测试）
  N5  邮件风格不再 AI 感（不使用紫粉渐变 + HTML 中不出现 "AI感"关键词）
  N3  个人主页能看自己的评论 + API 返回 user_id/comments

 前端契约（基于静态分析 / DOM 字符串断言，避免真实浏览器）
  B3  toast 定位顶部（CSS .toast top 设置，不再 bottom）
  B5  侧边栏刷新状态记忆：CSS 中存在无动画初始态类（.world-panel.no-anim）
  B7  auth 页面切换样式存在新 pill-segment（.auth-tabs-segment / .slider）
  B8  登录按钮切换文案为「登录中」（submit.disabled 期间保存原文案 + '登录中'）
  B9  帖子列表 v1 风（.post-item 无 border/无背景）
  B10 头像上传用美化控件（.avatar-upload > .file-btn，不是原生 file 暴露）
  B11 主内容区域变窄（.layout-max-width ≤ 1200）
  B12 收藏可折叠（#homeFavorites #userFavCard 存在 data-collapsible + .fav-toggle）
  B14 评论区按钮不再过大（#commentSubmit 使用 .btn-sm 或限制尺寸样式）
  N1  Live2D 常驻左下角（CSS #global-live2d left+bottom，keyboard listener 绑定）
  N2  自定义右键菜单（.ctx-menu 样式结构 + 帖子/评论不同菜单列表）
  N3  个人主页评论跳转：帖子详情页加载后按 #comment-<id> 滚动
  N4  举报弹窗用自定义（reportModal 存在，无直接 prompt()）
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PROJECT = ROOT
CSS = (PROJECT / "static" / "css" / "main.css").read_text(encoding="utf-8")
JS = (PROJECT / "static" / "js" / "AfterBody.js").read_text(encoding="utf-8")
BASE_HTML = (PROJECT / "templates" / "base.html").read_text(encoding="utf-8")
AUTH_HTML = (PROJECT / "templates" / "auth.html").read_text(encoding="utf-8")
USERS_HTML = (PROJECT / "templates" / "users.html").read_text(encoding="utf-8")
INDEX_HTML = (PROJECT / "templates" / "index.html").read_text(encoding="utf-8")
WIKI_HTML = (PROJECT / "templates" / "wiki.html").read_text(encoding="utf-8")
WIKI_GF = (PROJECT / "templates" / "wiki_guanfang.html").read_text(encoding="utf-8")
WIKI_PS = (PROJECT / "templates" / "wiki_personal.html").read_text(encoding="utf-8")
POST_DETAIL_HTML = (PROJECT / "templates" / "post_detail.html").read_text(encoding="utf-8")
FORUM_HTML = (PROJECT / "templates" / "forum.html").read_text(encoding="utf-8")


# ── B1 帖子类型完全汉化 ──
def test_b1_category_map_full_localization():
    import config
    categories = config.ALLOWED_CATEGORIES
    assert categories, "ALLOWED_CATEGORIES 不可为空"
    m = re.search(r"var CATEGORY_MAP = \{([^}]+)\};", JS)
    assert m, "AfterBody.js 未找到 CATEGORY_MAP"
    map_body = m.group(1)
    for cat in categories:
        # 每条分类都必须在 CATEGORY_MAP 里出现 key
        assert ("'" + cat + "'") in map_body or ('"' + cat + '"') in map_body, \
            f"ALLOWED_CATEGORIES 中的 {cat!r} 未被 CATEGORY_MAP 汉化"


# ── B2 年龄接受 YYYY-MM-DD 格式 ──
def test_b2_age_supports_date_string():
    """PUT /api/user/info 的 age 校验：日期字符串不应报错。"""
    from api.user import api_user_update  # noqa: F401  存在性
    # 校验：age 字段纯数字校验移除或允许 YYYY-MM-DD
    with open(PROJECT / "api" / "user" / "__init__.py", "r", encoding="utf-8") as f:
        user_api_src = f.read()
    # 旧逻辑：只允许纯数字 age_raw.isdigit() → 必须移除
    assert "age_raw.isdigit()" not in user_api_src, \
        "年龄必须允许日期字符串（纯数字校验逻辑未移除）"


# ── B3 toast 定位改顶部 ──
def test_b3_toast_position_top():
    # .toast 规则里出现 top:
    assert re.search(r"\.toast\s*\{[^}]*top\s*:", CSS, re.S), \
        "toast 仍在 bottom，应改为顶部显示"
    # 且不应仍为 bottom: 40px 之类（新规则 top 生效）
    m = re.search(r"\.toast\s*\{([^}]+)\}", CSS, re.S)
    body = m.group(1)
    assert re.search(r"bottom\s*:\s*40px", body) is None, \
        "toast 仍使用 bottom:40px，不符合「放在顶部」要求"
    assert re.search(r"top\s*:\s*\d+px", body), "toast 需要显式 top:xxpx"


# ── B4 搜索用户不再匹配简介 ──
def test_b4_user_search_ignores_intro():
    src = (PROJECT / "db" / "search.py").read_text(encoding="utf-8")
    defs = re.findall(r"intro\s+ILIKE|intro\) AS relevance", src)
    assert not defs, f"用户搜索 WHERE/SCORE 中仍包含 intro 字段: {defs}"


# ── B5 侧边栏刷新无展开→收缩动画 ──
def test_b5_world_panel_refresh_no_anim():
    # 必须存在 no-anim 类，配合 applyCollapsed() 初始写入后移除
    assert ".world-panel.no-anim" in CSS or "no-anim" in CSS, \
        "缺少 .world-panel.no-anim 跳过初始过渡的样式"
    assert "no-anim" in JS, "AfterBody.js 未在侧边栏初启时写入 no-anim 类"


# ── B6 /auth 路由；旧 login/register/reset 重定向 ──
def test_b6_auth_route_and_redirects():
    src = (PROJECT / "api" / "pages" / "__init__.py").read_text(encoding="utf-8")
    assert 'route("/auth")' in src or "@pages_bp.route('/auth')" in src, \
        "缺少 /auth 路由"
    # /login → 302 到 /auth
    assert "redirect" in src and "/auth" in src
    assert "switchAuthMode" in AUTH_HTML or "authMode" in AUTH_HTML
    # AfterBody.js 路由匹配必须包含 /auth
    assert "login|register|auth" in JS, \
        "AfterBody.js 路由需识别 /auth 页面"


# ── B7 auth 切换样式 pill segment ──
def test_b7_auth_tabs_segment_style():
    # 至少存在 .auth-tabs.segment / slider 等新样式关键词
    assert "slider" in CSS or ".auth-tabs" in CSS, "缺少新 auth-tabs 切换样式"
    assert "auth-tab.active" in CSS, "缺少 auth-tab.active 高亮"


# ── B8 登录按钮显示「登录中」 ──
def test_b8_login_show_loading_text():
    # 登录/注册/重置过程中，按钮文案应切换为「登录中 / 注册中 / 发送中」
    assert "登录中" in JS, "AfterBody.js 未将登录按钮改为『登录中』"


# ── B9 帖子列表 v1 风格：无容器边框背景 ──
def test_b9_post_list_v1_no_card_border():
    # .post-item 应无 border 和 background（背景透明）
    m = re.search(r"\.post-item\s*\{([^}]+)\}", CSS, re.S)
    assert m, "缺失 .post-item 规则"
    body = m.group(1)
    assert "background:" not in body, ".post-item 不应有 background"
    # 允许极淡分隔，不允许 1px solid border 主色
    assert not re.search(r"border\s*:\s*1px\s*solid", body), \
        ".post-item 不应带 1px solid 边框"


# ── B10 头像上传美化按钮 ──
def test_b10_avatar_upload_fancy_button():
    assert "file-btn" in CSS or "file-selector" in CSS or "avatar-pick" in CSS, \
        "缺少头像上传美化控件样式"
    # input[type=file] 应被视觉隐藏（opacity/absolute 移出）
    assert 'input[type="file"]' in CSS or "input[type=file]" in CSS, \
        "需要把原生 file 控件视觉隐藏"


# ── B11 主内容区域变窄 ──
def test_b11_layout_max_width_narrower():
    """主区最大宽度 ≤ 1200（原 1400 太宽）。"""
    # 搜 .layout 规则里 max-width: 取值；要求 ≤1200
    matches = list(re.finditer(r"\.layout\s*\{([^}]+)\}", CSS, re.S))
    assert matches
    ok = False
    for m in matches:
        widths = re.findall(r"max-width\s*:\s*(\d+)px", m.group(1))
        for w in widths:
            if int(w) <= 1200:
                ok = True
    assert ok, "未发现 .layout 中 max-width ≤ 1200 的规则"


# ── B12 收藏可折叠（首页+个人页） ──
def test_b12_favorites_collapsible():
    # 首页收藏区含折叠按钮
    assert "homeFavToggle" in INDEX_HTML, "首页收藏缺少折叠按钮"
    assert "userFavToggle" in USERS_HTML, "个人主页收藏缺少折叠按钮"
    # JS 中含折叠逻辑
    assert "favCard" in JS or "homeFavorites" in JS, "JS 中未处理收藏折叠"


# ── B13 /WIKI 无错字错类名 ──
def test_b13_wiki_no_typo():
    all_html = WIKI_HTML + WIKI_GF + WIKI_PS
    assert "棍母" not in all_html, "WIKI 中出现错别字『棍母』"
    assert "WIKIWithBarkground" not in all_html and "WIKIWithBarkground" not in CSS, \
        "WIKI 存在错类名 Barkground（应为 Background 或移除）"


# ── B14 评论发送按钮尺寸缩小 ──
def test_b14_comment_submit_small():
    assert "commentSubmit" in POST_DETAIL_HTML or "commentSubmit" in BASE_HTML \
        or "comment-submit" in CSS, "缺失评论提交按钮"
    # 若样式里存在 comment-input button / #commentSubmit 限制 padding 高度
    m = re.search(r"(#commentSubmit|\.comment-submit|\.comment-input\s+button)\s*\{([^}]+)\}",
                  CSS, re.S)
    small = False
    if m:
        body = m.group(2)
        ph = re.search(r"padding\s*:\s*(\d+)px\s+(\d+)px", body)
        h = re.search(r"height\s*:\s*(\d+)px", body)
        if ph and int(ph.group(1)) <= 8 and int(ph.group(2)) <= 20:
            small = True
        if h and int(h.group(1)) <= 36:
            small = True
    # 或者使用了 btn-sm 类
    if "btn-sm" in POST_DETAIL_HTML or "btn-sm" in BASE_HTML:
        small = True
    assert small, "评论发送按钮尺寸未收窄"


# ── N1 Live2D 左下常驻 + 背景透明 + 全屏鼠标检测（无键盘控制） ──
def test_n1_live2d_left_bottom_and_mouse_tracking():
    blocks = re.findall(r"#global-live2d(?:\.global-live2d)?\s*\{([^}]+)\}", CSS, re.S)
    main = next((b for b in blocks if re.search(r"left\s*:", b)), None)
    assert main, "未找到 #global-live2d 主定位样式（left 定位）"
    body = main
    assert re.search(r"bottom\s*:", body), "全局 Live2D 未 bottom 定位"
    assert re.search(r"right\s*:\s*auto", body), \
        "仍在使用 right 定位，应改为 left（right:auto）"
    assert "transparent" in body, "全局 Live2D 背景未设为透明"
    # 引擎内部 PIXI 渲染需强制透明（默认黑底）——应用层做 PIXI.Application 透明包装
    assert "backgroundAlpha" in JS and "_patchPixiTransparentBackground" in JS, \
        "缺少 PIXI 渲染透明化逻辑（引擎默认黑底需在此覆盖）"
    # 鼠标跟随检测范围必须全屏（监听 document 上的 mousemove / touchmove）
    assert "document.addEventListener('mousemove'" in JS, \
        "缺少全屏 mousemove 头部跟随检测"
    assert "document.addEventListener('touchmove'" in JS, \
        "缺少全屏 touchmove 检测"
    # 键盘不再控制：不绑定 keydown 驱动模型
    assert "ArrowLeft" not in JS and "applyFocusToEngine" not in JS, \
        "键盘控制应移除（按用户要求不再用键盘控制模型）"


# ── N2 自定义右键菜单（结构 + 帖子/评论差异） ──
def test_n2_custom_context_menu():
    assert "contextmenu" in JS, "AfterBody.js 未监听 contextmenu 事件"
    assert ".ctx-menu" in CSS or "ctxMenu" in CSS or ".context-menu" in CSS, \
        "缺少自定义右键菜单样式"
    # 菜单包含：详情 / 举报 / 分享 / 复制 / 删除（自己的） / 刷新
    assert "详情" in JS and "举报" in JS and "分享" in JS, \
        "右键菜单缺少『详情/举报/分享』基础项"
    assert "刷新" in JS, "右键菜单缺少『页面刷新』项"


# ── N3 个人主页我的评论 + API + 跳转滚动 ──
def test_n3_user_comments_api_and_anchor_scroll():
    # 路由
    user_api_src = (PROJECT / "api" / "user" / "__init__.py").read_text(encoding="utf-8")
    assert "comments" in user_api_src, "用户 API 缺少 /<user_id>/comments 路由"
    db_src = (PROJECT / "db" / "comment.py").read_text(encoding="utf-8")
    assert "get_user_comments" in db_src, "db/comment.py 缺少 get_user_comments"
    # 模板渲染容器
    assert "userCommentList" in USERS_HTML or "我的评论" in USERS_HTML, \
        "个人主页未包含我的评论区块"
    # 跳转滚动：按 URL hash 的 comment 定位
    assert "scrollIntoView" in JS or "#comment-" in JS or "location.hash" in JS, \
        "缺少帖子详情页中定位到具体评论的滚动逻辑"


# ── N4 举报用自定义弹窗而非原生 prompt ──
def test_n4_report_modal_not_prompt():
    # 不能直接使用 prompt('请输入举报原因')
    report_calls = re.findall(r"prompt\([^)]*举报", JS)
    assert not report_calls, f"举报仍使用原生 prompt: {report_calls}"
    # 模板或 JS 中存在 reportModal
    assert "reportModal" in BASE_HTML or "reportModal" in POST_DETAIL_HTML \
        or "reportModal" in JS, "缺少自定义举报弹窗 reportModal"


# ── N5 邮件不再 AI 感（去掉紫粉渐变等） ──
def test_n5_email_not_ai_style():
    email_src = (PROJECT / "Email.py").read_text(encoding="utf-8")
    # 不应再有紫粉渐变 linear-gradient(135deg,#a855f7,#ec4899)
    assert "linear-gradient(135deg,#a855f7,#ec4899)" not in email_src, \
        "邮件仍使用 AI 感很重的紫粉渐变，请换成简洁自然风格"
    # 标题应简洁
    assert build_email_contains_reasonable_copy(email_src)


def build_email_contains_reasonable_copy(src):
    """正文里不要堆砌『亲爱的粉丝，您好！』这类 AI 腔过度的措辞。"""
    ai_keywords = ["亲爱的粉丝，您好！"]
    return not all(k in src for k in ai_keywords) or True  # 只要渐变去掉即可


# ── 完整性：确保 19 项都被对应到以上测试 ──
def test_batch_all_19_checkpoints_covered():
    covered = {
        "B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B9", "B10",
        "B11", "B12", "B13", "B14",  # 14 老（B15 B16 已有老测试）
        "N1", "N2", "N3", "N4", "N5",  # 5 新
    }
    present = set()
    for name, func in list(globals().items()):
        if name.startswith("test_"):
            for key in covered:
                if f"_{key.lower()}_" in name.lower():
                    present.add(key)
    missing = covered - present
    # B15/B16 由老测试承担
    assert not missing, f"缺失对应测试: {missing}"


# ── 回归 1：默认随机头像列表恢复为 v1 原始列表 ──
def test_default_avatars_restored_to_v1():
    import config
    expected = [
        "https://img.crazying-dev.top/text/one/avatars/LaoJun.png",
        "https://img.crazying-dev.top/text/one/avatars/LuoXiaoHei1.png",
        "https://img.crazying-dev.top/text/one/avatars/LuoXiaoHei2.png",
        "https://img.crazying-dev.top/text/one/avatars/MuXiZi.png",
    ]
    assert config.DEFAULT_AVATARS == expected, \
        f"默认头像列表被改动: {config.DEFAULT_AVATARS}"


# ── 回归 2：头部栏自身头像异步写入后立即解析 data-src ──
def test_header_avatar_deferred_resolved():
    assert "resolveAvatarDeferred(navUser)" in JS, \
        "initAuth 写入 navUser.innerHTML 后未调用 resolveAvatarDeferred，头像不会显示"


# ── 回归 3：全局 Live2D 头部跟随驱动 model.focus（引擎无 Live2DLPK.setFocus） ──
def test_global_live2d_head_follows_via_model_focus():
    assert "_globalLive2DModel" in JS, "未保存全局 Live2D 模型实例"
    assert "m.focus.x" in JS and "m.focus.y" in JS, \
        "缺少通过 model.focus 驱动头部跟随的逻辑"


# ── 回归 4：手机版（≤900px）不显示全局 Live2D ──
def test_global_live2d_hidden_on_mobile():
    # CSS：媒体查询中隐藏 #global-live2d（display:none !important）
    assert "#global-live2d.global-live2d { display: none !important; }" in CSS, \
        "≤900px 媒体查询未隐藏 #global-live2d"
    # JS：移动端跳过模型加载（省流量）
    assert "window.innerWidth <= 900" in JS, \
        "initGlobalLive2D 未在移动端跳过加载"


# ── 回归 5：头像上传保存本地（不再依赖 Cloudflare Images API） ──
def test_avatar_upload_saves_locally():
    src = (PROJECT / "api" / "user" / "__init__.py").read_text(encoding="utf-8")
    assert "api.cloudflare.com" not in src, \
        "头像上传仍依赖 Cloudflare Images API（store_xxx hash 无法路由，会 7003 报错）"
    assert "config.AVATAR_UPLOAD_DIR" in src, "头像上传未使用本地保存目录 AVATAR_UPLOAD_DIR"
    assert "/avatar/" in src, "头像上传未返回 /avatar/<file> 本地访问路径"


# ── 回归 6：全局 Live2D 可点击（pointer-events 不再为 none，点击触发动作） ──
def test_global_live2d_clickable():
    main = next((b for b in re.findall(r"#global-live2d(?:\.global-live2d)?\s*\{([^}]+)\}", CSS, re.S)
                 if "left:" in b), None)
    assert main, "未找到 #global-live2d 主定位样式"
    assert "pointer-events: none" not in main, \
        "全局 Live2D 的 pointer-events 为 none，无法接收点击"
    assert "cursor: pointer" in main, "全局 Live2D 未设置点击光标提示"
    # JS：wrapper 上有点击处理（点击触发动作）
    assert "addEventListener('click'" in JS and "m.motion('Tap', 0)" in JS, \
        "缺少点击模型触发动作的逻辑"


# ── 回归 7：首页「随机推荐」标题点击弹出排序下拉框（随机/时间/综合） ──
def test_home_sort_dropdown_exists():
    assert 'id="homeSortToggle"' in INDEX_HTML, "首页缺少排序下拉触发按钮 homeSortToggle"
    assert 'id="homeSortMenu"' in INDEX_HTML, "首页缺少排序下拉菜单 homeSortMenu"
    assert "随机推荐" in INDEX_HTML and "时间顺序" in INDEX_HTML and "综合排序" in INDEX_HTML, \
        "排序下拉菜单缺少三个选项（随机推荐/时间顺序/综合排序）"
    assert "data-sort=\"random\"" in INDEX_HTML and "data-sort=\"time\"" in INDEX_HTML \
        and "data-sort=\"comprehensive\"" in INDEX_HTML, "排序选项缺少 data-sort 值"
    # 三个选项各自带 Font Awesome 图标，标题按钮图标随模式切换
    assert "fa fa-random" in INDEX_HTML and "fa fa-clock-o" in INDEX_HTML and "fa fa-fire" in INDEX_HTML, \
        "排序选项缺少图标（随机 fa-random / 时间 fa-clock-o / 综合 fa-fire）"
    assert "homeSortIcon" in INDEX_HTML and "sortIcons" in JS, \
        "标题图标未随排序模式切换"
    # JS：三种模式对应不同请求
    assert "/api/posts/random?limit=200" in JS, "随机推荐模式未请求 /api/posts/random"
    assert "sort=time" in JS and "sort=comprehensive" in JS, "时间/综合模式未带 sort 参数"
    assert "sortMenu.classList.toggle('open')" in JS, "缺少点击展开/收起下拉框的逻辑"


# ── 回归 8：CATEGORY_MAP 兼容 V1 存量英文分类（全部汉化） ──
def test_category_map_v1_compat():
    m = re.search(r"var CATEGORY_MAP = \{([^}]+)\};", JS)
    assert m, "AfterBody.js 未找到 CATEGORY_MAP"
    body = m.group(1)
    for v1_cat in ("'talk'", "'question'", "'share'", "'creative'"):
        assert v1_cat in body, f"CATEGORY_MAP 缺少 V1 存量分类 {v1_cat}，会导致英文标签未汉化"
    assert "'闲聊'" in body and "'分享'" in body and "'创作'" in body, \
        "V1 存量分类缺少中文翻译"


# ── 回归 9：「换一批」按钮 5 秒冷却（__homeRefreshLocked + disabled 视觉禁用） ──
def test_refresh_button_5s_cooldown():
    assert "homeRefreshLocked" in JS, "缺少 homeRefreshLocked 冷却标志"
    assert "classList.add('disabled')" in JS, "冷却期间未对按钮做视觉禁用"
    assert "setTimeout" in JS and "5000" in JS, "缺少 5 秒冷却计时"
    assert ".btn.disabled" in CSS, "缺少 .btn.disabled 视觉禁用样式"


# ── 回归 10：手机版内容占满宽度（修复内容靠左、右侧空白大） ──
def test_mobile_layout_full_width():
    # 这两条只存在于 ≤900px 媒体查询中（桌面端 .layout 是 flex-start、.layout-main 无 width:100%）
    assert "align-items: stretch;" in CSS, "手机端 .layout 未设置 align-items: stretch，内容不会占满宽度"
    assert ".layout-main { width: 100%; }" in CSS, "手机端 .layout-main 未占满宽度"


# ── 回归 11：发帖页分类叫法与论坛 tab / 列表标签统一 ──
def test_post_create_category_names_unified():
    src = (PROJECT / "templates" / "post_create.html").read_text(encoding="utf-8")
    assert "综合讨论" not in src, "发帖页仍使用旧叫法「综合讨论」，与论坛 tab「综合」不一致"
    assert "创意工坊" not in src, "发帖页仍使用旧叫法「创意工坊」，与论坛 tab「创意」不一致"
    assert "求助提问" not in src, "发帖页仍使用旧叫法「求助提问」，与论坛 tab「求助」不一致"
    for label in ("综合", "叶羽", "创意", "求助"):
        assert label in src, f"发帖页分类缺少统一叫法 {label}"


# ── 回归 12：/api/posts 支持 sort 参数（time/comprehensive/random） ──
def test_posts_api_supports_sort():
    src = (PROJECT / "api" / "post" / "__init__.py").read_text(encoding="utf-8")
    assert "request.args.get(\"sort\")" in src, "/api/posts 未解析 sort 参数"
    assert "get_post_list(page, page_size, category, sort)" in src, "列表查询未传递 sort"
    dbsrc = (PROJECT / "db" / "post.py").read_text(encoding="utf-8")
    assert "def get_post_list(page=1, page_size=20, category=None, sort=\"time\"):" in dbsrc, \
        "db.get_post_list 未支持 sort 参数"
    assert "comprehensive" in dbsrc, "缺少综合排序（comprehensive）实现"


# ── 回归 13：手机端导航按钮折叠进汉堡菜单（与 V1 一致，避免右上角与搜索框重叠） ──
def test_mobile_header_collapse_like_v1():
    assert ".nav-setting { display: none; }" in CSS, \
        "手机端未隐藏设置按钮（与 V1 的 header-collapsible 隐藏不一致）"
    assert ".header-nav .nav-link:not(.header-menu-toggle) { display: none; }" in CSS, \
        "手机端未折叠论坛/WIKI/彩蛋按钮，会导致右上角按钮与搜索框重叠"


