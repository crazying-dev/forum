package top.crazying.forum.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import top.crazying.forum.core.richtext.RichBlock
import top.crazying.forum.core.richtext.RichDocument
import top.crazying.forum.core.richtext.RichSpan

/**
 * [RichDocument] 的 HTML / Markdown 解析与序列化往返用例。
 *
 * 服务端存 HTML 富文本（content_format=html），编辑器也输出同一套白名单标签；
 * 这里覆盖段落、行内样式、列表、引用、代码块、图片、分隔线、引用卡片，
 * 以及脚本/样式与不安全 URL / 事件的丢弃行为。
 */
class RichDocumentTest {

    @Test
    fun paragraphAndBr_roundTrip() {
        val doc = RichDocument.fromHtml("<p>第一段<br>第二行</p><p>第二段</p>")

        assertEquals(2, doc.blocks.size)
        val first = doc.blocks[0] as RichBlock.Paragraph
        assertEquals("第一段\n第二行", first.spans.joinToString("") { it.text })
        assertEquals(RichBlock.Paragraph(listOf(RichSpan("第二段"))), doc.blocks[1])

        val html = doc.toHtml()
        assertTrue(html.contains("<p>第一段\n第二行</p>"))
        assertTrue(html.contains("<p>第二段</p>"))
    }

    @Test
    fun heading_roundTrip() {
        val doc = RichDocument.fromHtml("<h2>二级标题</h2>")

        assertEquals(
            RichBlock.Heading(2, listOf(RichSpan("二级标题"))),
            doc.blocks.single(),
        )
        assertEquals("<h2>二级标题</h2>", doc.toHtml())
    }

    @Test
    fun fromHtml_parsesInlineStyles() {
        val doc = RichDocument.fromHtml(
            "<p><strong>粗</strong><em>斜</em><u>下划</u><s>删除</s><code>代码</code>" +
                "<a href=\"https://example.com/a?b=1&amp;c=2\">链接</a></p>",
        )

        val paragraph = doc.blocks.single() as RichBlock.Paragraph
        assertEquals(6, paragraph.spans.size)
        assertTrue(paragraph.spans[0].bold)
        assertTrue(paragraph.spans[1].italic)
        assertTrue(paragraph.spans[2].underline)
        assertTrue(paragraph.spans[3].strike)
        assertTrue(paragraph.spans[4].code)
        assertEquals("https://example.com/a?b=1&c=2", paragraph.spans[5].link)
    }

    @Test
    fun toHtml_writesInlineStyles() {
        val doc = RichDocument(
            listOf(
                RichBlock.Paragraph(
                    listOf(
                        RichSpan("粗", bold = true),
                        RichSpan("斜", italic = true),
                        RichSpan("下划", underline = true),
                        RichSpan("删除", strike = true),
                        RichSpan("代码", code = true),
                        RichSpan("链接", link = "https://example.com/a?b=1&c=2"),
                    ),
                ),
            ),
        )

        assertEquals(
            "<p><strong>粗</strong><em>斜</em><u>下划</u><s>删除</s><code>代码</code>" +
                "<a href=\"https://example.com/a?b=1&amp;c=2\">链接</a></p>",
            doc.toHtml(),
        )
    }

    @Test
    fun lists_roundTripWithNesting() {
        val doc = RichDocument.fromHtml(
            "<ul><li>一</li><li>二<ul><li>子项</li></ul></li></ul>" +
                "<ol><li>甲</li><li>乙</li></ol>",
        )

        assertEquals(2, doc.blocks.size)
        val bullet = doc.blocks[0] as RichBlock.BulletList
        assertEquals(2, bullet.items.size)
        assertEquals(RichBlock.Paragraph(listOf(RichSpan("一"))), bullet.items[0].blocks.single())
        val nested = bullet.items[1].blocks.filterIsInstance<RichBlock.BulletList>().single()
        assertEquals(RichBlock.Paragraph(listOf(RichSpan("子项"))), nested.items.single().blocks.single())

        val ordered = doc.blocks[1] as RichBlock.OrderedList
        assertEquals(2, ordered.items.size)

        val html = doc.toHtml()
        assertTrue(html.contains("<ul><li>一</li><li>二<ul><li>子项</li></ul></li></ul>"))
        assertTrue(html.contains("<ol><li>甲</li><li>乙</li></ol>"))
    }

    @Test
    fun blockquote_roundTrip() {
        val doc = RichDocument.fromHtml("<blockquote><p>引用内容</p></blockquote>")

        val quote = doc.blocks.single() as RichBlock.Quote
        assertEquals(RichBlock.Paragraph(listOf(RichSpan("引用内容"))), quote.blocks.single())
        assertEquals("<blockquote><p>引用内容</p></blockquote>", doc.toHtml())
    }

    @Test
    fun codeBlock_preservesAngleBrackets() {
        val doc = RichDocument.fromHtml("<pre>if (a &lt; b &amp;&amp; c &gt; d) {}</pre>")

        val code = doc.blocks.single() as RichBlock.CodeBlock
        assertEquals("if (a < b && c > d) {}", code.text)

        val html = doc.toHtml()
        assertEquals("<pre><code>if (a &lt; b &amp;&amp; c &gt; d) {}</code></pre>", html)
        // 再解析一遍，代码里的尖括号仍是字面文本
        val reparsed = RichDocument.fromHtml(html).blocks.single() as RichBlock.CodeBlock
        assertTrue(reparsed.text.contains("if (a < b && c > d) {}"))
    }

    @Test
    fun imageDividerAndEmbed_roundTrip() {
        val doc = RichDocument.fromHtml(
            "<p>前</p><img src=\"https://example.com/a.png\" alt=\"配图\"><hr>" +
                "<div data-embed=\"post\" data-id=\"42\" data-title=\"标题\"></div><p>后</p>",
        )

        assertEquals(5, doc.blocks.size)
        val image = doc.blocks[1] as RichBlock.Image
        assertEquals("https://example.com/a.png", image.url)
        assertEquals("配图", image.alt)
        assertEquals(RichBlock.Divider, doc.blocks[2])
        val embed = doc.blocks[3] as RichBlock.Embed
        assertEquals("post", embed.type)
        assertEquals("42", embed.id)
        assertEquals("标题", embed.attrs["data-title"])

        val html = doc.toHtml()
        assertTrue(html.contains("<img src=\"https://example.com/a.png\" alt=\"配图\">"))
        assertTrue(html.contains("<hr>"))
        assertTrue(html.contains("<div data-embed=\"post\" data-id=\"42\" data-title=\"标题\"></div>"))
    }

    @Test
    fun scriptAndStyleContent_isDropped() {
        val doc = RichDocument.fromHtml(
            "<p>前</p><script>alert('x')</script><style>.a{color:red}</style><p>后</p>",
        )

        assertEquals(2, doc.blocks.size)
        val plain = doc.toPlainText()
        assertTrue(plain.contains("前"))
        assertTrue(plain.contains("后"))
        assertFalse(plain.contains("alert"))
        assertFalse(plain.contains("color"))
        assertFalse(doc.toHtml().contains("script"))
    }

    @Test
    fun unsafeHrefAndEventAttributes_areDropped() {
        val doc = RichDocument.fromHtml(
            "<p><a href=\"javascript:alert(1)\">点我</a></p>" +
                "<img src=\"https://example.com/x.png\" onerror=\"alert(2)\">",
        )

        val paragraph = doc.blocks[0] as RichBlock.Paragraph
        assertNull(paragraph.spans.single().link)
        assertEquals("https://example.com/x.png", (doc.blocks[1] as RichBlock.Image).url)

        val html = doc.toHtml()
        assertFalse(html.contains("javascript:"))
        assertFalse(html.contains("onerror"))
        assertTrue(html.contains("<p>点我</p>"))
        assertTrue(html.contains("<img src=\"https://example.com/x.png\" alt=\"\">"))
    }

    @Test
    fun entities_decodeAndPlainText() {
        val doc = RichDocument.fromHtml("<p>A &amp; B &lt; C&nbsp;D&#65;&#x42;</p><h2>标题</h2>")

        val paragraph = doc.blocks[0] as RichBlock.Paragraph
        assertEquals("A & B < C\u00A0DAB", paragraph.spans.joinToString("") { it.text })
        assertEquals("A & B < C\u00A0DAB\n\n标题", doc.toPlainText())

        val html = doc.toHtml()
        assertTrue(html.contains("A &amp; B &lt; C"))
    }

    @Test
    fun toPlainText_formatsBlocks() {
        val doc = RichDocument.fromHtml(
            "<h2>标题</h2><p>正文 <strong>加粗</strong></p>" +
                "<ul><li>第一</li><li>第二</li></ul>" +
                "<ol><li>甲</li><li>乙</li></ol>" +
                "<img src=\"https://example.com/a.png\" alt=\"图\"><hr><pre>代码</pre>",
        )

        assertEquals(
            "标题\n\n正文 加粗\n\n• 第一\n• 第二\n\n1. 甲\n2. 乙\n\n[图片：图]\n\n———\n\n代码",
            doc.toPlainText(),
        )
    }

    @Test
    fun fromMarkdown_convertsBoldAndCode() {
        val doc = RichDocument.fromMarkdown("**粗体** 与 `code`")

        val paragraph = doc.blocks.single() as RichBlock.Paragraph
        assertTrue(paragraph.spans.any { it.bold && it.text == "粗体" })
        assertTrue(paragraph.spans.any { it.code && it.text == "code" })

        val html = doc.toHtml()
        assertTrue(html.contains("<strong>粗体</strong>"))
        assertTrue(html.contains("<code>code</code>"))
    }

    @Test
    fun fromMarkdown_convertsList() {
        val doc = RichDocument.fromMarkdown("- 第一\n- 第二")

        assertTrue(doc.blocks.any { it is RichBlock.BulletList })
        val html = doc.toHtml()
        assertTrue(html.contains("<ul>"))
        assertTrue(html.contains("<li>第一</li>"))
    }
}
