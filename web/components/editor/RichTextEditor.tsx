"use client";

// 富文本编辑器（TipTap）：发帖正文用
// - 工具条：加粗/斜体/删除线/H2/H3/无序/有序/引用/链接/图片上传/撤销/重做 + 三种引用卡片
// - 图片选中：宽度条（25/50/75/100% 按编辑区换算 + 自定义 40-2400px + 还原）
// - 引用节点选中：版式/尺寸/字段开关（用户）/对齐；序列化严格按契约（lib/embed.ts）
// - 图片上传：mediaApi.upload → 插入站内相对路径 /api/v1/media/{id}

import { useEffect, useRef, useState } from "react";
import Placeholder from "@tiptap/extension-placeholder";
import Image from "@tiptap/extension-image";
import { EditorContent, useEditor, useEditorState } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { useToast } from "@/components/Toast";
import Modal from "@/components/ui/Modal";
import { ApiException, EmbedKind, mediaApi } from "@/lib/api";
import { USER_EMBED_FIELDS } from "@/lib/embed";
import EmbedNode from "./Embed";
import QuotePickerModal from "./QuotePickerModal";

/** 图片宽度属性归一：仅接受纯正整数（与 RichContent 渲染端一致） */
const ResizableImage = Image.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      width: {
        default: null,
        parseHTML: (element) => {
          const raw = (element.getAttribute("width") ?? "").trim();
          if (!/^\d+$/.test(raw)) return null;
          const n = Number.parseInt(raw, 10);
          return n > 0 ? n : null;
        },
        renderHTML: (attributes) => (attributes.width ? { width: attributes.width } : {}),
      },
    };
  },
});

/** 图片约束（与服务端一致） */
const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
const ALLOWED_IMAGE_TYPES = ["image/png", "image/jpeg", "image/webp", "image/gif"];
/** 自定义宽度范围（px） */
const MIN_IMAGE_WIDTH = 40;
const MAX_IMAGE_WIDTH = 2400;

const EMPTY_TOOLBAR_STATE = {
  bold: false,
  italic: false,
  strike: false,
  h2: false,
  h3: false,
  bulletList: false,
  orderedList: false,
  blockquote: false,
  link: false,
  isImage: false,
  imageWidth: null as number | null,
  isEmbed: false,
  embedType: "",
  embedVariant: "card",
  embedSize: "md",
  embedFields: null as string | null,
  embedAlign: "left",
  canUndo: false,
  canRedo: false,
};

/** 工具条按钮（active 高亮；复用全局 .editor-tool 样式） */
function ToolbarButton({
  title,
  active = false,
  disabled = false,
  onClick,
  children,
}: {
  title: string;
  active?: boolean;
  disabled?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      className={`editor-tool ${active ? "active" : ""}`}
      title={title}
      aria-label={title}
      disabled={disabled}
      onClick={onClick}
    >
      {children}
    </button>
  );
}

/** 富文本编辑器：value/onChange 均为存储态 HTML */
export default function RichTextEditor({
  value,
  onChange,
  placeholder = "在此输入内容…",
}: {
  value: string;
  onChange: (html: string) => void;
  placeholder?: string;
}) {
  const { toast } = useToast();
  const [linkOpen, setLinkOpen] = useState(false);
  const [linkUrl, setLinkUrl] = useState("");
  const [pickerKind, setPickerKind] = useState<EmbedKind | null>(null);
  const [uploading, setUploading] = useState(false);
  // 自定义宽度输入缓冲（null = 直接显示编辑器实际宽度，避免用 effect 同步 state）
  const [widthDraft, setWidthDraft] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  // 记录编辑器最近一次的产出：外部 value 与之相同则不回灌（避免光标跳动）
  const lastValueRef = useRef(value);
  const onChangeRef = useRef(onChange);

  useEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);

  const editor = useEditor({
    // Next.js SSR：首帧不渲染编辑器（避免 hydration 不一致）
    immediatelyRender: false,
    extensions: [
      StarterKit.configure({
        // 与后端白名单对齐：禁用代码/代码块，标题仅 2-3 级
        link: { openOnClick: false, HTMLAttributes: {} },
        code: false,
        codeBlock: false,
        heading: { levels: [2, 3] },
      }),
      ResizableImage,
      EmbedNode,
      Placeholder.configure({ placeholder }),
    ],
    content: value,
    editorProps: { attributes: { class: "rich-editor-body" } },
    onUpdate: ({ editor: ed }) => {
      const html = ed.getHTML();
      lastValueRef.current = html;
      onChangeRef.current(html);
    },
  });

  // 外部 value 变化（如重置表单）时同步内容；自身编辑引发的变化不回灌
  useEffect(() => {
    if (!editor) return;
    if (value === lastValueRef.current) return;
    lastValueRef.current = value;
    editor.commands.setContent(value || "", { emitUpdate: false });
  }, [editor, value]);

  const st =
    useEditorState({
      editor,
      selector: ({ editor: ed }) =>
        ed
          ? {
              bold: ed.isActive("bold"),
              italic: ed.isActive("italic"),
              strike: ed.isActive("strike"),
              h2: ed.isActive("heading", { level: 2 }),
              h3: ed.isActive("heading", { level: 3 }),
              bulletList: ed.isActive("bulletList"),
              orderedList: ed.isActive("orderedList"),
              blockquote: ed.isActive("blockquote"),
              link: ed.isActive("link"),
              isImage: ed.isActive("image"),
              imageWidth: (ed.getAttributes("image").width as number | null | undefined) ?? null,
              isEmbed: ed.isActive("embed"),
              embedType: (ed.getAttributes("embed").embedType as string | undefined) || "",
              embedVariant: (ed.getAttributes("embed").variant as string | undefined) || "card",
              embedSize: (ed.getAttributes("embed").size as string | undefined) || "md",
              embedFields: (ed.getAttributes("embed").fields as string | null | undefined) ?? null,
              embedAlign: (ed.getAttributes("embed").align as string | undefined) || "left",
              canUndo: ed.can().undo(),
              canRedo: ed.can().redo(),
            }
          : EMPTY_TOOLBAR_STATE,
    }) ?? EMPTY_TOOLBAR_STATE;

  // 自定义宽度输入框显示值：输入中显示缓冲值，否则显示编辑器实际宽度
  const widthInputValue = widthDraft ?? (st.imageWidth !== null ? String(st.imageWidth) : "");

  /** 图片当前实时宽度（读编辑器实时值，避免 state 时序问题） */
  const currentImageWidth = (): number | null =>
    (editor?.getAttributes("image").width as number | null | undefined) ?? null;

  const setImageWidth = (width: number | null) => {
    editor?.chain().focus().updateAttributes("image", { width }).run();
  };

  /** 解析并提交宽度（40-2400 整数；非法或与当前一致时不提交） */
  const commitImageWidth = (raw: string | number) => {
    const n = Math.round(Number(raw));
    if (!Number.isFinite(n) || n < MIN_IMAGE_WIDTH) return;
    const clamped = Math.min(n, MAX_IMAGE_WIDTH);
    if (clamped !== currentImageWidth()) setImageWidth(clamped);
  };

  /** 百分比按编辑区宽度换算为 px */
  const applyImagePercent = (pct: number) => {
    const base = editor?.view.dom.clientWidth || 720;
    setImageWidth(Math.max(MIN_IMAGE_WIDTH, Math.round((base * pct) / 100)));
  };

  const openLinkModal = () => {
    setLinkUrl((editor?.getAttributes("link").href as string | undefined) ?? "");
    setLinkOpen(true);
  };

  const applyLink = () => {
    if (!editor) return;
    const url = linkUrl.trim();
    if (url) editor.chain().focus().extendMarkRange("link").setLink({ href: url }).run();
    else editor.chain().focus().extendMarkRange("link").unsetLink().run();
    setLinkOpen(false);
  };

  /** 引用字段开关：全选回退为缺省（不输出 data-fields），全不选写出空串 */
  const toggleEmbedField = (key: string) => {
    if (!editor) return;
    const all = USER_EMBED_FIELDS.map((f) => f.key);
    const active = st.embedFields === null ? [...all] : st.embedFields.split(",").map((s) => s.trim());
    const next = active.includes(key) ? active.filter((k) => k !== key) : [...active, key];
    const kept = all.filter((k) => next.includes(k));
    const fields = kept.length === all.length ? null : kept.join(",");
    editor.chain().focus().updateAttributes("embed", { fields }).run();
  };

  const pickFile = () => fileRef.current?.click();

  const onFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file || !editor) return;
    if (!ALLOWED_IMAGE_TYPES.includes(file.type)) {
      toast("仅支持 PNG/JPG/WebP/GIF 图片", "error");
      return;
    }
    if (file.size > MAX_IMAGE_BYTES) {
      toast("图片大小不能超过 5MB", "error");
      return;
    }
    setUploading(true);
    try {
      const r = await mediaApi.upload(file);
      // 站内相对路径（论坛站直通）
      editor.chain().focus().setImage({ src: r.url || `/api/v1/media/${r.id}` }).run();
    } catch (err) {
      toast(err instanceof ApiException ? err.message : "图片上传失败", "error");
    } finally {
      setUploading(false);
    }
  };

  /** 插入引用节点（属性缺省：card / md / 全字段 / 左对齐） */
  const insertEmbed = (kind: EmbedKind, id: string) => {
    editor?.chain().focus().insertContent({ type: "embed", attrs: { embedType: kind, embedId: id } }).run();
    setPickerKind(null);
  };

  return (
    <div className="rich-editor">
      {editor && (
        <div className="form-editor-toolbar rich-editor-toolbar">
          <ToolbarButton title="加粗" active={st.bold} onClick={() => editor.chain().focus().toggleBold().run()}>
            <i className="fa fa-bold"></i>
          </ToolbarButton>
          <ToolbarButton title="斜体" active={st.italic} onClick={() => editor.chain().focus().toggleItalic().run()}>
            <i className="fa fa-italic"></i>
          </ToolbarButton>
          <ToolbarButton title="删除线" active={st.strike} onClick={() => editor.chain().focus().toggleStrike().run()}>
            <i className="fa fa-strikethrough"></i>
          </ToolbarButton>
          <span className="editor-sep"></span>
          <ToolbarButton title="二级标题" active={st.h2} onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}>
            <span className="editor-tool-text">H2</span>
          </ToolbarButton>
          <ToolbarButton title="三级标题" active={st.h3} onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}>
            <span className="editor-tool-text">H3</span>
          </ToolbarButton>
          <ToolbarButton title="无序列表" active={st.bulletList} onClick={() => editor.chain().focus().toggleBulletList().run()}>
            <i className="fa fa-list-ul"></i>
          </ToolbarButton>
          <ToolbarButton title="有序列表" active={st.orderedList} onClick={() => editor.chain().focus().toggleOrderedList().run()}>
            <i className="fa fa-list-ol"></i>
          </ToolbarButton>
          <ToolbarButton title="引用段落" active={st.blockquote} onClick={() => editor.chain().focus().toggleBlockquote().run()}>
            <i className="fa fa-quote-left"></i>
          </ToolbarButton>
          <span className="editor-sep"></span>
          <ToolbarButton title="插入链接" active={st.link} onClick={openLinkModal}>
            <i className="fa fa-link"></i>
          </ToolbarButton>
          <ToolbarButton title="插入图片" disabled={uploading} onClick={pickFile}>
            <i className={uploading ? "fa fa-spinner fa-spin" : "fa fa-picture-o"}></i>
          </ToolbarButton>
          <span className="editor-sep"></span>
          <ToolbarButton title="撤销" disabled={!st.canUndo} onClick={() => editor.chain().focus().undo().run()}>
            <i className="fa fa-undo"></i>
          </ToolbarButton>
          <ToolbarButton title="重做" disabled={!st.canRedo} onClick={() => editor.chain().focus().redo().run()}>
            <i className="fa fa-repeat"></i>
          </ToolbarButton>
          <span className="editor-sep"></span>
          <ToolbarButton title="引用用户" onClick={() => setPickerKind("user")}>
            <i className="fa fa-user-o"></i>
            <span className="editor-tool-text">引用</span>
          </ToolbarButton>
          <ToolbarButton title="引用帖子" onClick={() => setPickerKind("post")}>
            <i className="fa fa-file-text-o"></i>
            <span className="editor-tool-text">引用</span>
          </ToolbarButton>
          <ToolbarButton title="引用文章" onClick={() => setPickerKind("article")}>
            <i className="fa fa-book"></i>
            <span className="editor-tool-text">引用</span>
          </ToolbarButton>
        </div>
      )}

      {/* 图片宽度条（选中图片时） */}
      {editor && st.isImage && (
        <div className="rich-editor-option-bar">
          <span className="rich-editor-option-label">图片宽度</span>
          {[25, 50, 75, 100].map((pct) => (
            <button
              key={pct}
              type="button"
              className="rich-editor-option-btn"
              onClick={() => {
                setWidthDraft(null);
                applyImagePercent(pct);
              }}
            >
              {pct}%
            </button>
          ))}
          <span className="rich-editor-option-label">自定义</span>
          <input
            type="number"
            className="rich-editor-number"
            min={MIN_IMAGE_WIDTH}
            max={MAX_IMAGE_WIDTH}
            step={20}
            placeholder="原始"
            value={widthInputValue}
            onChange={(e) => {
              const raw = e.target.value;
              setWidthDraft(raw);
              // 输入即提交：>=40 的合法值直接生效（"3/36" 等中间态自然被跳过，失焦亦会兜底提交）
              if (raw !== "") commitImageWidth(raw);
            }}
            onBlur={(e) => {
              const raw = e.target.value.trim();
              if (raw !== "") commitImageWidth(raw);
              setWidthDraft(null);
            }}
          />
          <span className="rich-editor-option-label">px</span>
          <button
            type="button"
            className="rich-editor-option-btn"
            onClick={() => {
              setWidthDraft(null);
              setImageWidth(null);
            }}
          >
            还原
          </button>
        </div>
      )}

      {/* 引用样式条（选中引用节点时） */}
      {editor && st.isEmbed && (
        <div className="rich-editor-option-bar">
          <span className="rich-editor-option-label">版式</span>
          <button
            type="button"
            className={`rich-editor-option-btn ${st.embedVariant === "card" ? "active" : ""}`}
            onClick={() => editor.chain().focus().updateAttributes("embed", { variant: "card" }).run()}
          >
            完整
          </button>
          <button
            type="button"
            className={`rich-editor-option-btn ${st.embedVariant === "compact" ? "active" : ""}`}
            onClick={() => editor.chain().focus().updateAttributes("embed", { variant: "compact" }).run()}
          >
            紧凑
          </button>
          <span className="rich-editor-option-label">尺寸</span>
          {([
            { key: "sm", label: "小" },
            { key: "md", label: "中" },
            { key: "lg", label: "大" },
          ] as const).map((s) => (
            <button
              key={s.key}
              type="button"
              className={`rich-editor-option-btn ${st.embedSize === s.key ? "active" : ""}`}
              onClick={() => editor.chain().focus().updateAttributes("embed", { size: s.key }).run()}
            >
              {s.label}
            </button>
          ))}
          {st.embedType === "user" && (
            <>
              <span className="rich-editor-option-label">字段</span>
              {USER_EMBED_FIELDS.map((f) => {
                const on =
                  st.embedFields === null ||
                  st.embedFields.split(",").map((x) => x.trim()).includes(f.key);
                return (
                  <button
                    key={f.key}
                    type="button"
                    className={`rich-editor-option-btn ${on ? "active" : ""}`}
                    onClick={() => toggleEmbedField(f.key)}
                  >
                    {f.label}
                  </button>
                );
              })}
            </>
          )}
          <span className="rich-editor-option-label">对齐</span>
          <button
            type="button"
            className={`rich-editor-option-btn ${st.embedAlign === "left" ? "active" : ""}`}
            onClick={() => editor.chain().focus().updateAttributes("embed", { align: "left" }).run()}
          >
            左
          </button>
          <button
            type="button"
            className={`rich-editor-option-btn ${st.embedAlign === "center" ? "active" : ""}`}
            onClick={() => editor.chain().focus().updateAttributes("embed", { align: "center" }).run()}
          >
            中
          </button>
        </div>
      )}

      <EditorContent editor={editor} className="rich-editor-content" />
      <p className="form-editor-tips rich-editor-tips">
        支持标题、列表、引用、链接、图片与引用卡片；点击图片可调整宽度，图片与引用会随正文一并保存。
      </p>

      <input
        ref={fileRef}
        type="file"
        accept="image/png,image/jpeg,image/webp,image/gif"
        style={{ display: "none" }}
        onChange={onFileChange}
      />

      {/* 链接 URL 输入（留空移除） */}
      {linkOpen && (
        <Modal open onClose={() => setLinkOpen(false)} cardStyle={{ maxWidth: 420 }}>
          <h3 className="donate-title">
            <i className="fa fa-link"></i> 插入链接
          </h3>
          <input
            className="form-input"
            type="text"
            value={linkUrl}
            placeholder="https://example.com（留空并应用可移除链接）"
            autoFocus
            onChange={(e) => setLinkUrl(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                applyLink();
              }
            }}
          />
          <div className="report-actions">
            <button className="report-cancel" onClick={() => setLinkOpen(false)}>
              取消
            </button>
            <button className="report-submit" onClick={applyLink}>
              应用
            </button>
          </div>
        </Modal>
      )}

      {pickerKind && (
        <QuotePickerModal kind={pickerKind} onClose={() => setPickerKind(null)} onPick={insertEmbed} />
      )}
    </div>
  );
}
