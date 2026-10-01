"use client";

import { useRouter } from "next/navigation";
import { useStore } from "@/lib/store";
import Modal from "./ui/Modal";

/** 控制台弹窗：收纳桌面端次级功能入口与主题偏好（替代原「更多 / 主题」下拉） */
export default function ConsoleModal({
  open,
  onClose,
  onDonate,
  onInstall,
  onEasterEgg,
}: {
  open: boolean;
  onClose: () => void;
  onDonate: () => void;
  onInstall: () => void;
  onEasterEgg: () => void;
}) {
  const router = useRouter();
  const { theme, setTheme } = useStore();

  // 导航类入口：先关闭弹窗再跳转（沿用原下拉逻辑）
  const go = (href: string) => {
    onClose();
    router.push(href);
  };

  return (
    <Modal open={open} onClose={onClose} lockScroll cardStyle={{ maxWidth: 660 }}>
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
        <button className="console-tile" type="button" onClick={() => { onClose(); onInstall(); }}>
          <i className="fa fa-download"></i>
          <span>安装论坛客户端</span>
        </button>
        <button className="console-tile" type="button" onClick={() => { onClose(); onEasterEgg(); }}>
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
