// Package sanitize 富文本净化：发帖 / 会馆介绍页 / 文章正文共用同一白名单。
// 引用节点存储形态（冻结契约，admin 侧同步实现）：
//
//	<div data-embed="user|post|article" data-id="{1-64位[A-Za-z0-9_-]}"
//	     [data-variant="card|compact"] [data-size="sm|md|lg"]
//	     [data-fields="intro,guild 逗号子集，空串=全不显示，缺省=全显示"]
//	     [data-align="left|center"]></div>
package sanitize

import (
	"regexp"
	"strings"

	"github.com/microcosm-cc/bluemonday"
)

// 引用节点属性值正则（冻结契约）。
var (
	reEmbedType    = regexp.MustCompile(`^(user|post|article)$`)
	reEmbedID      = regexp.MustCompile(`^[A-Za-z0-9_-]{1,64}$`)
	reEmbedVariant = regexp.MustCompile(`^(card|compact)$`)
	reEmbedSize    = regexp.MustCompile(`^(sm|md|lg)$`)
	reEmbedFields  = regexp.MustCompile(`^[a-z,]{0,64}$`)
	reEmbedAlign   = regexp.MustCompile(`^(left|center)$`)
)

// policy 富文本白名单：仅保留格式标签、链接、图片与引用节点。
var policy = newPolicy()

func newPolicy() *bluemonday.Policy {
	p := bluemonday.NewPolicy()
	p.AllowElements("p", "br", "hr", "h1", "h2", "h3", "h4",
		"strong", "b", "em", "i", "u", "s", "strike",
		"ul", "ol", "li", "blockquote", "figure", "figcaption",
		"pre", "code",
		"a", "img", "div")
	p.AllowAttrs("href").OnElements("a")
	// 图片宽度/高度由管理端编辑器写入（整数），此处不做值约束
	p.AllowAttrs("src", "alt", "width", "height").OnElements("img")
	// 引用节点：属性缺省=全显示；非法值直接剔除属性，节点本身保留
	p.AllowAttrs("data-embed").Matching(reEmbedType).OnElements("div")
	p.AllowAttrs("data-id").Matching(reEmbedID).OnElements("div")
	p.AllowAttrs("data-variant").Matching(reEmbedVariant).OnElements("div")
	p.AllowAttrs("data-size").Matching(reEmbedSize).OnElements("div")
	p.AllowAttrs("data-fields").Matching(reEmbedFields).OnElements("div")
	p.AllowAttrs("data-align").Matching(reEmbedAlign).OnElements("div")
	p.AllowRelativeURLs(true)
	p.AllowURLSchemes("http", "https")
	return p
}

// SanitizeRichContent 净化富文本 HTML；空串直返。
func SanitizeRichContent(html string) string {
	if html == "" {
		return ""
	}
	return policy.Sanitize(html)
}

// reTags 简单 HTML 标签匹配（仅用于正文空值粗筛，非完整解析，不得用于净化输出）。
var reTags = regexp.MustCompile(`<[^>]*>`)

// StripTagsAndTrim 去除 HTML 标签并 TrimSpace；用于发帖正文「净化后是否为空」检测
// （纯标签/纯空白内容视为空，如 <p></p>、<p><br></p>）。
func StripTagsAndTrim(html string) string {
	return strings.TrimSpace(reTags.ReplaceAllString(html, ""))
}
