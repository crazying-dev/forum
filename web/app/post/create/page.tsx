"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import GlobalLoading from "@/components/GlobalLoading";
import RichTextEditor from "@/components/editor/RichTextEditor";
import { useToast } from "@/components/Toast";
import BackButton from "@/components/ui/BackButton";
import { postApi, userApi, guildApi, ApiException, GuildMembership } from "@/lib/api";
import { POST_CATEGORIES, contrastText, themeColor, themeInk, themeTint } from "@/lib/constants";

const COMPLIANCE = [
  "遵守中华人民共和国相关法律法规，不得发布违法违规内容",
  "禁止涉及政治敏感、涉黄涉暴、血腥恐怖、毒品赌博等内容",
  "禁止人身攻击、谩骂侮辱、恶意引战、网络暴力等行为",
  "禁止发布广告、 spam、外链刷量、引流等垃圾信息",
  "禁止泄露他人或自己的隐私信息（真实姓名、电话、地址等）",
  "禁止侵犯他人知识产权，转载请注明出处或获得授权",
  "内容应与论坛主题（罗小黑战记及二次元文化）相关，鼓励友善交流",
  "违反以上规定的帖子将被删除，情节严重者将封禁账号",
];

/** 富文本是否为空（无文本且无图片/引用节点）：编辑器空文档序列化为 <p></p> */
function hasRichContent(html: string): boolean {
  const text = html.replace(/<[^>]*>/g, "").replace(/&nbsp;/g, " ").trim();
  return !!text || /<img\b/i.test(html) || /data-embed=/i.test(html);
}

/**
 * 发帖页（useSearchParams 需在 Suspense 内，遵循 Next.js App Router 规范）：
 * 发布到（公共空间 / 我的会馆）+ 分类联动 + 富文本编辑器（TipTap，提交 HTML）；支持 ?guild=slug 预选会馆。
 */
export default function PostCreatePage() {
  return (
    <Suspense
      fallback={
        <div className="route-loading">
          <GlobalLoading />
        </div>
      }
    >
      <PostCreateForm />
    </Suspense>
  );
}

function PostCreateForm() {
  const router = useRouter();
  const params = useSearchParams();
  const { toast } = useToast();
  // ?guild=slug：由会馆页「发帖」入口传入，与用户所属会馆匹配时预选该会馆
  const guildSlug = params.get("guild") || "";
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [pubCat, setPubCat] = useState(POST_CATEGORIES[0].key);
  const [guildCat, setGuildCat] = useState("");
  const [guildCats, setGuildCats] = useState<string[]>([]);
  const [target, setTarget] = useState<"public" | "guild">("public");
  const [guild, setGuild] = useState<GuildMembership | null>(null);
  const [noticeOpen, setNoticeOpen] = useState(false);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  // 已加入会馆则默认发布到会馆；未加入（未登录）仅公共空间
  useEffect(() => {
    (async () => {
      try {
        const r = await userApi.me();
        if (!r.guild) return;
        setGuild(r.guild);
        const d = await guildApi.detail(r.guild.slug);
        const names = (d.guild.categories || []).map((c) => c.name);
        setGuildCats(names);
        setGuildCat(names[0] || "");
        // 未指定会馆：沿用「已加入则默认发到会馆」；指定了非本人所属会馆：退回公共空间
        if (!guildSlug || guildSlug === r.guild.slug) setTarget("guild");
        else setTarget("public");
      } catch {
        /* 未登录或接口异常：仅公共空间 */
      }
    })();
  }, [guildSlug]);

  const category = target === "guild" ? guildCat : pubCat;
  const chips = target === "guild" ? guildCats : POST_CATEGORIES.map((c) => c.key);
  const theme = themeColor(guild?.theme_color);
  const themeFg = contrastText(theme);
  const inkStyle = { "--guild-ink": themeInk(theme) } as React.CSSProperties;

  const submit = async () => {
    if (!title.trim()) return setErr("请输入标题");
    // 编辑器空文档序列化为 <p></p>，故按「无文本且无图片/引用节点」判空
    if (!hasRichContent(content)) return setErr("请输入内容");
    // 目标为会馆时必须携带会馆 uuid：缺失说明会馆数据异常，明确报错阻断，
    // 避免静默降级成发布到公共空间
    if (target === "guild" && !guild?.uuid) {
      toast("会馆标识缺失，请刷新重试", "error");
      return;
    }
    setBusy(true);
    setErr("");
    try {
      const r = await postApi.create(title.trim(), content, category, target === "guild" && guild ? guild.uuid : undefined);
      router.push(`/post/${r.id}`);
    } catch (e) {
      setErr(e instanceof ApiException ? e.message : "发布失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="post-create-container">
        <div className="post-create-header">
          <BackButton className="post-create-back" />
          <h1 className="post-create-title">发布新帖子</h1>
          <div style={{ width: 60 }}></div>
        </div>

        <div className="post-create-form">
          {/* 发布到 */}
          <div className="form-group">
            <label className="form-label">发布到</label>
            <div className="post-target-segmented">
              <button
                className={`post-target-btn ${target === "public" ? "active" : ""}`}
                style={target === "public" ? { background: "var(--color-primary)" } : undefined}
                onClick={() => setTarget("public")}
              >
                <i className="fa fa-globe"></i> 公共空间
              </button>
              {guild && (
                <button
                  className={`post-target-btn ${target === "guild" ? "active" : ""}`}
                  style={
                    target === "guild"
                      ? ({ background: theme, borderColor: theme, "--guild-btn-fg": themeFg } as React.CSSProperties)
                      : undefined
                  }
                  onClick={() => setTarget("guild")}
                >
                  <i className="fa fa-home"></i> 我的会馆（{guild.name}）
                </button>
              )}
            </div>
            {target === "guild" && guild && (
              <p className="post-target-hint theme-ink" style={inkStyle}>
                <i className="fa fa-info-circle"></i> 帖子将发布到会馆「{guild.name}」，所有访客可见
              </p>
            )}
          </div>

          {/* 分类（会馆无自定义分类时隐藏） */}
          {chips.length > 0 && (
            <div className="form-group">
              <label className="form-label">帖子分类</label>
              <div className="form-category-select" id="form-category-select">
                {chips.map((key) => {
                  const label = target === "guild" ? key : POST_CATEGORIES.find((c) => c.key === key)?.label || key;
                  const active = category === key;
                  return (
                    <button
                      key={key}
                      className={`category-chip ${active ? "active" : ""}`}
                      data-value={key}
                      style={active && target === "guild" ? { background: theme, color: themeFg } : undefined}
                      onClick={() => (target === "guild" ? setGuildCat(key) : setPubCat(key))}
                    >
                      {label}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          <div className="form-group">
            <label className="form-label">帖子标题</label>
            <input
              type="text"
              className="form-input"
              id="post-title-input"
              placeholder="请输入标题..."
              maxLength={100}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </div>

          <div className="form-group">
            <label className="form-label">帖子内容</label>
            <RichTextEditor value={content} onChange={setContent} placeholder="在此输入正文…" />
          </div>

          {err && <p style={{ color: "#ef4444", margin: "12px 0 0" }}>{err}</p>}

          <div className="form-actions">
            <button className="btn-cancel" onClick={() => router.back()}>取消</button>
            <button
              className="btn-submit"
              id="post-submit-btn"
              disabled={busy}
              onClick={submit}
              style={target === "guild" ? { background: theme, color: themeFg } : undefined}
            >
              <i className="fa fa-paper-plane"></i> {busy ? "发布中..." : "发布"}
            </button>
          </div>

          {/* 发帖须知（默认收起） */}
          <div className={`post-compliance-collapse ${noticeOpen ? "open" : ""}`} style={noticeOpen ? { background: themeTint(theme, "14") } : undefined}>
            <button type="button" className="post-compliance-toggle" onClick={() => setNoticeOpen(!noticeOpen)} aria-expanded={noticeOpen}>
              <i className="fa fa-shield"></i>
              <span>发帖须知</span>
              <i className={`fa ${noticeOpen ? "fa-chevron-up" : "fa-chevron-down"} post-compliance-arrow`}></i>
            </button>
            {noticeOpen && (
              <ul className="post-compliance-list">
                {COMPLIANCE.map((li, i) => (
                  <li key={i}>{li}</li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
