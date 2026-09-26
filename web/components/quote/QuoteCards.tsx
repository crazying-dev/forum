"use client";

// ===== 引用卡片（数据渲染端共用）=====
// 排版属性来自引用节点契约（见 lib/embed.ts）；所有文本均经 React 转义渲染，
// 不使用 dangerouslySetInnerHTML，链接一律站内相对路径。

import Link from "next/link";
import CategoryBadge from "@/components/ui/CategoryBadge";
import { UserAvatar } from "@/components/ui/UserAvatar";
import { UserGuildChip } from "@/components/ui/UserGuildChip";
import { EmbedArticleItem, EmbedPostItem, EmbedUserItem } from "@/lib/api";
import { timeAgo } from "@/lib/constants";
import { EmbedResolvedItem, EmbedSpec, hasEmbedField } from "@/lib/embed";

export type QuoteVariant = "card" | "compact";
export type QuoteSize = "sm" | "md" | "lg";
export type QuoteAlign = "left" | "center";

/** 卡片根类：类型 + 版式/尺寸/对齐（对齐仅 card 版式有意义） */
function cardClass(kind: "user" | "post" | "article", variant: QuoteVariant, size: QuoteSize, align: QuoteAlign): string {
  const cls = ["quote-card", `quote-card-${kind}`, `quote-card-${variant}`, `quote-card-${size}`];
  if (align === "center" && variant === "card") cls.push("quote-card-center");
  return cls.join(" ");
}

/** 用户引用卡片：头像（含前缀/VIP 角标）+ 昵称 + VIP/会馆 chip + 简介 */
export function UserQuoteCard({
  user,
  variant = "card",
  size = "md",
  fields = null,
  align = "left",
}: {
  user: EmbedUserItem;
  variant?: QuoteVariant;
  size?: QuoteSize;
  fields?: string | null;
  align?: QuoteAlign;
}) {
  const guild = user.guild;
  const showVip = hasEmbedField(fields, "vip") && !!user.vip && user.vip !== "0";
  const showGuild = hasEmbedField(fields, "guild") && !!guild;
  // 紧凑版式不展示简介（字段开关仍作用于 VIP / 会馆）
  const showIntro = variant === "card" && hasEmbedField(fields, "intro");
  return (
    <Link href={`/users/${encodeURIComponent(user.id)}`} className={cardClass("user", variant, size, align)}>
      <span className="quote-card-avatar">
        <UserAvatar src={user.avatar} alt={user.name} userId={user.id} vip={showVip} />
      </span>
      <span className="quote-card-body">
        <span className="quote-card-name-row">
          <span className="quote-card-name">{user.name}</span>
          {showVip && (
            <span className="quote-card-vip" title="VIP">
              <i className="fa fa-diamond"></i> VIP
            </span>
          )}
          {showGuild && guild && <UserGuildChip name={guild.name} color={guild.theme_color} />}
        </span>
        {showIntro && <span className="quote-card-intro">{user.intro || "这个人很懒，什么都没留下～"}</span>}
      </span>
    </Link>
  );
}

/** 帖子引用卡片：标题 + 作者/分类/会馆/时间 */
export function PostQuoteCard({
  post,
  variant = "card",
  size = "md",
  align = "left",
}: {
  post: EmbedPostItem;
  variant?: QuoteVariant;
  size?: QuoteSize;
  align?: QuoteAlign;
}) {
  return (
    <Link href={`/post/${encodeURIComponent(post.id)}`} className={cardClass("post", variant, size, align)}>
      <span className="quote-card-head">
        <i className="fa fa-file-text-o"></i>
        <span className="quote-card-kind">帖子</span>
      </span>
      <span className="quote-card-title">{post.title || "无标题"}</span>
      <span className="quote-card-meta">
        <span className="quote-card-meta-item">
          <i className="fa fa-user-o"></i> {post.user_name}
        </span>
        <CategoryBadge category={post.category} className="quote-card-category" />
        {post.guild_name && (
          <span className="quote-card-meta-item">
            <i className="fa fa-home"></i> {post.guild_name}
          </span>
        )}
        {variant === "card" && (
          <span className="quote-card-meta-item">
            <i className="fa fa-clock-o"></i> {timeAgo(post.created_at)}
          </span>
        )}
      </span>
    </Link>
  );
}

/** 文章引用卡片：标题 + 作者/会馆/时间 */
export function ArticleQuoteCard({
  article,
  variant = "card",
  size = "md",
  align = "left",
}: {
  article: EmbedArticleItem;
  variant?: QuoteVariant;
  size?: QuoteSize;
  align?: QuoteAlign;
}) {
  return (
    <Link href={`/article/${encodeURIComponent(article.id)}`} className={cardClass("article", variant, size, align)}>
      <span className="quote-card-head">
        <i className="fa fa-book"></i>
        <span className="quote-card-kind">文章</span>
      </span>
      <span className="quote-card-title">{article.title || "无标题"}</span>
      <span className="quote-card-meta">
        {article.author_name && (
          <span className="quote-card-meta-item">
            <i className="fa fa-pencil"></i> {article.author_name}
          </span>
        )}
        {article.guild_name && (
          <span className="quote-card-meta-item">
            <i className="fa fa-home"></i> {article.guild_name}
          </span>
        )}
        {variant === "card" && (
          <span className="quote-card-meta-item">
            <i className="fa fa-clock-o"></i> {timeAgo(article.created_at)}
          </span>
        )}
      </span>
    </Link>
  );
}

/** 加载中骨架 */
export function QuoteCardSkeleton({ variant = "card" }: { variant?: QuoteVariant }) {
  return (
    <div className={`quote-card quote-card-skeleton quote-card-${variant}`} aria-busy="true">
      <span className="quote-card-avatar quote-skeleton-block"></span>
      <span className="quote-card-body">
        <span className="quote-card-skeleton-line quote-skeleton-block"></span>
        <span className="quote-card-skeleton-line quote-card-skeleton-line-short quote-skeleton-block"></span>
      </span>
    </div>
  );
}

/** 内容已删除/不可用占位 */
export function QuoteCardMissing() {
  return (
    <div className="quote-card quote-card-missing">
      <i className="fa fa-chain-broken"></i> 内容已删除或不可用
    </div>
  );
}

/** 按引用节点属性分发到对应卡片；data 为 null（已删除/不可用）时渲染占位 */
export function QuoteCard({ spec, data }: { spec: EmbedSpec; data: EmbedResolvedItem | null }) {
  if (!data) return <QuoteCardMissing />;
  if (data.type === "user" && spec.type === "user") {
    return <UserQuoteCard user={data.user} variant={spec.variant} size={spec.size} fields={spec.fields} align={spec.align} />;
  }
  if (data.type === "post" && spec.type === "post") {
    return <PostQuoteCard post={data.post} variant={spec.variant} size={spec.size} align={spec.align} />;
  }
  if (data.type === "article" && spec.type === "article") {
    return <ArticleQuoteCard article={data.article} variant={spec.variant} size={spec.size} align={spec.align} />;
  }
  return <QuoteCardMissing />;
}

export default QuoteCard;
