"use client";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useStore } from "@/lib/store";

function VerifyInner() {
  const params = useSearchParams();
  const { userId } = useStore();
  const token = params.get("token") || "";
  const [status, setStatus] = useState<"loading" | "ok" | "fail">("loading");
  const [msg, setMsg] = useState("");

  useEffect(() => {
    if (!token) { setStatus("fail"); setMsg("缺少验证 token"); return; }
    fetch(`${process.env.NEXT_PUBLIC_API_BASE || ""}/ov2/api/auth/verify-token?token=${encodeURIComponent(token)}&type=email_verify`, { credentials: "include" })
      .then((r) => r.json())
      .then((d) => {
        if (d.success) { setStatus("ok"); setMsg("邮箱验证成功！"); }
        else { setStatus("fail"); setMsg("验证失败或链接已过期"); }
      })
      .catch(() => { setStatus("fail"); setMsg("验证失败或链接已过期"); });
  }, [token]);

  return (
    <>
      <div className="verify-container">
        {status === "loading" && <div className="post-loading">验证中...</div>}
        {status === "ok" && (
          <div className="verify-card success">
            <div className="verify-icon">
              <i className="fa fa-check-circle"></i>
            </div>
            <h2>验证成功</h2>
            <p>{msg} 您的邮箱已成功验证，感谢您的使用！</p>
            <Link className="verify-btn" href={userId ? `/users/${userId}` : "/auth"}>
              {userId ? "返回个人主页" : "返回登录"}
            </Link>
          </div>
        )}
        {status === "fail" && (
          <div className="verify-card failed">
            <div className="verify-icon">
              <i className="fa fa-times-circle"></i>
            </div>
            <h2>验证失败</h2>
            <p>{msg} 验证链接已过期或无效，请重新操作。</p>
            <Link className="verify-btn" href="/auth">返回登录</Link>
          </div>
        )}
      </div>
    </>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={<div style={{ textAlign: "center", padding: 40 }}>加载中...</div>}>
      <VerifyInner />
    </Suspense>
  );
}
