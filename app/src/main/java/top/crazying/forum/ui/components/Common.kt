package top.crazying.forum.ui.components

import android.content.Context
import android.text.method.LinkMovementMethod
import android.widget.TextView
import android.widget.Toast
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.text.HtmlCompat
import coil3.compose.AsyncImage
import top.crazying.forum.core.MarkdownBody
import top.crazying.forum.core.TimeFmt
import top.crazying.forum.data.Post
import top.crazying.forum.theme.ForumTheme

/** 轻提示（底部 Toast），用于提交成功/失败反馈。 */
fun toast(context: Context, message: String) {
    if (message.isBlank()) return
    Toast.makeText(context, message, Toast.LENGTH_SHORT).show()
}

// ────────────────── 基础容器 ──────────────────

@Composable
fun ForumCard(
    modifier: Modifier = Modifier,
    content: @Composable () -> Unit,
) {
    val colors = ForumTheme.colors
    Box(
        modifier = modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .background(colors.bgCard)
            .border(1.dp, colors.border, RoundedCornerShape(12.dp))
            .padding(14.dp),
    ) {
        content()
    }
}

@Composable
fun SectionTitle(text: String, modifier: Modifier = Modifier) {
    Text(
        text = text,
        color = ForumTheme.colors.textPrimary,
        fontSize = 16.sp,
        fontWeight = FontWeight.SemiBold,
        modifier = modifier,
    )
}

@Composable
fun Muted(text: String, modifier: Modifier = Modifier, maxLines: Int = 2) {
    Text(
        text = text,
        color = ForumTheme.colors.textMuted,
        fontSize = 12.sp,
        maxLines = maxLines,
        overflow = TextOverflow.Ellipsis,
        modifier = modifier,
    )
}

@Composable
fun HDivider(modifier: Modifier = Modifier) {
    Box(
        modifier = modifier
            .fillMaxWidth()
            .height(1.dp)
            .background(ForumTheme.colors.borderDivider),
    )
}

/** 小圆角标签（分类 / 状态）。 */
@Composable
fun Pill(
    text: String,
    active: Boolean = false,
    modifier: Modifier = Modifier,
    // 注意：onClick 必须是最后一个参数。否则 `Pill("x", active = true) { ... }`
    // 的尾随 lambda 会绑定到 modifier 而编译失败。
    onClick: (() -> Unit)? = null,
) {
    val colors = ForumTheme.colors
    val bg = if (active) colors.primary else colors.bgItemActive
    val fg = if (active) colors.primaryText else colors.textSecondary
    Box(
        modifier = modifier
            .clip(RoundedCornerShape(50))
            .background(bg)
            .then(if (onClick != null) Modifier.clickable { onClick() } else Modifier)
            .padding(horizontal = 12.dp, vertical = 6.dp),
    ) {
        Text(text = text, color = fg, fontSize = 12.sp, maxLines = 1)
    }
}

/** 主按钮（实心）。 */
@Composable
fun PrimaryButton(
    text: String,
    onClick: () -> Unit,
    enabled: Boolean = true,
    modifier: Modifier = Modifier,
) {
    val colors = ForumTheme.colors
    Box(
        modifier = modifier
            .clip(RoundedCornerShape(10.dp))
            .background(if (enabled) colors.primary else colors.bgItemActive)
            .clickable(enabled = enabled) { onClick() }
            .padding(horizontal = 16.dp, vertical = 11.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = text,
            color = if (enabled) colors.primaryText else colors.textMuted,
            fontSize = 14.sp,
            fontWeight = FontWeight.Medium,
        )
    }
}

/** 次级按钮（描边）。 */
@Composable
fun GhostButton(
    text: String,
    onClick: () -> Unit,
    enabled: Boolean = true,
    tint: Color? = null,
    modifier: Modifier = Modifier,
) {
    val colors = ForumTheme.colors
    val fg = tint ?: colors.textSecondary
    Box(
        modifier = modifier
            .clip(RoundedCornerShape(10.dp))
            .border(1.dp, colors.border, RoundedCornerShape(10.dp))
            .clickable(enabled = enabled) { onClick() }
            .padding(horizontal = 14.dp, vertical = 10.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(text = text, color = fg, fontSize = 13.sp)
    }
}

/** 头像：圆角方块（与 Web 端卡片头像风格一致）。 */
@Composable
fun Avatar(
    url: String?,
    size: Dp = 36.dp,
    shape: androidx.compose.ui.graphics.Shape = CircleShape,
    onClick: (() -> Unit)? = null,
) {
    val colors = ForumTheme.colors
    Box(
        modifier = Modifier
            .size(size)
            .clip(shape)
            .background(colors.bgItemActive)
            .then(if (onClick != null) Modifier.clickable { onClick() } else Modifier),
        contentAlignment = Alignment.Center,
    ) {
        if (url.isNullOrBlank()) {
            Text("猫", color = colors.textMuted, fontSize = (size.value / 2.4f).sp)
        } else {
            AsyncImage(
                model = top.crazying.forum.core.Constants.absolute(url),
                contentDescription = null,
                contentScale = ContentScale.Crop,
                modifier = Modifier.fillMaxSize(),
            )
        }
    }
}

// ────────────────── 状态占位 ──────────────────

@Composable
fun LoadingBox(modifier: Modifier = Modifier, text: String = "加载中…") {
    val colors = ForumTheme.colors
    Column(
        modifier = modifier.fillMaxWidth().padding(vertical = 40.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        CircularProgressIndicator(color = colors.primary, strokeWidth = 3.dp)
        Text(text, color = colors.textMuted, fontSize = 13.sp)
    }
}

@Composable
fun EmptyBox(text: String = "暂无内容", modifier: Modifier = Modifier) {
    Box(
        modifier = modifier.fillMaxWidth().padding(vertical = 48.dp, horizontal = 20.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(text, color = ForumTheme.colors.textMuted, fontSize = 13.sp, textAlign = TextAlign.Center)
    }
}

@Composable
fun ErrorBox(message: String, onRetry: (() -> Unit)? = null, modifier: Modifier = Modifier) {
    val colors = ForumTheme.colors
    Column(
        modifier = modifier.fillMaxWidth().padding(vertical = 40.dp, horizontal = 20.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(
            text = message.ifBlank { "加载失败" },
            color = colors.danger,
            fontSize = 13.sp,
            textAlign = TextAlign.Center,
        )
        if (onRetry != null) GhostButton(text = "重试", onClick = onRetry)
    }
}

// ────────────────── HTML 正文 ──────────────────

/**
 * HTML → 富文本（**仅供可信的自有 HTML**：wiki README、彩蛋文本等）。
 *
 * 用户内容的正文一律走 [MarkdownBodyView]，不要用本函数 —— 三端口径是
 * 「不渲染 HTML 语法」，正文里的 HTML 标签必须按字面文字展示。
 */
@Composable
fun HtmlBody(html: String, modifier: Modifier = Modifier, fontSizeSp: Float = 15f) {
    val colors = ForumTheme.colors
    val spanned = remember(html) {
        val safe = html
            .replace(Regex("(?i)<img[^>]*>"), "")
            .replace(Regex("(?i)<script[\\s\\S]*?</script>"), "")
        runCatching { HtmlCompat.fromHtml(safe, HtmlCompat.FROM_HTML_MODE_COMPACT) }
            .getOrElse { safe }
    }
    AndroidView(
        modifier = modifier.fillMaxWidth(),
        factory = { ctx ->
            TextView(ctx).apply {
                setLineSpacing(0f, 1.25f)
                includeFontPadding = false
            }
        },
        update = { tv ->
            tv.text = spanned
            tv.setTextColor(colors.textPrimary.toArgb())
            tv.textSize = fontSizeSp
            tv.setLinkTextColor(colors.primary.toArgb())
            // 让 <a> 链接可点击（HtmlCompat 会生成 URLSpan）
            tv.movementMethod = LinkMovementMethod.getInstance()
        },
    )
}

// ────────────────── 帖子正文（Markdown） ──────────────────

/**
 * 帖子正文：**一律按 Markdown 渲染**，正文里的 HTML 标签按字面文字展示。
 *
 * 服务端 `content` 存的是用户原文（Markdown / 纯文本），三端口径一致：
 * 不解析 HTML 语法。实现上先由 [MarkdownBody.toHtml] 转成 HTML 再交给
 * [HtmlBody] 用系统 TextView 渲染（保留段落 / 粗体 / 链接 / 代码块等标签）。
 */
@Composable
fun MarkdownBodyView(text: String, modifier: Modifier = Modifier, fontSizeSp: Float = 15f) {
    HtmlBody(MarkdownBody.toHtml(text), modifier = modifier, fontSizeSp = fontSizeSp)
}

// ────────────────── 帖子卡片 ──────────────────

@Composable
fun PostCardView(
    post: Post,
    onClick: () -> Unit,
    onUserClick: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val colors = ForumTheme.colors
    Column(
        modifier = modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .background(colors.bgCard)
            .border(1.dp, colors.border, RoundedCornerShape(12.dp))
            .clickable { onClick() }
            .padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Pill(post.categoryLabel)
            Spacer(Modifier.weight(1f))
            Muted(TimeFmt.fmtTime(post.createdAt), maxLines = 1)
        }

        Text(
            text = post.title,
            color = colors.textPrimary,
            fontSize = 16.sp,
            fontWeight = FontWeight.SemiBold,
            maxLines = 2,
            overflow = TextOverflow.Ellipsis,
        )

        val preview = post.preview
        if (preview.isNotBlank()) {
            Text(
                text = preview,
                color = colors.textSecondary,
                fontSize = 13.sp,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
        }

        Row(verticalAlignment = Alignment.CenterVertically) {
            Avatar(post.userAvatar, 22.dp) {
                if (post.userId.isNotBlank()) onUserClick(post.userId)
            }
            Spacer(Modifier.width(6.dp))
            Text(
                text = post.userName,
                color = colors.textAccent,
                fontSize = 12.sp,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.clickable(enabled = post.userId.isNotBlank()) {
                    onUserClick(post.userId)
                },
            )
            Spacer(Modifier.weight(1f))
            Muted("赞 ${post.likes} · 阅 ${post.views} · 评 ${post.commentCount}", maxLines = 1)
        }
    }
}

/** 用户行（搜索结果 / 关注列表）。 */
@Composable
fun UserRow(
    name: String,
    avatar: String,
    subtitle: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val colors = ForumTheme.colors
    Row(
        modifier = modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(10.dp))
            .clickable { onClick() }
            .padding(horizontal = 4.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Avatar(avatar, 40.dp)
        Spacer(Modifier.width(10.dp))
        Column(modifier = Modifier.weight(1f)) {
            Text(name, color = colors.textPrimary, fontSize = 14.sp, fontWeight = FontWeight.Medium, maxLines = 1)
            if (subtitle.isNotBlank()) {
                Text(subtitle, color = colors.textMuted, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        }
    }
}
