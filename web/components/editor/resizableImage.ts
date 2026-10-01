// 可调宽度图片（发帖正文 / 评论编辑器共用）
// - 宽度以 width 属性存储（parseHTML/renderHTML），与服务端白名单一致
// - imageWidthPlugin：视图层 Decoration 内联 style，仅作用于编辑视图，不写入 getHTML()/序列化
// - 常量：自定义宽度范围（px，40-2400，与 RichContent 渲染端上限一致）

import Image from "@tiptap/extension-image";
import { Plugin } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";

/**
 * 图片宽度视图层同步（Decoration）：遍历文档为带 width 的图片节点挂内联 style。
 * - 仅编辑视图装饰，不写入 getHTML()/序列化，存储仍为 width 属性
 * - 装饰随每次 transaction 由节点属性重算，更新/还原即时生效
 */
export function imageWidthPlugin(): Plugin {
  return new Plugin({
    props: {
      decorations(state) {
        const decos: Decoration[] = [];
        state.doc.descendants((node, pos) => {
          if (node.type.name !== "image") return;
          const width = node.attrs.width;
          if (typeof width === "number" && width > 0) {
            decos.push(Decoration.node(pos, pos + node.nodeSize, { style: `width: ${width}px;` }));
          }
        });
        return DecorationSet.create(state.doc, decos);
      },
    },
  });
}

/** 图片宽度属性归一：仅接受纯正整数（与 RichContent 渲染端一致） */
export const ResizableImage = Image.extend({
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
  addProseMirrorPlugins() {
    return [...(this.parent?.() ?? []), imageWidthPlugin()];
  },
});

/** 自定义宽度范围（px） */
export const MIN_IMAGE_WIDTH = 40;
export const MAX_IMAGE_WIDTH = 2400;
