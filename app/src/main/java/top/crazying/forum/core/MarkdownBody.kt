package top.crazying.forum.core

/**
 * 帖子正文渲染：Markdown（**不渲染 HTML 语法**）。
 *
 * 三端统一口径：服务端 `content` 存的是**用户原文**，一律按 Markdown 渲染；
 * 正文里的 HTML 标签按字面文字展示（不解析、不执行）。入库侧同样：安卓发帖
 * 已不再把纯文本包装成 `<p>…<br>…</p>`（见 PostCreateScreen），历史上被包装
 * 过的正文由服务端 `tool/content_migrate.py` 一次性还原成原文。
 *
 * 这里把 Markdown 子集转成 HTML 再交 HtmlCompat 渲染：标题 / 列表 / 引用 /
 * 代码块 / 分隔线 / 粗斜体 / 删除线 / 行内代码 / 链接。段落内换行 → `<br>`，
 * 空行分段 → 新 `<p>`（单换行即换行，对齐网页端 marked 的 breaks:true）。
 * 行内文本统一先做 HTML 转义，所以 `<div>` 这类标签会以字面文字出现。
 *
 * 纯 Kotlin 实现（无 Android 依赖），逻辑可单独验证。
 */
object MarkdownBody {

    private val FENCE = Regex("^\\s*(`{3,}|~{3,})(.*)$")
    private val HEADING = Regex("^(#{1,6})\\s+(.*)$")
    private val HR = Regex("^\\s*([-*_])(?:\\s*\\1){2,}\\s*$")
    private val UNORDERED = Regex("^\\s*[-*+]\\s+(.*)$")
    private val ORDERED = Regex("^\\s*\\d+[.)]\\s+(.*)$")
    private val QUOTE = Regex("^\\s*>\\s?(.*)$")

    private val RE_IMG = Regex("!\\[([^\\]]*)\\]\\(([^)\\s]+)(?:\\s+\"[^\"]*\")?\\)")
    private val RE_LINK = Regex("\\[([^\\]]+)\\]\\(([^)\\s]+)\\)")
    private val RE_CODE = Regex("`([^`]+)`")
    private val RE_BOLD_STAR = Regex("\\*\\*(.+?)\\*\\*")
    private val RE_BOLD_UNDER = Regex("__(.+?)__")
    private val RE_STRIKE = Regex("~~(.+?)~~")
    private val RE_ITALIC_STAR = Regex("\\*([^*\\n]+)\\*")
    private val RE_ITALIC_UNDER = Regex("(?<![0-9A-Za-z_])_([^_\\n]+)_(?![0-9A-Za-z_])")

    /** 正文（Markdown 子集） → HTML。HTML 标签会被转义成字面文字。 */
    fun toHtml(src: String): String {
        if (src.isBlank()) return ""
        val lines = src.replace("\r\n", "\n").replace('\r', '\n').split('\n')
        val out = StringBuilder(src.length + 64)
        val para = ArrayList<String>()
        val quote = ArrayList<String>()
        var listTag: String? = null

        fun flushPara() {
            if (para.isEmpty()) return
            out.append("<p>").append(inline(para.joinToString("<br>"))).append("</p><br>")
            para.clear()
        }

        fun flushQuote() {
            if (quote.isEmpty()) return
            out.append("<blockquote>")
                .append(inline(quote.joinToString("<br>")))
                .append("</blockquote><br>")
            quote.clear()
        }

        fun closeList() {
            val tag = listTag ?: return
            out.append("</").append(tag).append(">")
            listTag = null
        }

        fun closeBlocks() {
            flushPara()
            flushQuote()
            closeList()
        }

        var i = 0
        while (i < lines.size) {
            val line = lines[i].trimEnd()

            // ``` 代码块
            val fence = FENCE.find(line)
            if (fence != null) {
                closeBlocks()
                val marker = fence.groupValues[1].substring(0, 1)
                val code = StringBuilder()
                i += 1
                while (i < lines.size && !lines[i].trimStart().startsWith(marker)) {
                    if (code.isNotEmpty()) code.append('\n')
                    code.append(lines[i])
                    i += 1
                }
                if (i < lines.size) i += 1
                out.append("<pre><code>")
                    .append(escapeHtml(code.toString()))
                    .append("</code></pre><br>")
                continue
            }

            // 空行：结束当前块
            if (line.isBlank()) {
                closeBlocks()
                i += 1
                continue
            }

            // # 标题
            val heading = HEADING.find(line)
            if (heading != null) {
                closeBlocks()
                val level = heading.groupValues[1].length
                out.append("<h").append(level).append(">")
                    .append(inline(heading.groupValues[2].trim()))
                    .append("</h").append(level).append("><br>")
                i += 1
                continue
            }

            // --- 分隔线
            if (HR.matches(line)) {
                closeBlocks()
                out.append("<hr>")
                i += 1
                continue
            }

            // > 引用
            val quoted = QUOTE.find(line)
            if (quoted != null) {
                flushPara()
                closeList()
                quote.add(quoted.groupValues[1].trim())
                i += 1
                continue
            }
            flushQuote()

            // - / 1. 列表
            val bullet = UNORDERED.find(line)
            val ordered = ORDERED.find(line)
            if (bullet != null || ordered != null) {
                flushPara()
                val tag = if (bullet != null) "ul" else "ol"
                if (listTag != tag) {
                    closeList()
                    out.append("<").append(tag).append(">")
                    listTag = tag
                }
                val item = (bullet ?: ordered)!!.groupValues[1].trim()
                out.append("<li>").append(inline(item)).append("</li>")
                i += 1
                continue
            }
            closeList()

            // 普通文本行：累积成段落（段内换行保留为 <br>）
            para.add(line.trim())
            i += 1
        }
        closeBlocks()
        return out.toString()
    }

    // ────────────────── 行内 / 转义 ──────────────────

    private fun escapeHtml(s: String): String {
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

    /** 行内语法（输入先转义，再套用标记；生成的都是受支持的 HTML 标签）。 */
    private fun inline(src: String): String {
        var s = escapeHtml(src)
        // 远端内嵌图本轮不展示（HtmlBody 会再剥掉 <img>），只保留替代文字
        s = RE_IMG.replace(s) { m -> m.groupValues[1] }
        // 行内代码最先处理，避免里面的 * _ 被当成强调
        s = RE_CODE.replace(s) { m -> "<tt>" + m.groupValues[1] + "</tt>" }
        s = RE_LINK.replace(s) { m ->
            val href = m.groupValues[2]
            if (href.startsWith("http://") || href.startsWith("https://") || href.startsWith("/")) {
                "<a href=\"" + href + "\">" + m.groupValues[1] + "</a>"
            } else {
                m.groupValues[1]
            }
        }
        s = RE_BOLD_STAR.replace(s) { m -> "<b>" + m.groupValues[1] + "</b>" }
        s = RE_BOLD_UNDER.replace(s) { m -> "<b>" + m.groupValues[1] + "</b>" }
        s = RE_STRIKE.replace(s) { m -> "<strike>" + m.groupValues[1] + "</strike>" }
        s = RE_ITALIC_STAR.replace(s) { m -> "<i>" + m.groupValues[1] + "</i>" }
        s = RE_ITALIC_UNDER.replace(s) { m -> "<i>" + m.groupValues[1] + "</i>" }
        return s
    }
}
