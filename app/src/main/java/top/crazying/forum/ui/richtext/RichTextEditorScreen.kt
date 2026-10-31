package top.crazying.forum.ui.richtext

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.compose.ui.unit.sp
import top.crazying.forum.theme.ForumTheme
import top.crazying.forum.ui.components.GhostButton

/**
 * 全屏编辑宿主：发帖、评论共用（世界频道已改为页面内联纯文本输入）。
 *
 * 顶部固定「取消 / 标题 / 发布」，中间可选 header（发帖页放标题与分类），
 * 下方是共享的 `RichTextEditor`。
 */
@Composable
fun RichTextEditorScreen(
    state: RichEditorState,
    title: String,
    publishLabel: String = "发布",
    publishing: Boolean = false,
    uploadingImage: Boolean = false,
    placeholder: String = "说点什么…",
    header: (@Composable () -> Unit)? = null,
    overlay: Boolean = false,
    onPickImage: () -> Unit,
    onCancel: () -> Unit,
    onPublish: () -> Unit,
) {
    val content: @Composable () -> Unit = {
    val colors = ForumTheme.colors
    BackHandler(enabled = !publishing) { onCancel() }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(colors.bgBody)
            .statusBarsPadding()
            .imePadding(),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .background(colors.bgHeader)
                .padding(horizontal = 10.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            GhostButton(text = "取消", enabled = !publishing, onClick = onCancel)
            Text(
                text = title,
                color = colors.textPrimary,
                fontSize = 16.sp,
                fontWeight = FontWeight.SemiBold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f).padding(horizontal = 10.dp),
            )
            GhostButton(
                text = if (publishing) "发布中…" else publishLabel,
                enabled = !publishing && !uploadingImage,
                tint = colors.primary,
                onClick = onPublish,
            )
        }

        if (header != null) {
            Column(modifier = Modifier.fillMaxWidth().background(colors.bgCard)) {
                header()
            }
        }

        if (uploadingImage) {
            Text(
                text = "图片上传中…",
                color = colors.textMuted,
                fontSize = 11.sp,
                modifier = Modifier.padding(horizontal = 14.dp, vertical = 6.dp),
            )
        }

        RichTextEditor(
            state = state,
            modifier = Modifier.weight(1f),
            placeholder = placeholder,
            onPickImage = onPickImage,
        )
    }
    }

    if (overlay) {
        Dialog(
            onDismissRequest = { if (!publishing) onCancel() },
            properties = DialogProperties(
                usePlatformDefaultWidth = false,
                decorFitsSystemWindows = false,
            ),
        ) {
            content()
        }
    } else {
        content()
    }
}
