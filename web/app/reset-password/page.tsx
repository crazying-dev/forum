"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { AuthInput } from "@/components/ui/AuthInput";
import { authApi, ApiException } from "@/lib/api";

type Status = "validating" | "valid" | "submitting" | "success" | "invalid";

/** 从地址栏取 token（不用 useSearchParams，避免客户端页强制 Suspense 包裹） */
function readToken() {
  if (typeof window === "undefined") return "";
  return new URLSearchParams(window.location.search).get("token") || "";
}

/** 重置密码链接页：校验 token → 设置新密码 → 成功自动回登录页 */
export default function ResetPasswordPage() {
  const router = useRouter();
  const [token, setToken] = useState("");
  const [status, setStatus] = useState<Status>("validating");
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [password, setPassword] = useState("");
  const [password2, setPassword2] = useState("");
  const [err, setErr] = useState("");

  // 挂载时校验 token（每次挂载只校验一次；异步函数内更新状态，避免 effect 同步级联渲染）
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const t = readToken();
      if (!t) {
        if (cancelled) return;
        setMessage("链接无效或缺少重置凭证，请重新申请");
        setStatus("invalid");
        return;
      }
      setToken(t);
      try {
        const r = await authApi.validateResetToken(t);
        if (cancelled) return;
        setEmail(r.data?.email || "");
        setStatus("valid");
      } catch (e) {
        if (cancelled) return;
        setMessage(e instanceof ApiException ? e.message : "链接无效或已过期");
        setStatus("invalid");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // 成功态：约 3 秒后自动跳转登录页
  useEffect(() => {
    if (status !== "success") return;
    const timer = setTimeout(() => router.replace("/auth"), 3000);
    return () => clearTimeout(timer);
  }, [status, router]);

  const submit = async () => {
    if (status === "submitting") return;
    if (!/^(?=.*[A-Za-z])(?=.*\d).{8,}$/.test(password)) {
      setErr("密码至少 8 位，且需同时包含字母和数字");
      return;
    }
    if (password !== password2) {
      setErr("两次输入的密码不一致");
      return;
    }
    setErr("");
    setStatus("submitting");
    try {
      await authApi.confirmResetPassword(token, password);
      setStatus("success");
    } catch (e) {
      setErr(e instanceof ApiException ? e.message : "重置失败，请稍后再试");
      setStatus("valid");
    }
  };

  return (
    <div className="auth-container">
      <div className="auth-card reset-password-card">
        {status === "validating" && (
          <div className="auth-form reset-status">
            <div className="reset-icon"><i className="fa fa-spinner fa-spin"></i></div>
            <h2>正在校验重置链接...</h2>
            <p className="reset-desc">请稍候</p>
          </div>
        )}

        {status === "invalid" && (
          <div className="auth-form reset-status">
            <div className="reset-icon invalid"><i className="fa fa-times-circle"></i></div>
            <h2>链接无效或已过期</h2>
            <p className="reset-desc">{message || "重置链接无效、已过期或打开次数已达上限"}</p>
            <Link href="/auth" className="auth-btn primary reset-link-btn">重新申请</Link>
          </div>
        )}

        {status === "success" && (
          <div className="auth-form reset-status">
            <div className="reset-icon success"><i className="fa fa-check-circle"></i></div>
            <h2>密码重置成功，请使用新密码登录</h2>
            <p className="reset-desc">约 3 秒后自动跳转登录页</p>
            <button className="auth-btn primary" onClick={() => router.replace("/auth")}>前往登录</button>
          </div>
        )}

        {(status === "valid" || status === "submitting") && (
          <div className="auth-form">
            <div className="auth-header">
              <h2>设置新密码</h2>
              <p>{email ? `重置链接对应邮箱：${email}` : "请设置新的登录密码"}</p>
            </div>
            <AuthInput
              icon="lock"
              type="password"
              placeholder="新密码（至少8位，含字母和数字）"
              value={password}
              onChange={(v) => { setPassword(v); if (err) setErr(""); }}
            />
            <AuthInput
              icon="lock"
              type="password"
              placeholder="确认新密码"
              value={password2}
              onChange={(v) => { setPassword2(v); if (err) setErr(""); }}
              onKeyDown={(e) => e.key === "Enter" && submit()}
            />
            <div className="auth-error">{err}</div>
            <button className="auth-btn primary" disabled={status === "submitting"} onClick={submit}>
              {status === "submitting" ? "提交中..." : "确认重置"}
            </button>
            <button
              className="auth-btn secondary"
              style={{ marginTop: 12, background: "var(--color-bg-icon)", color: "var(--color-text-secondary)" }}
              onClick={() => router.replace("/auth")}
            >
              返回登录
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
