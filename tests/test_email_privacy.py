"""验证邮件隐私：多收件人逐个单独发送，每封 To 头仅含自己邮箱。"""
from __future__ import annotations

import sys
import smtplib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unittest.mock import MagicMock, patch, PropertyMock

import Email


def test_multi_recipient_each_email_has_only_its_own_to():
    """多收件人 -> 逐个 sendmail，每封邮件的 To 头只含对应邮箱。"""
    receivers = ["a@example.com", "b@example.com", "c@example.com"]
    captured_sends: list[tuple[str, str]] = []  # [(rcpt, msg_string)]

    fake_smtp = MagicMock(spec=smtplib.SMTP_SSL)
    def fake_sendmail(_from, to_addrs, msg_str):
        assert isinstance(to_addrs, list) and len(to_addrs) == 1, \
            f"预期单个收件人，实际: {to_addrs}"
        rcpt = to_addrs[0]
        captured_sends.append((rcpt, msg_str))
        return {}
    fake_smtp.sendmail.side_effect = fake_sendmail

    # 只替换 SMTP_SSL 类，保留 smtplib 自身（异常类不被 MagicMock 覆盖）
    with patch.object(Email.config, "SMTP_PASSWORD", "fake-pw"), \
         patch.object(Email.config, "SMTP_HOST", "smtp.example.com"), \
         patch.object(Email.config, "SMTP_PORT", 465), \
         patch.object(Email.config, "SMTP_USER", "bot@example.com"), \
         patch("smtplib.SMTP_SSL", return_value=fake_smtp):
        ok, err = Email.send_email("测试主题", "测试内容", receiver_list=receivers)

    assert ok, f"发送失败: {err}"
    assert len(captured_sends) == 3, f"应发送3封，实际{len(captured_sends)}封"
    for rcpt, msg_str in captured_sends:
        for other in receivers:
            if other == rcpt:
                continue
            # 同封邮件头里绝对不能出现其他收件人
            header_part = msg_str.split("Subject:", 1)[0] if "Subject:" in msg_str else msg_str
            assert f"To: {other}" not in header_part and f"<{other}>" not in header_part, \
                f"给 {rcpt} 的邮件头里不应出现 {other}（隐私泄露）"


def test_single_recipient_still_works():
    """单个收件人不影响。"""
    captured_sends = []

    fake_smtp = MagicMock(spec=smtplib.SMTP_SSL)
    def fake_sendmail(_from, to_addrs, msg_str):
        captured_sends.append((to_addrs, msg_str))
        return {}
    fake_smtp.sendmail.side_effect = fake_sendmail

    with patch.object(Email.config, "SMTP_PASSWORD", "fake-pw"), \
         patch.object(Email.config, "SMTP_HOST", "smtp.example.com"), \
         patch.object(Email.config, "SMTP_PORT", 465), \
         patch.object(Email.config, "SMTP_USER", "bot@example.com"), \
         patch("smtplib.SMTP_SSL", return_value=fake_smtp):
        ok, err = Email.send_email("t", "c", receiver_list=["only@example.com"])

    assert ok, f"err={err}"
    assert len(captured_sends) == 1
    to, msg = captured_sends[0]
    assert to == ["only@example.com"]
    assert "To: only@example.com" in msg


if __name__ == "__main__":
    test_single_recipient_still_works()
    print("SINGLE_PASS")
    test_multi_recipient_each_email_has_only_its_own_to()
    print("MULTI_PASS")
    print("ALL_PASSED")
