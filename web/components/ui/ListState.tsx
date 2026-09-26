"use client";

import GlobalLoading from "@/components/GlobalLoading";

/** 列表加载中 / 空状态 / 加载更多按钮(forum/search/home 共用) */
export function ListLoading({ className = "forum-loading", text = "加载中..." }: { className?: string; text?: string }) {
  return (
    <div className={className}>
      <GlobalLoading size={56} text={text} />
    </div>
  );
}

export function ListEmpty({ className = "forum-empty", text = "暂无帖子" }: { className?: string; text?: string }) {
  return <div className={className}>{text}</div>;
}

export function LoadMoreButton({
  loading,
  onClick,
  id,
  className = "forum-load-more",
}: {
  loading: boolean;
  onClick: () => void;
  id?: string;
  className?: string;
}) {
  return (
    <div className={className} id={id}>
      <button onClick={onClick} disabled={loading}>
        {loading ? "加载中..." : "加载更多"}
      </button>
    </div>
  );
}
