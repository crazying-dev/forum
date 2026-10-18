"use client";

import { useEffect, useRef } from "react";
import { useToast } from "@/components/Toast";

/** beforeinstallprompt 事件（Chrome/Edge 提供；Safari 走手动添加到主屏幕） */
interface InstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice?: Promise<{ outcome: "accepted" | "dismissed" }>;
}

/**
 * PWA 安装按钮（下载页用）。
 * 与 Header 内 installPWA 行为保持一致：捕获 beforeinstallprompt → 原生安装；
 * 已安装 / 浏览器不支持时给出提示。Header 按任务约束不改动，故独立成小组件。
 */
export default function PwaInstallButton({
  className = "",
  label = "安装论坛客户端",
}: {
  className?: string;
  label?: string;
}) {
  const deferredPromptRef = useRef<InstallPromptEvent | null>(null);
  const installedRef = useRef(false);
  const { toast } = useToast();

  useEffect(() => {
    const onBeforeInstall = (e: Event) => {
      e.preventDefault();
      deferredPromptRef.current = e as InstallPromptEvent;
    };
    const onInstalled = () => {
      deferredPromptRef.current = null;
      installedRef.current = true;
      try {
        localStorage.setItem("pwa_installed", "1");
      } catch {
        /* 忽略存储异常 */
      }
    };
    window.addEventListener("beforeinstallprompt", onBeforeInstall);
    window.addEventListener("appinstalled", onInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", onBeforeInstall);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  const isInstalled = () => {
    try {
      if (window.matchMedia && window.matchMedia("(display-mode: standalone)").matches) return true;
      if (("standalone" in window.navigator) && !!(window.navigator as Navigator & { standalone?: boolean }).standalone) {
        return true;
      }
      if (installedRef.current) return true;
      if (localStorage.getItem("pwa_installed") === "1") return true;
    } catch {
      /* 忽略 */
    }
    return false;
  };

  const install = async () => {
    if (isInstalled()) {
      toast("客户端已安装，请从桌面或主屏幕点击「妖精论坛」图标打开", "info");
      return;
    }
    const promptEvent = deferredPromptRef.current;
    if (!promptEvent || typeof promptEvent.prompt !== "function") {
      toast("当前浏览器不支持安装客户端 (PWA)，建议使用 Chrome / Edge / Safari 最新版", "warning");
      return;
    }
    try {
      await promptEvent.prompt();
      const result = await promptEvent.userChoice;
      if (result?.outcome === "accepted") {
        installedRef.current = true;
        try {
          localStorage.setItem("pwa_installed", "1");
        } catch {
          /* 忽略存储异常 */
        }
        toast("安装成功，请从桌面或主屏幕打开", "success");
      }
    } catch {
      toast("当前浏览器不支持安装客户端 (PWA)，建议使用 Chrome / Edge / Safari 最新版", "warning");
    } finally {
      deferredPromptRef.current = null; // 一次只能调用一次 prompt
    }
  };

  return (
    <button type="button" className={className} onClick={() => void install()}>
      <i className="fa fa-download" aria-hidden="true"></i> {label}
    </button>
  );
}
