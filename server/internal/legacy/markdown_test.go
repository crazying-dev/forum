package legacy

import (
	"strings"
	"testing"
)

func TestHTMLToMarkdownBasicBlocks(t *testing.T) {
	in := `<h1>标题</h1><p>你好 <strong>世界</strong> 和 <em>大家</em></p>` +
		`<ul><li>第一项</li><li>第二项</li></ul>` +
		`<blockquote><p>引用</p></blockquote>` +
		`<pre><code>fmt.Println("hi")</code></pre>`
	out := HTMLToMarkdown(in)
	for _, want := range []string{"# 标题", "**世界**", "*大家*", "- 第一项", "- 第二项", "> 引用", "```", "fmt.Println"} {
		if !strings.Contains(out, want) {
			t.Errorf("输出缺少 %q：\n%s", want, out)
		}
	}
}

func TestHTMLToMarkdownFiltersEmbed(t *testing.T) {
	in := `<p>前文</p><div data-embed="post" data-id="PS123"></div><p>后文</p>`
	out := HTMLToMarkdown(in)
	if strings.Contains(out, "data-embed") || strings.Contains(out, "PS123") {
		t.Fatalf("data-embed 节点应被过滤：\n%s", out)
	}
	if !strings.Contains(out, "前文") || !strings.Contains(out, "后文") {
		t.Fatalf("普通文本应保留：\n%s", out)
	}
}

func TestHTMLToMarkdownEscapesRawHTML(t *testing.T) {
	in := `<p>&lt;script&gt;alert(1)&lt;/script&gt;</p><script>alert(2)</script><p>safe</p>`
	out := HTMLToMarkdown(in)
	if strings.Contains(out, "<script") || strings.Contains(out, "alert(2)") {
		t.Fatalf("raw script 不应透传：\n%s", out)
	}
	if !strings.Contains(out, "&lt;script&gt;") {
		t.Fatalf("文本中的 < 应转义：\n%s", out)
	}
	if !strings.Contains(out, "safe") {
		t.Fatalf("正常文本丢失：\n%s", out)
	}
}

func TestHTMLToMarkdownURLSchemeWhitelist(t *testing.T) {
	in := `<a href="javascript:alert(1)">bad</a>` +
		`<a href="https://example.com/a">good</a>` +
		`<img src="data:image/png;base64,AAAA" alt="bad">` +
		`<img src="https://example.com/i.png" alt="good">`
	out := HTMLToMarkdown(in)
	if strings.Contains(out, "javascript:") || strings.Contains(out, "data:image") {
		t.Fatalf("危险 scheme 应被剔除：\n%s", out)
	}
	if !strings.Contains(out, "[good](https://example.com/a)") {
		t.Fatalf("https 链接应保留：\n%s", out)
	}
	if !strings.Contains(out, "![good](https://example.com/i.png)") {
		t.Fatalf("https 图片应保留：\n%s", out)
	}
	if !strings.Contains(out, "bad") {
		t.Fatalf("非法链接文本仍应保留：\n%s", out)
	}
}

func TestHTMLToMarkdownUnknownTagsDropped(t *testing.T) {
	out := HTMLToMarkdown(`<p>hello <custom-tag>world</custom-tag></p>`)
	if strings.Contains(out, "<custom-tag") || strings.Contains(out, "</custom-tag") {
		t.Fatalf("未知标签不应输出：\n%s", out)
	}
	if !strings.Contains(out, "hello world") {
		t.Fatalf("未知标签内文本应保留：\n%s", out)
	}
}

func TestHTMLToMarkdownEmpty(t *testing.T) {
	if got := HTMLToMarkdown("  "); got != "" {
		t.Fatalf("空白输入应为空，实际 %q", got)
	}
}
