import Link from "next/link";
import type { Post } from "@/lib/api";
import { timeAgo } from "@/lib/constants";
import CategoryBadge from "./ui/CategoryBadge";
import SpaceBadge from "./ui/SpaceBadge";
import { UserAvatar, UserName } from "./ui/UserAvatar";

/** 帖子卡片（与 legacy renderPostCard 结构 1:1）；showSpace 开启后显示会馆/公共空间标签 */
export default function PostCard({
  post,
  showTime = true,
  showSpace = false,
}: {
  post: Post;
  showTime?: boolean;
  showSpace?: boolean;
}) {
  const summary = (post.summary || "").replace(/<[^>]+>/g, "").substring(0, 100);

  return (
    <Link className="post-card" href={`/post/${post.id}`}>
      <div className="post-card-left">
        <div className="post-card-avatar">
          <UserAvatar src={post.user_avatar} />
        </div>
      </div>
      <div className="post-card-body">
        <div className="post-card-header">
          <CategoryBadge category={post.category} />
          {showSpace && <SpaceBadge name={post.guild_name} color={post.guild_theme_color} />}
          <span className="post-card-author Username">
            <UserName name={post.user_name} userId={post.user_id} />
          </span>
          {showTime && <span className="post-card-time">{timeAgo(post.created_at)}</span>}
        </div>
        <h3 className="post-card-title">{post.title}</h3>
        <p className="post-card-summary">
          {summary}
          {summary.length >= 100 ? "..." : ""}
        </p>
        <div className="post-card-footer">
          <span className="post-card-stats">
            <i className="fa fa-eye"></i> {post.views || 0}
          </span>
          <span className="post-card-stats">
            <i className="fa fa-thumbs-up"></i> {post.likes || 0}
          </span>
          <span className="post-card-stats">
            <i className="fa fa-comment"></i> {post.comment_count ?? 0}
          </span>
        </div>
      </div>
    </Link>
  );
}
