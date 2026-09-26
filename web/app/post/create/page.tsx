"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Markdown from "@/components/Markdown";
import BackButton from "@/components/ui/BackButton";
import { postApi, userApi, guildApi, ApiException, GuildMembership } from "@/lib/api";
import { POST_CATEGORIES, themeColor, themeTint } from "@/lib/constants";

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

/** 发帖页：发布到（公共空间 / 我的会馆）+ 分类联动 + 桌面左右排版 */
export default function PostCreatePage() {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [pubCat, setPubCat] = useState(POST_CATEGORIES[0].key);
  const [guildCat, setGuildCat] = useState("");
  const [guildCats, setGuildCats] = useState<string[]>([]);
  const [target, setTarget] = useState<"public" | "guild">("public");
  const [guild, setGuild] = useState<GuildMembership | null>(null);
  const [tab, setTab] = useState<"edit" | "preview">("edit");
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
        setTarget("guild");
        const d = await guildApi.detail(r.guild.slug);
        const names = (d.guild.categories || []).map((c) => c.name);
        setGuildCats(names);
        setGuildCat(names[0] || "");
      } catch {
        /* 未登录或接口异常：仅公共空间 */
      }
    })();
  }, []);

  const category = target === "guild" ? guildCat : pubCat;
  const chips = target === "guild" ? guildCats : POST_CATEGORIES.map((c) => c.key);
  const theme = themeColor(guild?.theme_color);

  const submit = async () => {
    if (!title.trim()) return setErr("请输入标题");
    if (!content.trim()) return setErr("请输入内容");
    setBusy(true);
    setErr("");
    try {
      const r = await postApi.create(title.trim(), content, category, target === "guild" && guild ? guild.id : undefined);
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
                  style={target === "guild" ? { background: theme, borderColor: theme } : undefined}
                  onClick={() => setTarget("guild")}
                >
                  <i className="fa fa-home"></i> 我的会馆（{guild.name}）
                </button>
              )}
            </div>
            {target === "guild" && guild && (
              <p className="post-target-hint" style={{ color: theme }}>
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
                      style={active && target === "guild" ? { background: theme } : undefined}
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
            <div className="form-html-warning">
              <i className="fa fa-markdown"></i> 支持 Markdown 语法，HTML 标签会被自动转义
            </div>
            <div className="form-editor-tabs">
              <button className={`editor-tab ${tab === "edit" ? "active" : ""}`} id="tab-edit" onClick={() => setTab("edit")}>
                编辑
              </button>
              <button className={`editor-tab ${tab === "preview" ? "active" : ""}`} id="tab-preview" onClick={() => setTab("preview")}>
                预览
              </button>
            </div>
            <div className={`post-editor-split ${tab === "edit" ? "show-edit" : "show-preview"}`}>
              <textarea
                className="form-editor"
                id="post-content-editor"
                placeholder="在此输入 Markdown 内容..."
                value={content}
                onChange={(e) => setContent(e.target.value)}
              />
              <div className="form-preview post-editor-preview" id="post-content-preview">
                <Markdown content={content} className="markdown-body" />
              </div>
            </div>
          </div>

          {err && <p style={{ color: "#ef4444", margin: "12px 0 0" }}>{err}</p>}

          <div className="form-actions">
            <button className="btn-cancel" onClick={() => router.back()}>取消</button>
            <button className="btn-submit" id="post-submit-btn" disabled={busy} onClick={submit} style={target === "guild" ? { background: theme } : undefined}>
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
