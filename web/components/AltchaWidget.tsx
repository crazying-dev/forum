"use client";

import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";
import { apiUrl } from "@/lib/api-base";

/** GET /captcha/config 返回中前端关心的字段。 */
interface CaptchaConfig {
  enabled: boolean;
  algorithm?: string;
  cost?: number;
}

export type AltchaState = "unverified" | "verifying" | "verified" | "code" | "error" | "expired";
export interface AltchaWidgetHandle {
  /** ALTCHA 是否启用（配置接口 enabled=true，且未被构建期开关关闭）。 */
  isEnabled: () => boolean;
  /** 读取已验证的 ALTCHA payload（base64），未完成验证时为 null。 */
  getPayload: () => string | null;
  /** 确保已完成验证：必要时主动触发求解，返回 payload；未启用或失败返回 null。 */
  ensurePayload: () => Promise<string | null>;
  /** 重置状态，使下一次提交重新求解（每次业务请求成功后 payload 即失效）。 */
  reset: () => void;
}

interface AltchaWidgetProps {
  className?: string;
  /** verified 事件：验证完成并拿到 payload。 */
  onVerified?: (payload: string) => void;
  /** statechange 事件：unverified / verifying / verified / code / error / expired。 */
  onStateChange?: (state: AltchaState) => void;
  /** error 状态：验证失败。 */
  onError?: (message: string) => void;
}

/** altcha-widget 自定义元素在浏览器端暴露的方法（v3 与 v2 共用 verify/reset）。 */
interface AltchaElement extends HTMLElement {
  getState?: () => string;
  verify?: () => Promise<{ payload?: string } | null>;
  reset?: () => void;
}

let configPromise: Promise<CaptchaConfig | null> | null = null;

// 配置只需拉取一次（同一页面多次挂载共享）；失败不缓存，下次挂载重试。
function loadCaptchaConfig(): Promise<CaptchaConfig | null> {
  if (!configPromise) {
    configPromise = fetch(apiUrl("/captcha/config"), { credentials: "same-origin" })
      .then(async (res) => {
        if (!res.ok) return null;
        const data = (await res.json()) as CaptchaConfig | null;
        return data && typeof data.enabled === "boolean" ? data : null;
      })
      .catch(() => {
        configPromise = null;
        return null;
      });
  }
  return configPromise;
}

/**
 * ALTCHA v2 人机验证 Widget。
 *
 * - 使用 Web Component `<altcha-widget challenge={apiUrl("/captcha/challenge")} language="zh" auto="onsubmit">`；
 * - 通过 ref 暴露 getPayload()/ensurePayload()/reset()，供登录、注册、发码、找回密码复用；
 * - 处理 verified / statechange / expired / error 状态；
 * - `/captcha/config` 返回 enabled=false（或 NEXT_PUBLIC_ALTCHA_ENABLED=false）时不渲染。
 */
export const AltchaWidget = forwardRef<AltchaWidgetHandle, AltchaWidgetProps>(function AltchaWidget(
  { className, onVerified, onStateChange, onError },
  ref
) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const elementRef = useRef<AltchaElement | null>(null);
  const payloadRef = useRef<string | null>(null);
  const waitersRef = useRef<Array<(payload: string | null) => void>>([]);
  const callbacksRef = useRef({ onVerified, onStateChange, onError });
  const [status, setStatus] = useState<"checking" | "ready" | "disabled">("checking");

  useEffect(() => {
    callbacksRef.current = { onVerified, onStateChange, onError };
  }, [onVerified, onStateChange, onError]);

  const resolveWaiters = useCallback((payload: string | null) => {
    const waiters = waitersRef.current;
    waitersRef.current = [];
    waiters.forEach((resolve) => resolve(payload));
  }, []);

  const getPayload = useCallback((): string | null => {
    if (payloadRef.current) return payloadRef.current;
    // 兜底：widget 处于已验证状态时读取其 hidden input（name="altcha"）。
    // 仅在 verified 时读取，避免 reset 后 DOM 尚未刷新时拿到旧 payload。
    if (elementRef.current?.getState?.() !== "verified") return null;
    const input = containerRef.current?.querySelector<HTMLInputElement>('input[name="altcha"]');
    const value = input?.value.trim();
    return value ? value : null;
  }, []);

  const reset = useCallback(() => {
    payloadRef.current = null;
    resolveWaiters(null);
    elementRef.current?.reset?.();
  }, [resolveWaiters]);

  const ensurePayload = useCallback(async (): Promise<string | null> => {
    const current = getPayload();
    if (current) return current;

    const element = elementRef.current;
    if (!element || typeof element.verify !== "function") return null;

    // 用户已点击验证（widget 正在求解）时不要重复发起，等待事件结果。
    if (element.getState?.() === "verifying") {
      return new Promise<string | null>((resolve) => {
        waitersRef.current.push(resolve);
        window.setTimeout(() => resolve(null), 120000);
      });
    }

    try {
      const result = await element.verify();
      const payload = result?.payload ?? getPayload();
      if (payload) {
        payloadRef.current = payload;
        return payload;
      }
    } catch {
      // 失败原因由 statechange 事件上报。
    }
    return null;
  }, [getPayload]);

  useImperativeHandle(
    ref,
    () => ({
      isEnabled: () => status === "ready",
      getPayload,
      ensurePayload,
      reset,
    }),
    [status, getPayload, ensurePayload, reset]
  );

  // 1) 读取服务端开关：enabled=false 时不渲染。
  useEffect(() => {
    if (process.env.NEXT_PUBLIC_ALTCHA_ENABLED === "false") {
      setStatus("disabled");
      return;
    }
    let cancelled = false;
    loadCaptchaConfig().then((config) => {
      if (cancelled) return;
      setStatus(config?.enabled ? "ready" : "disabled");
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // 2) 动态加载 Web Component（仅浏览器端执行）并挂载。
  useEffect(() => {
    if (status !== "ready") return;
    const container = containerRef.current;
    if (!container) return;

    let cancelled = false;
    let element: AltchaElement | null = null;

    const onVerifiedEvent = (event: Event) => {
      const payload = (event as CustomEvent<{ payload?: string }>).detail?.payload;
      if (!payload) return;
      payloadRef.current = payload;
      resolveWaiters(payload);
      callbacksRef.current.onVerified?.(payload);
    };

    const onStateChangeEvent = (event: Event) => {
      const detail = (event as CustomEvent<{ state?: string; payload?: string | null }>).detail;
      const nextState = detail?.state as AltchaState | undefined;
      if (nextState === "verified" && detail?.payload) {
        payloadRef.current = detail.payload;
        resolveWaiters(detail.payload);
      } else if (nextState === "unverified" || nextState === "error" || nextState === "expired") {
        payloadRef.current = null;
        resolveWaiters(null);
      }
      if (nextState) callbacksRef.current.onStateChange?.(nextState);
      if (nextState === "error") callbacksRef.current.onError?.("人机验证失败，请重试");
    };

    const onExpired = () => {
      payloadRef.current = null;
      resolveWaiters(null);
      callbacksRef.current.onStateChange?.("expired");
    };

    (async () => {
      try {
        await import("altcha");
        try {
          // 注册 zh-cn 文案；language="zh" 会按主语言自动匹配到 zh-cn。
          await import("altcha/i18n/zh-cn");
        } catch {
          // 中文包加载失败时退回内置英文，不阻断验证。
        }
      } catch {
        // widget 资源加载失败：隐藏组件（后端仍会兜底校验）。
        if (!cancelled) setStatus("disabled");
        return;
      }
      if (cancelled) return;

      element = document.createElement("altcha-widget") as AltchaElement;
      element.setAttribute("challenge", apiUrl("/captcha/challenge"));
      element.setAttribute("language", "zh");
      element.setAttribute("auto", "onsubmit");
      element.setAttribute("name", "altcha");
      element.addEventListener("verified", onVerifiedEvent);
      element.addEventListener("statechange", onStateChangeEvent);
      element.addEventListener("expired", onExpired);
      container.appendChild(element);
      elementRef.current = element;
    })();

    return () => {
      cancelled = true;
      if (element) {
        element.removeEventListener("verified", onVerifiedEvent);
        element.removeEventListener("statechange", onStateChangeEvent);
        element.removeEventListener("expired", onExpired);
        element.remove();
      }
      if (elementRef.current === element) elementRef.current = null;
      payloadRef.current = null;
      resolveWaiters(null);
    };
  }, [status, resolveWaiters]);

  if (status !== "ready") return null;

  return (
    <div
      ref={containerRef}
      className={`altcha-slot${className ? ` ${className}` : ""}`}
      aria-live="polite"
    />
  );
});
