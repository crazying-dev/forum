package legacy

import (
	"fmt"
	"net/url"
	"strings"

	"golang.org/x/net/html"
	"golang.org/x/net/html/atom"
)

// HTMLToMarkdown 将富文本 HTML 保守转换为 Markdown。
//
// 约束（与 routes-contract 一致）：
//   - 过滤 div[data-embed]（新引用节点，旧客户端无法渲染）；
//   - 未知/危险标签丢弃，只保留其文本；文本节点中的 < > 转义，避免 raw HTML 注入；
//   - 链接/图片仅允许 http/https 与相对地址，javascript:/data:/vbscript: 等一律丢弃；
//   - 解析失败时整段按纯文本转义，绝不原样透传 HTML。
func HTMLToMarkdown(input string) string {
	input = strings.TrimSpace(input)
	if input == "" {
		return ""
	}
	doc, err := html.Parse(strings.NewReader(input))
	if err != nil {
		return escapeText(input)
	}
	var b strings.Builder
	renderNode(&b, doc)
	out := cleanupMarkdown(b.String())
	if out == "" {
		// 形如 <div data-embed=...></div> 的纯引用节点转换后为空，属于预期。
		return ""
	}
	return out
}

// renderNode 递归渲染节点。块级元素负责补齐空行，内联元素只输出标记。
func renderNode(b *strings.Builder, n *html.Node) {
	switch n.Type {
	case html.DocumentNode:
		renderChildren(b, n)
	case html.TextNode:
		b.WriteString(normalizeInlineText(n.Data))
	case html.ElementNode:
		renderElement(b, n)
	}
}

func renderChildren(b *strings.Builder, n *html.Node) {
	for child := n.FirstChild; child != nil; child = child.NextSibling {
		renderNode(b, child)
	}
}

func renderElement(b *strings.Builder, n *html.Node) {
	// 新引用节点整体丢弃（含子节点），旧 APP 无法识别。
	if n.DataAtom == atom.Div && hasAttr(n, "data-embed") {
		return
	}
	switch n.DataAtom {
	case atom.Script, atom.Style, atom.Iframe, atom.Object, atom.Embed, atom.Form,
		atom.Input, atom.Button, atom.Textarea, atom.Select, atom.Option, atom.Noscript,
		atom.Svg, atom.Math, atom.Video, atom.Audio, atom.Canvas, atom.Map:
		return
	case atom.P:
		block(b, func() { renderChildren(b, n) })
	case atom.Br:
		b.WriteString("\\\n")
	case atom.Hr:
		b.WriteString("\n\n---\n\n")
	case atom.H1, atom.H2, atom.H3, atom.H4, atom.H5, atom.H6:
		level := int(n.Data[1] - '0')
		b.WriteString("\n\n" + strings.Repeat("#", level) + " ")
		b.WriteString(normalizeInlineText(textContent(n)))
		b.WriteString("\n\n")
	case atom.Strong, atom.B:
		wrapInline(b, "**", n)
	case atom.Em, atom.I:
		wrapInline(b, "*", n)
	case atom.S, atom.Strike, atom.Del:
		wrapInline(b, "~~", n)
	case atom.Code:
		if n.Parent != nil && n.Parent.DataAtom == atom.Pre {
			b.WriteString(textContent(n))
			return
		}
		code := textContent(n)
		b.WriteString("`" + strings.ReplaceAll(code, "`", "\\`") + "`")
	case atom.Pre:
		code := strings.TrimRight(textContent(n), "\n")
		fence := "```"
		if strings.Contains(code, "```") {
			fence = "~~~"
		}
		b.WriteString("\n\n" + fence + "\n" + code + "\n" + fence + "\n\n")
	case atom.Blockquote:
		var inner strings.Builder
		renderChildren(&inner, n)
		text := strings.TrimSpace(cleanupMarkdown(inner.String()))
		if text == "" {
			return
		}
		lines := strings.Split(text, "\n")
		b.WriteString("\n\n")
		for _, line := range lines {
			b.WriteString("> " + strings.TrimRight(line, " ") + "\n")
		}
		b.WriteString("\n")
	case atom.Ul:
		renderList(b, n, false)
	case atom.Ol:
		renderList(b, n, true)
	case atom.Li:
		// 不在列表上下文中的孤立 li：按普通段落输出。
		block(b, func() { renderChildren(b, n) })
	case atom.A:
		renderLink(b, n)
	case atom.Img:
		renderImage(b, n)
	case atom.Div, atom.Section, atom.Article, atom.Header, atom.Footer, atom.Main, atom.Aside,
		atom.Figure, atom.Figcaption, atom.Table, atom.Thead, atom.Tbody, atom.Tfoot, atom.Tr, atom.Td, atom.Th,
		atom.Dl, atom.Dt, atom.Dd:
		block(b, func() { renderChildren(b, n) })
	default:
		// 未知标签：丢弃标签本身，保留可读文本，绝不输出 raw HTML。
		renderChildren(b, n)
	}
}

func block(b *strings.Builder, fn func()) {
	b.WriteString("\n\n")
	fn()
	b.WriteString("\n\n")
}

func wrapInline(b *strings.Builder, marker string, n *html.Node) {
	var inner strings.Builder
	renderChildren(&inner, n)
	text := normalizeWhitespace(inner.String())
	if text == "" {
		return
	}
	b.WriteString(marker + text + marker)
}

func renderLink(b *strings.Builder, n *html.Node) {
	href, ok := safeURL(attr(n, "href"), true)
	var inner strings.Builder
	renderChildren(&inner, n)
	text := strings.TrimSpace(normalizeWhitespace(inner.String()))
	if !ok || text == "" {
		b.WriteString(text)
		return
	}
	text = strings.ReplaceAll(text, "]", "\\]")
	b.WriteString("[" + text + "](" + escapeURL(href) + ")")
}

func renderImage(b *strings.Builder, n *html.Node) {
	src, ok := safeURL(attr(n, "src"), true)
	if !ok || src == "" {
		return
	}
	alt := normalizeInlineText(attr(n, "alt"))
	alt = strings.ReplaceAll(alt, "]", "\\]")
	b.WriteString("![" + alt + "](" + escapeURL(src) + ")")
}

func renderList(b *strings.Builder, n *html.Node, ordered bool) {
	b.WriteString("\n\n")
	index := 1
	for child := n.FirstChild; child != nil; child = child.NextSibling {
		if child.Type != html.ElementNode || child.DataAtom != atom.Li {
			continue
		}
		var inner strings.Builder
		renderChildren(&inner, child)
		text := strings.TrimSpace(cleanupMarkdown(inner.String()))
		marker := "- "
		if ordered {
			marker = fmt.Sprintf("%d. ", index)
			index++
		}
		if text == "" {
			continue
		}
		lines := strings.Split(text, "\n")
		b.WriteString(marker + strings.TrimRight(lines[0], " ") + "\n")
		for _, line := range lines[1:] {
			if strings.TrimSpace(line) == "" {
				continue
			}
			b.WriteString("  " + strings.TrimRight(line, " ") + "\n")
		}
	}
	b.WriteString("\n")
}

// safeURL 校验链接/图片地址：http、https 与相对地址放行；其余 scheme 一律拒绝。
func safeURL(raw string, allowRelative bool) (string, bool) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return "", false
	}
	u, err := url.Parse(raw)
	if err != nil {
		return "", false
	}
	scheme := strings.ToLower(u.Scheme)
	if scheme == "" {
		// 排除协议相对地址 //evil.com（旧 APP 可能被劫持到外站）。
		if !allowRelative || strings.HasPrefix(raw, "//") {
			return "", false
		}
		return raw, true
	}
	if scheme == "http" || scheme == "https" {
		return raw, true
	}
	return "", false
}

func escapeURL(raw string) string {
	raw = strings.ReplaceAll(raw, " ", "%20")
	raw = strings.ReplaceAll(raw, "(", "%28")
	raw = strings.ReplaceAll(raw, ")", "%29")
	return raw
}

// escapeText 保守转义文本中的 HTML 元字符。
func escapeText(s string) string {
	s = strings.ReplaceAll(s, "&", "&amp;")
	s = strings.ReplaceAll(s, "<", "&lt;")
	s = strings.ReplaceAll(s, ">", "&gt;")
	return s
}

// normalizeInlineText 压平内联空白并转义 HTML 元字符（用于原始文本/属性值）。
func normalizeInlineText(s string) string {
	out := normalizeWhitespace(s)
	if out == " " {
		return out
	}
	return escapeText(out)
}

// normalizeWhitespace 仅压平空白；输入已经是渲染后的 Markdown/已转义文本时使用，避免二次转义。
func normalizeWhitespace(s string) string {
	if s == "" {
		return ""
	}
	leading := strings.HasPrefix(s, " ") || strings.HasPrefix(s, "\n") || strings.HasPrefix(s, "\t")
	trailing := strings.HasSuffix(s, " ") || strings.HasSuffix(s, "\n") || strings.HasSuffix(s, "\t")
	fields := strings.Fields(s)
	if len(fields) == 0 {
		return " "
	}
	out := strings.Join(fields, " ")
	if leading {
		out = " " + out
	}
	if trailing {
		out += " "
	}
	return out
}

func textContent(n *html.Node) string {
	var b strings.Builder
	var walk func(*html.Node)
	walk = func(node *html.Node) {
		if node.Type == html.TextNode {
			b.WriteString(node.Data)
		}
		for child := node.FirstChild; child != nil; child = child.NextSibling {
			walk(child)
		}
	}
	walk(n)
	return b.String()
}

func attr(n *html.Node, key string) string {
	for _, a := range n.Attr {
		if strings.EqualFold(a.Key, key) {
			return a.Val
		}
	}
	return ""
}

func hasAttr(n *html.Node, key string) bool {
	return attr(n, key) != ""
}

func cleanupMarkdown(s string) string {
	s = strings.ReplaceAll(s, "\r\n", "\n")
	s = strings.ReplaceAll(s, "\r", "\n")
	lines := strings.Split(s, "\n")
	out := make([]string, 0, len(lines))
	blank := 0
	for _, line := range lines {
		line = strings.TrimRight(line, " \t")
		if strings.TrimSpace(line) == "" {
			blank++
			if blank > 1 {
				continue
			}
			out = append(out, "")
			continue
		}
		blank = 0
		out = append(out, line)
	}
	return strings.TrimSpace(strings.Join(out, "\n"))
}
