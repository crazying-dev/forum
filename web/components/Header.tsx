"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState, useRef, useEffect } from "react";
import { useStore } from "@/lib/store";
import { miscApi } from "@/lib/api";
import { apiUrl } from "@/lib/api-base";
import { getSiteConfig } from "@/lib/site-config";
import { fetchDailyQuote, QUOTE_CHANCE } from "@/lib/daily-quote";
import { useToast } from "./Toast";
import Modal from "./ui/Modal";
import ConsoleModal, { type MessageUnread } from "./ConsoleModal";
import WorldChannelModal, { WorldChannelLauncher } from "./world/WorldChannelModal";

/** 彩蛋数据含少量 HTML（<br> 换行等）：转为单行纯文本，供胶囊提示展示 */
function eggPlainText(s: string): string {
  return s
    .replace(/<\s*br\b[^>]*>/gi, " ")
    .replace(/<[^>]*>/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

export default function Header() {
  const { setTheme, user, userId, logout } = useStore();
  const { toast } = useToast();
  const router = useRouter();
  const pathname = usePathname();
  const [search, setSearch] = useState("");
  // 顶部栏下拉菜单："" = 收起，"user" 对应用户菜单（控制台改为弹窗）
  const [openMenu, setOpenMenu] = useState<"" | "user">("");
  const [showMobileMenu, setShowMobileMenu] = useState(false);
  const [showSearchLayer, setShowSearchLayer] = useState(false);
  const [showDonate, setShowDonate] = useState(false);
  const [showConsole, setShowConsole] = useState(false);
  const [showWorld, setShowWorld] = useState(false);
  // 消息中心未读数（GET /messages/summary）：仅登录后拉取
  const [unread, setUnread] = useState<MessageUnread>({ likes: 0, comments: 0, system: 0, chat: 0 });
  const menuRef = useRef<HTMLUListElement>(null);
  const searchLayerInputRef = useRef<HTMLInputElement>(null);

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

  // 消息中心未读：登录后拉取；路由切换 / 窗口重新可见时刷新（进入消息中心后徽标可及时清除）
  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    const loadUnread = async () => {
      try {
        const res = await fetch(apiUrl("/messages/summary"), { credentials: "include" });
        const data = await res.json().catch(() => null);
        if (cancelled || !data?.success) return;
        setUnread({
          likes: Number(data.likes) || 0,
          comments: Number(data.comments) || 0,
          system: Number(data.system) || 0,
          chat: Number(data.chat) || 0,
        });
      } catch {
        // 未读数失败不影响导航
      }
    };
    loadUnread();
    const onVisible = () => {
      if (document.visibilityState === "visible") loadUnread();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [user, pathname]);

  // OAuth 授权等页不显示全局导航栏（Header 保持挂载，仅不渲染内容，避免导航时品牌图重载）
  if (pathname.startsWith("/oauth")) return null;

  // /search 页隐藏桌面搜索框（页内已有搜索入口）
  const isSearchPage = pathname.startsWith("/search");
  // 未登录不展示未读徽标（登出会整页刷新，无需在副作用里重置状态）
  const unreadTotal = user ? unread.likes + unread.comments + unread.system + unread.chat : 0;
  const unreadBadge = unreadTotal > 99 ? "99+" : String(unreadTotal);

  const doSearch = () => {
    const k = search.trim();
    if (k) {
      router.push(`/search?k=${encodeURIComponent(k)}`);
      setShowSearchLayer(false);
    }
  };

  const showEasterEgg = async () => {
    // 站点配置开启「每日一言」时，按概率改播引言（与彩蛋同为顶部胶囊提示）；否则维持原彩蛋
    const cfg = await getSiteConfig();
    if (cfg?.daily_quote.enabled && Math.random() < QUOTE_CHANCE) {
      const q = await fetchDailyQuote();
      if (q) {
        toast(`「${q.text}」${q.from ? ` —— ${q.from}` : ""}`, "info");
        return;
      }
    }
    try {
      const egg = await miscApi.easterEgg();
      const name = eggPlainText(egg.Name);
      const text = eggPlainText(egg.Text);
      toast(name && text ? `${name}：${text}` : name || text || "彩蛋", "info");
    } catch {
      toast("彩蛋获取失败", "error");
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
        {!isSearchPage && (
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
        )}
        <div className="header-right">
          {/* 移动端世界频道按钮（仅 ≤700px 显示）：打开世界频道窗口 */}
          <button
            className="header-btn header-world-toggle"
            type="button"
            aria-label="世界频道"
            onClick={() => setShowWorld(true)}
          >
            <i className="fa fa-globe"></i>
          </button>
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
            {/* 控制台：次级功能与偏好设置收纳（弹窗）；内有消息中心，未读时按钮显示总数徽标 */}
            <li className="header-collapsible">
              <button
                className="header-btn header-console-btn"
                aria-haspopup="dialog"
                aria-expanded={showConsole}
                title={unreadTotal > 0 ? `${unreadTotal} 条未读消息` : "控制台"}
                onClick={() => setShowConsole(true)}
              >
                <i className="fa fa-sliders"></i>
                <span>控制台</span>
                {unreadTotal > 0 && <span className="header-unread-badge">{unreadBadge}</span>}
              </button>
            </li>
            <li className="header-collapsible">
              <Link className="header-btn" href="/post/create">
                <i className="fa fa-pencil"></i>
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
            {/* 社区 */}
            <div className="mobile-menu-title">社区</div>
            <Link className="mobile-menu-item" href="/messages" onClick={() => setShowMobileMenu(false)}>
              <i className="fa fa-envelope-o"></i> 消息中心
              {unreadTotal > 0 && <span className="mobile-menu-badge">{unreadBadge}</span>}
            </Link>
            <Link className="mobile-menu-item" href="/huiguan" onClick={() => setShowMobileMenu(false)}><i className="fa fa-home"></i> 会馆</Link>
            <Link className="mobile-menu-item" href="/WIKI" onClick={() => setShowMobileMenu(false)}><i className="fa fa-book"></i> WIKI</Link>
            <button className="mobile-menu-item" onClick={() => { setShowMobileMenu(false); setShowWorld(true); }}><i className="fa fa-globe"></i> 世界频道</button>
            <div className="mobile-menu-divider"></div>
            {/* 工具与服务 */}
            <div className="mobile-menu-title">工具与服务</div>
            <Link className="mobile-menu-item" href="/download" onClick={() => setShowMobileMenu(false)}><i className="fa fa-download"></i> 客户端下载</Link>
            <Link className="mobile-menu-item" href="/changelog" onClick={() => setShowMobileMenu(false)}><i className="fa fa-history"></i> 更新日志</Link>
            <Link className="mobile-menu-item" href="/tools/year-converter" onClick={() => setShowMobileMenu(false)}><i className="fa fa-hourglass-half"></i> 无限年换算</Link>
            <div className="mobile-menu-divider"></div>
            {/* 帮助与支持 */}
            <div className="mobile-menu-title">帮助与支持</div>
            <Link className="mobile-menu-item" href="/guide" onClick={() => setShowMobileMenu(false)}><i className="fa fa-map-o"></i> 论坛指南</Link>
            <Link className="mobile-menu-item" href="/feedback" onClick={() => setShowMobileMenu(false)}><i className="fa fa-comments-o"></i> 反馈中心</Link>
            <button className="mobile-menu-item" onClick={() => { setShowMobileMenu(false); router.push("/feedback/submit"); }}><i className="fa fa-bug"></i> 提交反馈</button>
            <button className="mobile-menu-item" onClick={() => { setShowDonate(true); setShowMobileMenu(false); }}><i className="fa fa-heart"></i> 赞赏</button>
            <button className="mobile-menu-item" onClick={showEasterEgg}><i className="fa fa-gift"></i> 彩蛋</button>
            <div className="mobile-menu-divider"></div>
            {/* 外观 */}
            <div className="mobile-menu-title">外观</div>
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

      {/* 世界频道：桌面端右上角悬浮入口（组件内 CSS 在 ≤700px 自动隐藏，移动端走顶部栏图标/抽屉） */}
      <WorldChannelLauncher onOpen={() => setShowWorld(true)} />
      {/* 世界频道窗口（受控）：桌面拖拽窗口 / 移动端底部全屏 */}
      <WorldChannelModal open={showWorld} onClose={() => setShowWorld(false)} />

      {/* 控制台弹窗（桌面端「控制台」按钮） */}
      <ConsoleModal
        open={showConsole}
        onClose={() => setShowConsole(false)}
        onDonate={() => setShowDonate(true)}
        onEasterEgg={showEasterEgg}
        onOpenWorld={() => setShowWorld(true)}
        unread={unread}
      />

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
