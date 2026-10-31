package top.crazying.forum.core

/**
 * 按 Unicode 码点截断文本，避免切断 emoji / 补充平面字符的代理对。
 *
 * 世界频道服务端按 rune（码点）计 2000 字上限；客户端用同一口径截断，
 * 中文与 emoji 都不会被截成半个字符。
 *
 * @param text 原始文本
 * @param maxCodePoints 最大保留码点数（≤0 时返回空串）
 */
fun takeCodePoints(text: String, maxCodePoints: Int): String {
    if (maxCodePoints <= 0) return ""
    if (text.isEmpty()) return text
    // 编码单元数不超过上限时，码点数必然也不超过（每个码点至少 1 个单元）。
    if (text.length <= maxCodePoints) return text
    var count = 0
    var index = 0
    while (index < text.length) {
        if (count == maxCodePoints) break
        index += Character.charCount(text.codePointAt(index))
        count++
    }
    return text.substring(0, index)
}
