package top.crazying.forum.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** [MarkdownBody] 的三端口径回归用例（正文原文入库，一律按 Markdown 渲染）。 */
class MarkdownBodyTest {

    @Test
    fun paragraphSingleNewline_becomesRealBr() {
        val html = MarkdownBody.toHtml("第一行\n第二行")
        assertTrue("段落内单换行必须生成真正的 <br>", html.contains("<br>"))
        assertFalse("不得把 <br> 转义成字面文字", html.contains("&lt;br&gt;"))
        assertTrue(html.contains("第一行"))
        assertTrue(html.contains("第二行"))
    }

    @Test
    fun quoteSingleNewline_becomesRealBr() {
        val html = MarkdownBody.toHtml("> 一行\n> 二行")
        assertTrue(html.contains("<blockquote>"))
        assertTrue(html.contains("<br>"))
        assertFalse(html.contains("&lt;br&gt;"))
    }

    @Test
    fun blankLine_splitsIntoTwoParagraphs() {
        val html = MarkdownBody.toHtml("甲\n\n乙")
        assertEquals(2, Regex("<p>").findAll(html).count())
    }

    @Test
    fun literalHtml_isEscapedNotRendered() {
        val html = MarkdownBody.toHtml("<div>原文标签</div>")
        assertTrue(html.contains("&lt;div&gt;"))
        assertFalse(html.contains("<div>"))
    }

    @Test
    fun inlineBoldInsideMultiLineParagraph_stillWorks() {
        val html = MarkdownBody.toHtml("第一行 **粗体**\n第二行")
        assertTrue(html.contains("<b>粗体</b>"))
        assertTrue(html.contains("<br>"))
        assertFalse(html.contains("&lt;br&gt;"))
    }

    @Test
    fun blankSource_returnsEmpty() {
        assertEquals("", MarkdownBody.toHtml("   "))
    }
}
