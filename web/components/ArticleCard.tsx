import Link from "next/link";
import type { FeedItem } from "@/lib/api";
import { prefixBadgeColor, timeAgo } from "@/lib/constants";
import { PrefixBadgeSvg } from "./PrefixBadge";
import SpaceBadge from "./ui/SpaceBadge";
import { UserName } from "./ui/UserAvatar";

/** 会馆文章卡片（信息流混排用）：文章徽章 + 标题 + 摘要 + 执笔 + 浏览量 + 更新时间（时间在头部行右侧） */
export default function ArticleCard({ item, showSpace = true }: { item: FeedItem; showSpace?: boolean }) {
  const summary = (item.summary || "").replace(/<[^>]+>/g, "").substring(0, 100);
  const authorName = item.author?.name || item.user_name;
  // 身份小图标：按作者 user_id 前缀取色（HG/YJ），无徽章时不渲染，避免占位空隙
  const badgeColor = prefixBadgeColor(item.user_id);

  return (
    <Link className="post-card article-card" href={`/article/${item.id}`}>
      <div className="post-card-left">
        <div className="post-card-avatar article-card-icon">
          <i className="fa fa-book"></i>
        </div>
      </div>
      <div className="post-card-body">
        <div className="post-card-header">
          <span className="article-badge">文章</span>
          {showSpace && <SpaceBadge name={item.guild_name} color={item.guild_theme_color} />}
          <span className="post-card-author Username">
            <UserName name={authorName} />
          </span>
          {badgeColor && (
            <span className="post-card-prefix-badge" title="身份徽标">
              <PrefixBadgeSvg color={badgeColor} />
            </span>
          )}
          <span className="post-card-time">{timeAgo(item.updated_at || item.created_at)}</span>
        </div>
        <h3 className="post-card-title">{item.title}</h3>
        <p className="post-card-summary">
          {summary}
          {summary.length >= 100 ? "..." : ""}
        </p>
        <div className="post-card-footer">
          <span className="post-card-stats">
            <i className="fa fa-eye"></i> {item.views || 0}
          </span>
          <span className="post-card-stats article-card-author">
            <i className="fa fa-pencil"></i> 执笔 {authorName}
          </span>
          {item.participants_count > 0 && (
            <span className="post-card-stats">
              <i className="fa fa-users"></i> {item.participants_count}
            </span>
          )}
        </div>
      </div>
    </Link>
  );
}
