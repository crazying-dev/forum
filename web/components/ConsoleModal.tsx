"use client";

import { useRouter } from "next/navigation";
import { useStore } from "@/lib/store";
import Modal from "./ui/Modal";

// 消息中心四类未读数（GET /messages/summary）
export interface MessageUnread {
  likes: number;
  comments: number;
  system: number;
  chat: number;
}

/** 控制台弹窗：收纳桌面端次级功能入口与主题偏好（替代原「更多 / 主题」下拉） */
export default function ConsoleModal({
  open,
  onClose,
  onDonate,
  onEasterEgg,
  onOpenWorld,
  unread,
}: {
  open: boolean;
  onClose: () => void;
  onDonate: () => void;
  onEasterEgg: () => void;
  onOpenWorld: () => void;
  unread?: MessageUnread;
}) {
  const router = useRouter();
  const { theme, setTheme } = useStore();

  const unreadTotal = unread ? unread.likes + unread.comments + unread.system + unread.chat : 0;
  const unreadBadge = unreadTotal > 99 ? "99+" : String(unreadTotal);

  // 导航类入口：先关闭弹窗再跳转（沿用原下拉逻辑）
  const go = (href: string) => {
    onClose();
    router.push(href);
  };

  return (
    <Modal open={open} onClose={onClose} lockScroll cardClassName="donate-card console-card">
      <h3 className="console-title">
        <i className="fa fa-sliders"></i> 控制台
      </h3>
      <p className="console-subtitle">更多功能与偏好设置</p>
      <div className="console-grid">
        <button className="console-tile" type="button" onClick={() => go("/WIKI")}>
          <img src="/assets/img/wiki_avatar_l.png" alt="" />
          <span>WIKI</span>
        </button>
        <button className="console-tile" type="button" onClick={() => { onClose(); onDonate(); }}>
          <i className="fa fa-heart"></i>
          <span>赞赏</span>
        </button>
        <button className="console-tile" type="button" onClick={() => go("/feedback/submit")}>
          <i className="fa fa-bug"></i>
          <span>提交反馈</span>
        </button>
        <button className="console-tile" type="button" onClick={() => go("/feedback")}>
          <i className="fa fa-comments-o"></i>
          <span>反馈中心</span>
        </button>
        <button className="console-tile" type="button" onClick={() => go("/guide")}>
          <i className="fa fa-map-o"></i>
          <span>论坛指南</span>
        </button>
        <button className="console-tile" type="button" onClick={() => go("/download")}>
          <i className="fa fa-download"></i>
          <span>客户端下载</span>
        </button>
        <button className="console-tile" type="button" onClick={() => go("/messages")}>
          <i className="fa fa-envelope-o"></i>
          <span>消息中心</span>
          {unreadTotal > 0 && <span className="console-tile-badge">{unreadBadge}</span>}
        </button>
        <button className="console-tile" type="button" onClick={() => go("/changelog")}>
          <i className="fa fa-history"></i>
          <span>更新日志</span>
        </button>
        <button className="console-tile" type="button" onClick={() => go("/tools/year-converter")}>
          <i className="fa fa-hourglass-half"></i>
          <span>无限年换算</span>
        </button>
        {/* 世界频道：关闭控制台后打开世界频道窗口 */}
        <button className="console-tile" type="button" onClick={() => { onClose(); onOpenWorld(); }}>
          <i className="fa fa-globe"></i>
          <span>世界频道</span>
        </button>
        {/* 安装网页应用：跳转下载页，由下载页的 PWA 按钮完成安装 */}
        <button className="console-tile" type="button" onClick={() => go("/download")}>
          <i className="fa fa-mobile"></i>
          <span>安装网页应用</span>
        </button>
        {/* 彩蛋：不关闭控制台，提示浮层叠加显示（可连续点击查看） */}
        <button className="console-tile" type="button" onClick={onEasterEgg}>
          <i className="fa fa-gift"></i>
          <span>彩蛋</span>
        </button>
        <div className="console-theme">
          <div className="console-theme-head">
            <i className="fa fa-paint-brush"></i> 主题
          </div>
          <div className="console-theme-pills">
            <button
              className={`console-pill ${theme === "day" ? "active" : ""}`}
              type="button"
              onClick={() => setTheme("day")}
            >
              亮色
            </button>
            <button
              className={`console-pill ${theme === "night" ? "active" : ""}`}
              type="button"
              onClick={() => setTheme("night")}
            >
              暗色
            </button>
            <button
              className={`console-pill ${theme === "default" ? "active" : ""}`}
              type="button"
              onClick={() => setTheme("default")}
            >
              默认（跟随时间）
            </button>
          </div>
        </div>
      </div>
    </Modal>
  );
}
