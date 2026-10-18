"use client";

// ===== 消息列表数据层 =====
// - 单类（likes/comments/system）与「全部」聚合共用；全部为三类首页并发拉取后按时间倒序合并
// - cursor 分页（每类独立 cursor），加载更多时只请求还有下一页的分类
// - SSE 新条目由父级通过 incoming 传入，按 key 去重后合并；正在查看时顺带标记已读

import { useCallback, useEffect, useRef, useState } from "react";
import {
  MESSAGE_PAGE_SIZE,
  type CommentMessage,
  type LikeMessage,
  type MessageCategory,
  type SystemMessage,
  messagesApi,
} from "@/lib/api/messages";
import {
  categoriesOfType,
  categoryOfFeedItem,
  commentToFeedItem,
  likeToFeedItem,
  mergeFeedItems,
  systemToFeedItem,
  type FeedItem,
  type MessageType,
} from "./types";

interface CategoryPage {
  category: MessageCategory;
  items: FeedItem[];
  hasMore: boolean;
  next: string;
  error: string;
}

type CursorMap = Record<MessageCategory, string>;
type MoreMap = Record<MessageCategory, boolean>;

const EMPTY_CURSORS: CursorMap = { likes: "", comments: "", system: "" };
const EMPTY_MORE: MoreMap = { likes: false, comments: false, system: false };

function errorText(err: unknown): string {
  return err instanceof Error && err.message ? err.message : "加载失败，请稍后重试";
}

async function fetchCategoryPage(category: MessageCategory, cursor: string): Promise<CategoryPage> {
  try {
    if (category === "likes") {
      const r = await messagesApi.likes(cursor, MESSAGE_PAGE_SIZE);
      return {
        category,
        items: (r.items || []).map((m: LikeMessage) => likeToFeedItem(m)),
        hasMore: !!r.has_more,
        next: r.next_cursor || "",
        error: "",
      };
    }
    if (category === "comments") {
      const r = await messagesApi.comments(cursor, MESSAGE_PAGE_SIZE);
      return {
        category,
        items: (r.items || []).map((m: CommentMessage) => commentToFeedItem(m)),
        hasMore: !!r.has_more,
        next: r.next_cursor || "",
        error: "",
      };
    }
    const r = await messagesApi.system(cursor, MESSAGE_PAGE_SIZE);
    return {
      category,
      items: (r.items || []).map((m: SystemMessage) => systemToFeedItem(m)),
      hasMore: !!r.has_more,
      next: r.next_cursor || "",
      error: "",
    };
  } catch (err) {
    return { category, items: [], hasMore: false, next: "", error: errorText(err) };
  }
}

/**
 * 消息列表 hook。
 * @param type 当前类型（chat 不走此 hook）
 * @param enabled 未登录 / 移动端未进入详情时为 false，避免误标已读
 * @param incoming SSE 新条目（父级累积，hook 内合并去重）
 * @param onRead 某分类已读成功后的回调（清侧栏徽标）
 * @param refreshToken 轮询 / 手动刷新计数
 */
export function useMessageFeed(
  type: MessageType,
  enabled: boolean,
  incoming: FeedItem[],
  onRead?: (category: MessageCategory) => void,
  refreshToken = 0
) {
  const [items, setItems] = useState<FeedItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadedType, setLoadedType] = useState<MessageType | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState("");
  const [hasMore, setHasMore] = useState(false);

  const seqRef = useRef(0);
  const loadedTypeRef = useRef<MessageType | null>(null);
  const cursorsRef = useRef<CursorMap>({ ...EMPTY_CURSORS });
  const moreRef = useRef<MoreMap>({ ...EMPTY_MORE });
  const loadingMoreRef = useRef(false);
  const lastReadAtRef = useRef<Record<MessageCategory, string>>({ likes: "", comments: "", system: "" });
  const lastRefreshRef = useRef(refreshToken);
  const onReadRef = useRef(onRead);

  useEffect(() => {
    onReadRef.current = onRead;
  }, [onRead]);

  /** 标记分类已读（只前进不后退；失败不阻断 UI） */
  const markCategoryRead = useCallback((category: MessageCategory, at: string) => {
    const ts = at && !Number.isNaN(Date.parse(at)) ? at : new Date().toISOString();
    const prev = lastReadAtRef.current[category];
    if (prev && Date.parse(ts) <= Date.parse(prev)) return;
    lastReadAtRef.current[category] = ts;
    void messagesApi
      .read(category, ts)
      .then(() => onReadRef.current?.(category))
      .catch(() => {
        /* 下次加载/新消息时重试 */
      });
  }, []);

  const loadFirst = useCallback(
    async (silent = false) => {
      if (!enabled || type === "chat") return;
      const seq = ++seqRef.current;
      if (!silent) {
        setLoading(true);
        setError("");
      }

      const categories = categoriesOfType(type);
      const results = await Promise.all(categories.map((c) => fetchCategoryPage(c, "")));
      if (seq !== seqRef.current) return;

      const okResults = results.filter((r) => !r.error);
      const failed = results.filter((r) => r.error);
      const merged = mergeFeedItems(
        [],
        okResults.flatMap((r) => r.items)
      );

      const cursors: CursorMap = { ...EMPTY_CURSORS };
      const more: MoreMap = { ...EMPTY_MORE };
      for (const r of okResults) {
        cursors[r.category] = r.next;
        more[r.category] = r.hasMore;
      }
      cursorsRef.current = cursors;
      moreRef.current = more;
      loadedTypeRef.current = type;

      setItems(merged);
      setHasMore(categories.some((c) => more[c]));
      setError(failed.length === categories.length ? failed[0]?.error || "加载失败，请稍后重试" : "");
      setLoading(false);
      setLoadedType(type);

      // 单类详情打开时标记已读（「全部」是聚合浏览，不清空各分类徽标；SSE 实时条目光临时例外）
      if (type !== "all" && merged.length > 0) {
        markCategoryRead(categories[0], merged[0].created_at);
      }
    },
    [enabled, type, markCategoryRead]
  );

  // 类型/可用性变化：使旧请求失效（不在此同步 setState，避免级联渲染）
  useEffect(() => {
    seqRef.current += 1;
    loadedTypeRef.current = null;
    loadingMoreRef.current = false;
    cursorsRef.current = { ...EMPTY_CURSORS };
    moreRef.current = { ...EMPTY_MORE };
  }, [type, enabled]);

  // 首屏 / 重新进入详情
  useEffect(() => {
    if (!enabled || type === "chat") return;
    // 延后一个 tick，避免在 effect 内同步触发加载态更新
    const t = window.setTimeout(() => void loadFirst(false), 0);
    return () => window.clearTimeout(t);
  }, [enabled, type, loadFirst]);

  // 轮询 / 手动刷新（保留旧列表，静默合并）
  useEffect(() => {
    if (refreshToken === lastRefreshRef.current) return;
    lastRefreshRef.current = refreshToken;
    if (!enabled || type === "chat") return;
    const t = window.setTimeout(() => void loadFirst(true), 0);
    return () => window.clearTimeout(t);
  }, [refreshToken, enabled, type, loadFirst]);

  const loadMore = useCallback(async () => {
    if (!enabled || type === "chat" || loadingMoreRef.current) return;
    const categories = categoriesOfType(type).filter((c) => moreRef.current[c]);
    if (categories.length === 0) return;

    const seq = seqRef.current;
    loadingMoreRef.current = true;
    setLoadingMore(true);
    const results = await Promise.all(categories.map((c) => fetchCategoryPage(c, cursorsRef.current[c])));
    if (seq !== seqRef.current || loadedTypeRef.current !== type) {
      loadingMoreRef.current = false;
      setLoadingMore(false);
      return;
    }

    const okResults = results.filter((r) => !r.error);
    for (const r of okResults) {
      cursorsRef.current[r.category] = r.next;
      moreRef.current[r.category] = r.hasMore;
    }
    setItems((prev) => mergeFeedItems(prev, okResults.flatMap((r) => r.items)));
    setHasMore(categoriesOfType(type).some((c) => moreRef.current[c]));
    loadingMoreRef.current = false;
    setLoadingMore(false);
  }, [enabled, type]);

  // SSE 新条目：合并去重；正在查看对应分类时立即标记已读
  useEffect(() => {
    if (!enabled || type === "chat" || incoming.length === 0) return;
    const categories = categoriesOfType(type);
    const accepted = incoming.filter((item) => categories.includes(categoryOfFeedItem(item)));
    if (accepted.length === 0) return;
    const t = window.setTimeout(() => {
      setItems((prev) => mergeFeedItems(prev, accepted));
      for (const item of accepted) markCategoryRead(categoryOfFeedItem(item), item.created_at);
    }, 0);
    return () => window.clearTimeout(t);
  }, [incoming, enabled, type, markCategoryRead]);

  const refresh = useCallback(() => {
    void loadFirst();
  }, [loadFirst]);

  // 切换类型后、首屏请求返回前也显示加载态（避免先闪一下空态）
  const effectiveLoading = loading || (enabled && type !== "chat" && loadedType !== type);
  return { items, loading: effectiveLoading, loadingMore, error, hasMore, refresh, loadMore };
}
