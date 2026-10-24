"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState, useCallback, useRef } from "react";
import { useToast } from "@/components/Toast";
import Modal from "@/components/ui/Modal";
import Markdown from "@/components/Markdown";
import RichContent from "@/components/ui/RichContent";
import CommentSection from "@/components/CommentSection";
import type { CommentEditorHandle } from "@/components/editor/CommentEditor";
import { UserAvatar, UserName } from "@/components/ui/UserAvatar";
import { UserGuildChip } from "@/components/ui/UserGuildChip";
import CategoryBadge from "@/components/ui/CategoryBadge";
import SpaceBadge from "@/components/ui/SpaceBadge";
import BackButton from "@/components/ui/BackButton";
import { postApi, Comment, ApiException } from "@/lib/api";
import { useStore } from "@/lib/store";
import { formatTime } from "@/lib/constants";

/** 定时发布时间展示（YYYY-MM-DD HH:mm，本地时区） */
function fmtDateTime(v?: string) {
  const d = new Date(v || "");
  if (!v || isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** published_at 在未来即定时未发布（未发布帖仅作者可见，故仅作者会看到该标记） */
function isScheduled(v?: string) {
  return !!v && new Date(v).getTime() > Date.now();
}

export default function PostDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { userId, user } = useStore();
  const { toast } = useToast();
  const [post, setPost] = useState<any | null>(null);
  const [comments, setComments] = useState<Comment[]>([]);
  const [liked, setLiked] = useState(false);
  const [favorited, setFavorited] = useState(false);
  const [commentText, setCommentText] = useState("");
  const [replyTo, setReplyTo] = useState<{ id: string; name: string } | null>(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);
  const [showReport, setShowReport] = useState(false);
  const [submittingComment, setSubmittingComment] = useState(false);
  const commentEditorRef = useRef<CommentEditorHandle>(null);

  const load = useCallback(async () => {
    try {
      const r = await postApi.detail(id);
      setPost(r.post);
      setComments(r.comments || []);
      setLiked(r.liked);
      setFavorited(r.favorited);
    } catch (e) {
      setErr(e instanceof ApiException ? e.message : "帖子不存在");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  // 从个人中心评论卡片跳转：滚动定位到目标评论并高亮
  useEffect(() => {
    if (comments.length === 0) return;
    const m = window.location.hash.match(/^#comment-(.+)/);
    if (!m) return;
    const timer = setTimeout(() => {
      const el = document.querySelector(`[data-comment-id="${CSS.escape(m[1])}"]`);
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
        el.classList.add("comment-highlight");
        setTimeout(() => el.classList.remove("comment-highlight"), 2500);
      }
    }, 100);
    return () => clearTimeout(timer);
  }, [comments]);

  const doLike = async () => {
    if (!userId) return router.push("/auth");
    try {
      const r = await postApi.like(id);
      setLiked(r.liked);
      setPost((p: any) => (p ? { ...p, likes: r.likes } : p));
    } catch (e: any) {
      toast(e.message, "error");
    }
  };

  const doLikeComment = async (c: Comment) => {
    if (!userId) return router.push("/auth");
    try {
      const r = await postApi.likeComment(c.id);
      setComments((prev) => prev.map((x) => (x.id === c.id ? { ...x, likes: r.likes, liked_by_me: r.liked } : x)));
    } catch (e: any) {
      toast(e instanceof ApiException ? e.message : "操作失败，请稍后再试", "error");
    }
  };

  const doFavorite = async () => {
    if (!userId) return router.push("/auth");
    try {
      const r = await postApi.favorite(id);
      setFavorited(r.favorited);
    } catch (e: any) {
      toast(e.message, "error");
    }
  };

  const submitComment = async (altcha?: string) => {
    if (!userId) return router.push("/auth");
    if (submittingComment) return; // 提交中：忽略重复点击/快捷键，防重复发送
    const content = commentText.trim();
    if (!content) {
      toast("请先输入内容", "warning");
      return;
    }
    setSubmittingComment(true);
    try {
      // 评论存 HTML（content_format=html）；回复仅与直接对象建立 parent_id 关联
      const r = await postApi.createComment(id, content, replyTo?.id, "html", altcha);
      setComments((prev) => [...prev, r.comment]);
      setCommentText("");
      setReplyTo(null);
      toast(replyTo ? "回复发送成功" : "评论发送成功", "success");
    } catch (e: any) {
      toast(e instanceof ApiException ? e.message : "发送失败，请稍后再试", "error");
    } finally {
      setSubmittingComment(false);
    }
  };

  const deleteComment = async (cid: string) => {
    if (!window.confirm("确定删除这条评论吗？")) return;
    try {
      await postApi.deleteComment(cid);
      // 删除后重拉：服务端归并/提升口径（父级缺失等）以最新数据为准
      await load();
    } catch (e: any) {
      toast(e.message, "error");
    }
  };

  const deletePost = async () => {
    if (!window.confirm("确定删除这篇帖子吗？")) return;
    try {
      await postApi.remove(id);
      router.push("/forum");
    } catch (e: any) {
      toast(e.message, "error");
    }
  };

  if (loading) return <div className="post-loading" style={{ padding: 40 }}>加载中...</div>;
  if (!post) return <div className="post-error" style={{ padding: 40 }}>{err || "帖子不存在"}</div>;

  const mainCount = comments.filter((c) => !c.parent_id).length;

  const sharePost = async () => {
    const url = window.location.href;
    try {
      if (navigator.share) {
        await navigator.share({ title: post.title, url });
      } else {
        await navigator.clipboard.writeText(url);
        toast("链接已复制", "success");
      }
    } catch {
      /* 用户取消分享 */
    }
  };

  return (
    <>
      <div className="post-detail-container">
        <div className="post-detail-header">
          <BackButton />
        </div>

        <article className="post-content">
          <div className="post-meta-top">
            <CategoryBadge category={post.category} className="post-category-badge" />
            <SpaceBadge name={post.guild_name} color={post.guild_theme_color} />
            {isScheduled(post.published_at) && (
              <span className="post-scheduled-tag-wrap">
                <span className="post-scheduled-tag" title="尚未到达发布时间，仅自己可见">
                  <i className="fa fa-clock-o"></i> 定时发布 {fmtDateTime(post.published_at)}
                </span>
              </span>
            )}
          </div>
          <h1 className="post-title">{post.title}</h1>

          <div className="post-author-row">
            <Link href={`/users/${post.user_id}`} className="post-author-avatar">
              <UserAvatar src={post.user_avatar} userId={post.user_id} />
            </Link>
            <div className="post-author-info">
              <div className="post-author-name-row">
                <Link href={`/users/${post.user_id}`} className="post-author-name Username">
                  <UserName name={post.user_name} />
                </Link>
                <UserGuildChip name={post.user_guild_name} color={post.user_guild_theme_color} isLeader={post.user_is_leader} />
              </div>
              <div className="post-author-meta">
                <span>{formatTime(post.created_at)}</span>
                <span>·</span>
                <span><i className="fa fa-eye"></i> {post.views || 0}</span>
              </div>
            </div>
          </div>

          {post.content_format === "html" ? (
            <RichContent content={post.content} className="post-body-html" />
          ) : (
            <div className="post-body-html">
              <Markdown content={post.content} />
            </div>
          )}

          <div className="post-actions">
            <button className={`post-action-btn ${liked ? "liked" : ""}`} id="post-like-btn" onClick={doLike}>
              <i className="fa fa-thumbs-up"></i>
              <span id="post-like-count">{post.likes || 0}</span>
            </button>
            <button className={`post-action-btn ${favorited ? "favorited" : ""}`} id="post-favorite-btn" onClick={doFavorite}>
              <i className="fa fa-bookmark"></i>
              <span className="post-action-label">收藏</span>
            </button>
            <button className="post-action-btn" onClick={() => commentEditorRef.current?.focus()}>
              <i className="fa fa-comment"></i>
              <span>{mainCount}</span>
            </button>
            <button className="post-action-btn" onClick={sharePost}>
              <i className="fa fa-share-alt"></i>
              <span className="post-action-label">分享</span>
            </button>
            {(!userId || post.user_id !== userId) && (
              <button className="post-action-btn" onClick={() => setShowReport(true)}>
                <i className="fa fa-flag"></i>
                <span className="post-action-label">举报</span>
              </button>
            )}
            {userId && post.user_id === userId && (
              <button className="post-action-btn post-delete-btn" onClick={deletePost}>
                <i className="fa fa-trash-o"></i>
                <span className="post-action-label">删除</span>
              </button>
            )}
          </div>
        </article>

        <div className="comment-section">
          <CommentSection
            comments={comments}
            userId={userId}
            editorRef={commentEditorRef}
            replyText={commentText}
            replyTo={replyTo}
            setReplyTo={setReplyTo}
            onChangeReplyText={setCommentText}
            onSubmit={submitComment}
            submitting={submittingComment}
            canWrite={!!user}
            onDelete={deleteComment}
            onLike={doLikeComment}
          />
        </div>
      </div>
      {showReport && <ReportPostDialog postId={id} onClose={() => setShowReport(false)} />}
    </>
  );
}

/** 举报帖子弹窗（还原 legacy showReportDialog：单选原因 + 补充说明 + 取消/提交） */
function ReportPostDialog({ postId, onClose }: { postId: string; onClose: () => void }) {
  const { toast } = useToast();
  const [reason, setReason] = useState("spam");
  const [detail, setDetail] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const reasons = [
    { value: "spam", label: "垃圾广告" },
    { value: "abuse", label: "辱骂攻击" },
    { value: "porn", label: "色情低俗" },
    { value: "illegal", label: "违法违规" },
    { value: "infringement", label: "侵权抄袭" },
    { value: "other", label: "其他" },
  ];

  const submit = async () => {
    if (submitting) return;
    if (!reason) {
      toast("请选择举报原因", "warning");
      return;
    }
    setSubmitting(true);
    try {
      await postApi.report(postId, reason, detail.trim());
      toast("举报成功，感谢反馈！", "success");
      onClose();
    } catch (e: any) {
      toast(e instanceof ApiException ? e.message : "举报失败", "error");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal open onClose={onClose} cardStyle={{ maxWidth: 480 }}>
      <h3 className="donate-title"><i className="fa fa-flag"></i> 举报帖子</h3>
      <div className="report-reason-list">
        {reasons.map((r) => (
          <label className="report-reason-item" key={r.value}>
            <input type="radio" name="report-reason" value={r.value} checked={reason === r.value} onChange={() => setReason(r.value)} />
            {r.label}
          </label>
        ))}
      </div>
      <textarea
        className="report-detail-input textarea"
        id="report-detail"
        placeholder="补充说明（可选，最多500字）"
        maxLength={500}
        rows={4}
        value={detail}
        onChange={(e) => setDetail(e.target.value)}
      />
      <div className="report-actions">
        <button className="report-cancel" onClick={onClose}>取消</button>
        <button className="report-submit" disabled={submitting} onClick={submit}>
          {submitting ? "提交中..." : "提交举报"}
        </button>
      </div>
    </Modal>
  );
}
