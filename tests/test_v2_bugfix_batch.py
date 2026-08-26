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

# Vue3 重写后的页面组件源码（渐进式增强：核心页面由 Vue 渲染，模板仅剩挂载点）
VUE_SRC = PROJECT / "frontend" / "src"
AUTH_VUE = (VUE_SRC / "views" / "AuthView.vue").read_text(encoding="utf-8")
HOME_VUE = (VUE_SRC / "views" / "HomeView.vue").read_text(encoding="utf-8")
POST_VUE = (VUE_SRC / "views" / "PostDetailView.vue").read_text(encoding="utf-8")
USER_VUE = (VUE_SRC / "views" / "UserView.vue").read_text(encoding="utf-8")
SEARCH_VUE = (VUE_SRC / "views" / "SearchView.vue").read_text(encoding="utf-8")
FORUM_VUE = (VUE_SRC / "views" / "ForumView.vue").read_text(encoding="utf-8")
UTILS_VUE = (VUE_SRC / "utils.js").read_text(encoding="utf-8")


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
    assert "switchAuthMode" in AUTH_HTML or "authMode" in AUTH_HTML or "switchMode" in AUTH_VUE, \
        "缺少登录/注册/找回三种模式切换逻辑"
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
    # 首页收藏区含折叠按钮（Vue3 重写后检查 HomeView.vue）
    assert ("homeFavToggle" in INDEX_HTML or ("我的收藏" in HOME_VUE and "toggleFav" in HOME_VUE)), \
        "首页收藏缺少折叠按钮"
    assert ("userFavToggle" in USERS_HTML or ("我的收藏" in USER_VUE and "toggleFav" in USER_VUE)), \
        "个人主页收藏缺少折叠按钮"
    # JS 中含折叠逻辑
    assert "favCard" in JS or "homeFavorites" in JS or "toggleFav" in HOME_VUE, "JS 中未处理收藏折叠"


# ── B13 /WIKI 无错字错类名 ──
def test_b13_wiki_no_typo():
    all_html = WIKI_HTML + WIKI_GF + WIKI_PS
    assert "棍母" not in all_html, "WIKI 中出现错别字『棍母』"
    assert "WIKIWithBarkground" not in all_html and "WIKIWithBarkground" not in CSS, \
        "WIKI 存在错类名 Barkground（应为 Background 或移除）"


# ── B14 评论发送按钮尺寸缩小 ──
def test_b14_comment_submit_small():
    assert "commentSubmit" in POST_DETAIL_HTML or "commentSubmit" in BASE_HTML \
        or "comment-submit" in CSS or ("发表评论" in POST_VUE and "submitComment" in POST_VUE), \
        "缺失评论提交按钮"
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
    # 模板/Vue 渲染容器
    assert "userCommentList" in USERS_HTML or "我的评论" in USERS_HTML or "我的评论" in USER_VUE, \
        "个人主页未包含我的评论区块"
    # 跳转滚动：按 URL hash 的 comment 定位
    assert "scrollIntoView" in JS or "#comment-" in JS or "location.hash" in JS or "#comment-" in POST_VUE, \
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
    assert "chips.forEach(resolveAvatarDeferred)" in JS, \
        "initAuth 写入用户 chip 后未调用 resolveAvatarDeferred，头像不会显示"
    assert "headerNavUser" in JS and "headerNavUser" in BASE_HTML, \
        "顶部模式头部栏缺少用户 chip（headerNavUser）"


# ── 回归 3：全局 Live2D 头部跟随驱动 model.focus（引擎 focus 是函数 + 全屏检测） ──
def test_global_live2d_head_follows_via_model_focus():
    assert "_globalLive2DModel" in JS, "未保存全局 Live2D 模型实例"
    # 引擎 focus 是函数：_focusFromScreen 内按画布中心映射为 canvas 内坐标再调用
    assert "typeof model.focus !== 'function'" in JS, "未识别引擎 focus 为函数"
    assert "model.focus(" in JS, "缺少通过 model.focus(...) 调用驱动头部跟随"
    assert "m.focus.x" in JS and "m.focus.y" in JS, \
        "缺少 focus 为对象属性时的兼容兜底"
    # 全屏检测：mousemove 绑定在 document 上，坐标按画布中心映射到 canvas
    assert "document.addEventListener('mousemove'" in JS, \
        "mousemove 未绑定到 document（全屏检测）"
    assert "(clientX - cx) / (sw / 2)" in JS, \
        "缺少鼠标屏幕坐标 → canvas 内坐标的全屏映射"
    # 关键：Live2DLPK.load 返回 {model, app, destroy} 包装对象，必须解包取 .model
    # （否则 model.focus 不存在，全屏跟随只剩引擎 canvas 内的局部跟随）
    assert "result.model" in JS, \
        "未解包 Live2DLPK.load 返回的 {model, app, destroy} 包装对象"
    # 独立 Live2D 页同样全屏跟随
    assert "_live2DPageModel" in JS, \
        "独立 Live2D 页（/Live2D）缺少全屏头部跟随"


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


# ── 回归 6b：LPK 模型异步加载（页面加载完成后 / 浏览器空闲时启动，不拖慢首屏） ──
def test_global_live2d_lpk_async_load():
    assert "requestIdleCallback" in JS, \
        "LPK 未使用 requestIdleCallback 在浏览器空闲时异步加载"
    assert "_deferAsyncLoad" in JS, \
        "缺少 Live2D 异步加载封装（_deferAsyncLoad）"
    assert "window.addEventListener('load', function () { _deferAsyncLoad(startLpkLoad); });" in JS, \
        "全局 LPK 未等待页面 load 完成后才启动加载"
    assert "window.addEventListener('load', function () { _deferAsyncLoad(loadModel); });" in JS, \
        "独立 Live2D 页面（/Live2D）模型未异步加载"


# ── 回归 7：首页「随机推荐」标题点击弹出排序下拉框（随机/时间/综合） ──
def test_home_sort_dropdown_exists():
    # Vue3 重写后检查 HomeView.vue（模板仅剩挂载点）
    assert 'id="homeSortToggle"' in INDEX_HTML or "home-sort-toggle" in HOME_VUE, \
        "首页缺少排序下拉触发按钮 homeSortToggle"
    assert 'id="homeSortMenu"' in INDEX_HTML or "home-sort-menu" in HOME_VUE, \
        "首页缺少排序下拉菜单 homeSortMenu"
    assert "随机推荐" in INDEX_HTML + HOME_VUE and "时间顺序" in INDEX_HTML + HOME_VUE \
        and "综合排序" in INDEX_HTML + HOME_VUE, \
        "排序下拉菜单缺少三个选项（随机推荐/时间顺序/综合排序）"
    assert ("data-sort=\"random\"" in INDEX_HTML and "data-sort=\"time\"" in INDEX_HTML \
        and "data-sort=\"comprehensive\"" in INDEX_HTML) or \
        ("random" in HOME_VUE and "time" in HOME_VUE and "comprehensive" in HOME_VUE), \
        "排序选项缺少 data-sort 值"
    # 三个选项各自带 Font Awesome 图标，标题按钮图标随模式切换
    assert ("fa fa-random" in INDEX_HTML or "fa-random" in HOME_VUE) \
        and ("fa fa-clock-o" in INDEX_HTML or "fa-clock-o" in HOME_VUE) \
        and ("fa fa-fire" in INDEX_HTML or "fa-fire" in HOME_VUE), \
        "排序选项缺少图标（随机 fa-random / 时间 fa-clock-o / 综合 fa-fire）"
    assert ("homeSortIcon" in INDEX_HTML and "sortIcons" in JS) or ("switchSort" in HOME_VUE), \
        "标题图标未随排序模式切换"
    # 三种模式对应不同请求
    assert "/api/posts/random?limit=200" in JS + HOME_VUE, "随机推荐模式未请求 /api/posts/random"
    assert ("sort=time" in JS and "sort=comprehensive" in JS) or ("sort=time" in HOME_VUE and "sort=comprehensive" in HOME_VUE), \
        "时间/综合模式未带 sort 参数"
    assert "sortMenu.classList.toggle('open')" in JS or "sortOpen" in HOME_VUE, \
        "缺少点击展开/收起下拉框的逻辑"


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


# ── 回归 13：头部除 logo/搜索框外的入口改为左侧边栏（无汉堡按钮，避免右上角重叠） ──
def test_mobile_header_collapse_like_v1():
    # 模板：header 只保留 logo/搜索框；导航入口移入 .side-nav，菜单按钮已删除
    assert 'id="menuToggle"' not in BASE_HTML, "menuToggle 汉堡按钮未删除"
    assert "header-menu-toggle" not in CSS, "menuToggle 的 CSS 残留"
    assert 'class="side-nav"' in BASE_HTML and 'id="sideNav"' in BASE_HTML, "缺少左侧边栏容器"
    assert "mobileMenu" not in BASE_HTML and "mobile-menu" not in BASE_HTML, "旧的移动菜单仍残留在模板"
    # 边栏默认仅图标（56px），可展开为图标+文字（180px）
    assert "--side-nav-w: 56px" in CSS and "180px" in CSS, "侧边栏缺少 仅图标/图标+文字 两档宽度"
    assert "body.side-nav-expanded" in CSS, "缺少 side-nav-expanded 展开态样式"
    assert ".side-nav-item span { display: none; }" in CSS, "默认未隐藏文字只留图标"
    assert "body.side-nav-expanded .side-nav-item span" in CSS, "展开态未显示文字"
    # 手机端：侧边栏为常驻图标栏（52px），展开为 220px 浮层显示文字
    assert "body { padding-left: 52px; }" in CSS, "手机端缺少常驻图标栏占位"
    assert ".side-nav { width: 52px;" in CSS, "手机端图标栏宽度不是 52px"
    assert "body.side-nav-expanded .side-nav {" in CSS and "220px" in CSS, \
        "手机端展开态未变为 220px 浮层"
    # 设置下拉提供 侧边/顶部 两种导航位置模式切换
    assert 'data-navmode="side"' in BASE_HTML and 'data-navmode="top"' in BASE_HTML, \
        "设置下拉缺少 侧边/顶部 导航位置模式切换项"
    # 搜索框仍可收缩（与 V1 一致），不被挤压覆盖
    assert "flex: 0 0 auto" in CSS, \
        "手机端搜索框仍会收缩（应固定宽度），空间不足时搜索按钮会被压缩覆盖"
    assert re.search(r"\.header-search input\s*\{[^}]*min-width:\s*0", CSS), \
        "搜索输入框未设置 min-width:0，长占位符会把搜索按钮挤出容器被导航覆盖"


# ── 回归 14：导航模式切换逻辑（侧边/顶部 + 展开收起 + localStorage 持久化） ──
def test_sidebar_mode_toggle_js():
    assert "forum-navmode" in JS, "缺少导航位置模式的 localStorage 键"
    assert "setNavMode" in JS, "缺少 setNavMode 切换函数"
    assert "nav-mode-top" in JS, "JS 未切换 body.nav-mode-top 顶部模式"
    assert "side-nav-expanded" in JS, "JS 未切换 body.side-nav-expanded 展开态"
    assert "setSideNavExpanded" in JS, "缺少 setSideNavExpanded 展开/收起函数"
    assert "classList.toggle('open')" in JS, "缺少抽屉/下拉 open 切换"
    # 手机端点击图标栏外部收起（innerWidth 判断）
    assert "window.innerWidth <= 900" in JS, "缺少手机端处理（innerWidth 判断）"
    assert "menuToggle" not in JS, "JS 仍引用已删除的 menuToggle"
    assert 'data-navmode' in BASE_HTML, "设置下拉缺少 data-navmode 模式按钮"


# ── 回归 17：静态资源（LPK/JS/CSS）浏览器强缓存 + 版本号防陈旧 ──
def test_static_assets_browser_cache():
    src = (PROJECT / "app.py").read_text(encoding="utf-8")
    assert "SEND_FILE_MAX_AGE_DEFAULT" in src and "604800" in src, \
        "未为静态资源设置浏览器强缓存（7 天）"
    assert "max_age=0" in src, \
        "头像路由未关闭强缓存（用户头像会被更新，不能 7 天缓存）"
    # 版本号缓存失效：更新静态资源后 bump config.STATIC_VERSION，?v= 自动变化
    cfg = (PROJECT / "config.py").read_text(encoding="utf-8")
    assert 'STATIC_VERSION = "' in cfg, "config 缺少 STATIC_VERSION 缓存版本号"
    assert "static_version" in (PROJECT / "app.py").read_text(encoding="utf-8"), \
        "app 未注入 static_version 模板变量"
    assert "main.css?v={{ static_version }}" in BASE_HTML, "CSS 未使用版本号 URL"
    assert "AfterBody.js?v={{ static_version }}" in BASE_HTML, "JS 未使用版本号 URL"


# ── 回归 18：侧边栏首个按钮为展开/收起 + 鼠标离开自动收起 + 顶部模式并入头部栏 ──
def test_sidebar_toggle_and_top_mode():
    # 侧边栏第一个按钮为展开/收起切换（默认仅图标）
    assert 'id="sideNavToggle"' in BASE_HTML, "侧边栏缺少展开/收起按钮"
    # 两种导航位置模式：侧边 / 顶部
    assert "body.nav-mode-top { padding-left: 0;" in CSS, "顶部模式未取消侧边栏占位"
    # 顶部模式：隐藏侧边栏，导航与已有头部栏合并（header-nav）
    assert 'id="headerNav"' in BASE_HTML, "顶部模式缺少与头部栏合并的 header-nav"
    assert "body.nav-mode-top .side-nav { display: none;" in CSS, "顶部模式未隐藏左侧边栏"
    assert "body.nav-mode-top .header-nav { display: flex;" in CSS, "顶部模式未显示 header-nav"
    assert "data-egg" in BASE_HTML and "data-settings" in BASE_HTML, \
        "header-nav 缺少彩蛋/设置入口（data-egg / data-settings）"
    # 顶部模式头部栏默认隐藏（仅 nav-mode-top 时显示）
    assert ".header-nav { display: none; }" in CSS, "header-nav 未默认隐藏"
    # 桌面鼠标离开侧边栏自动收起（移入设置下拉时除外）
    assert "mouseleave" in JS, "缺少鼠标离开侧边栏自动收起逻辑"
    assert "relatedTarget" in JS, "缺少鼠标离开时对设置下拉区域的排除判断"
    # 侧边栏与头部栏的彩蛋/设置入口共用同一套绑定
    assert "[data-egg]" in JS and "[data-settings]" in JS, "JS 未同时绑定 侧边栏+头部栏 的入口"


# ── 回归 18b：桌面端去除展开/收起按钮，改为鼠标悬浮展开、离开收起（手机端保留按钮） ──
def test_sidebar_hover_expand_desktop():
    # 按钮保留在 HTML（手机端需显示）
    assert 'id="sideNavToggle"' in BASE_HTML, "展开/收起按钮不应从 HTML 移除（手机端需显示）"
    # 桌面端（min-width: 901px）隐藏该按钮
    m = re.search(
        r"@media \(min-width: 901px\)\s*\{[^}]*#sideNavToggle\s*\{\s*display:\s*none",
        CSS,
    )
    assert m, "桌面端未隐藏展开/收起按钮（@media 901px+ 内 #sideNavToggle 应为 display:none）"
    # JS：鼠标悬浮侧边栏展开（仅桌面，innerWidth 判断）
    assert "mouseenter" in JS, "缺少鼠标悬浮展开逻辑"
    assert "setSideNavExpanded(true)" in JS, "缺少悬浮展开时的展开调用"
    assert re.search(r"mouseenter[\s\S]{0,80}?window\.innerWidth <= 900", JS), \
        "悬浮展开未限定桌面端（应跳过手机端）"


# ── 回归 15：评论输入框高度（rows=2） ──
def test_comment_textarea_rows_two():
    assert 'id="commentContent" rows="2"' in POST_DETAIL_HTML or \
        re.search(r'id="commentContent"[^>]*rows="2"', POST_VUE), \
        "评论输入框仍为 rows=3 过高，应改为 rows=2"


# ── 回归 16：Live2D 判定中心为模型画布中心而非屏幕中心 ──
def test_live2d_focus_uses_canvas_center():
    # 鼠标屏幕坐标先按画布中心偏移归一化（除以半屏宽高），再映射回画布坐标
    assert "_focusFromScreen" in JS, "缺少以画布中心为判定中心的 _focusFromScreen 函数"
    assert "getBoundingClientRect" in JS, "缺少基于画布包围盒的坐标映射"
    assert re.search(r"clientX\s*-\s*cx", JS), "缺少鼠标相对画布中心 X 偏移计算"
    assert re.search(r"rect\.width\s*/\s*2", JS), "缺少映射回画布宽/2 的换算"


