"use client";

import { useEffect, useRef, useState } from "react";
import RichContent from "@/components/ui/RichContent";
import { ListEmpty, ListLoading } from "@/components/ui/ListState";
import { guideApi, GuideNodeDetail, GuideNodeItem } from "@/lib/api";
import { formatTime } from "@/lib/constants";

interface TreeNode {
  node: GuideNodeItem;
  children: TreeNode[];
}

/** 列表（已按 sort,id 升序）组装为多叉树；parent 缺失的节点作为根 */
function buildTree(nodes: GuideNodeItem[]): TreeNode[] {
  const map = new Map<string, TreeNode>();
  for (const n of nodes) map.set(n.id, { node: n, children: [] });
  const roots: TreeNode[] = [];
  for (const n of nodes) {
    const item = map.get(n.id)!;
    const parent = n.parent_id ? map.get(n.parent_id) : undefined;
    if (parent) parent.children.push(item);
    else roots.push(item);
  }
  return roots;
}

/** 论坛指南：左侧多层目录树（folder 展开/收起、doc 选中高亮），右侧 RichContent 正文 */
export default function GuidePage() {
  const [nodes, setNodes] = useState<GuideNodeItem[]>([]);
  const [treeLoading, setTreeLoading] = useState(true);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [activeId, setActiveId] = useState<string | null>(null);
  const [doc, setDoc] = useState<GuideNodeDetail | null>(null);
  const [docLoading, setDocLoading] = useState(false);
  const [mobileTreeOpen, setMobileTreeOpen] = useState(false);
  // 请求序号：快速切换文档时丢弃过期响应
  const docSeqRef = useRef(0);

  const openDoc = async (id: string) => {
    setMobileTreeOpen(false);
    if (activeId === id && doc && !docLoading) return;
    const seq = ++docSeqRef.current;
    setActiveId(id);
    setDocLoading(true);
    try {
      const r = await guideApi.getDoc(id);
      if (seq !== docSeqRef.current) return;
      setDoc(r.data.node);
    } catch {
      if (seq !== docSeqRef.current) return;
      setDoc(null);
    } finally {
      if (seq === docSeqRef.current) setDocLoading(false);
    }
  };

  useEffect(() => {
    let alive = true;
    guideApi
      .getTree()
      .then((r) => {
        if (!alive) return;
        const list = r.data.nodes || [];
        setNodes(list);
        // 默认展开全部目录，方便一眼看到层级
        setExpanded(new Set(list.filter((n) => n.kind === "folder").map((n) => n.id)));
        // 默认选中第一篇文档（无文档时展示空态）
        const firstDoc = list.find((n) => n.kind === "doc");
        if (firstDoc) openDoc(firstDoc.id);
      })
      .catch(() => {
        if (alive) setNodes([]);
      })
      .finally(() => {
        if (alive) setTreeLoading(false);
      });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggleFolder = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const renderTree = (list: TreeNode[], depth: number) => (
    <ul className="guide-tree">
      {list.map((t) => {
        const isFolder = t.node.kind === "folder";
        const isOpen = expanded.has(t.node.id);
        return (
          <li key={t.node.id} className="guide-tree-item">
            {isFolder ? (
              <button
                type="button"
                className="guide-tree-folder"
                style={{ paddingLeft: 10 + depth * 16 }}
                onClick={() => toggleFolder(t.node.id)}
                aria-expanded={isOpen}
              >
                <i className={`fa ${isOpen ? "fa-caret-down" : "fa-caret-right"} guide-tree-caret`}></i>
                <i className="fa fa-folder-o guide-tree-icon"></i>
                <span className="guide-tree-text">{t.node.title}</span>
              </button>
            ) : (
              <button
                type="button"
                className={`guide-tree-doc ${activeId === t.node.id ? "active" : ""}`}
                style={{ paddingLeft: 10 + depth * 16 + 18 }}
                onClick={() => openDoc(t.node.id)}
              >
                <i className="fa fa-file-text-o guide-tree-icon"></i>
                <span className="guide-tree-text">{t.node.title}</span>
              </button>
            )}
            {t.children.length > 0 && (isFolder ? isOpen : true) && renderTree(t.children, depth + 1)}
          </li>
        );
      })}
    </ul>
  );

  return (
    <div className="forum-container guide-page">
      <div className="forum-header">
        <h1 className="forum-title">论坛指南</h1>
        <p className="forum-subtitle">使用说明与玩法介绍</p>
      </div>

      <div className="guide-layout">
        {/* 窄屏：目录折叠开关（桌面隐藏） */}
        <button
          type="button"
          className="guide-tree-toggle"
          onClick={() => setMobileTreeOpen(!mobileTreeOpen)}
          aria-expanded={mobileTreeOpen}
        >
          <i className={`fa ${mobileTreeOpen ? "fa-folder-open-o" : "fa-folder-o"}`}></i>
          {mobileTreeOpen ? "收起目录" : "展开目录"}
        </button>

        {/* 移动端右侧抽屉遮罩：点击关闭目录 */}
        <div
          className={`guide-drawer-overlay ${mobileTreeOpen ? "open" : ""}`}
          onClick={() => setMobileTreeOpen(false)}
          aria-hidden="true"
        ></div>

        <aside className={`guide-sidebar ${mobileTreeOpen ? "open" : ""}`} aria-label="指南目录">
          {treeLoading ? (
            <ListLoading />
          ) : nodes.length === 0 ? (
            <ListEmpty text="暂无指南内容" />
          ) : (
            renderTree(buildTree(nodes), 0)
          )}
        </aside>

        <main className="guide-content">
          {docLoading ? (
            <ListLoading />
          ) : !doc ? (
            <ListEmpty text="请从左侧目录选择一篇指南" />
          ) : (
            <article className="guide-doc">
              <h2 className="guide-doc-title">{doc.title}</h2>
              {doc.updated_at && <div className="guide-doc-meta">更新于 {formatTime(doc.updated_at)}</div>}
              <RichContent content={doc.content} className="guide-doc-body" />
            </article>
          )}
        </main>
      </div>
    </div>
  );
}
