package top.crazying.forum.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import top.crazying.forum.theme.ForumTheme

/**
 * 带顶欄的页面骨架（推入栈的页面用）。
 *
 * insets 分工：顶欄自带状态栏内边距；最外层 Scaffold 已刻意关掉了 contentWindowInsets，
 * 所以这里不需要再手动 `statusBarsPadding()`。
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PageScaffold(
    title: String,
    onBack: (() -> Unit)? = null,
    actions: @Composable RowScope.() -> Unit = {},
    bottomBar: @Composable () -> Unit = {},
    content: @Composable (PaddingValues) -> Unit,
) {
    val colors = ForumTheme.colors
    Scaffold(
        containerColor = colors.bgBody,
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        text = title,
                        color = colors.textPrimary,
                        fontSize = 17.sp,
                        fontWeight = FontWeight.SemiBold,
                        maxLines = 1,
                    )
                },
                navigationIcon = {
                    if (onBack != null) {
                        IconButton(onClick = onBack) {
                            Icon(
                                imageVector = Icons.AutoMirrored.Filled.ArrowBack,
                                contentDescription = "返回",
                                tint = colors.textPrimary,
                            )
                        }
                    }
                },
                actions = actions,
                colors = TopAppBarDefaults.topAppBarColors(containerColor = colors.bgHeader),
            )
        },
        bottomBar = bottomBar,
        content = content,
    )
}

/** 无顶欄的 tab 根页占位（保留供后续页面复用）。 */
@Composable
fun TabPage(content: @Composable () -> Unit) {
    Box(Modifier.fillMaxSize()) { content() }
}

/**
 * 主题化输入框。
 *
 * 用 `BasicTextField` 手搭而不是用 Material3 的 TextField，
 * 一是能直接套四套色板，二是避开 M3 组件参数在大版本间的变动。
 */
@Composable
fun ForumTextField(
    value: String,
    onValueChange: (String) -> Unit,
    placeholder: String = "",
    singleLine: Boolean = true,
    minHeight: Dp = 46.dp,
    visual: VisualTransformation = VisualTransformation.None,
    keyboardOptions: KeyboardOptions = KeyboardOptions.Default,
    modifier: Modifier = Modifier,
) {
    val colors = ForumTheme.colors
    Box(
        modifier = modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(10.dp))
            .background(colors.bgInput)
            .border(1.dp, colors.border, RoundedCornerShape(10.dp))
            .padding(horizontal = 12.dp, vertical = 11.dp),
        contentAlignment = Alignment.CenterStart,
    ) {
        if (value.isEmpty() && placeholder.isNotEmpty()) {
            Text(placeholder, color = colors.textMuted, fontSize = 14.sp, maxLines = 1)
        }
        BasicTextField(
            value = value,
            onValueChange = onValueChange,
            singleLine = singleLine,
            textStyle = TextStyle(color = colors.textPrimary, fontSize = 14.sp),
            cursorBrush = SolidColor(colors.primary),
            visualTransformation = visual,
            keyboardOptions = keyboardOptions,
            modifier = Modifier
                .fillMaxWidth()
                .heightIn(min = minHeight - 22.dp),
        )
    }
}

/** 一行「标签 + 值」，用于设置页与资料页。 */
@Composable
fun InfoRow(
    label: String,
    value: String,
    modifier: Modifier = Modifier,
) {
    val colors = ForumTheme.colors
    Row(
        modifier = modifier.fillMaxWidth().padding(vertical = 7.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, color = colors.textMuted, fontSize = 13.sp)
        Spacer(Modifier.weight(1f))
        Text(
            text = value,
            color = colors.textSecondary,
            fontSize = 13.sp,
            maxLines = 1,
        )
    }
}

/** 固定高度的空占位。 */
@Composable
fun VSpace(height: Dp) {
    Box(Modifier.fillMaxWidth().height(height))
}
