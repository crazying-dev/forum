package top.crazying.forum.ui.richtext

import android.graphics.Paint
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextLayoutResult
import androidx.compose.ui.text.TextRange
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.TextFieldValue
import androidx.compose.ui.text.style.LineHeightStyle
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextIndent
import androidx.compose.ui.text.ParagraphStyle
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil3.compose.AsyncImage
import top.crazying.forum.core.Constants
import top.crazying.forum.core.richtext.RichBlock
import top.crazying.forum.core.richtext.RichDocument
import top.crazying.forum.core.richtext.RichListItem
import top.crazying.forum.core.richtext.RichSpan
import top.crazying.forum.theme.ForumTheme
import top.crazying.forum.ui.components.HDivider

/** 段落块类型（编辑器侧）。 */
enum class BlockKind { PARAGRAPH, H1, H2, H3, BULLET, ORDERED, QUOTE, CODE }

internal data class ParaMeta(val start: Int, val end: Int, val kind: BlockKind)

internal sealed interface EditorUnit {
    data class Text(
        val value: TextFieldValue,
        val types: List<BlockKind>,
        val metas: List<ParaMeta>,
    ) : EditorUnit

    data class Image(val url: String, val alt: String = "") : EditorUnit
    data object Divider : EditorUnit
}

/**
 * 编辑器状态：文档快照、切换块类型、套用行内样式、插入图片/分割线、撤销重做。
 *
 * 文本段（TextUnit）内部是单个 `BasicTextField`，所以跨段选区、中文 IME、
 * 光标/选区手柄都由 Compose 原生处理；图片/分割线是原子段，会把文档切开。
 */
class RichEditorState internal constructor(initial: RichDocument) {

    internal val units = mutableStateListOf<EditorUnit>()
    internal var activeIndex by mutableStateOf(0)

    private data class Snapshot(val units: List<EditorUnit>, val active: Int)
    private val undoStack = ArrayDeque<Snapshot>()
    private val redoStack = ArrayDeque<Snapshot>()
    private var lastPushAt = 0L

    init {
        val initialUnits = fromDocument(initial)
        if (initialUnits.isEmpty()) {
            units.add(emptyTextUnit())
        } else {
            units.addAll(initialUnits)
        }
    }

    val isEmpty: Boolean
        get() = units.all { unit ->
            when (unit) {
                is EditorUnit.Text -> unit.value.text.isBlank()
                else -> false
            }
        }

    val plainTextLength: Int
        get() = units.sumOf { if (it is EditorUnit.Text) it.value.text.length else 0 }

    val canUndo: Boolean get() = undoStack.isNotEmpty()
    val canRedo: Boolean get() = redoStack.isNotEmpty()

    fun toDocument(): RichDocument {
        val blocks = ArrayList<RichBlock>()
        var i = 0
        while (i < units.size) {
            when (val unit = units[i]) {
                is EditorUnit.Image -> {
                    blocks.add(RichBlock.Image(unit.url, unit.alt))
                    i++
                }

                EditorUnit.Divider -> {
                    blocks.add(RichBlock.Divider)
                    i++
                }

                is EditorUnit.Text -> {
                    val paragraphs = unit.value.text.split('\n')
                    val types = unit.types
                    var p = 0
                    while (p < paragraphs.size) {
                        val kind = types.getOrElse(p) { BlockKind.PARAGRAPH }
                        val start = paragraphStart(unit.value.text, p)
                        val end = start + paragraphs[p].length
                        val spans = spansOf(unit.value.annotatedString, start, end)
                        when (kind) {
                            BlockKind.PARAGRAPH -> {
                                blocks.add(RichBlock.Paragraph(spans))
                                p++
                            }

                            BlockKind.H1, BlockKind.H2, BlockKind.H3 -> {
                                val level = when (kind) {
                                    BlockKind.H1 -> 1
                                    BlockKind.H2 -> 2
                                    else -> 3
                                }
                                blocks.add(RichBlock.Heading(level, spans))
                                p++
                            }

                            BlockKind.BULLET, BlockKind.ORDERED -> {
                                val items = ArrayList<RichListItem>()
                                while (p < paragraphs.size) {
                                    val k = types.getOrElse(p) { BlockKind.PARAGRAPH }
                                    if (k != kind) break
                                    val s = paragraphStart(unit.value.text, p)
                                    val e = s + paragraphs[p].length
                                    items.add(RichListItem(listOf(RichBlock.Paragraph(spansOf(unit.value.annotatedString, s, e)))))
                                    p++
                                }
                                blocks.add(
                                    if (kind == BlockKind.BULLET) RichBlock.BulletList(items)
                                    else RichBlock.OrderedList(items),
                                )
                            }

                            BlockKind.QUOTE -> {
                                val quoted = ArrayList<RichBlock>()
                                while (p < paragraphs.size) {
                                    val k = types.getOrElse(p) { BlockKind.PARAGRAPH }
                                    if (k != BlockKind.QUOTE) break
                                    val s = paragraphStart(unit.value.text, p)
                                    val e = s + paragraphs[p].length
                                    quoted.add(RichBlock.Paragraph(spansOf(unit.value.annotatedString, s, e)))
                                    p++
                                }
                                blocks.add(RichBlock.Quote(quoted))
                            }

                            BlockKind.CODE -> {
                                val lines = ArrayList<String>()
                                while (p < paragraphs.size) {
                                    val k = types.getOrElse(p) { BlockKind.PARAGRAPH }
                                    if (k != BlockKind.CODE) break
                                    lines.add(paragraphs[p])
                                    p++
                                }
                                blocks.add(RichBlock.CodeBlock(lines.joinToString("\n")))
                            }
                        }
                    }
                    i++
                }
            }
        }
        return RichDocument(blocks)
    }

    fun toHtml(): String = toDocument().toHtml()

    internal fun pushUndo(force: Boolean = false) {
        val now = System.currentTimeMillis()
        if (!force && now - lastPushAt < 350L) return
        lastPushAt = now
        undoStack.addLast(Snapshot(units.toList(), activeIndex))
        while (undoStack.size > 50) undoStack.removeFirst()
        redoStack.clear()
    }

    fun undo() {
        val snap = undoStack.removeLastOrNull() ?: return
        redoStack.addLast(Snapshot(units.toList(), activeIndex))
        restore(snap)
    }

    fun redo() {
        val snap = redoStack.removeLastOrNull() ?: return
        undoStack.addLast(Snapshot(units.toList(), activeIndex))
        restore(snap)
    }

    private fun restore(snap: Snapshot) {
        units.clear()
        units.addAll(snap.units)
        activeIndex = snap.active.coerceIn(0, (units.size - 1).coerceAtLeast(0))
    }

    internal fun onTextChange(index: Int, newValue: TextFieldValue) {
        val unit = units.getOrNull(index) as? EditorUnit.Text ?: return
        if (newValue.text == unit.value.text) {
            units[index] = unit.copy(value = newValue)
            return
        }
        pushUndo()
        val types = adjustTypes(unit, newValue)
        val metas = buildMetas(newValue.text, types)
        val annotated = rebuild(newValue.annotatedString, newValue.text, metas)
        units[index] = unit.copy(
            value = TextFieldValue(annotated, selection = newValue.selection, composition = newValue.composition),
            types = types,
            metas = metas,
        )
    }

    private fun adjustTypes(unit: EditorUnit.Text, newValue: TextFieldValue): List<BlockKind> {
        val old = unit.types
        val newCount = newValue.text.count { it == '\n' } + 1
        if (newCount == old.size) return old
        val list = old.toMutableList()
        if (newCount > old.size) {
            val at = newValue.text.take(newValue.selection.start.coerceIn(0, newValue.text.length))
                .count { it == '\n' }
                .coerceIn(0, old.size)
            val inherit = old.getOrElse((at - 1).coerceAtLeast(0)) { BlockKind.PARAGRAPH }
            repeat(newCount - old.size) { list.add(at.coerceAtMost(list.size), inherit) }
        } else {
            val at = newValue.text.take(newValue.selection.start.coerceIn(0, newValue.text.length))
                .count { it == '\n' }
                .coerceIn(0, (list.size - 1).coerceAtLeast(0))
            repeat(old.size - newCount) {
                if (list.size > 1) list.removeAt(at.coerceAtMost(list.size - 1))
            }
        }
        while (list.size < newCount) list.add(list.lastOrNull() ?: BlockKind.PARAGRAPH)
        while (list.size > newCount) list.removeAt(list.size - 1)
        return list
    }

    internal fun toggleInline(kind: StyleKind) {
        val index = activeTextIndex()
        val unit = units.getOrNull(index) as? EditorUnit.Text ?: return
        val sel = unit.value.selection
        val start = minOf(sel.start, sel.end)
        val end = maxOf(sel.start, sel.end)
        if (start >= end) return
        val target = spanFor(kind)
        val active = unit.value.annotatedString.spanStyles.any {
            it.start <= start && it.end >= end && sameKind(it.item, target)
        }
        val updated = mutateSpans(unit.value.annotatedString, start, end, target, active)
        pushUndo(force = true)
        units[index] = unit.copy(
            value = TextFieldValue(
                rebuild(updated, unit.value.text, unit.metas),
                selection = unit.value.selection,
            ),
        )
    }

    internal fun applyLink(url: String, linkColor: Color) {
        if (url.isBlank()) return
        val index = activeTextIndex()
        val unit = units.getOrNull(index) as? EditorUnit.Text ?: return
        val sel = unit.value.selection
        val start = minOf(sel.start, sel.end)
        val end = maxOf(sel.start, sel.end)
        if (start >= end) return
        val src = unit.value.annotatedString
        val base = buildAnnotatedString {
            append(src.text)
            for (span in src.spanStyles) addStyle(span.item, span.start, span.end)
            for (ann in src.getStringAnnotations(0, src.length)) {
                if (ann.tag == "link" && ann.start < end && ann.end > start) {
                    if (ann.start < start) addStringAnnotation(ann.tag, ann.item, ann.start, start)
                    if (ann.end > end) addStringAnnotation(ann.tag, ann.item, end, ann.end)
                } else {
                    addStringAnnotation(ann.tag, ann.item, ann.start, ann.end)
                }
            }
            addStringAnnotation("link", url, start, end)
            addStyle(SpanStyle(color = linkColor, textDecoration = TextDecoration.Underline), start, end)
        }
        pushUndo(force = true)
        units[index] = unit.copy(
            value = TextFieldValue(
                rebuild(base, unit.value.text, unit.metas),
                selection = unit.value.selection,
            ),
        )
    }

    private fun spanFor(kind: StyleKind): SpanStyle = when (kind) {
        StyleKind.BOLD -> SpanStyle(fontWeight = FontWeight.Bold)
        StyleKind.ITALIC -> SpanStyle(fontStyle = FontStyle.Italic)
        StyleKind.UNDERLINE -> SpanStyle(textDecoration = TextDecoration.Underline)
        StyleKind.STRIKE -> SpanStyle(textDecoration = TextDecoration.LineThrough)
        StyleKind.CODE -> SpanStyle(fontFamily = FontFamily.Monospace)
    }

    private fun sameKind(a: SpanStyle, b: SpanStyle): Boolean = when {
        b.fontWeight != null -> a.fontWeight == b.fontWeight
        b.fontStyle != null -> a.fontStyle == b.fontStyle
        b.textDecoration != null -> a.textDecoration == b.textDecoration
        b.fontFamily != null -> a.fontFamily == b.fontFamily
        else -> false
    }

    private fun mutateSpans(
        src: AnnotatedString,
        start: Int,
        end: Int,
        target: SpanStyle,
        remove: Boolean,
    ): AnnotatedString {
        val b = buildAnnotatedString {
            append(src.text)
            for (span in src.spanStyles) {
                if (sameKind(span.item, target)) {
                    if (span.end <= start || span.start >= end) {
                        addStyle(span.item, span.start, span.end)
                    } else {
                        if (span.start < start) addStyle(span.item, span.start, start)
                        if (span.end > end) addStyle(span.item, end, span.end)
                    }
                } else {
                    addStyle(span.item, span.start, span.end)
                }
            }
            for (ann in src.getStringAnnotations(0, src.length)) {
                addStringAnnotation(ann.tag, ann.item, ann.start, ann.end)
            }
            if (!remove) addStyle(target, start, end)
        }
        return b
    }

    internal fun setBlockKind(kind: BlockKind) {
        val index = activeTextIndex()
        val unit = units.getOrNull(index) as? EditorUnit.Text ?: return
        val sel = unit.value.selection
        val start = minOf(sel.start, sel.end)
        val end = maxOf(sel.start, sel.end)
        val first = unit.value.text.take(start).count { it == '\n' }
        val last = unit.value.text.take(end).count { it == '\n' }
        val types = unit.types.toMutableList()
        for (p in first..last.coerceAtMost(types.size - 1)) types[p] = kind
        pushUndo(force = true)
        val metas = buildMetas(unit.value.text, types)
        units[index] = unit.copy(
            value = TextFieldValue(rebuild(unit.value.annotatedString, unit.value.text, metas), unit.value.selection),
            types = types,
            metas = metas,
        )
    }

    internal fun activeTextIndex(): Int {
        val idx = activeIndex.coerceIn(0, (units.size - 1).coerceAtLeast(0))
        if (units.getOrNull(idx) is EditorUnit.Text) return idx
        for (i in units.indices) if (units[i] is EditorUnit.Text) return i
        return -1
    }

    internal fun unitAt(index: Int): EditorUnit? = units.getOrNull(index)

    internal fun replaceUnit(index: Int, unit: EditorUnit) {
        if (index in units.indices) units[index] = unit
    }

    internal fun appendTextUnitIfNeeded(): Int {
        val idx = activeTextIndex()
        if (idx >= 0) return idx
        units.add(emptyTextUnit())
        activeIndex = units.lastIndex
        return units.lastIndex
    }

    fun insertImage(url: String, alt: String = "") {
        if (url.isBlank()) return
        insertAtomic(EditorUnit.Image(url, alt))
    }

    internal fun insertDivider() {
        insertAtomic(EditorUnit.Divider)
    }

    private fun insertAtomic(atomic: EditorUnit) {
        pushUndo(force = true)
        val idx = activeTextIndex()
        if (idx < 0) {
            units.add(atomic)
            units.add(emptyTextUnit())
            activeIndex = units.lastIndex
            return
        }
        val unit = units[idx] as EditorUnit.Text
        val pos = unit.value.selection.max.coerceIn(0, unit.value.text.length)
        val paragraph = unit.value.text.take(pos).count { it == '\n' }
        val leftText = unit.value.text.substring(0, pos)
        val rightText = unit.value.text.substring(pos)
        val leftTypes = unit.types.take((paragraph + 1).coerceAtMost(unit.types.size))
        val rightTypes = if (rightText.isEmpty()) emptyList() else {
            listOf(unit.types.getOrElse(paragraph) { BlockKind.PARAGRAPH }) +
                unit.types.drop((paragraph + 1).coerceAtMost(unit.types.size))
        }
        val leftAnnotated = unit.value.annotatedString.subSequence(0, pos)
        val rightAnnotated = unit.value.annotatedString.subSequence(pos, unit.value.annotatedString.length)

        val replacement = ArrayList<EditorUnit>()
        if (leftText.isNotEmpty()) {
            replacement.add(
                EditorUnit.Text(
                    value = TextFieldValue(
                        rebuild(leftAnnotated, leftText, buildMetas(leftText, leftTypes)),
                        selection = TextRange(leftText.length),
                    ),
                    types = leftTypes,
                    metas = buildMetas(leftText, leftTypes),
                ),
            )
        }
        replacement.add(atomic)
        if (rightText.isNotEmpty()) {
            replacement.add(
                EditorUnit.Text(
                    value = TextFieldValue(
                        rebuild(rightAnnotated, rightText, buildMetas(rightText, rightTypes)),
                        selection = TextRange(0),
                    ),
                    types = rightTypes,
                    metas = buildMetas(rightText, rightTypes),
                ),
            )
        }
        if (replacement.none { it is EditorUnit.Text }) replacement.add(emptyTextUnit())
        units.removeAt(idx)
        units.addAll(idx, replacement)
        activeIndex = units.indexOfLast { it is EditorUnit.Text }.coerceAtLeast(0)
    }

    private fun emptyTextUnit(): EditorUnit.Text = EditorUnit.Text(
        value = TextFieldValue(AnnotatedString(""), selection = TextRange(0)),
        types = listOf(BlockKind.PARAGRAPH),
        metas = listOf(ParaMeta(0, 0, BlockKind.PARAGRAPH)),
    )

    private fun fromDocument(doc: RichDocument): List<EditorUnit> {
        val out = ArrayList<EditorUnit>()
        val text = StringBuilder()
        val types = ArrayList<BlockKind>()
        var first = true

        fun flushText() {
            if (text.isEmpty() && types.isEmpty()) return
            val value = TextFieldValue(AnnotatedString(text.toString()), selection = TextRange(0))
            out.add(EditorUnit.Text(value, types.toList(), buildMetas(text.toString(), types)))
            text.clear()
            types.clear()
            first = true
        }

        fun addParagraph(textValue: String, kind: BlockKind) {
            if (!first) text.append('\n')
            text.append(textValue)
            types.add(kind)
            first = false
        }

        fun walk(block: RichBlock) {
            when (block) {
                is RichBlock.Paragraph -> {
                    flushText()
                    addParagraph(block.spans.joinToString("") { it.text }, BlockKind.PARAGRAPH)
                }

                is RichBlock.Heading -> {
                    flushText()
                    addParagraph(
                        block.spans.joinToString("") { it.text },
                        when (block.level) {
                            1 -> BlockKind.H1
                            2 -> BlockKind.H2
                            else -> BlockKind.H3
                        },
                    )
                }

                is RichBlock.BulletList -> {
                    flushText()
                    block.items.forEach { item ->
                        addParagraph(item.blocks.filterIsInstance<RichBlock.Paragraph>().joinToString(" ") { it.spans.joinToString("") { s -> s.text } }, BlockKind.BULLET)
                    }
                }

                is RichBlock.OrderedList -> {
                    flushText()
                    block.items.forEach { item ->
                        addParagraph(item.blocks.filterIsInstance<RichBlock.Paragraph>().joinToString(" ") { it.spans.joinToString("") { s -> s.text } }, BlockKind.ORDERED)
                    }
                }

                is RichBlock.Quote -> {
                    flushText()
                    block.blocks.forEach { inner ->
                        if (inner is RichBlock.Paragraph) {
                            addParagraph(inner.spans.joinToString("") { it.text }, BlockKind.QUOTE)
                        }
                    }
                }

                is RichBlock.CodeBlock -> {
                    flushText()
                    block.text.split('\n').forEach { line -> addParagraph(line, BlockKind.CODE) }
                }

                is RichBlock.Image -> {
                    flushText()
                    out.add(EditorUnit.Image(block.url, block.alt))
                }

                RichBlock.Divider -> {
                    flushText()
                    out.add(EditorUnit.Divider)
                }

                is RichBlock.Embed -> Unit
            }
        }
        doc.blocks.forEach { walk(it) }
        flushText()
        return out
    }

    private fun buildMetas(text: String, types: List<BlockKind>): List<ParaMeta> {
        val out = ArrayList<ParaMeta>()
        var start = 0
        for (i in types.indices) {
            val end = if (i < types.size - 1) {
                val nl = text.indexOf('\n', start)
                if (nl < 0) text.length else nl
            } else text.length
            out.add(ParaMeta(start, end, types[i]))
            start = end + 1
        }
        return out
    }

    private fun rebuild(value: AnnotatedString, text: String, metas: List<ParaMeta>): AnnotatedString = buildAnnotatedString {
        append(text)
        for (span in value.spanStyles) {
            val start = span.start.coerceIn(0, text.length)
            val end = span.end.coerceIn(start, text.length)
            if (start < end) addStyle(span.item, start, end)
        }
        for (ann in value.getStringAnnotations(0, value.length)) {
            val start = ann.start.coerceIn(0, text.length)
            val end = ann.end.coerceIn(start, text.length)
            if (start < end) addStringAnnotation(ann.tag, ann.item, start, end)
        }
        for (meta in metas) {
            val start = meta.start.coerceIn(0, text.length)
            val end = meta.end.coerceIn(start, text.length)
            if (start >= end) continue
            val paragraph = ParagraphStyle(
                textIndent = when (meta.kind) {
                    BlockKind.BULLET, BlockKind.ORDERED -> TextIndent(firstLine = 20.sp, restLine = 20.sp)
                    BlockKind.QUOTE, BlockKind.CODE -> TextIndent(firstLine = 12.sp, restLine = 12.sp)
                    else -> TextIndent(firstLine = 0.sp, restLine = 0.sp)
                },
                lineHeight = if (meta.kind == BlockKind.CODE) 20.sp else 24.sp,
            )
            addStyle(paragraph, start, end)
            val span = when (meta.kind) {
                BlockKind.H1 -> SpanStyle(fontSize = 23.sp, fontWeight = FontWeight.Bold)
                BlockKind.H2 -> SpanStyle(fontSize = 20.sp, fontWeight = FontWeight.Bold)
                BlockKind.H3 -> SpanStyle(fontSize = 18.sp, fontWeight = FontWeight.Bold)
                BlockKind.CODE -> SpanStyle(fontFamily = FontFamily.Monospace)
                else -> null
            }
            if (span != null) addStyle(span, start, end)
        }
    }

    private fun paragraphStart(text: String, index: Int): Int {
        if (index <= 0) return 0
        var p = 0
        var at = 0
        while (p < index) {
            val nl = text.indexOf('\n', at)
            if (nl < 0) return text.length
            at = nl + 1
            p++
        }
        return at
    }

    private fun spansOf(annotated: AnnotatedString, start: Int, end: Int): List<RichSpan> {
        if (start >= end) return emptyList()
        val points = sortedSetOf(start, end)
        for (span in annotated.spanStyles) {
            if (span.start < end && span.end > start) {
                points.add(span.start.coerceIn(start, end))
                points.add(span.end.coerceIn(start, end))
            }
        }
        val links = annotated.getStringAnnotations("link", start, end)
        for (link in links) {
            points.add(link.start.coerceIn(start, end))
            points.add(link.end.coerceIn(start, end))
        }
        val out = ArrayList<RichSpan>()
        val pts = points.toList()
        for (i in 0 until pts.size - 1) {
            val a = pts[i]
            val b = pts[i + 1]
            if (a >= b) continue
            var bold = false
            var italic = false
            var underline = false
            var strike = false
            var code = false
            for (span in annotated.spanStyles) {
                if (span.start <= a && span.end >= b) {
                    if (span.item.fontWeight == FontWeight.Bold) bold = true
                    if (span.item.fontStyle == FontStyle.Italic) italic = true
                    val deco = span.item.textDecoration
                    if (deco != null) {
                        if (deco.contains(TextDecoration.Underline)) underline = true
                        if (deco.contains(TextDecoration.LineThrough)) strike = true
                    }
                    if (span.item.fontFamily == FontFamily.Monospace) code = true
                }
            }
            val link = links.firstOrNull { it.start <= a && it.end >= b }?.item
            out.add(
                RichSpan(
                    text = annotated.text.substring(a, b),
                    bold = bold,
                    italic = italic,
                    underline = underline,
                    strike = strike,
                    code = code,
                    link = link,
                ),
            )
        }
        return mergeSpans(out)
    }

    private fun mergeSpans(spans: List<RichSpan>): List<RichSpan> {
        if (spans.size <= 1) return spans
        val out = ArrayList<RichSpan>(spans.size)
        for (span in spans) {
            val prev = out.lastOrNull()
            if (prev != null && prev.copy(text = "") == span.copy(text = "")) {
                out[out.size - 1] = prev.copy(text = prev.text + span.text)
            } else {
                out.add(span)
            }
        }
        return out
    }
}

@Composable
fun rememberRichEditorState(initial: RichDocument = RichDocument.EMPTY): RichEditorState =
    remember { RichEditorState(initial) }

@Composable
fun RichTextEditor(
    state: RichEditorState,
    modifier: Modifier = Modifier,
    placeholder: String = "说点什么…",
    minHeight: Dp = 260.dp,
    onPickImage: (() -> Unit)? = null,
) {
    val colors = ForumTheme.colors
    var linkDialog by remember { mutableStateOf(false) }

    Column(modifier = modifier.fillMaxWidth()) {
        EditorToolbar(
            state = state,
            onPickImage = onPickImage,
            onLink = { linkDialog = true },
        )
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .heightIn(min = minHeight)
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 12.dp, vertical = 10.dp),
        ) {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (state.isEmpty) {
                    Text(
                        text = placeholder,
                        color = colors.textMuted,
                        fontSize = 14.sp,
                        modifier = Modifier.padding(bottom = 4.dp),
                    )
                }
                state.units.forEachIndexed { index, unit ->
                    when (unit) {
                        is EditorUnit.Text -> TextUnitView(state, index, unit)
                        is EditorUnit.Image -> ImageUnitView(state, index, unit)
                        EditorUnit.Divider -> DividerUnitView(state, index)
                    }
                }
            }
        }
    }

    if (linkDialog) {
        LinkDialog(
            onDismiss = { linkDialog = false },
            onConfirm = { url ->
                linkDialog = false
                state.applyLink(url, colors.primary)
            },
        )
    }
}

@Composable
private fun TextUnitView(state: RichEditorState, index: Int, unit: EditorUnit.Text) {
    val colors = ForumTheme.colors
    var layout by remember { mutableStateOf<TextLayoutResult?>(null) }
    BasicTextField(
        value = unit.value,
        onValueChange = { state.onTextChange(index, it) },
        textStyle = TextStyle(
            color = colors.textPrimary,
            fontSize = 15.sp,
            lineHeight = 24.sp,
        ),
        cursorBrush = SolidColor(colors.primary),
        onTextLayout = { layout = it },
        modifier = Modifier
            .fillMaxWidth()
            .onFocusChanged { if (it.isFocused) state.activeIndex = index },
        decorationBox = { inner ->
            Box {
                val l = layout
                if (l != null) {
                    Canvas(Modifier.matchParentSize()) {
                        drawDecorations(l, unit.metas, colors, this)
                    }
                }
                inner()
            }
        },
    )
}

private fun drawDecorations(
    layout: TextLayoutResult,
    metas: List<ParaMeta>,
    colors: top.crazying.forum.theme.ForumColors,
    scope: androidx.compose.ui.graphics.drawscope.DrawScope,
) {
    val paint = Paint().apply {
        isAntiAlias = true
        textSize = with(scope) { 14.sp.toPx() }
        color = colors.primary.toArgb()
    }
    for (meta in metas) {
        if (meta.start >= meta.end) continue
        val firstLine = layout.getLineForOffset(meta.start.coerceIn(0, layout.layoutInput.text.length))
        val lastLine = layout.getLineForOffset((meta.end - 1).coerceIn(0, layout.layoutInput.text.length))
        if (firstLine < 0 || lastLine < 0) continue
        val top = layout.getLineTop(firstLine)
        val bottom = layout.getLineBottom(lastLine)
        when (meta.kind) {
            BlockKind.QUOTE -> {
                scope.drawRect(
                    color = colors.bgInput,
                    topLeft = Offset(0f, top),
                    size = Size(scope.size.width, (bottom - top).coerceAtLeast(1f)),
                )
                scope.drawRect(
                    color = colors.primary.copy(alpha = 0.55f),
                    topLeft = Offset(0f, top),
                    size = Size(with(scope) { 3.dp.toPx() }, (bottom - top).coerceAtLeast(1f)),
                )
            }

            BlockKind.CODE -> scope.drawRoundRect(
                color = colors.bgInput,
                topLeft = Offset(0f, top),
                size = Size(scope.size.width, (bottom - top).coerceAtLeast(1f)),
                cornerRadius = CornerRadius(with(scope) { 8.dp.toPx() }),
            )

            BlockKind.BULLET -> scope.drawCircle(
                color = colors.primary,
                radius = with(scope) { 2.5.dp.toPx() },
                center = Offset(with(scope) { 8.dp.toPx() }, top + (bottom - top) / 2f),
            )

            BlockKind.ORDERED -> {
                // 序号用 nativeCanvas 画，避免为每个列表项额外建 Compose 节点。
                val text = "•"
                scope.drawContext.canvas.nativeCanvas.drawText(
                    text,
                    with(scope) { 4.dp.toPx() },
                    top + (bottom - top) / 2f + paint.textSize / 3f,
                    paint,
                )
            }

            else -> Unit
        }
    }
}

@Composable
private fun ImageUnitView(state: RichEditorState, index: Int, unit: EditorUnit.Image) {
    val colors = ForumTheme.colors
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(10.dp))
            .background(colors.bgInput)
            .padding(6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        AsyncImage(
            model = Constants.absolute(unit.url),
            contentDescription = unit.alt.ifBlank { "正文图片" },
            modifier = Modifier
                .weight(1f)
                .height(140.dp)
                .clip(RoundedCornerShape(8.dp)),
        )
        Text(
            text = "删除",
            color = colors.danger,
            fontSize = 12.sp,
            modifier = Modifier
                .padding(horizontal = 10.dp)
                .clickable {
                    state.pushUndo(force = true)
                    state.units.removeAt(index)
                    if (state.units.none { it is EditorUnit.Text }) state.units.add(EditorUnit.Text(
                        value = TextFieldValue(AnnotatedString(""), selection = TextRange(0)),
                        types = listOf(BlockKind.PARAGRAPH),
                        metas = listOf(ParaMeta(0, 0, BlockKind.PARAGRAPH)),
                    ))
                },
        )
    }
}

@Composable
private fun DividerUnitView(state: RichEditorState, index: Int) {
    val colors = ForumTheme.colors
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(modifier = Modifier.weight(1f)) { HDivider() }
        Text(
            text = "删除",
            color = colors.danger,
            fontSize = 12.sp,
            modifier = Modifier
                .padding(horizontal = 10.dp)
                .clickable {
                    state.pushUndo(force = true)
                    state.units.removeAt(index)
                },
        )
    }
}

@Composable
private fun EditorToolbar(
    state: RichEditorState,
    onPickImage: (() -> Unit)?,
    onLink: () -> Unit,
) {
    val colors = ForumTheme.colors
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(colors.bgHeader)
            .horizontalScroll(rememberScrollState())
            .padding(horizontal = 8.dp, vertical = 6.dp),
        horizontalArrangement = Arrangement.spacedBy(4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        ToolButton("B") { state.toggleInline(StyleKind.BOLD) }
        ToolButton("I") { state.toggleInline(StyleKind.ITALIC) }
        ToolButton("U") { state.toggleInline(StyleKind.UNDERLINE) }
        ToolButton("S") { state.toggleInline(StyleKind.STRIKE) }
        ToolButton("</>") { state.toggleInline(StyleKind.CODE) }
        ToolButton("链接") { onLink() }
        ToolDivider()
        ToolButton("H1") { state.setBlockKind(BlockKind.H1) }
        ToolButton("H2") { state.setBlockKind(BlockKind.H2) }
        ToolButton("H3") { state.setBlockKind(BlockKind.H3) }
        ToolButton("正文") { state.setBlockKind(BlockKind.PARAGRAPH) }
        ToolDivider()
        ToolButton("• 列表") { state.setBlockKind(BlockKind.BULLET) }
        ToolButton("1. 列表") { state.setBlockKind(BlockKind.ORDERED) }
        ToolButton("引用") { state.setBlockKind(BlockKind.QUOTE) }
        ToolButton("代码块") { state.setBlockKind(BlockKind.CODE) }
        ToolDivider()
        ToolButton("分割线") { state.insertDivider() }
        if (onPickImage != null) ToolButton("图片") { onPickImage() }
        ToolDivider()
        ToolButton("撤销") { state.undo() }
        ToolButton("重做") { state.redo() }
    }
}

@Composable
private fun ToolButton(text: String, onClick: () -> Unit) {
    val colors = ForumTheme.colors
    Text(
        text = text,
        color = colors.textSecondary,
        fontSize = 12.sp,
        modifier = Modifier
            .clip(RoundedCornerShape(7.dp))
            .background(colors.bgInput)
            .clickable { onClick() }
            .padding(horizontal = 8.dp, vertical = 6.dp),
    )
}

@Composable
private fun ToolDivider() {
    val colors = ForumTheme.colors
    Box(
        modifier = Modifier
            .width(1.dp)
            .height(20.dp)
            .background(colors.border),
    )
}

@Composable
private fun LinkDialog(onDismiss: () -> Unit, onConfirm: (String) -> Unit) {
    var url by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("插入链接") },
        text = {
            OutlinedTextField(
                value = url,
                onValueChange = { url = it },
                singleLine = true,
                placeholder = { Text("https://…") },
            )
        },
        confirmButton = {
            TextButton(
                onClick = { onConfirm(url.trim()) },
                enabled = url.trim().isNotEmpty(),
            ) { Text("确定") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("取消") } },
    )
}

enum class StyleKind { BOLD, ITALIC, UNDERLINE, STRIKE, CODE }
