"use client";

// 评论富文本编辑器（TipTap 3.31.3）：
// - 工具条：加粗/斜体/删除线、链接、图片上传（scene=comment_image）、emoji 面板、引用用户/帖子/文章
// - Ctrl/Cmd+Enter 提交；纯文本 1-500 字（纯图片 / 纯引用卡片视为有效）
// - 紧凑尺寸（.comment-editor-*），评论以 HTML 存储（服务端统一净化）

import { useEffect, useImperativeHandle, useRef, useState } from "react";
import Image from "@tiptap/extension-image";
import Placeholder from "@tiptap/extension-placeholder";
import { EditorContent, useEditor, useEditorState } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { useToast } from "@/components/Toast";
import Modal from "@/components/ui/Modal";
import { ApiException, EmbedKind, mediaApi } from "@/lib/api";
import EmbedNode from "./Embed";
import QuotePickerModal from "./QuotePickerModal";

// emoji 面板（由原评论输入框迁入编辑器，分类与内容保持 1:1）
const EMOJI_CATEGORIES: { name: string; icon: string; emojis: string[] }[] = [
  {
    name: "表情",
    icon: "😀",
    emojis: ["😀", "😁", "😂", "🤣", "😊", "😍", "🥰", "😘", "😎", "🤔", "😅", "😉", "🙃", "😭", "😢", "😡", "🤬", "😤", "😳", "🥺", "😴", "🤯", "😇", "🙄"],
  },
  {
    name: "手势",
    icon: "👍",
    emojis: ["👍", "👎", "👏", "🙏", "💪", "🤝", "✌️", "🤞", "👌", "👊", "🖐️", "🙌", "🤙", "👋", "💅", "🫶"],
  },
  {
    name: "爱心",
    icon: "❤️",
    emojis: ["❤️", "💔", "💕", "💖", "💘", "💝", "💯", "✨", "🔥", "⭐", "🌟", "💫", "⚡", "💥", "💤", "💦"],
  },
  {
    name: "食物",
    icon: "🍕",
    emojis: ["🍎", "🍌", "🍉", "🍇", "🍓", "🍔", "🍕", "🍟", "🌭", "🍜", "🍣", "🍰", "🍦", "☕", "🍺", "🥤"],
  },
  {
    name: "动物",
    icon: "🐱",
    emojis: ["🐱", "🐶", "🐼", "🐰", "🦊", "🐸", "🐷", "🐵", "🐯", "🦁", "🐦", "🐧", "🌹", "🌸", "🌵", "🌈"],
  },
  {
    name: "活动",
    icon: "🎉",
    emojis: ["🎉", "🎊", "🎈", "🎁", "🏆", "🚀", "🎮", "🎯", "🎨", "🎤", "🎧", "⚽", "🏀", "🏸", "🎳", "🎲"],
  },
];

/** 图片约束（与服务端一致） */
const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
const ALLOWED_IMAGE_TYPES = ["image/png", "image/jpeg", "image/webp", "image/gif"];
/** 纯文本上限（与服务端 1-500 一致） */
const MAX_COMMENT_CHARS = 500;

/** 富文本 → 纯文本（去标签 + &nbsp; 归一 + trim；码点计数与 Go rune 对齐） */
function plainTextOf(html: string): string {
  return html.replace(/<[^>]*>/g, "").replace(/&nbsp;/g, " ").trim();
}
/** 是否含图片/引用卡片（此时纯文本可以为 0） */
function hasRichMedia(html: string): boolean {
  return /<img\b/i.test(html) || /data-embed=/i.test(html);
}

/** 行内格式 active 态初始值（useEditorState 首帧） */
const EMPTY_TOOLBAR_STATE = { bold: false, italic: false, strike: false, link: false };

/** 暴露给父级的句柄：聚焦编辑器（「评论数」按钮跳转输入框用） */
export interface CommentEditorHandle {
  focus: () => void;
}

/** 评论富文本编辑器（value/onChange 均为存储态 HTML） */
export default function CommentEditor({
  value,
  onChange,
  onSubmit,
  placeholder = "写下你的评论…",
  editorRef,
  submitting = false,
}: {
  value: string;
  onChange: (html: string) => void;
  onSubmit: () => void;
  placeholder?: string;
  editorRef?: React.RefObject<CommentEditorHandle | null>;
  /** 提交中：禁用发送按钮，防双击重复 */
  submitting?: boolean;
}) {
  const { toast } = useToast();
  const [showEmoji, setShowEmoji] = useState(false);
  const [emojiCat, setEmojiCat] = useState(0);
  const [linkOpen, setLinkOpen] = useState(false);
  const [linkUrl, setLinkUrl] = useState("");
  const [pickerKind, setPickerKind] = useState<EmbedKind | null>(null);
  const [uploading, setUploading] = useState(false);
  const [plainLen, setPlainLen] = useState(() => plainTextOf(value).length);
  const fileRef = useRef<HTMLInputElement>(null);
  const emojiWrapRef = useRef<HTMLDivElement>(null);
  // 记录编辑器最近一次的产出：外部 value 与之相同则不回灌（避免光标跳动）
  const lastValueRef = useRef(value);
  const onChangeRef = useRef(onChange);
  const onSubmitRef = useRef(onSubmit);

  useEffect(() => {
    onChangeRef.current = onChange;
    onSubmitRef.current = onSubmit;
  }, [onChange, onSubmit]);

  const editor = useEditor({
    // Next.js SSR：首帧不渲染编辑器（避免 hydration 不一致）
    immediatelyRender: false,
    extensions: [
      StarterKit.configure({
        // 评论只需行内格式与链接：禁用标题/列表/引用段落/代码等块级能力
        heading: false,
        bulletList: false,
        orderedList: false,
        blockquote: false,
        code: false,
        codeBlock: false,
        horizontalRule: false,
        link: { openOnClick: false, HTMLAttributes: {} },
      }),
      Image,
      EmbedNode,
      Placeholder.configure({ placeholder }),
    ],
    content: value,
    editorProps: {
      attributes: { class: "comment-editor-body" },
      handleKeyDown: (_view, event) => {
        // Ctrl/Cmd+Enter 提交（普通 Enter 仍为换行）
        if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
          event.preventDefault();
          onSubmitRef.current();
          return true;
        }
        return false;
      },
    },
    onUpdate: ({ editor: ed }) => {
      const html = ed.getHTML();
      lastValueRef.current = html;
      onChangeRef.current(html);
      setPlainLen(plainTextOf(html).length);
    },
  });

  // 外部 value 变化（发送成功后清空等）时同步内容；自身编辑引发的变化不回灌
  useEffect(() => {
    if (!editor) return;
    if (value === lastValueRef.current) return;
    lastValueRef.current = value;
    editor.commands.setContent(value || "", { emitUpdate: false });
    setPlainLen(plainTextOf(value || "").length);
  }, [editor, value]);

  // 行内格式 active 态（useEditorState 保证选区变化时重渲染）
  const st =
    useEditorState({
      editor,
      selector: ({ editor: ed }) =>
        ed
          ? {
              bold: ed.isActive("bold"),
              italic: ed.isActive("italic"),
              strike: ed.isActive("strike"),
              link: ed.isActive("link"),
            }
          : EMPTY_TOOLBAR_STATE,
    }) ?? EMPTY_TOOLBAR_STATE;

  // 父级 ref → 编辑器 focus 句柄
  useImperativeHandle(editorRef, () => ({ focus: () => editor?.chain().focus().run() }), [editor]);

  // 点击外部关闭 emoji 面板
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (emojiWrapRef.current && !emojiWrapRef.current.contains(e.target as Node)) {
        setShowEmoji(false);
      }
    };
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, []);

  const insertEmoji = (emoji: string) => {
    editor?.chain().focus().insertContent(emoji).run();
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
      const r = await mediaApi.upload(file, "comment_image");
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

  /** 提交前校验：纯文本 ≤500 且（≥1 字 或 含图片/引用卡），与服务端口径一致 */
  const trySubmit = () => {
    if (submitting) return; // 提交中忽略重复点击
    const html = editor?.getHTML() ?? value;
    const text = plainTextOf(html);
    const len = Array.from(text).length;
    if (len > MAX_COMMENT_CHARS) {
      toast(`评论内容最多 ${MAX_COMMENT_CHARS} 字`, "warning");
      return;
    }
    if (len === 0 && !hasRichMedia(html)) {
      toast("请先输入内容", "warning");
      return;
    }
    onSubmitRef.current();
  };

  return (
    <div className="comment-editor">
      {editor && (
        <div className="comment-editor-toolbar">
          <button
            type="button"
            className={`editor-tool ${st.bold ? "active" : ""}`}
            title="加粗"
            onClick={() => editor.chain().focus().toggleBold().run()}
          >
            <i className="fa fa-bold"></i>
          </button>
          <button
            type="button"
            className={`editor-tool ${st.italic ? "active" : ""}`}
            title="斜体"
            onClick={() => editor.chain().focus().toggleItalic().run()}
          >
            <i className="fa fa-italic"></i>
          </button>
          <button
            type="button"
            className={`editor-tool ${st.strike ? "active" : ""}`}
            title="删除线"
            onClick={() => editor.chain().focus().toggleStrike().run()}
          >
            <i className="fa fa-strikethrough"></i>
          </button>
          <button type="button" className={`editor-tool ${st.link ? "active" : ""}`} title="插入链接" onClick={openLinkModal}>
            <i className="fa fa-link"></i>
          </button>
          <button type="button" className="editor-tool" title="插入图片" disabled={uploading} onClick={pickFile}>
            <i className={uploading ? "fa fa-spinner fa-spin" : "fa fa-picture-o"}></i>
          </button>
          <div className="comment-emoji-wrap" ref={emojiWrapRef}>
            <button
              type="button"
              className={`editor-tool ${showEmoji ? "active" : ""}`}
              title="表情"
              onClick={() => setShowEmoji((v) => !v)}
            >
              <i className="fa fa-smile-o"></i>
            </button>
            {showEmoji && (
              <div className="comment-emoji-panel">
                <div className="comment-emoji-grid">
                  {EMOJI_CATEGORIES[emojiCat].emojis.map((e) => (
                    <button type="button" className="comment-emoji-item" key={e} onClick={() => insertEmoji(e)}>
                      {e}
                    </button>
                  ))}
                </div>
                <div className="comment-emoji-tabs">
                  {EMOJI_CATEGORIES.map((c, i) => (
                    <button
                      type="button"
                      className={`comment-emoji-tab ${i === emojiCat ? "active" : ""}`}
                      key={c.name}
                      onClick={() => setEmojiCat(i)}
                      title={c.name}
                    >
                      <span className="comment-emoji-tab-icon">{c.icon}</span>
                      <span className="comment-emoji-tab-label">{c.name}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
          <span className="editor-sep"></span>
          <button type="button" className="editor-tool comment-editor-quote" title="引用用户" onClick={() => setPickerKind("user")}>
            <i className="fa fa-user-o"></i>
            <span className="editor-tool-text">引用</span>
          </button>
          <button type="button" className="editor-tool comment-editor-quote" title="引用帖子" onClick={() => setPickerKind("post")}>
            <i className="fa fa-file-text-o"></i>
            <span className="editor-tool-text">引用</span>
          </button>
          <button type="button" className="editor-tool comment-editor-quote" title="引用文章" onClick={() => setPickerKind("article")}>
            <i className="fa fa-book"></i>
            <span className="editor-tool-text">引用</span>
          </button>
          <span className="comment-editor-count">
            <span className={plainLen > MAX_COMMENT_CHARS ? "over" : ""}>{plainLen}</span>/{MAX_COMMENT_CHARS}
          </span>
        </div>
      )}

      <EditorContent editor={editor} className="comment-editor-content" />

      <div className="comment-editor-actions">
        <span className="comment-editor-hint">Ctrl/⌘+Enter 发送</span>
        <button className="comment-send-btn" onClick={trySubmit} disabled={uploading || submitting}>
          {submitting ? "发送中..." : "发送"}
        </button>
      </div>

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

      {pickerKind && <QuotePickerModal kind={pickerKind} onClose={() => setPickerKind(null)} onPick={insertEmbed} />}
    </div>
  );
}
