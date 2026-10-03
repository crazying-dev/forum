"use client";

import { useState, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { AuthInput } from "@/components/ui/AuthInput";
import { useToast, ToastType } from "@/components/Toast";
import { authApi, ApiException } from "@/lib/api";
import { useStore } from "@/lib/store";

type Mode = "login" | "register" | "forgot";

function LoginInner() {
  const router = useRouter();
  const params = useSearchParams();
  const { refreshUser } = useStore();
  const { toast } = useToast();
  const [mode, setMode] = useState<Mode>("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [password2, setPassword2] = useState("");
  const [code, setCode] = useState("");
  const [remember, setRemember] = useState(true);
  const [busy, setBusy] = useState(false);
  const [countdown, setCountdown] = useState(0);
  const [pwdMatch, setPwdMatch] = useState<"" | "ok" | "no">("");

  // URL ?mode=reset&token= 兼容：带 token 的旧链接跳转到重置链接页；仅 mode=reset 时落到忘记密码
  const modeParam = params.get("mode");
  const tokenParam = params.get("token");
  useEffect(() => {
    if (modeParam === "reset") {
      if (tokenParam) {
        router.replace(`/reset-password?token=${encodeURIComponent(tokenParam)}`);
      } else {
        setMode("forgot");
      }
    }
  }, [modeParam, tokenParam, router]);

  useEffect(() => {
    if (countdown <= 0) return;
    const t = setInterval(() => setCountdown((c) => c - 1), 1000);
    return () => clearInterval(t);
  }, [countdown]);

  const showMsg = (m: string, type: ToastType = "error") => toast(m, type);

  const login = async () => {
    if (!name || !password) return showMsg("请输入账号和密码", "warning");
    setBusy(true);
    try {
      const r = await authApi.login(name, password, remember);
      await refreshUser();
      router.push(`/users/${r.id}`);
    } catch (e) {
      showMsg(e instanceof ApiException ? e.message : "登录失败");
    } finally {
      setBusy(false);
    }
  };

  const sendRegisterCode = async () => {
    if (!email) return showMsg("请输入邮箱", "warning");
    setBusy(true);
    try {
      await authApi.sendRegisterCode(email);
      showMsg("验证码已发送，请查收邮箱", "success");
      setCountdown(60);
    } catch (e) {
      showMsg(e instanceof ApiException ? e.message : "发送失败");
    } finally {
      setBusy(false);
    }
  };

  const register = async () => {
    if (!name || !email || !password || !code) return showMsg("请填写完整信息", "warning");
    if (password.length < 8) return showMsg("密码至少8位", "warning");
    if (password !== password2) return showMsg("两次密码不一致", "warning");
    setBusy(true);
    try {
      await authApi.register(name, email, password, code);
      await refreshUser();
      router.push("/");
    } catch (e) {
      showMsg(e instanceof ApiException ? e.message : "注册失败");
    } finally {
      setBusy(false);
    }
  };

  const sendResetLink = async () => {
    if (!email) return showMsg("请输入邮箱", "warning");
    setBusy(true);
    try {
      await authApi.sendResetLink(email);
      showMsg("重置链接已发送至邮箱（若邮箱存在），10 分钟内有效、最多可打开 3 次，请前往邮箱查收", "success");
    } catch (e) {
      showMsg(e instanceof ApiException ? e.message : "发送失败");
    } finally {
      setBusy(false);
    }
  };

  const switchMode = (m: Mode) => {
    setMode(m);
    setPwdMatch("");
  };

  return (
    <div className="auth-container">
      <div className="auth-card">
        <div className="auth-tabs">
          <button className={`auth-tab ${mode === "login" ? "active" : ""}`} data-tab="login" onClick={() => switchMode("login")}>登录</button>
          <button className={`auth-tab ${mode === "register" ? "active" : ""}`} data-tab="register" onClick={() => switchMode("register")}>注册</button>
        </div>

        {mode === "login" && (
          <div className="auth-form" id="loginForm">
            <div className="auth-header">
              <h2>欢迎回来</h2>
              <p>登录您的妖精论坛账号</p>
            </div>
            <AuthInput icon="user" placeholder="用户名或邮箱" value={name} onChange={setName} />
            <AuthInput icon="lock" type="password" placeholder="密码" value={password} onChange={setPassword} onKeyDown={(e) => e.key === "Enter" && login()} />
            <div className="auth-options">
              <label className="remember-me">
                <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
                <span>记住我</span>
              </label>
              <a href="#" className="forgot-password" onClick={(e) => { e.preventDefault(); switchMode("forgot"); }}>忘记密码？</a>
            </div>
            <button className="auth-btn primary" disabled={busy} onClick={login}>{busy ? "登录中..." : "登录"}</button>
          </div>
        )}

        {mode === "register" && (
          <div className="auth-form" id="registerForm">
            <div className="auth-header">
              <h2>加入我们</h2>
              <p>创建您的妖精论坛账号</p>
            </div>
            <AuthInput icon="user" placeholder="用户名（2-20个字符）" value={name} onChange={setName} />
            <AuthInput icon="envelope" type="email" placeholder="邮箱" value={email} onChange={setEmail} />
            <AuthInput
              icon="lock"
              type="password"
              placeholder="密码（至少8位，含字母和数字）"
              value={password}
              onChange={(v) => { setPassword(v); setPwdMatch(password2 && v === password2 ? "ok" : password2 ? "no" : ""); }}
            />
            <AuthInput
              icon="lock"
              type="password"
              placeholder="确认密码"
              value={password2}
              onChange={(v) => { setPassword2(v); setPwdMatch(password && v === password ? "ok" : v ? "no" : ""); }}
            />
            <div className="auth-input-group auth-code-group">
              <span className="auth-icon"><i className="fa fa-shield"></i></span>
              <input type="text" placeholder="验证码（6位数字）" maxLength={6} inputMode="numeric" pattern="[0-9]*" value={code} onChange={(e) => setCode(e.target.value)} />
              <button className="auth-btn code-btn" disabled={busy || countdown > 0} onClick={sendRegisterCode}>
                {countdown > 0 ? `${countdown}s` : "获取验证码"}
              </button>
            </div>
            <button className="auth-btn primary" disabled={busy} onClick={register}>{busy ? "注册中..." : "注册"}</button>
            <div className="auth-error">{pwdMatch === "no" ? "❌ 两次密码不一致" : pwdMatch === "ok" ? "✅ 密码一致" : ""}</div>
          </div>
        )}

        {mode === "forgot" && (
          <div className="auth-form" id="forgotPasswordForm">
            <div className="auth-header">
              <h2>重置密码</h2>
              <p>输入注册邮箱，我们将发送重置链接</p>
            </div>
            <AuthInput icon="envelope" type="email" placeholder="注册邮箱" value={email} onChange={setEmail} onKeyDown={(e) => e.key === "Enter" && sendResetLink()} />
            <button className="auth-btn primary" disabled={busy} onClick={sendResetLink}>{busy ? "发送中..." : "发送重置链接"}</button>
            <button className="auth-btn secondary" style={{ marginTop: 12, background: "var(--color-bg-icon)", color: "var(--color-text-secondary)" }} onClick={() => switchMode("login")}>返回登录</button>
          </div>
        )}

        <div className="auth-footer">
          <p>登录即表示您同意<Link href="/privacy">隐私政策</Link>和服务条款</p>
        </div>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <>
      <Suspense fallback={<div style={{ textAlign: "center", padding: 40 }}>加载中...</div>}>
        <LoginInner />
      </Suspense>
    </>
  );
}
