"use client";

// 引用选择弹窗：用户（/search?type=users）/ 帖子（/search?type=posts）/ 文章（/articles/search）
// 关键词至少 2 个字符（与后端一致）；行内「插入」按钮回传所选 id。

import { useCallback, useEffect, useRef, useState } from "react";
import Modal from "@/components/ui/Modal";
import { UserAvatar } from "@/components/ui/UserAvatar";
import {
  ApiException,
  ArticleSearchItem,
  EmbedKind,
  Post,
  UserBrief,
  guildApi,
  miscApi,
} from "@/lib/api";
import { categoryLabel, timeAgo } from "@/lib/constants";

const TABS: { key: EmbedKind; label: string }[] = [
  { key: "user", label: "用户" },
  { key: "post", label: "帖子" },
  { key: "article", label: "文章" },
];

const PAGE_SIZE = 10;

/** 引用选择弹窗（默认开在传入的类型页签） */
export default function QuotePickerModal({
  kind,
  onClose,
  onPick,
}: {
  kind: EmbedKind;
  onClose: () => void;
  onPick: (kind: EmbedKind, id: string) => void;
}) {
  const [tab, setTab] = useState<EmbedKind>(kind);
  const [keyword, setKeyword] = useState("");
  const [users, setUsers] = useState<UserBrief[]>([]);
  const [posts, setPosts] = useState<Post[]>([]);
  const [articles, setArticles] = useState<ArticleSearchItem[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [err, setErr] = useState("");
  // 请求序号：丢弃迟到的旧关键词/旧页签响应
  const reqRef = useRef(0);
  const pageRef = useRef(1);
  const k = keyword.trim();

  const search = useCallback(async (target: EmbedKind, kw: string, pageNo: number, append: boolean) => {
    const reqId = ++reqRef.current;
    if (append) setLoadingMore(true);
    else setLoading(true);
    setErr("");
    try {
      if (target === "user") {
        const r = await miscApi.search(kw, "users", pageNo, PAGE_SIZE);
        if (reqRef.current !== reqId) return;
        setUsers((prev) => (append ? [...prev, ...(r.users || [])] : r.users || []));
        setHasMore(!!r.users_has_more);
      } else if (target === "post") {
        const r = await miscApi.search(kw, "posts", pageNo, PAGE_SIZE);
        if (reqRef.current !== reqId) return;
        setPosts((prev) => (append ? [...prev, ...(r.posts || [])] : r.posts || []));
        setHasMore(!!r.posts_has_more);
      } else {
        const r = await guildApi.searchArticles(kw, pageNo, PAGE_SIZE);
        if (reqRef.current !== reqId) return;
        setArticles((prev) => (append ? [...prev, ...(r.articles || [])] : r.articles || []));
        setHasMore(!!r.has_more);
      }
      pageRef.current = pageNo;
    } catch (e) {
      if (reqRef.current !== reqId) return;
      setErr(e instanceof ApiException ? e.message : "搜索失败，请稍后再试");
      if (!append) {
        setUsers([]);
        setPosts([]);
        setArticles([]);
        setHasMore(false);
      }
    } finally {
      if (reqRef.current === reqId) {
        setLoading(false);
        setLoadingMore(false);
      }
    }
  }, []);

  // 关键词/页签变化：防抖搜索（k<2 时不发请求，结果区仅展示提示文案；
  // 不在此直接 setState，避免 effect 内同步更新引发级联渲染）
  useEffect(() => {
    pageRef.current = 1;
    if (k.length < 2) {
      reqRef.current += 1; // 作废在途请求的结果
      return;
    }
    const timer = window.setTimeout(() => void search(tab, k, 1, false), 300);
    return () => window.clearTimeout(timer);
  }, [k, tab, search]);

  const loadMore = () => {
    if (loadingMore || !hasMore) return;
    void search(tab, k, pageRef.current + 1, true);
  };

  const tooShort = k.length < 2;
  // 关键词不足 2 字符时隐藏旧结果与加载态（清空动作由派生值表达）
  const busy = !tooShort && loading;
  const list = tooShort ? 0 : tab === "user" ? users.length : tab === "post" ? posts.length : articles.length;
  const emptyText = tooShort
    ? "输入至少 2 个字符开始搜索"
    : err || `没有找到相关${TABS.find((t) => t.key === tab)?.label || "内容"}`;

  return (
    <Modal
      open
      onClose={onClose}
      className="follow-list-modal quote-picker-modal"
      overlayClassName="follow-list-overlay"
      cardClassName="follow-list-container quote-picker-container"
      closeable={false}
    >
      <div className="follow-list-header">
        <h3>插入引用</h3>
        <button className="follow-list-close" onClick={onClose} aria-label="关闭">
          &times;
        </button>
      </div>
      <div className="follow-list-tabs">
        {TABS.map((t) => (
          <button
            key={t.key}
            className={`follow-tab ${tab === t.key ? "active" : ""}`}
            onClick={() => setTab(t.key)}
          >
            引用{t.label}
          </button>
        ))}
      </div>
      <div className="quote-picker-search">
        <i className="fa fa-search"></i>
        <input
          className="quote-picker-input"
          type="text"
          value={keyword}
          placeholder={`搜索${TABS.find((t) => t.key === tab)?.label || ""}名称/标题（至少 2 个字符）`}
          onChange={(e) => setKeyword(e.target.value)}
          autoFocus
        />
      </div>
      <div className="follow-list-content">
        {busy ? (
          <p className="loading-text" style={{ textAlign: "center" }}>
            搜索中...
          </p>
        ) : list === 0 ? (
          <p className="loading-text" style={{ textAlign: "center" }}>{emptyText}</p>
        ) : (
          <>
            {tab === "user" &&
              users.map((u) => (
                <div className="follow-user-item" key={u.id}>
                  <span className="follow-user-avatar">
                    <UserAvatar src={u.avatar} alt={u.name} userId={u.id} />
                  </span>
                  <div className="follow-user-info">
                    <div className="follow-user-name-row">
                      <span className="follow-user-name">{u.name}</span>
                      <span className="quote-picker-id">{u.id}</span>
                    </div>
                    <p className="follow-user-intro">{u.intro || "这个人很懒，什么都没留下～"}</p>
                  </div>
                  <button className="quote-picker-insert" onClick={() => onPick("user", u.id)}>
                    插入
                  </button>
                </div>
              ))}
            {tab === "post" &&
              posts.map((p) => (
                <div className="quote-picker-item" key={p.id}>
                  <div className="quote-picker-item-body">
                    <p className="quote-picker-item-title">{p.title}</p>
                    <p className="quote-picker-item-meta">
                      <span>
                        <i className="fa fa-user-o"></i> {p.user_name}
                      </span>
                      <span>
                        <i className="fa fa-tag"></i> {categoryLabel(p.category)}
                      </span>
                      <span>
                        <i className="fa fa-clock-o"></i> {timeAgo(p.created_at)}
                      </span>
                    </p>
                  </div>
                  <button className="quote-picker-insert" onClick={() => onPick("post", p.id)}>
                    插入
                  </button>
                </div>
              ))}
            {tab === "article" &&
              articles.map((a) => (
                <div className="quote-picker-item" key={a.id}>
                  <div className="quote-picker-item-body">
                    <p className="quote-picker-item-title">{a.title}</p>
                    <p className="quote-picker-item-meta">
                      {a.guild_name && (
                        <span>
                          <i className="fa fa-home"></i> {a.guild_name}
                        </span>
                      )}
                      <span>
                        <i className="fa fa-clock-o"></i> {timeAgo(a.created_at)}
                      </span>
                    </p>
                  </div>
                  <button className="quote-picker-insert" onClick={() => onPick("article", a.id)}>
                    插入
                  </button>
                </div>
              ))}
            {hasMore && (
              <button className="quote-picker-more" disabled={loadingMore} onClick={loadMore}>
                {loadingMore ? "加载中..." : "加载更多"}
              </button>
            )}
          </>
        )}
      </div>
    </Modal>
  );
}
