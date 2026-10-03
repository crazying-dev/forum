"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { userApi, ApiException } from "@/lib/api";
import { useStore } from "@/lib/store";
import { useToast } from "@/components/Toast";
import { useCenterCard } from "@/components/CenterCard";

type DeleteMode = "purge" | "anonymize";

/** CenterCard 二次确认（自带 busy/error 状态；确认调用 API，取消调 hide） */
function DeleteConfirmCard({
  mode,
  password,
  confirmName,
  onSuccess,
  onCancel,
}: {
  mode: DeleteMode;
  password: string;
  confirmName: string;
  onSuccess: () => void;
  onCancel: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const confirm = async () => {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await userApi.deleteAccount({ mode, password, confirmName });
      onSuccess();
    } catch (e) {
      setError(e instanceof ApiException ? e.message : "注销失败，请稍后再试");
      setBusy(false);
    }
  };

  return (
    <div className="account-delete-confirm">
      <h3><i className="fa fa-exclamation-triangle"></i> 确认注销账号？</h3>
      <p className="account-delete-confirm-mode">
        已选择：<strong>{mode === "purge" ? "彻底删除" : "匿名化保留"}</strong>
      </p>
      <p className="account-delete-confirm-warn">
        {mode === "purge"
          ? "此操作不可恢复：你的账号与全部个人数据将被永久删除。"
          : "注销后账号将无法登录：公开内容（含会馆文章）将以匿名形式保留。"}
      </p>
      {error && <p className="account-delete-confirm-error">{error}</p>}
      <div className="account-delete-confirm-actions">
        <button type="button" className="account-btn-cancel" onClick={onCancel} disabled={busy}>取消</button>
        <button type="button" className="account-btn-danger" onClick={confirm} disabled={busy}>
          {busy ? "注销中..." : "确认注销"}
        </button>
      </div>
    </div>
  );
}

/** 账号注销页：选择注销模式 → 密码 + 用户名确认 → 二次确认 → 注销 */
export default function AccountDeletePage() {
  const router = useRouter();
  const { user, loadingUser } = useStore();
  const { toast } = useToast();
  const { show, hide } = useCenterCard();
  const [mode, setMode] = useState<DeleteMode | null>(null);
  const [password, setPassword] = useState("");
  const [confirmName, setConfirmName] = useState("");

  // 未登录（且加载完毕）→ 跳登录页
  useEffect(() => {
    if (!loadingUser && !user) router.replace("/auth");
  }, [loadingUser, user, router]);

  if (loadingUser) return <div className="loading-text" style={{ padding: 40 }}>加载中...</div>;
  if (!user) return null;

  const nameMatched = confirmName === user.name;
  const canSubmit = !!mode && !!password && nameMatched;

  const openConfirm = () => {
    if (!mode || !canSubmit) return;
    show(
      <DeleteConfirmCard
        mode={mode}
        password={password}
        confirmName={confirmName}
        onCancel={hide}
        onSuccess={() => {
          hide();
          toast("账号已注销", "success");
          // 注销后本地会话已失效：整页跳回首页以清理 store 状态（稍候让 Toast 展示完）
          setTimeout(() => { window.location.href = "/"; }, 1200);
        }}
      />
    );
  };

  return (
    <div className="account-page">
      <div className="account-card">
        <div className="account-page-header">
          <h1><i className="fa fa-user-times"></i> 账号注销</h1>
          <p>注销前请仔细阅读以下说明，选择适合你的注销方式。</p>
        </div>

        <div className="account-warn-bar">
          <i className="fa fa-exclamation-triangle"></i> 注销后无法恢复，请谨慎操作。
        </div>

        <div className="account-mode-list">
          <button
            type="button"
            className={`account-mode-card ${mode === "purge" ? "selected" : ""}`}
            onClick={() => setMode("purge")}
          >
            <div className="account-mode-head">
              <span className="account-mode-radio" aria-hidden="true"></span>
              <h3>彻底删除</h3>
            </div>
            <p className="account-mode-desc">永久删除账号与全部个人数据，不保留任何内容。</p>
            <ul className="account-mode-notes">
              <li>他人对你评论的回复会一并删除</li>
              <li>你发布的帖子、评论、收藏等数据会被删除</li>
              <li>会馆文章会被删除</li>
            </ul>
          </button>

          <button
            type="button"
            className={`account-mode-card ${mode === "anonymize" ? "selected" : ""}`}
            onClick={() => setMode("anonymize")}
          >
            <div className="account-mode-head">
              <span className="account-mode-radio" aria-hidden="true"></span>
              <h3>匿名化保留</h3>
            </div>
            <p className="account-mode-desc">账号将无法登录，公开内容以匿名形式保留。</p>
            <ul className="account-mode-notes">
              <li>会馆文章保留，署名显示为「已注销账户」</li>
              <li>帖子与评论保留，但不再显示原用户名</li>
              <li>他人对你评论的回复保留（作者匿名）</li>
            </ul>
          </button>
        </div>

        {mode && (
          <div className="account-confirm-area">
            <h3>确认身份</h3>
            <div className="account-field">
              <label htmlFor="account-delete-password">登录密码</label>
              <input
                id="account-delete-password"
                type="password"
                placeholder="请输入当前密码"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            <div className="account-field">
              <label htmlFor="account-delete-name">输入「{user.name}」以确认</label>
              <input
                id="account-delete-name"
                type="text"
                placeholder={`输入「${user.name}」以确认`}
                autoComplete="off"
                value={confirmName}
                onChange={(e) => setConfirmName(e.target.value)}
              />
            </div>
            {confirmName && !nameMatched && (
              <p className="account-field-hint">用户名不一致，请与当前用户名完全一致</p>
            )}
            <button type="button" className="account-btn-danger account-submit-btn" disabled={!canSubmit} onClick={openConfirm}>
              确认注销
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
