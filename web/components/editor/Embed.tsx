"use client";

// 引用节点（TipTap 自定义 block 节点）
// 存储契约见 lib/embed.ts：缺省属性不输出（variant=card / size=md / align=left），
// data-fields 缺省=全显示、空串=全不显示。

import {
  mergeAttributes,
  Node,
  NodeViewProps,
  NodeViewWrapper,
  ReactNodeViewRenderer,
} from "@tiptap/react";
import { QuoteCard, QuoteCardMissing, QuoteCardSkeleton } from "@/components/quote/QuoteCards";
import { EmbedKind } from "@/lib/api";
import { normalizeEmbed, useEmbed } from "@/lib/embed";

/** 节点属性 → 契约值归一（与 lib/embed.ts 保持一致） */
function attrValue(value: unknown, allowed: readonly string[], fallback: string): string {
  const v = typeof value === "string" ? value : "";
  return allowed.includes(v) ? v : fallback;
}

/** 编辑器内引用节点预览：加载中骨架 / 已删除占位 / 引用卡片 */
function EmbedNodeView({ node, selected, deleteNode }: NodeViewProps) {
  const spec = normalizeEmbed({
    type: node.attrs.embedType as string,
    id: node.attrs.embedId as string,
    variant: attrValue(node.attrs.variant, ["card", "compact"], "card"),
    size: attrValue(node.attrs.size, ["sm", "md", "lg"], "md"),
    fields: typeof node.attrs.fields === "string" ? (node.attrs.fields as string) : undefined,
    align: attrValue(node.attrs.align, ["left", "center"], "left"),
  });
  const { loading, data } = useEmbed(spec?.type, spec?.id);

  return (
    <NodeViewWrapper
      className={`embed-node ${selected ? "embed-node-selected" : ""}`}
      data-embed-node={spec?.type || ""}
      contentEditable={false}
    >
      {!spec ? (
        <QuoteCardMissing />
      ) : loading ? (
        <QuoteCardSkeleton variant={spec.variant} />
      ) : (
        <QuoteCard spec={spec} data={data} />
      )}
      {selected && (
        <button type="button" className="embed-node-remove" title="删除引用" onClick={() => deleteNode()}>
          <i className="fa fa-trash-o"></i>
        </button>
      )}
    </NodeViewWrapper>
  );
}

/** 引用节点（用户/帖子/文章）：原子块节点，序列化为契约 div */
export const EmbedNode = Node.create({
  name: "embed",
  group: "block",
  atom: true,
  draggable: true,
  selectable: true,

  addAttributes() {
    return {
      embedType: {
        default: "user" as EmbedKind,
        parseHTML: (element) => element.getAttribute("data-embed"),
        renderHTML: (attributes) => ({ "data-embed": attributes.embedType }),
      },
      embedId: {
        default: "",
        parseHTML: (element) => element.getAttribute("data-id") || "",
        renderHTML: (attributes) => ({ "data-id": attributes.embedId }),
      },
      variant: {
        default: "card",
        parseHTML: (element) => (element.getAttribute("data-variant") === "compact" ? "compact" : "card"),
        renderHTML: (attributes) => (attributes.variant === "compact" ? { "data-variant": "compact" } : {}),
      },
      size: {
        default: "md",
        parseHTML: (element) => {
          const raw = element.getAttribute("data-size");
          return raw === "sm" || raw === "lg" ? raw : "md";
        },
        renderHTML: (attributes) =>
          attributes.size === "sm" || attributes.size === "lg" ? { "data-size": attributes.size } : {},
      },
      // null = 属性缺省（全显示）；"" = 全不显示；"intro,vip" = 子集
      fields: {
        default: null,
        parseHTML: (element) => (element.hasAttribute("data-fields") ? element.getAttribute("data-fields") || "" : null),
        renderHTML: (attributes) => (typeof attributes.fields === "string" ? { "data-fields": attributes.fields } : {}),
      },
      align: {
        default: "left",
        parseHTML: (element) => (element.getAttribute("data-align") === "center" ? "center" : "left"),
        renderHTML: (attributes) => (attributes.align === "center" ? { "data-align": "center" } : {}),
      },
    };
  },

  parseHTML() {
    return [{ tag: "div[data-embed]" }];
  },

  renderHTML({ HTMLAttributes }) {
    return ["div", mergeAttributes(HTMLAttributes)];
  },

  addNodeView() {
    return ReactNodeViewRenderer(EmbedNodeView);
  },
});

export default EmbedNode;
