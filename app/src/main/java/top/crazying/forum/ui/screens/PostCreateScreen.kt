package top.crazying.forum.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.*
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

/**
 * 发帖页。
 *
 * 正文**原样直传**服务端，不做任何 HTML 包装 / 转义：三端统一为
 * 「原文入库 + 一律按 Markdown 渲染，HTML 标签按字面文字展示」。
 * 历史上这里会把纯文本包装成 `<p>…<br>…</p>`，已废弃。
 */
@Composable
fun PostCreateScreen(nav: Navigator, initialCategory: String = "general") {
    val colors = ForumTheme.colors
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    var category by remember { mutableStateOf(initialCategory) }
    var title by remember { mutableStateOf("") }
    var content by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf("") }

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

    fun publish() {
        if (busy) return
        error = ""
        val t = title.trim()
        val c = content.trim()
        when {
            t.isEmpty() -> { error = "请填写标题"; return }
            t.length > 100 -> { error = "标题不能超过 100 字"; return }
            c.isEmpty() -> { error = "请填写正文"; return }
        }
        busy = true
        scope.launch {
            val result = App.api.createPost(t, c, category)
            busy = false
            if (result.ok) {
                toast(context, "发布成功")
                val newId = result.obj()?.optJSONObject("post")?.optString("id", "") ?: ""
                nav.pop()
                if (newId.isNotBlank()) nav.push(Screen.PostDetail(newId))
            } else {
                error = result.message
            }
        }
    }

    PageScaffold(
        title = "发布帖子",
        onBack = { nav.pop() },
        actions = {
            GhostButton(
                text = if (busy) "发布中…" else "发布",
                onClick = { publish() },
                enabled = !busy,
                tint = colors.primary,
                modifier = Modifier.padding(end = 8.dp),
            )
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .background(colors.bgBody)
                .verticalScroll(rememberScrollState())
                .imePadding()
                .padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text("选择分类", color = colors.textPrimary, fontSize = 14.sp, fontWeight = FontWeight.Medium)
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

            Text("标题", color = colors.textPrimary, fontSize = 14.sp, fontWeight = FontWeight.Medium)
            ForumTextField(
                value = title,
                onValueChange = { if (it.length <= 100) title = it },
                placeholder = "不超过 100 字",
            )

            Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                Text(
                    text = "正文",
                    color = colors.textPrimary,
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Medium,
                    modifier = Modifier.weight(1f),
                )
                Text("${content.length} 字", color = colors.textMuted, fontSize = 12.sp)
            }
            ForumTextField(
                value = content,
                onValueChange = { content = it },
                placeholder = "支持分段（空行分段），本轮不支持富文本与图片",
                singleLine = false,
                minHeight = 220.dp,
            )

            if (error.isNotBlank()) {
                Text(error, color = colors.danger, fontSize = 13.sp)
            }

            PrimaryButton(
                text = if (busy) "发布中…" else "发布帖子",
                onClick = { publish() },
                enabled = !busy,
                modifier = Modifier.fillMaxWidth(),
            )

            EmptyBox("发布后可在帖子详情页查看与回复")
        }
    }
}
