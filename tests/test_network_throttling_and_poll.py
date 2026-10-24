"""需求对应的前端契约测试（纯静态 AST 模式匹配，不起浏览器）。
   1. 相同 URL 不要重复请求：apiFetch 有 in-flight Promise 合并（或内存去重）机制。
   2. 世界频道不显示时不请求：poll() 入口前必须检查面板"收起/隐藏"状态（collapsed / display none）。
   3. 页面不在最前端时世界频道不请求：监听 visibilitychange，document.hidden 时 clearTimeout。
"""
import os
import re
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
AFTERBODY = os.path.join(PROJECT_ROOT, "static", "js", "AfterBody.js")


def _read(p):
    with open(p, "r", encoding="utf-8") as f:
        return f.read()


def test_api_fetch_deduplicate_same_url():
    """apiFetch 应对相同 (method,url,body 序列化后的 key) 做 in-flight 合并：
       - 有一个 Map/_pending/_cache 对象存 in-flight Promise；
       - 请求发起前先查是否同 key 已在飞，直接返回已有 Promise；
       - 完成（不管成功失败）清理 key。"""
    js = _read(AFTERBODY)
    # 1. 存在请求缓存表 / 挂起表声明（命名随意：_pendingFetches / fetchDedup / inflightCache 等）
    has_inflight_store = bool(re.search(
        r"(var|let|const)\s+(_?\w*(?:inflight|dedup|pendingFetch|fetchCache|pendingReq|cache)\w*)"
        r"\s*=\s*(new\s+Map\(|new\s+WeakMap\(|new\s+Set\(|\{)",
        js, re.I,
    ))
    # 2. apiFetch 函数体里在 fetch() 调用前有"命中已有 Promise → return 旧 Promise"的分支
    has_dedup_check = bool(re.search(
        r"function\s+apiFetch[\s\S]{0,2500}?(if\s*\([^\)]*(?:inflight|dedup|pendingFetch|fetchCache|pendingReq|cache)"
        r"[^\)]*\)[\s\S]{0,200}?return\s+[\w$.]+\[?\s*['\"]?\s*key\s*['\"]?\s*\]?)"
        r"|apiFetch[\s\S]{0,1500}?\bif\s*\([^\)]*(?:has|get)\([^\)]*\)[\s\S]{0,180}?return",
        js, re.I,
    ))
    # 3. 构造/查询 key 使用 url + 可选 method/body（而非只有 method）
    has_key_with_url = bool(re.search(
        r"['\"]?key['\"]?\s*[:=]\s*[^\n;]{0,80}?url[^\n;]{0,80}?method"
        r"|\bkey\s*=\s*[^\n;]{0,80}?\+[^\n;]{0,50}?(?:url|method)"
        r"|JSON\.stringify\([^\)]*url[^\)]*method[^\)]*\)",
        js, re.I,
    ))
    # 至少两个指标通过即认为实现
    ok = sum([has_inflight_store, has_dedup_check, has_key_with_url]) >= 2
    assert ok, (
        "apiFetch 未实现同 URL 去重：需同时有 ①缓存表 ②命中后复用 Promise ③ key=method+url(+body)。\n"
        f"当前命中: inflight_store={has_inflight_store} dedup_check={has_dedup_check} key_with_url={has_key_with_url}"
    )


def test_world_poll_skips_when_panel_collapsed():
    """世界频道 poll() 在面板 hidden / collapsed / 不显示时不应请求 /api/world/ALL。
       判定方式：poll() 开头有对 panel show/collapse/visible 的 if-check，不满足 return。"""
    js = _read(AFTERBODY)
    # 定位 poll 函数（在 connectWorld 内部的 poll）
    poll_re = (
        r"function\s+poll\s*\(\s*\)\s*\{[\s\S]{0,500}?apiFetch\(\s*['\"]/api/world/ALL['\"]"
    )
    m = re.search(poll_re, js)
    assert m, "找不到 connectWorld 内部的 poll() / apiFetch(/api/world/ALL)"
    poll_body = m.group(0)
    # poll 开头必须有"面板不显示/收起 → return"的守卫
    guard_pat = [
        r"if\s*\([^\)]*(?:collapsed|hide|display\s*[!=]==?\s*['\"]none['\"]|hidden|!show|style\.display\s*[!=]="
        r"|el\(['\"]worldPanel['\"]\)[^\n]{0,60}?(display|hidden|classList|contains\(['\"]collapsed['\"]\)))[^\)]*\)"
        r"[\s\S]{0,80}?return",
        r"if\s*\([^\)]*worldPanel[\s\S]{0,40}?(display|hidden|classList\.contains)[^\)]*\)[\s\S]{0,80}?return",
        r"if\s*\([^\)]*(?:isCollapsed|isVisible|panelHidden|panelShow)[^\)]*\)[\s\S]{0,80}?return",
    ]
    guarded = any(re.search(p, poll_body, re.I) for p in guard_pat)
    assert guarded, (
        "poll() 请求 /api/world/ALL 前未检查世界面板是否收起/隐藏，需要在函数开头 return 跳过不发请求"
    )


def test_world_poll_pauses_on_page_hidden():
    """页面切后台（document.hidden / visibilitychange）时世界频道必须暂停轮询：
       - 有 document.addEventListener('visibilitychange', ...)
       - 回调里当 hidden 时 clearTimeout(worldPollTimer) 并设置 worldPollTimer=null/不 setTimeout。
       - 恢复（非 hidden）时应触发一次 poll。"""
    js = _read(AFTERBODY)
    has_visibility_listener = bool(re.search(
        r"addEventListener\(\s*['\"]visibilitychange['\"]\s*,", js, re.I,
    ))
    hidden_branch_clear = bool(re.search(
        r"(document\.hidden|visibilityState\s*[!=]==?\s*['\"]hidden['\"])[\s\S]{0,300}?"
        r"clearTimeout\([^)]*worldPollTimer[^)]*\)"
        r"|clearTimeout\([^)]*worldPollTimer[^)]*\)[\s\S]{0,300}?(document\.hidden|visibilityState.*hidden)",
        js, re.I,
    ))
    resume_on_visible = bool(re.search(
        r"![^\n;]*document\.hidden|visibilityState\s*[!=]==?\s*['\"]visible['\"]"
        r"[\s\S]{0,220}?(poll\(\)|setTimeout\([^,]+poll|connectWorld)",
        js, re.I,
    ))
    ok = has_visibility_listener and hidden_branch_clear and resume_on_visible
    assert ok, (
        "世界频道未按页面可见性暂停：需同时满足 "
        f"① visibilitychange 监听={has_visibility_listener} ② hidden→clearTimeout(worldPollTimer)={hidden_branch_clear} "
        f"③ visible→立即 poll/connectWorld={resume_on_visible}"
    )


if __name__ == "__main__":
    tests = [
        ("test_api_fetch_deduplicate_same_url", test_api_fetch_deduplicate_same_url),
        ("test_world_poll_skips_when_panel_collapsed", test_world_poll_skips_when_panel_collapsed),
        ("test_world_poll_pauses_on_page_hidden", test_world_poll_pauses_on_page_hidden),
    ]
    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL  {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR {name}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
