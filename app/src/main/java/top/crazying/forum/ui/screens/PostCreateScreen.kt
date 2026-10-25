package top.crazying.forum.ui.screens

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import top.crazying.forum.core.App
import top.crazying.forum.core.Constants
import top.crazying.forum.theme.ForumTheme
import top.crazying.forum.ui.Navigator
import top.crazying.forum.ui.Screen
import top.crazying.forum.ui.components.*
import top.crazying.forum.ui.richtext.RichTextEditorScreen
import top.crazying.forum.ui.richtext.rememberRichEditorState

/** 正文图片上限：与服务端 `media.MaxInputBytes`（5MB）一致。 */
private const val POST_IMAGE_MAX_BYTES = 5 * 1024 * 1024

/** 从 MIME 推断扩展名（服务端只接受 jpeg / png / webp / gif）。 */
private fun postImageExt(mime: String): String = when {
    mime.contains("png", ignoreCase = true) -> "png"
    mime.contains("webp", ignoreCase = true) -> "webp"
    mime.contains("gif", ignoreCase = true) -> "gif"
    else -> "jpg"
}

/**
 * 发帖页：全屏富文本编辑器。
 *
 * 正文由 `RichEditorState` 生成白名单 HTML（`state.toHtml()`），服务端按
 * `content_format=html` 入库；图片先传 `/media/images`（scene=`post_image`），
 * 成功后把返回的 url 以图片块插进正文。
 */
@Composable
fun PostCreateScreen(nav: Navigator, initialCategory: String = "general") {
    val colors = ForumTheme.colors
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    var category by remember { mutableStateOf(initialCategory) }
    var title by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var uploading by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf("") }
    val editor = rememberRichEditorState()

    if (!App.isLoggedIn) {
        PageScaffold(title = "发布帖子", onBack = { nav.pop() }) { padding ->
            Box(Modifier.fillMaxSize().padding(padding)) {
                ErrorBox(
                    message = "请先登录后再发帖",
                    onRetry = { nav.push(Screen.Auth()) },
                )
            }
        }
        return
    }

    // 选图 → 读字节 → 校验 5MB → 上传 → 插入正文（期间禁用发布按钮）
    val pickImage = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        scope.launch {
            val bytes = runCatching {
                context.contentResolver.openInputStream(uri)?.use { it.readBytes() }
            }.getOrNull()
            if (bytes == null) {
                toast(context, "读取图片失败")
                return@launch
            }
            if (bytes.size > POST_IMAGE_MAX_BYTES) {
                toast(context, "图片不能超过 5MB")
                return@launch
            }
            val mime = context.contentResolver.getType(uri) ?: "image/jpeg"
            uploading = true
            val result = App.api.uploadImage(bytes, "image." + postImageExt(mime), mime, "post_image")
            uploading = false
            if (result.ok) {
                val url = result.str("url")
                if (url.isNotBlank()) editor.insertImage(url) else toast(context, "上传成功但未返回图片地址")
            } else {
                toast(context, result.message)
            }
        }
    }

    fun publish() {
        if (busy || uploading) return
        error = ""
        val t = title.trim()
        when {
            t.isEmpty() -> { error = "请填写标题"; return }
            t.length > 100 -> { error = "标题不能超过 100 字"; return }
            editor.toDocument().isBlank -> { error = "请填写正文"; return }
        }
        busy = true
        scope.launch {
            val result = App.api.createPost(t, editor.toHtml(), category)
            busy = false
            if (result.ok) {
                toast(context, "发布成功")
                val newId = result.str("id")
                nav.pop()
                if (newId.isNotBlank()) nav.push(Screen.PostDetail(newId))
            } else {
                error = result.message
            }
        }
    }

    RichTextEditorScreen(
        state = editor,
        title = "发布帖子",
        publishLabel = "发布",
        publishing = busy,
        uploadingImage = uploading,
        placeholder = "正文支持标题、列表、引用、代码块与图片…",
        header = {
            Column(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 10.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        text = "标题",
                        color = colors.textPrimary,
                        fontSize = 13.sp,
                        fontWeight = FontWeight.Medium,
                    )
                    Spacer(Modifier.width(10.dp))
                    ForumTextField(
                        value = title,
                        onValueChange = { if (it.length <= 100) title = it },
                        placeholder = "不超过 100 字",
                        modifier = Modifier.weight(1f),
                    )
                    Spacer(Modifier.width(8.dp))
                    Text("${title.length}/100", color = colors.textMuted, fontSize = 11.sp)
                }
                Row(
                    modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    for (key in Constants.CATEGORY_ORDER) {
                        Pill(
                            text = Constants.categoryLabel(key),
                            active = category == key,
                            onClick = { category = key },
                        )
                    }
                }
                if (error.isNotBlank()) {
                    Text(error, color = colors.danger, fontSize = 12.sp)
                }
            }
        },
        onPickImage = { pickImage.launch("image/*") },
        onCancel = { if (!busy) nav.pop() },
        onPublish = { publish() },
    )
}
