package sanitize

import (
	"strings"
	"testing"
)

// 合法引用节点与格式标签应完整保留。
func TestSanitizeRichContentKeepsValidEmbed(t *testing.T) {
	in := `<p>看这里</p>` +
		`<div data-embed="post" data-id="PS123_abc-XYZ" data-variant="card" data-size="md" data-fields="intro,guild" data-align="center"></div>`
	out := SanitizeRichContent(in)
	for _, want := range []string{
		"<p>看这里</p>",
		`data-embed="post"`,
		`data-id="PS123_abc-XYZ"`,
		`data-variant="card"`,
		`data-size="md"`,
		`data-fields="intro,guild"`,
		`data-align="center"`,
	} {
		if !strings.Contains(out, want) {
			t.Errorf("合法内容应保留 %q，实际输出：%s", want, out)
		}
	}
}

// 最简合法形态：仅 data-embed + data-id（其余属性缺省）应保留。
func TestSanitizeRichContentKeepsMinimalEmbed(t *testing.T) {
	out := SanitizeRichContent(`<div data-embed="user" data-id="u1"></div>`)
	if !strings.Contains(out, `data-embed="user"`) || !strings.Contains(out, `data-id="u1"`) {
		t.Errorf("最简引用节点应保留，实际输出：%s", out)
	}
}

// 非法属性值应被剔除（节点本身保留，值不出现）。
func TestSanitizeRichContentDropsInvalidEmbedAttrs(t *testing.T) {
	in := `<div data-embed="user" data-id="bad id!" data-variant="huge" data-size="xl" data-fields="Intro,VIP" data-align="justify"></div>` +
		`<div data-embed="unknown" data-id="u1"></div>`
	out := SanitizeRichContent(in)
	for _, bad := range []string{"bad id!", `data-variant="huge"`, `data-size="xl"`, `data-fields="Intro,VIP"`, `data-align="justify"`, `data-embed="unknown"`} {
		if strings.Contains(out, bad) {
			t.Errorf("非法属性应剔除，实际输出：%s", out)
		}
	}
}

// 超长 data-id（>64）应被剔除。
func TestSanitizeRichContentDropsLongEmbedID(t *testing.T) {
	longID := strings.Repeat("a", 65)
	out := SanitizeRichContent(`<div data-embed="post" data-id="` + longID + `"></div>`)
	if strings.Contains(out, longID) {
		t.Errorf("超长 data-id 应剔除，实际输出：%s", out)
	}
}

// script / 事件属性 / style 应被剔除。
func TestSanitizeRichContentStripsXSS(t *testing.T) {
	in := `<p onclick="alert(1)">x</p><script>alert(2)</script><style>p{color:red}</style>` +
		`<img src="/api/v1/media/MD1" onerror="alert(3)" style="color:red">` +
		`<a href="javascript:alert(4)">y</a><iframe src="https://evil.example"></iframe>`
	out := SanitizeRichContent(in)
	for _, bad := range []string{"script", "onclick", "onerror", "alert(", "style=", "javascript:", "iframe"} {
		if strings.Contains(out, bad) {
			t.Errorf("危险内容应剔除 %q，实际输出：%s", bad, out)
		}
	}
}

// 原有格式标签与合法链接/图片（含相对 URL）应保留。
func TestSanitizeRichContentKeepsFormatting(t *testing.T) {
	in := `<h2>标题</h2><p><strong>粗</strong><em>斜</em><s>删</s></p>` +
		`<ul><li>一</li></ul><blockquote>引用</blockquote>` +
		`<a href="https://yjlt.top/post/PS1">链接</a><a href="/post/PS1">站内</a>` +
		`<img src="/api/v1/media/MD1" alt="图" width="600" height="400">`
	out := SanitizeRichContent(in)
	for _, want := range []string{"<h2>", "<strong>", "<em>", "<s>", "<ul>", "<li>", "<blockquote>",
		`href="https://yjlt.top/post/PS1"`, `href="/post/PS1"`, `<img src="/api/v1/media/MD1" alt="图" width="600" height="400">`} {
		if !strings.Contains(out, want) {
			t.Errorf("合法标签/属性应保留 %q，实际输出：%s", want, out)
		}
	}
}

// pre/code 代码块标签应保留（代码展示）。
func TestSanitizeRichContentKeepsPreCode(t *testing.T) {
	in := `<pre><code>func main() { println("hi") }</code></pre>`
	out := SanitizeRichContent(in)
	for _, want := range []string{"<pre>", "<code>", "func main()"} {
		if !strings.Contains(out, want) {
			t.Errorf("代码块内容应保留 %q，实际输出：%s", want, out)
		}
	}
}

// 空串直返。
func TestSanitizeRichContentEmpty(t *testing.T) {
	if got := SanitizeRichContent(""); got != "" {
		t.Errorf("空串应直返，实际：%q", got)
	}
}

// 去标签 + TrimSpace：纯标签/纯空白视为空，文本内容保留。
func TestStripTagsAndTrim(t *testing.T) {
	cases := []struct {
		in   string
		want string
	}{
		{"", ""},
		{"   ", ""},
		{"<p></p>", ""},
		{"<p><br></p>", ""},
		{"<p>  </p>", ""},
		{`<div data-embed="post" data-id="PS1"></div>`, ""},
		{"<p>你好</p>", "你好"},
		{"<p> 你好 </p>", "你好"},
	}
	for _, tc := range cases {
		if got := StripTagsAndTrim(tc.in); got != tc.want {
			t.Errorf("StripTagsAndTrim(%q) = %q，期望 %q", tc.in, got, tc.want)
		}
	}
}
