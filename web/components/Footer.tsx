"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

/** 页脚（多列布局：品牌/免责声明 · 公众号） */
export default function Footer() {
  // 公众号二维码：桌面悬停展示；移动端点击开关（点击外部/ESC 关闭）
  const [qrOpen, setQrOpen] = useState(false);
  const qrRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!qrOpen) return;
    const onPointerDown = (e: PointerEvent) => {
      if (!qrRef.current?.contains(e.target as Node)) setQrOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setQrOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [qrOpen]);

  return (
    <footer id="footer">
      <div className="footer-container">
        <div className="footer-col footer-brand">
          <h4 className="footer-title">
            <img src="/assets/img/favicon.png" alt="" className="footer-logo" />
            妖精论坛
          </h4>
          <p className="footer-desc">罗小黑战记同人社区</p>
          <p className="footer-disclaimer">
            <i className="fa fa-info-circle"></i> 本二创无官方授权，仅粉丝公益创作
          </p>
          <Link href="/privacy" id="FooterPrivacy"><i className="fa fa-shield"></i> 隐私政策</Link>
        </div>
        <div className="footer-col">
          <h4 className="footer-title"><i className="fa fa-weixin"></i> 公众号</h4>
          <span
            className={`qr-hover-wrap${qrOpen ? " open" : ""}`}
            ref={qrRef}
            role="button"
            tabIndex={0}
            aria-expanded={qrOpen}
            onClick={() => setQrOpen((v) => !v)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                setQrOpen((v) => !v);
              }
            }}
          >
            <span id="Footer公众号">悬停扫码</span>
            <img className="qr-img" src="/assets/img/OfficialAccount.jpg" alt="公众号二维码" />
          </span>
        </div>
      </div>
    </footer>
  );
}
