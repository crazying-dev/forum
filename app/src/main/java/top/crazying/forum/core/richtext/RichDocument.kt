package top.crazying.forum.core.richtext

import top.crazying.forum.core.MarkdownBody

/** 一份富文本文档（块级结构 + 行内样式），编辑器与渲染器共用。 */
data class RichDocument(val blocks: List<RichBlock> = emptyList()) {

    val isBlank: Boolean
        get() = blocks.all { it.isBlankBlock() }

    fun toHtml(): String = RichHtml.serialize(this)

    fun toPlainText(): String = RichText.plain(this)

    companion object {
        val EMPTY = RichDocument()

        fun fromHtml(html: String): RichDocument = RichHtml.parse(html)

        fun fromMarkdown(markdown: String): RichDocument =
            RichHtml.parse(MarkdownBody.toHtml(markdown))

        /** 按服务端 content_format 选择解析入口（html / markdown）。 */
        fun fromContent(content: String, format: String?): RichDocument =
            if ((format ?: "").equals("html", ignoreCase = true)) fromHtml(content)
            else fromMarkdown(content)
    }
}

sealed interface RichBlock {

    data class Paragraph(val spans: List<RichSpan>) : RichBlock

    data class Heading(val level: Int, val spans: List<RichSpan>) : RichBlock

    data class BulletList(val items: List<RichListItem>) : RichBlock

    data class OrderedList(val items: List<RichListItem>) : RichBlock

    data class Quote(val blocks: List<RichBlock>) : RichBlock

    data class CodeBlock(val text: String) : RichBlock

    data class Image(val url: String, val alt: String = "") : RichBlock

    data object Divider : RichBlock

    /** 网页端 TipTap 的引用卡片节点。 */
    data class Embed(
        val type: String,
        val id: String,
        val attrs: Map<String, String> = emptyMap(),
    ) : RichBlock
}

/** 列表项可以包含段落/嵌套列表（嵌套列表只在渲染侧支持，编辑器只生成一层）。 */
data class RichListItem(val blocks: List<RichBlock>)

/** 行内样式；一段文本可以同时带多种样式。 */
data class RichSpan(
    val text: String,
    val bold: Boolean = false,
    val italic: Boolean = false,
    val underline: Boolean = false,
    val strike: Boolean = false,
    val code: Boolean = false,
    val link: String? = null,
) {
    val isPlain: Boolean
        get() = !bold && !italic && !underline && !strike && !code && link.isNullOrBlank()

    fun withStyle(style: InlineStyle): RichSpan = copy(
        bold = bold || style.bold,
        italic = italic || style.italic,
        underline = underline || style.underline,
        strike = strike || style.strike,
        code = code || style.code,
        link = link ?: style.link,
    )
}

data class InlineStyle(
    val bold: Boolean = false,
    val italic: Boolean = false,
    val underline: Boolean = false,
    val strike: Boolean = false,
    val code: Boolean = false,
    val link: String? = null,
)

private fun RichBlock.isBlankBlock(): Boolean = when (this) {
    is RichBlock.Paragraph -> spans.all { it.text.isBlank() }
    is RichBlock.Heading -> spans.all { it.text.isBlank() }
    is RichBlock.BulletList -> items.isEmpty()
    is RichBlock.OrderedList -> items.isEmpty()
    is RichBlock.Quote -> blocks.isEmpty() || blocks.all { it.isBlankBlock() }
    is RichBlock.CodeBlock -> text.isBlank()
    is RichBlock.Image -> url.isBlank()
    is RichBlock.Divider -> false
    is RichBlock.Embed -> id.isBlank()
}

/** HTML 序列化：输出严格落在 ouo `sanitize.SanitizeRichContent` 的白名单内。 */
object RichHtml {

    fun serialize(doc: RichDocument): String =
        doc.blocks.joinToString("\n") { serializeBlock(it) }

    private fun serializeBlock(block: RichBlock): String = when (block) {
        is RichBlock.Paragraph ->
            if (block.spans.all { it.text.isEmpty() }) "<p><br></p>"
            else "<p>" + serializeSpans(block.spans) + "</p>"

        is RichBlock.Heading -> {
            val level = block.level.coerceIn(1, 4)
            "<h$level>" + serializeSpans(block.spans) + "</h$level>"
        }

        is RichBlock.BulletList ->
            "<ul>" + block.items.joinToString("") { "<li>" + serializeListItem(it) + "</li>" } + "</ul>"

        is RichBlock.OrderedList ->
            "<ol>" + block.items.joinToString("") { "<li>" + serializeListItem(it) + "</li>" } + "</ol>"

        is RichBlock.Quote ->
            "<blockquote>" + block.blocks.joinToString("") { serializeBlock(it) } + "</blockquote>"

        is RichBlock.CodeBlock ->
            "<pre><code>" + escapeText(block.text) + "</code></pre>"

        is RichBlock.Image ->
            "<img src=\"" + escapeAttr(block.url) + "\" alt=\"" + escapeAttr(block.alt) + "\">"

        RichBlock.Divider -> "<hr>"

        is RichBlock.Embed -> {
            val sb = StringBuilder()
            sb.append("<div data-embed=\"").append(escapeAttr(block.type)).append("\"")
            sb.append(" data-id=\"").append(escapeAttr(block.id)).append("\"")
            for ((k, v) in block.attrs) {
                if (k == "data-embed" || k == "data-id") continue
                sb.append(" ").append(k).append("=\"").append(escapeAttr(v)).append("\"")
            }
            sb.append("></div>")
            sb.toString()
        }
    }

    private fun serializeListItem(item: RichListItem): String =
        item.blocks.joinToString("") { b ->
            when (b) {
                is RichBlock.Paragraph -> serializeSpans(b.spans)
                else -> serializeBlock(b)
            }
        }

    private fun serializeSpans(spans: List<RichSpan>): String {
        val sb = StringBuilder()
        for (span in spans) {
            if (span.text.isEmpty()) continue
            var html = escapeText(span.text)
            if (span.code) html = "<code>$html</code>"
            if (span.underline) html = "<u>$html</u>"
            if (span.strike) html = "<s>$html</s>"
            if (span.italic) html = "<em>$html</em>"
            if (span.bold) html = "<strong>$html</strong>"
            val link = span.link?.trim().orEmpty()
            if (link.isNotEmpty() && isSafeUrl(link)) {
                html = "<a href=\"" + escapeAttr(link) + "\">" + html + "</a>"
            }
            sb.append(html)
        }
        return sb.toString()
    }

    fun isSafeUrl(raw: String): Boolean {
        val s = raw.trim()
        if (s.isEmpty()) return false
        val lower = s.lowercase()
        if (lower.startsWith("javascript:") || lower.startsWith("vbscript:") || lower.startsWith("data:")) {
            return false
        }
        return lower.startsWith("http://") || lower.startsWith("https://") ||
            s.startsWith("/") || s.startsWith("#")
    }

    fun escapeText(s: String): String {
        val out = StringBuilder(s.length + 16)
        for (ch in s) {
            when (ch) {
                '&' -> out.append("&amp;")
                '<' -> out.append("&lt;")
                '>' -> out.append("&gt;")
                else -> out.append(ch)
            }
        }
        return out.toString()
    }

    fun escapeAttr(s: String): String {
        val out = StringBuilder(s.length + 16)
        for (ch in s) {
            when (ch) {
                '&' -> out.append("&amp;")
                '<' -> out.append("&lt;")
                '>' -> out.append("&gt;")
                '"' -> out.append("&quot;")
                '\'' -> out.append("&#39;")
                else -> out.append(ch)
            }
        }
        return out.toString()
    }

    // ────────────────── 解析 ──────────────────

    fun parse(html: String): RichDocument {
        if (html.isBlank()) return RichDocument.EMPTY
        val tokens = Tokenizer(html).tokenize()
        return RichDocument(Parser(tokens).parse())
    }

    private sealed interface Token {
        data class Text(val text: String) : Token
        data class Tag(
            val name: String,
            val attrs: Map<String, String>,
            val closing: Boolean,
            val selfClosing: Boolean,
        ) : Token
    }

    private class Tokenizer(private val html: String) {

        fun tokenize(): List<Token> {
            val out = ArrayList<Token>()
            var i = 0
            while (i < html.length) {
                val lt = html.indexOf('<', i)
                if (lt < 0) {
                    appendText(out, html.substring(i))
                    break
                }
                if (lt > i) appendText(out, html.substring(i, lt))
                if (html.startsWith("<!--", lt)) {
                    val end = html.indexOf("-->", lt + 4)
                    i = if (end < 0) html.length else end + 3
                    continue
                }
                if (html.startsWith("<!", lt) || html.startsWith("<?", lt)) {
                    val end = html.indexOf('>', lt + 2)
                    i = if (end < 0) html.length else end + 1
                    continue
                }
                val end = html.indexOf('>', lt + 1)
                if (end < 0) {
                    appendText(out, html.substring(lt))
                    break
                }
                val raw = html.substring(lt + 1, end).trim()
                if (raw.isEmpty()) {
                    i = end + 1
                    continue
                }
                if (raw.startsWith("/")) {
                    val name = raw.drop(1).trim().substringBefore(' ').lowercase()
                    if (name.isNotEmpty()) out.add(Token.Tag(name, emptyMap(), true, false))
                    i = end + 1
                    continue
                }
                val selfClosing = raw.endsWith("/")
                val body = raw.removeSuffix("/").trim()
                val name = body.substringBefore(' ').lowercase()
                val attrs = parseAttrs(body.substringAfter(' ', ""))
                if (name == "script" || name == "style") {
                    // 丢弃脚本/样式内容（不进入文档模型）。
                    val close = html.indexOf("</$name", end + 1, ignoreCase = true)
                    val closeEnd = if (close < 0) html.length else html.indexOf('>', close).let { if (it < 0) html.length else it + 1 }
                    i = closeEnd
                    continue
                }
                out.add(Token.Tag(name, attrs, false, selfClosing))
                i = end + 1
                if (name == "pre" && !selfClosing) {
                    // pre 内是原始文本：吞到 </pre>，避免把代码里的 < > 当标签。
                    val close = html.indexOf("</pre", i, ignoreCase = true)
                    val closeEnd = if (close < 0) html.length else html.indexOf('>', close).let { if (it < 0) html.length else it + 1 }
                    val rawText = html.substring(i, if (close < 0) html.length else close)
                    if (rawText.isNotEmpty()) out.add(Token.Text(decodeEntities(rawText)))
                    out.add(Token.Tag("pre", emptyMap(), true, false))
                    i = closeEnd
                }
            }
            return out
        }

        private fun appendText(out: MutableList<Token>, raw: String) {
            if (raw.isEmpty()) return
            val text = decodeEntities(raw)
            if (text.isNotEmpty()) out.add(Token.Text(text))
        }

        private fun parseAttrs(raw: String): Map<String, String> {
            if (raw.isBlank()) return emptyMap()
            val out = HashMap<String, String>()
            var i = 0
            while (i < raw.length) {
                while (i < raw.length && raw[i].isWhitespace()) i++
                val start = i
                while (i < raw.length && !raw[i].isWhitespace() && raw[i] != '=') i++
                if (i == start) break
                val name = raw.substring(start, i).lowercase()
                while (i < raw.length && raw[i].isWhitespace()) i++
                if (i < raw.length && raw[i] == '=') {
                    i++
                    while (i < raw.length && raw[i].isWhitespace()) i++
                    val quote = if (i < raw.length && (raw[i] == '"' || raw[i] == '\'')) raw[i++] else null
                    val valueStart = i
                    if (quote != null) {
                        while (i < raw.length && raw[i] != quote) i++
                        out[name] = decodeEntities(raw.substring(valueStart, i))
                        if (i < raw.length) i++
                    } else {
                        while (i < raw.length && !raw[i].isWhitespace()) i++
                        out[name] = decodeEntities(raw.substring(valueStart, i))
                    }
                } else {
                    out[name] = ""
                }
            }
            return out
        }
    }

    private class Parser(private val tokens: List<Token>) {
        private var pos = 0

        fun parse(): List<RichBlock> = parseBlocks(null)

        private fun parseBlocks(endTag: String?): List<RichBlock> {
            val blocks = ArrayList<RichBlock>()
            while (pos < tokens.size) {
                val token = tokens[pos]
                if (token is Token.Tag && token.closing && endTag != null && token.name == endTag) {
                    pos++
                    return blocks
                }
                when (token) {
                    is Token.Text -> {
                        // 块级裸文本：作为段落收集，连续文本在后续标签处 flush。
                        val spans = ArrayList<RichSpan>()
                        while (pos < tokens.size && tokens[pos] is Token.Text) {
                            val text = (tokens[pos] as Token.Text).text
                            if (text.isNotEmpty()) spans.add(RichSpan(text))
                            pos++
                        }
                        if (spans.isNotEmpty()) blocks.add(RichBlock.Paragraph(spans))
                    }

                    is Token.Tag -> {
                        if (token.closing) {
                            pos++
                            continue
                        }
                        when (token.name) {
                            "p" -> {
                                pos++
                                blocks.addAll(parseInlineBlocks("p"))
                            }

                            "h1", "h2", "h3", "h4", "h5", "h6" -> {
                                val level = token.name.substring(1).toIntOrNull() ?: 1
                                pos++
                                val spans = parseInlineBlocks(token.name)
                                    .filterIsInstance<RichBlock.Paragraph>()
                                    .flatMap { it.spans }
                                blocks.add(RichBlock.Heading(level, spans))
                            }

                            "ul", "ol" -> {
                                pos++
                                blocks.add(parseList(token.name, token.name == "ol"))
                            }

                            "blockquote" -> {
                                pos++
                                blocks.add(RichBlock.Quote(parseBlocks("blockquote")))
                            }

                            "pre" -> {
                                pos++
                                blocks.add(RichBlock.CodeBlock(parseRawText("pre")))
                            }

                            "hr" -> {
                                pos++
                                blocks.add(RichBlock.Divider)
                            }

                            "img" -> {
                                pos++
                                imageOf(token.attrs)?.let { blocks.add(it) }
                            }

                            "div" -> {
                                val embedType = token.attrs["data-embed"]
                                val embedId = token.attrs["data-id"]
                                if (!embedType.isNullOrBlank() && !embedId.isNullOrBlank()) {
                                    pos++
                                    blocks.add(RichBlock.Embed(embedType, embedId, token.attrs))
                                    skipUntilEnd("div")
                                } else {
                                    pos++
                                    blocks.addAll(parseBlocks("div"))
                                }
                            }

                            "br" -> pos++

                            else -> pos++
                        }
                    }
                }
            }
            return blocks
        }

        private fun parseInlineBlocks(endTag: String): List<RichBlock> {
            val out = ArrayList<RichBlock>()
            val spans = ArrayList<RichSpan>()
            val text = StringBuilder()
            var style = InlineStyle()

            fun flushText() {
                if (text.isEmpty()) return
                spans.add(RichSpan(text.toString()).withStyle(style))
                text.clear()
            }

            fun flushParagraph() {
                flushText()
                if (spans.isNotEmpty()) {
                    out.add(RichBlock.Paragraph(spans.toList()))
                    spans.clear()
                }
            }

            while (pos < tokens.size) {
                val token = tokens[pos]
                if (token is Token.Tag && token.closing && token.name == endTag) {
                    pos++
                    break
                }
                when (token) {
                    is Token.Text -> {
                        text.append(token.text)
                        pos++
                    }

                    is Token.Tag -> {
                        if (token.closing) {
                            pos++
                            continue
                        }
                        when (token.name) {
                            "br" -> {
                                text.append('\n')
                                pos++
                            }

                            "img" -> {
                                flushParagraph()
                                imageOf(token.attrs)?.let { out.add(it) }
                                pos++
                            }

                            "div" -> {
                                val embedType = token.attrs["data-embed"]
                                val embedId = token.attrs["data-id"]
                                if (!embedType.isNullOrBlank() && !embedId.isNullOrBlank()) {
                                    flushParagraph()
                                    out.add(RichBlock.Embed(embedType, embedId, token.attrs))
                                    pos++
                                    skipUntilEnd("div")
                                } else {
                                    pos++
                                }
                            }

                            "strong", "b", "em", "i", "u", "s", "strike", "del", "code", "a" -> {
                                flushText()
                                val old = style
                                style = styleFor(token, style)
                                pos++
                                val inner = parseInlineBlocks(token.name)
                                for (block in inner) {
                                    when (block) {
                                        // 递归只负责内层标签，外层样式（如 strong 包 em）要在此补上。
                                        is RichBlock.Paragraph -> spans.addAll(block.spans.map { it.withStyle(style) })
                                        else -> {
                                            flushParagraph()
                                            out.add(block)
                                        }
                                    }
                                }
                                style = old
                            }

                            else -> pos++
                        }
                    }
                }
            }
            flushParagraph()
            return out
        }

        private fun parseList(tag: String, ordered: Boolean): RichBlock {
            val items = ArrayList<RichListItem>()
            while (pos < tokens.size) {
                val token = tokens[pos]
                if (token is Token.Tag && token.closing && token.name == tag) {
                    pos++
                    break
                }
                if (token is Token.Tag && token.name == "li" && !token.closing) {
                    pos++
                    val itemBlocks = mutableListOf<RichBlock>()
                    // li 里的文本/行内元素按段落收集，块级元素（嵌套列表/引用）单独收集。
                    var inline = StringBuilder()
                    var itemSpans = ArrayList<RichSpan>()
                    var style = InlineStyle()

                    fun flushText() {
                        if (inline.isEmpty()) return
                        itemSpans.add(RichSpan(inline.toString()).withStyle(style))
                        inline.clear()
                    }

                    fun flushPara() {
                        flushText()
                        if (itemSpans.isNotEmpty()) {
                            itemBlocks.add(RichBlock.Paragraph(itemSpans.toList()))
                            itemSpans = ArrayList()
                        }
                    }

                    while (pos < tokens.size) {
                        val t = tokens[pos]
                        if (t is Token.Tag && t.closing && t.name == "li") {
                            pos++
                            break
                        }
                        when (t) {
                            is Token.Text -> {
                                inline.append(t.text)
                                pos++
                            }

                            is Token.Tag -> {
                                if (t.closing) {
                                    pos++
                                    continue
                                }
                                when (t.name) {
                                    "ul", "ol" -> {
                                        flushPara()
                                        pos++
                                        itemBlocks.add(parseList(t.name, t.name == "ol"))
                                    }

                                    "p" -> {
                                        flushPara()
                                        pos++
                                        itemBlocks.addAll(parseInlineBlocks("p"))
                                    }

                                    "blockquote" -> {
                                        flushPara()
                                        pos++
                                        itemBlocks.add(RichBlock.Quote(parseBlocks("blockquote")))
                                    }

                                    "br" -> {
                                        inline.append('\n')
                                        pos++
                                    }

                                    "strong", "b", "em", "i", "u", "s", "strike", "del", "code", "a" -> {
                                        flushText()
                                        val oldStyle = style
                                        style = styleFor(t, style)
                                        pos++
                                        val inner = parseInlineBlocks(t.name)
                                        for (b in inner) {
                                            if (b is RichBlock.Paragraph) {
                                                itemSpans.addAll(b.spans.map { it.withStyle(style) })
                                            }
                                        }
                                        style = oldStyle
                                    }

                                    else -> pos++
                                }
                            }
                        }
                    }
                    flushPara()
                    items.add(RichListItem(itemBlocks))
                } else {
                    pos++
                }
            }
            return if (ordered) RichBlock.OrderedList(items) else RichBlock.BulletList(items)
        }

        private fun parseRawText(endTag: String): String {
            val sb = StringBuilder()
            while (pos < tokens.size) {
                val token = tokens[pos]
                if (token is Token.Tag && token.closing && token.name == endTag) {
                    pos++
                    break
                }
                if (token is Token.Text) sb.append(token.text)
                pos++
            }
            return sb.toString().trim('\n')
        }

        private fun skipUntilEnd(name: String) {
            var depth = 1
            while (pos < tokens.size && depth > 0) {
                val token = tokens[pos]
                if (token is Token.Tag && token.name == name) {
                    if (token.closing) depth-- else if (!token.selfClosing) depth++
                }
                pos++
            }
        }

        private fun imageOf(attrs: Map<String, String>): RichBlock.Image? {
            val src = attrs["src"]?.trim().orEmpty()
            if (src.isEmpty() || !isSafeUrl(src)) return null
            return RichBlock.Image(src, attrs["alt"]?.trim().orEmpty())
        }

        private fun styleFor(tag: Token.Tag, old: InlineStyle): InlineStyle = when (tag.name) {
            "strong", "b" -> old.copy(bold = true)
            "em", "i" -> old.copy(italic = true)
            "u" -> old.copy(underline = true)
            "s", "strike", "del" -> old.copy(strike = true)
            "code" -> old.copy(code = true)
            "a" -> {
                val href = tag.attrs["href"]?.trim().orEmpty()
                if (isSafeUrl(href)) old.copy(link = href) else old
            }

            else -> old
        }
    }

    private fun decodeEntities(raw: String): String {
        if (!raw.contains('&')) return raw
        val sb = StringBuilder(raw.length)
        var i = 0
        while (i < raw.length) {
            val ch = raw[i]
            if (ch != '&') {
                sb.append(ch)
                i++
                continue
            }
            val end = raw.indexOf(';', i + 1)
            if (end < 0) {
                sb.append(ch)
                i++
                continue
            }
            val entity = raw.substring(i + 1, end)
            val decoded = when {
                entity == "amp" -> "&"
                entity == "lt" -> "<"
                entity == "gt" -> ">"
                entity == "quot" -> "\""
                entity == "apos" -> "'"
                entity == "nbsp" -> "\u00A0"
                entity.startsWith("#x", true) -> entity.drop(2).toIntOrNull(16)?.toChar()?.toString()
                entity.startsWith("#") -> entity.drop(1).toIntOrNull()?.toChar()?.toString()
                else -> null
            }
            if (decoded == null) {
                sb.append(ch)
                i++
            } else {
                sb.append(decoded)
                i = end + 1
            }
        }
        return sb.toString()
    }
}

/** 纯文本提取（列表符号、图片占位、引用卡片占位）。 */
object RichText {

    fun plain(doc: RichDocument): String =
        doc.blocks.joinToString("\n\n") { plainBlock(it) }.trim()

    private fun plainBlock(block: RichBlock): String = when (block) {
        is RichBlock.Paragraph -> plainSpans(block.spans)
        is RichBlock.Heading -> plainSpans(block.spans)
        is RichBlock.BulletList -> block.items.joinToString("\n") { "• " + plainItem(it) }
        is RichBlock.OrderedList -> block.items.mapIndexed { i, item -> "${i + 1}. " + plainItem(item) }
            .joinToString("\n")
        is RichBlock.Quote -> block.blocks.joinToString("\n") { plainBlock(it) }
        is RichBlock.CodeBlock -> block.text
        is RichBlock.Image -> if (block.alt.isBlank()) "[图片]" else "[图片：${block.alt}]"
        RichBlock.Divider -> "———"
        is RichBlock.Embed -> "[引用内容]"
    }

    private fun plainItem(item: RichListItem): String =
        item.blocks.joinToString(" ") { plainBlock(it) }

    private fun plainSpans(spans: List<RichSpan>): String =
        spans.joinToString("") { it.text }
}
