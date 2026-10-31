package top.crazying.forum.ui.richtext

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.LinkAnnotation
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextLinkStyles
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil3.compose.AsyncImage
import top.crazying.forum.core.Constants
import top.crazying.forum.core.richtext.RichBlock
import top.crazying.forum.core.richtext.RichDocument
import top.crazying.forum.core.richtext.RichListItem
import top.crazying.forum.core.richtext.RichSpan
import top.crazying.forum.theme.ForumColors
import top.crazying.forum.theme.ForumTheme
import top.crazying.forum.ui.components.Avatar
import top.crazying.forum.ui.components.HDivider

/**
 * 富文本只读渲染器。
 *
 * 与编辑器共用 `RichDocument`：正文/评论/世界频道都走这里。
 * `compact` 用于评论与世界频道（更小字号、更紧凑间距）。
 */
@Composable
fun RichTextView(
    doc: RichDocument,
    modifier: Modifier = Modifier,
    compact: Boolean = false,
    onEmbedClick: ((RichBlock.Embed) -> Unit)? = null,
) {
    val colors = ForumTheme.colors
    val uriHandler = LocalUriHandler.current
    val embeds = remember(doc) { collectEmbeds(doc) }
    var embedMap by remember(doc) { mutableStateOf<Map<String, EmbedData>>(emptyMap()) }
    LaunchedEffect(doc) {
        if (embeds.isNotEmpty()) embedMap = EmbedsStore.load(embeds)
    }

    Column(
        modifier = modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(if (compact) 7.dp else 10.dp),
    ) {
        for (block in doc.blocks) {
            RichBlockView(
                block = block,
                colors = colors,
                compact = compact,
                embedMap = embedMap,
                onEmbedClick = { embed ->
                    if (onEmbedClick != null) {
                        onEmbedClick(embed)
                    } else {
                        val data = embedMap[EmbedsStore.key(embed.type, embed.id)]
                        val url = data?.url ?: when (embed.type) {
                            "user" -> "/user/${embed.id}"
                            "post" -> "/post/${embed.id}"
                            "article" -> "/article/${embed.id}"
                            else -> ""
                        }
                        if (url.isNotBlank()) runCatching { uriHandler.openUri(Constants.absolute(url)) }
                    }
                },
            )
        }
    }
}

@Composable
private fun RichBlockView(
    block: RichBlock,
    colors: ForumColors,
    compact: Boolean,
    embedMap: Map<String, EmbedData>,
    onEmbedClick: (RichBlock.Embed) -> Unit,
) {
    when (block) {
        is RichBlock.Paragraph -> RichSpansText(
            spans = block.spans,
            colors = colors,
            compact = compact,
            style = TextStyle(fontSize = if (compact) 14.sp else 15.sp, lineHeight = if (compact) 21.sp else 24.sp),
        )

        is RichBlock.Heading -> RichSpansText(
            spans = block.spans,
            colors = colors,
            compact = compact,
            style = TextStyle(
                fontSize = when (block.level.coerceIn(1, 4)) {
                    1 -> if (compact) 18.sp else 23.sp
                    2 -> if (compact) 17.sp else 20.sp
                    3 -> if (compact) 16.sp else 18.sp
                    else -> if (compact) 15.sp else 16.sp
                },
                lineHeight = if (compact) 24.sp else 30.sp,
                fontWeight = FontWeight.Bold,
            ),
        )

        is RichBlock.BulletList -> RichListView(
            items = block.items,
            ordered = false,
            colors = colors,
            compact = compact,
            embedMap = embedMap,
            onEmbedClick = onEmbedClick,
        )

        is RichBlock.OrderedList -> RichListView(
            items = block.items,
            ordered = true,
            colors = colors,
            compact = compact,
            embedMap = embedMap,
            onEmbedClick = onEmbedClick,
        )

        is RichBlock.Quote -> Row(
            modifier = Modifier
                .fillMaxWidth()
                .height(IntrinsicSize.Min)
                .clip(RoundedCornerShape(8.dp))
                .background(colors.bgInput),
        ) {
            Box(
                modifier = Modifier
                    .width(3.dp)
                    .fillMaxHeight()
                    .background(colors.primary.copy(alpha = 0.55f)),
            )
            Column(
                modifier = Modifier
                    .weight(1f)
                    .padding(horizontal = 10.dp, vertical = 8.dp),
                verticalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                for (inner in block.blocks) {
                    RichBlockView(inner, colors, compact, embedMap, onEmbedClick)
                }
            }
        }

        is RichBlock.CodeBlock -> Box(
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(8.dp))
                .background(colors.bgInput)
                .padding(10.dp),
        ) {
            Text(
                text = block.text,
                color = colors.textPrimary,
                fontFamily = FontFamily.Monospace,
                fontSize = if (compact) 12.sp else 13.sp,
                lineHeight = if (compact) 18.sp else 20.sp,
                softWrap = false,
                modifier = Modifier.horizontalScroll(rememberScrollState()),
            )
        }

        is RichBlock.Image -> AsyncImage(
            model = Constants.absolute(block.url),
            contentDescription = block.alt.ifBlank { "正文图片" },
            contentScale = ContentScale.FillWidth,
            modifier = Modifier
                .fillMaxWidth()
                .heightIn(max = if (compact) 220.dp else 420.dp)
                .clip(RoundedCornerShape(10.dp))
                .background(colors.bgInput),
        )

        RichBlock.Divider -> HDivider()

        is RichBlock.Embed -> EmbedCard(
            embed = block,
            data = embedMap[EmbedsStore.key(block.type, block.id)],
            colors = colors,
            compact = compact,
            onClick = { onEmbedClick(block) },
        )
    }
}

@Composable
private fun RichSpansText(
    spans: List<RichSpan>,
    colors: ForumColors,
    compact: Boolean,
    style: TextStyle,
) {
    if (spans.isEmpty()) return
    val text = remember(spans, colors) { buildAnnotated(spans, colors) }
    Text(
        text = text,
        color = colors.textPrimary,
        fontSize = style.fontSize,
        lineHeight = style.lineHeight,
        fontWeight = style.fontWeight,
        modifier = Modifier.fillMaxWidth(),
    )
}

@Composable
private fun RichListView(
    items: List<RichListItem>,
    ordered: Boolean,
    colors: ForumColors,
    compact: Boolean,
    embedMap: Map<String, EmbedData>,
    onEmbedClick: (RichBlock.Embed) -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(if (compact) 4.dp else 6.dp)) {
        items.forEachIndexed { index, item ->
            Row(modifier = Modifier.fillMaxWidth()) {
                Text(
                    text = if (ordered) "${index + 1}." else "•",
                    color = colors.primary,
                    fontSize = if (compact) 13.sp else 14.sp,
                    lineHeight = if (compact) 20.sp else 22.sp,
                    modifier = Modifier.width(if (ordered) 24.dp else 16.dp),
                )
                Column(
                    modifier = Modifier.weight(1f),
                    verticalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    for (inner in item.blocks) {
                        RichBlockView(inner, colors, compact, embedMap, onEmbedClick)
                    }
                }
            }
        }
    }
}

@Composable
private fun EmbedCard(
    embed: RichBlock.Embed,
    data: EmbedData?,
    colors: ForumColors,
    compact: Boolean,
    onClick: () -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(10.dp))
            .background(colors.bgInput)
            .clickable { onClick() }
            .padding(horizontal = 10.dp, vertical = 9.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Avatar(data?.avatar.orEmpty(), if (compact) 28.dp else 34.dp)
        Spacer(Modifier.width(9.dp))
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = data?.title ?: "引用内容",
                color = colors.textPrimary,
                fontSize = if (compact) 13.sp else 14.sp,
                fontWeight = FontWeight.Medium,
                maxLines = 1,
            )
            val subtitle = data?.subtitle.orEmpty()
            Text(
                text = if (subtitle.isNotBlank()) subtitle else "点击查看",
                color = colors.textMuted,
                fontSize = 11.sp,
                maxLines = 1,
            )
        }
        Text("›", color = colors.textMuted, fontSize = 16.sp)
    }
}

private fun buildAnnotated(spans: List<RichSpan>, colors: ForumColors): AnnotatedString = buildAnnotatedString {
    for (span in spans) {
        if (span.text.isEmpty()) continue
        val start = length
        val decorations = buildList {
            if (span.underline) add(TextDecoration.Underline)
            if (span.strike) add(TextDecoration.LineThrough)
        }
        val style = SpanStyle(
            fontWeight = if (span.bold) FontWeight.Bold else null,
            fontStyle = if (span.italic) FontStyle.Italic else null,
            textDecoration = if (decorations.isEmpty()) null else TextDecoration.combine(decorations),
            fontFamily = if (span.code) FontFamily.Monospace else null,
            background = if (span.code) colors.bgInput else Color.Unspecified,
            color = if (!span.link.isNullOrBlank()) colors.primary else Color.Unspecified,
        )
        withStyle(style) { append(span.text) }
        val link = span.link?.trim().orEmpty()
        if (link.isNotEmpty()) {
            addLink(
                LinkAnnotation.Url(
                    url = link,
                    styles = TextLinkStyles(
                        style = SpanStyle(color = colors.primary, textDecoration = TextDecoration.Underline),
                    ),
                ),
                start = start,
                end = length,
            )
        }
    }
}

private fun collectEmbeds(doc: RichDocument): List<RichBlock.Embed> {
    val out = ArrayList<RichBlock.Embed>()
    fun walk(block: RichBlock) {
        when (block) {
            is RichBlock.Embed -> out.add(block)
            is RichBlock.Quote -> block.blocks.forEach { walk(it) }
            is RichBlock.BulletList -> block.items.forEach { item -> item.blocks.forEach { walk(it) } }
            is RichBlock.OrderedList -> block.items.forEach { item -> item.blocks.forEach { walk(it) } }
            else -> Unit
        }
    }
    doc.blocks.forEach { walk(it) }
    return out
}
