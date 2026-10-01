"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState, useRef, useEffect } from "react";
import { useStore } from "@/lib/store";
import { miscApi } from "@/lib/api";
import { useCenterCard } from "./CenterCard";
import { useToast } from "./Toast";
import Modal from "./ui/Modal";

export default function Header() {
  const { theme, setTheme, user, userId, logout } = useStore();
  const { show } = useCenterCard();
  const { toast } = useToast();
  const router = useRouter();
  const pathname = usePathname();
  const [search, setSearch] = useState("");
  // 顶部栏下拉菜单："" = 收起，"more"/"theme"/"user" 对应 更多 / 主题 / 用户
  const [openMenu, setOpenMenu] = useState<"" | "more" | "theme" | "user">("");
  const [showMobileMenu, setShowMobileMenu] = useState(false);
  const [showSearchLayer, setShowSearchLayer] = useState(false);
  const [showDonate, setShowDonate] = useState(false);
  const menuRef = useRef<HTMLUListElement>(null);
  const searchLayerInputRef = useRef<HTMLInputElement>(null);
  const deferredPromptRef = useRef<Event | null>(null);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpenMenu("");
      }
    };
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, []);

  // 关闭移动端菜单 / 搜索弹层（路由切换后）
  useEffect(() => {
    setShowMobileMenu(false);
    setShowSearchLayer(false);
  }, [pathname]);

  // 抽屉 / 搜索弹层打开时锁定背景滚动，ESC 关闭
  useEffect(() => {
    if (!showMobileMenu && !showSearchLayer) return;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setShowMobileMenu(false);
        setShowSearchLayer(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [showMobileMenu, showSearchLayer]);

  // 搜索弹层打开时自动聚焦输入框
  useEffect(() => {
    if (showSearchLayer) searchLayerInputRef.current?.focus();
  }, [showSearchLayer]);

  // PWA 安装：捕获 beforeinstallprompt（与 legacy base.html 一致）
  useEffect(() => {
    const onBeforeInstall = (e: Event) => {
      e.preventDefault();
      deferredPromptRef.current = e;
    };
    window.addEventListener("beforeinstallprompt", onBeforeInstall);
    return () => window.removeEventListener("beforeinstallprompt", onBeforeInstall);
  }, []);

  // OAuth 授权等页不显示全局导航栏（Header 保持挂载，仅不渲染内容，避免导航时品牌图重载）
  if (pathname.startsWith("/oauth")) return null;

  const doSearch = () => {
    const k = search.trim();
    if (k) {
      router.push(`/search?k=${encodeURIComponent(k)}`);
      setShowSearchLayer(false);
    }
  };

  const showEasterEgg = async () => {
    try {
      const egg = await miscApi.easterEgg();
      toast(`${egg.Name}：${egg.Text}`, "info");
    } catch {
      toast("彩蛋获取失败", "error");
    }
  };

  const installPWA = () => {
    const promptEvent = deferredPromptRef.current as any;
    if (promptEvent && typeof promptEvent.prompt === "function") {
      promptEvent.prompt();
      promptEvent.userChoice
        ?.then((result: { outcome: string }) => {
          if (result && result.outcome === "accepted") {
            try {
              localStorage.setItem("pwa_installed", "1");
            } catch {}
          }
          deferredPromptRef.current = null;
        })
        .catch(() => {
          toast("当前浏览器不支持安装", "warning");
        });
    } else {
      show(
        <div style={{ textAlign: "center", padding: "6px 4px 2px" }}>
          <div style={{ fontSize: 16, fontWeight: 600, color: "var(--color-text-primary)", marginBottom: 8 }}>
            当前浏览器不支持安装
          </div>
          <div style={{ fontSize: 14, color: "var(--color-text-secondary)", lineHeight: 1.6 }}>
            您的浏览器暂不支持安装论坛客户端 (PWA)。建议使用 Chrome / Edge / Safari 最新版本再次尝试。
          </div>
        </div>
      );
    }
  };

  return (
    <>
      <header id="header">
        <div className="header-left">
          {/* 移动端侧边栏展开按钮（仅 ≤700px 显示） */}
          <button
            className="header-btn header-menu-toggle"
            type="button"
            aria-label="打开导航菜单"
            onClick={() => setShowMobileMenu(!showMobileMenu)}
          >
            <i className="fa fa-bars"></i>
          </button>
          <Link className="header-left-link" href="/">
            <img src="/assets/img/favicon.png" alt="logo" id="logo" style={{ borderRadius: "50%" }} />
            <h1>
              妖精论坛
              <span className="header-brand-badge" aria-hidden="true" title="重构预览版 ov2">ov2</span>
            </h1>
          </Link>
        </div>
        <div className="header-center">
          <div id="search">
            <label htmlFor="search_input">
              <input
                id="search_input"
                placeholder="搜索帖子、用户、文章..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && doSearch()}
              />
            </label>
            <button id="search_button" onClick={doSearch}>
              <img alt="search_Button_ICON" src="/assets/img/search.svg" id="search_Button_ICON" />
            </button>
          </div>
        </div>
        <div className="header-right">
          {/* 移动端发帖按钮（仅 ≤700px 显示，样式见 header-responsive.css） */}
          <Link className="header-btn header-post-toggle" href="/post/create" aria-label="发帖">
            <i className="fa fa-pencil"></i>
            <span>发帖</span>
          </Link>
          {/* 移动端搜索按钮（仅 ≤700px 显示），点击打开全屏搜索弹层 */}
          <button
            className="header-btn header-search-toggle"
            type="button"
            aria-label="搜索"
            onClick={() => setShowSearchLayer(true)}
          >
            <i className="fa fa-search"></i>
          </button>
          <ul ref={menuRef}>
            <li className="header-collapsible">
              <Link className="header-btn" href="/huiguan">
                <i className="fa fa-home"></i>
                <span>会馆</span>
              </Link>
            </li>
            <li className="header-collapsible">
              <button className="header-btn" id="Easter-Egg" onClick={showEasterEgg}>
                <i className="fa fa-gift"></i>
                <span>彩蛋</span>
              </button>
            </li>
            {/* 更多：次级功能收纳 */}
            <li className={`header-collapsible header-setting ${openMenu === "more" ? "active" : ""}`}>
              <button className="header-btn" onClick={() => setOpenMenu(openMenu === "more" ? "" : "more")}>
                <i className="fa fa-ellipsis-h"></i>
                <span>更多</span>
              </button>
              {openMenu === "more" && (
                <div className="setting-dropdown dropdown-center">
                  <ul className="setting-dropdown-menu">
                    <li className="setting-dropdown-title">更多功能</li>
                    <li className="setting-dropdown-item" onClick={() => { setOpenMenu(""); router.push("/WIKI"); }}>
                      <img src="/assets/img/wiki_avatar_l.png" alt="" />
                      <span className="setting-item-text">WIKI</span>
                    </li>
                    <li className="setting-dropdown-item" onClick={() => { setOpenMenu(""); setShowDonate(true); }}>
                      <i className="fa fa-heart"></i>
                      <span className="setting-item-text">赞赏</span>
                    </li>
                    <li className="setting-dropdown-item" onClick={() => { setOpenMenu(""); router.push("/feedback/submit"); }}>
                      <i className="fa fa-bug"></i>
                      <span className="setting-item-text">提交反馈</span>
                    </li>
                    <li className="setting-dropdown-item" onClick={() => { setOpenMenu(""); router.push("/feedback"); }}>
                      <i className="fa fa-comments-o"></i>
                      <span className="setting-item-text">反馈中心</span>
                    </li>
                    <li className="setting-dropdown-item" onClick={() => { setOpenMenu(""); router.push("/guide"); }}>
                      <i className="fa fa-map-o"></i>
                      <span className="setting-item-text">论坛指南</span>
                    </li>
                    <li className="setting-dropdown-item" id="pwa-install-li" onClick={() => { setOpenMenu(""); installPWA(); }}>
                      <i className="fa fa-download"></i>
                      <span className="setting-item-text">安装论坛客户端</span>
                    </li>
                  </ul>
                </div>
              )}
            </li>
            <li className={`header-collapsible header-setting ${openMenu === "theme" ? "active" : ""}`}>
              <button className="header-btn" onClick={() => setOpenMenu(openMenu === "theme" ? "" : "theme")}>
                <i className="fa fa-paint-brush"></i>
                <span>主题</span>
              </button>
              {openMenu === "theme" && (
                <div className="setting-dropdown" id="settingDropdown">
                  <ul className="setting-dropdown-menu">
                    <li className="setting-dropdown-title">选择主题</li>
                    <li className={`setting-dropdown-item ${theme === "day" ? "active" : ""}`} onClick={() => setTheme("day")}>
                      <span className="setting-item-icon"></span>
                      <span className="setting-item-text">亮色</span>
                    </li>
                    <li className={`setting-dropdown-item ${theme === "night" ? "active" : ""}`} onClick={() => setTheme("night")}>
                      <span className="setting-item-icon"></span>
                      <span className="setting-item-text">暗色</span>
                    </li>
                    <li className={`setting-dropdown-item ${theme === "default" ? "active" : ""}`} onClick={() => setTheme("default")}>
                      <span className="setting-item-icon"></span>
                      <span className="setting-item-text">默认（跟随时间）</span>
                    </li>
                  </ul>
                </div>
              )}
            </li>
            <li className="header-collapsible">
              <Link className="header-post-btn" href="/post/create">
                <span className="header-post-icon" aria-hidden="true">✏️</span>
                <span>发帖</span>
              </Link>
            </li>
            <li className={`header-setting ${openMenu === "user" ? "active" : ""}`}>
              {user ? (
                <>
                  <button id="UserInfo" onClick={() => setOpenMenu(openMenu === "user" ? "" : "user")}>
                    <div className="user-avatar" id="user-avatar">
                      {user.avatar ? (
                        <img src={user.avatar} alt="" width={32} height={32} style={{ borderRadius: "50%" }} />
                      ) : (
                        <i className="fa fa-user"></i>
                      )}
                    </div>
                    <div id="user-name" className="Username">{user.name}</div>
                  </button>
                  {openMenu === "user" && (
                    <div className="setting-dropdown">
                      <ul className="setting-dropdown-menu">
                        <li className="setting-dropdown-title">{user.name}</li>
                        <li className="setting-dropdown-item" onClick={() => { setOpenMenu(""); router.push(`/users/${userId}`); }}>
                          <i className="fa fa-user-circle-o"></i>
                          <span className="setting-item-text">个人中心</span>
                        </li>
                        <li className="setting-dropdown-item" id="logoutBtn" onClick={() => { setOpenMenu(""); logout(); }}>
                          <i className="fa fa-sign-out"></i>
                          <span className="setting-item-text">退出登录</span>
                        </li>
                      </ul>
                    </div>
                  )}
                </>
              ) : (
                <Link id="UserInfo" href="/auth">
                  <div className="user-avatar" id="user-avatar">
                    <i className="fa fa-user"></i>
                  </div>
                  <div id="user-name" className="Username">登录</div>
                </Link>
              )}
            </li>
          </ul>
          {/* 侧边栏遮罩（点击关闭；仅抽屉打开时可见） */}
          <div
            className={`header-mobile-overlay ${showMobileMenu ? "open" : ""}`}
            onClick={() => setShowMobileMenu(false)}
          ></div>
          {/* 移动端侧边栏：左侧滑出抽屉 */}
          <nav className={`header-mobile-menu ${showMobileMenu ? "open" : ""}`} id="headerMobileMenu">
            <button
              className="mobile-menu-close"
              type="button"
              aria-label="关闭菜单"
              onClick={() => setShowMobileMenu(false)}
            >
              &times;
            </button>
            <div className="mobile-menu-user">
              {user ? (
                <Link className="mobile-menu-user-link" href={`/users/${userId}`} onClick={() => setShowMobileMenu(false)}>
                  <div className="mobile-menu-user-avatar">
                    {user.avatar ? <img src={user.avatar} alt="" /> : <i className="fa fa-user"></i>}
                  </div>
                  <span className="mobile-menu-user-name">{user.name}</span>
                </Link>
              ) : (
                <Link className="mobile-menu-user-link" href="/auth" onClick={() => setShowMobileMenu(false)}>
                  <div className="mobile-menu-user-avatar"><i className="fa fa-user"></i></div>
                  <span className="mobile-menu-user-name">登录</span>
                </Link>
              )}
            </div>
            <Link className="mobile-menu-item" href="/WIKI" onClick={() => setShowMobileMenu(false)}><i className="fa fa-book"></i> WIKI</Link>
            <Link className="mobile-menu-item" href="/huiguan" onClick={() => setShowMobileMenu(false)}><i className="fa fa-home"></i> 会馆</Link>
            <button className="mobile-menu-item" onClick={() => { setShowDonate(true); setShowMobileMenu(false); }}><i className="fa fa-heart"></i> 赞赏</button>
            <button className="mobile-menu-item" onClick={() => { setShowMobileMenu(false); router.push("/feedback/submit"); }}><i className="fa fa-bug"></i> 提交反馈</button>
            <Link className="mobile-menu-item" href="/feedback" onClick={() => setShowMobileMenu(false)}><i className="fa fa-comments-o"></i> 反馈中心</Link>
            <Link className="mobile-menu-item" href="/guide" onClick={() => setShowMobileMenu(false)}><i className="fa fa-map-o"></i> 论坛指南</Link>
            <button className="mobile-menu-item" id="pwa-install-mobile" onClick={installPWA}><i className="fa fa-download"></i> 安装论坛客户端</button>
            <button className="mobile-menu-item" onClick={showEasterEgg}><i className="fa fa-gift"></i> 彩蛋</button>
            <div className="mobile-menu-divider"></div>
            <div className="mobile-menu-title">主题</div>
            <button className="mobile-menu-item mobile-theme-btn" onClick={() => setTheme("day")}><i className="fa fa-sun-o"></i> 亮色</button>
            <button className="mobile-menu-item mobile-theme-btn" onClick={() => setTheme("night")}><i className="fa fa-moon-o"></i> 暗色</button>
            <button className="mobile-menu-item mobile-theme-btn" onClick={() => setTheme("default")}><i className="fa fa-desktop"></i> 默认</button>
            <div className="mobile-menu-divider"></div>
            {user && (
              <button className="mobile-menu-item" onClick={logout}><i className="fa fa-sign-out"></i> 退出登录</button>
            )}
          </nav>
        </div>
      </header>

      {/* 移动端全屏搜索弹层 */}
      {showSearchLayer && (
        <div className="search-layer" onClick={() => setShowSearchLayer(false)}>
          <div className="search-layer-bar-wrap" onClick={(e) => e.stopPropagation()}>
            <button
              className="search-layer-close"
              type="button"
              aria-label="关闭搜索"
              onClick={() => setShowSearchLayer(false)}
            >
              &times;
            </button>
            <div className="search-layer-bar">
              <i className="fa fa-search search-layer-icon"></i>
              <input
                ref={searchLayerInputRef}
                className="search-layer-input"
                placeholder="搜索帖子、用户、文章..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && doSearch()}
              />
              <button className="search-layer-submit" type="button" onClick={doSearch}>
                搜索
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 赞赏弹窗 */}
      <Modal open={showDonate} onClose={() => setShowDonate(false)}>
        <h3 className="donate-title"><i className="fa fa-heart"></i> 赞赏支持</h3>
        <p className="donate-subtitle">个人自发投喂，不为项目收益</p>
        <div className="donate-qr-wrap">
          <img src="/assets/img/help.png" alt="赞赏码" />
        </div>
        <p className="donate-tip">你的支持是我持续创作的动力 ❤️</p>
      </Modal>
    </>
  );
}
