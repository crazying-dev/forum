"use client";

import { useEffect, useState } from "react";
import Modal from "./ui/Modal";
import { AuthInput } from "./ui/AuthInput";
import { useToast } from "./Toast";
import { userApi, ApiException } from "@/lib/api";
import { useStore } from "@/lib/store";

/** 邮箱掩码：保留前 1-2 位本地部分，其余用 * 代替（a**@example.com） */
function maskEmail(email: string) {
  const at = email.indexOf("@");
  if (at <= 0) return email || "—";
  const local = email.slice(0, at);
  const keep = local.slice(0, Math.min(2, local.length));
  return `${keep}${"*".repeat(Math.max(local.length - keep.length, 2))}${email.slice(at)}`;
}

/** 进度持久化：Tab1 验证通过后在会话内保留 30 分钟（与服务端 stage=2 窗口一致），避免误关弹窗后因 1 小时限流无法继续 */
const OLD_DONE_KEY = "forum-email-change-old-done";

function readOldDoneFlag(): boolean {
  try {
    const raw = sessionStorage.getItem(OLD_DONE_KEY);
    if (!raw) return false;
    return Number(raw) > Date.now();
  } catch {
    return false;
  }
}

function writeOldDoneFlag() {
  try {
    sessionStorage.setItem(OLD_DONE_KEY, String(Date.now() + 30 * 60 * 1000));
  } catch {
    /* 忽略：无 sessionStorage 时仅当前弹窗生命周期内有效 */
  }
}

function clearOldDoneFlag() {
  try {
    sessionStorage.removeItem(OLD_DONE_KEY);
  } catch {
    /* 忽略 */
  }
}

/**
 * 更换邮箱弹窗：① 验证当前邮箱（验证码）→ ② 绑定新邮箱（新邮箱验证码）。
 * Tab2 在完成 Tab1 前不可用（点击提示）。成功后 Toast + refreshUser + 关闭。
 */
export default function EmailChangeModal({ onClose }: { onClose: () => void }) {
  const { user, refreshUser } = useStore();
  const { toast } = useToast();
  const [tab, setTab] = useState<"old" | "new">(() => (readOldDoneFlag() ? "new" : "old"));
  const [oldDone, setOldDone] = useState(() => readOldDoneFlag());
  const [currentEmail, setCurrentEmail] = useState(user?.email || "");
  const [oldCode, setOldCode] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [newCode, setNewCode] = useState("");
  const [oldCountdown, setOldCountdown] = useState(0);
  const [newCountdown, setNewCountdown] = useState(0);
  const [busy, setBusy] = useState(false);

  // store 无邮箱时补拉一次 /users/me（该接口本人视角包含 email）
  useEffect(() => {
    if (currentEmail) return;
    let cancelled = false;
    userApi
      .me()
      .then((r) => {
        if (!cancelled) setCurrentEmail(r.user?.email || "");
      })
      .catch(() => { /* 忽略：界面显示占位符 */ });
    return () => {
      cancelled = true;
    };
  }, [currentEmail]);

  useEffect(() => {
    if (oldCountdown <= 0) return;
    const t = setInterval(() => setOldCountdown((c) => c - 1), 1000);
    return () => clearInterval(t);
  }, [oldCountdown]);

  useEffect(() => {
    if (newCountdown <= 0) return;
    const t = setInterval(() => setNewCountdown((c) => c - 1), 1000);
    return () => clearInterval(t);
  }, [newCountdown]);

  const switchTab = (next: "old" | "new") => {
    if (next === "new" && !oldDone) {
      toast("请先完成当前邮箱验证", "warning");
      return;
    }
    setTab(next);
  };

  const sendOldCode = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await userApi.sendEmailChangeOldCode();
      toast("验证码已发送至当前邮箱", "success");
      setOldCountdown(60);
    } catch (e) {
      toast(e instanceof ApiException ? e.message : "发送失败", "error");
    } finally {
      setBusy(false);
    }
  };

  const verifyOld = async () => {
    if (busy) return;
    if (oldCode.length !== 6) {
      toast("请输入 6 位验证码", "warning");
      return;
    }
    setBusy(true);
    try {
      await userApi.verifyEmailChangeOld(oldCode);
      writeOldDoneFlag();
      setOldDone(true);
      setTab("new");
      toast("当前邮箱验证成功", "success");
    } catch (e) {
      toast(e instanceof ApiException ? e.message : "验证失败", "error");
    } finally {
      setBusy(false);
    }
  };

  const sendNewCode = async () => {
    if (busy) return;
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(newEmail.trim())) {
      toast("请输入有效的新邮箱", "warning");
      return;
    }
    setBusy(true);
    try {
      await userApi.sendEmailChangeNewCode(newEmail.trim());
      toast("验证码已发送至新邮箱", "success");
      setNewCountdown(60);
    } catch (e) {
      toast(e instanceof ApiException ? e.message : "发送失败", "error");
    } finally {
      setBusy(false);
    }
  };

  const confirm = async () => {
    if (busy) return;
    if (newCode.length !== 6) {
      toast("请输入 6 位验证码", "warning");
      return;
    }
    setBusy(true);
    try {
      await userApi.confirmEmailChange(newCode);
      clearOldDoneFlag();
      toast("邮箱换绑成功", "success");
      await refreshUser();
      onClose();
    } catch (e) {
      toast(e instanceof ApiException ? e.message : "换绑失败", "error");
      setBusy(false);
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      className="email-change-modal"
      overlayClassName="email-change-overlay"
      cardClassName="email-change-card"
      closeClassName="email-change-close"
    >
      <h3 className="email-change-title">更换邮箱</h3>

      <div className="email-change-tabs">
        <button
          type="button"
          className={`email-change-tab ${tab === "old" ? "active" : ""}`}
          onClick={() => switchTab("old")}
        >
          <span className={`email-change-step ${oldDone ? "done" : ""}`}>
            {oldDone ? <i className="fa fa-check"></i> : "1"}
          </span>
          验证当前邮箱
        </button>
        <button
          type="button"
          className={`email-change-tab ${tab === "new" ? "active" : ""} ${oldDone ? "" : "locked"}`}
          aria-disabled={!oldDone}
          onClick={() => switchTab("new")}
        >
          <span className="email-change-step">2</span>
          绑定新邮箱
        </button>
      </div>

      {tab === "old" && (
        <div className="email-change-body">
          <p className="email-change-tip">
            当前邮箱：<strong>{maskEmail(currentEmail)}</strong>
          </p>
          <p className="email-change-desc">请向当前邮箱发送验证码，以确认你是账号本人。</p>
          <div className="auth-input-group auth-code-group">
            <span className="auth-icon"><i className="fa fa-shield"></i></span>
            <input
              type="text"
              placeholder="验证码（6位数字）"
              maxLength={6}
              inputMode="numeric"
              pattern="[0-9]*"
              value={oldCode}
              onChange={(e) => setOldCode(e.target.value)}
            />
            <button type="button" className="auth-btn code-btn" disabled={busy || oldCountdown > 0} onClick={sendOldCode}>
              {oldCountdown > 0 ? `${oldCountdown}s` : "发送验证码"}
            </button>
          </div>
          <button type="button" className="auth-btn primary" disabled={busy} onClick={verifyOld}>
            {busy ? "验证中..." : "验证并进入下一步"}
          </button>
        </div>
      )}

      {tab === "new" && (
        <div className="email-change-body">
          <p className="email-change-desc">请输入新的邮箱地址，并完成新邮箱验证码验证。</p>
          <AuthInput
            icon="envelope"
            type="email"
            placeholder="新邮箱"
            value={newEmail}
            onChange={setNewEmail}
          />
          <div className="auth-input-group auth-code-group">
            <span className="auth-icon"><i className="fa fa-shield"></i></span>
            <input
              type="text"
              placeholder="验证码（6位数字）"
              maxLength={6}
              inputMode="numeric"
              pattern="[0-9]*"
              value={newCode}
              onChange={(e) => setNewCode(e.target.value)}
            />
            <button type="button" className="auth-btn code-btn" disabled={busy || newCountdown > 0} onClick={sendNewCode}>
              {newCountdown > 0 ? `${newCountdown}s` : "发送验证码"}
            </button>
          </div>
          <button type="button" className="auth-btn primary" disabled={busy} onClick={confirm}>
            {busy ? "绑定中..." : "完成换绑"}
          </button>
        </div>
      )}
    </Modal>
  );
}
