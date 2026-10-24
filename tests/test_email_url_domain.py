"""验证所有邮件 URL 全部指向固定域名 yjlt.top，不动态解析当前 host。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config


def test_site_base_url_is_fixed():
    """配置里必须有固定站点域名，不能依赖 request.host_url。"""
    expected = "https://yjlt.top"
    actual = getattr(config, "SITE_BASE_URL", None)
    assert actual == expected, (
        f"config.SITE_BASE_URL 应为 {expected!r}，实际 {actual!r}"
    )
    print("PASS: SITE_BASE_URL ==", actual)


def test_email_api_no_dynamic_host_url():
    """api/email/__init__.py 邮件模块不能再用 request.host_url。"""
    p = ROOT / "api" / "email" / "__init__.py"
    src = p.read_text(encoding="utf-8")
    assert "request.host_url" not in src, (
        f"{p} 中仍包含 request.host_url 动态解析，应改用 config.SITE_BASE_URL"
    )
    assert "config.SITE_BASE_URL" in src or "SITE_BASE_URL" in src, (
        f"{p} 中未使用 SITE_BASE_URL 固定域名"
    )
    print(f"PASS: {p} 使用固定域名")


def test_post_notify_no_dynamic_host_url():
    """新帖通知（api/post/__init__.py）不能再传 request.host_url 进去，
    内部必须直接用 config.SITE_BASE_URL。
    """
    p = ROOT / "api" / "post" / "__init__.py"
    src = p.read_text(encoding="utf-8")
    # 函数定义里不应再接受 host_url 参数
    assert "def _notify_fans_new_post_async(author_id, author_name, post_id, title, category, host_url)" not in src, (
        f"{p} _notify_fans_new_post_async 还保留 host_url 动态参数，应改用 config.SITE_BASE_URL"
    )
    # 调用处不应再传 request.host_url 给通知函数
    assert "request.host_url" not in src, (
        f"{p} 中仍包含 request.host_url 动态解析，应改用 config.SITE_BASE_URL"
    )
    print(f"PASS: {p} 使用固定域名")


if __name__ == "__main__":
    test_site_base_url_is_fixed()
    test_email_api_no_dynamic_host_url()
    test_post_notify_no_dynamic_host_url()
    print("ALL_PASSED")
