package top.crazying.forum.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import top.crazying.forum.theme.ForumTheme
import top.crazying.forum.ui.Navigator
import top.crazying.forum.ui.components.PageScaffold

/** 隐私政策页面中的一段内容（标题 / 正文 / 条目）。 */
private sealed interface PBlock {
    data class Heading(val text: String) : PBlock
    data class Paragraph(val text: String) : PBlock
    data class Bullet(val text: String) : PBlock
}

/**
 * 「隐私政策」页。
 *
 * 文案逐字取自三端唯一真源 `forum/.git/_privacy_policy_v2.md`，
 * 仅保留 `[通用]` 与 `[ANDROID]` 段，并按端内约定重编号（Android 小节并入「三、」为 3.1）。
 * Markdown 表格已改写为「· 名称 — 说明」的纯文本逐行排版。
 */
@Composable
fun PrivacyScreen(nav: Navigator) = PrivacyPolicyPage(onBack = { nav.pop() })

/**
 * 隐私政策正文页（返回行为由调用方决定）。
 *
 * * 从「我的」页进入：`PrivacyScreen(nav)` → 返回即 `nav.pop()`；
 * * 首启隐私同意门内「查看全文」：`PrivacyPolicyPage(onBack = { … })` → 返回即关闭全文。
 */
@Composable
fun PrivacyPolicyPage(onBack: () -> Unit) {
    val colors = ForumTheme.colors
    PageScaffold(title = "隐私政策", onBack = onBack) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(horizontal = 16.dp, vertical = 14.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            itemsIndexed(items = PRIVACY, key = { index, _ -> index }) { _, block ->
                when (block) {
                    is PBlock.Heading -> Text(
                        text = block.text,
                        color = colors.textPrimary,
                        fontSize = 16.sp,
                        fontWeight = FontWeight.SemiBold,
                        modifier = Modifier.padding(top = 8.dp),
                    )

                    is PBlock.Paragraph -> Text(
                        text = block.text,
                        color = colors.textSecondary,
                        fontSize = 13.sp,
                        lineHeight = 20.sp,
                    )

                    is PBlock.Bullet -> Text(
                        text = block.text,
                        color = colors.textSecondary,
                        fontSize = 13.sp,
                        lineHeight = 20.sp,
                        modifier = Modifier.padding(start = 4.dp),
                    )
                }
            }
        }
    }
}

/** 隐私政策正文（仅 [通用] + [ANDROID] 段，章节号一~十连续，Android 小节重编号为 3.1）。 */
private val PRIVACY: List<PBlock> = listOf(
    PBlock.Heading("妖精论坛 隐私政策"),
    PBlock.Paragraph("生效日期：2026 年 10 月 1 日　|　最近更新：2026 年 10 月 1 日　|　版本：2.0"),

    // —— 引言与适用范围 ——
    PBlock.Heading("引言与适用范围"),
    PBlock.Paragraph("「妖精论坛」（以下简称「本论坛」）是《罗小黑战记》的粉丝非官方二创项目，由个人开发者以公益、非营利方式运营，不隶属于任何官方机构，也不进行任何商业变现。"),
    PBlock.Paragraph("我们深知个人信息对你的重要性，并将按照《中华人民共和国个人信息保护法》《中华人民共和国网络安全法》《信息安全技术 个人信息安全规范》等法律法规与国家标准的要求，采取相应的安全保护措施保护你的个人信息。"),
    PBlock.Paragraph("本政策适用于以下三端产品："),
    PBlock.Bullet("· 网页端：crazying-dev.top 及其子域下的全部页面；"),
    PBlock.Bullet("· Windows 桌面客户端（CrForum，妖精论坛 Windows 版）；"),
    PBlock.Bullet("· Android 客户端（妖精论坛 Android 版）。"),
    PBlock.Paragraph("本政策不适用于通过本论坛跳转的第三方网站或服务（如 GitHub、哔哩哔哩、小红书等），它们的信息处理行为适用其各自的隐私政策。"),
    PBlock.Paragraph("请你在使用本论坛前仔细阅读并充分理解本政策。当你注册账号、登录或继续使用本论坛服务时，即表示你已同意本政策。"),

    // —— 一 ——
    PBlock.Heading("一、我们收集哪些个人信息"),
    PBlock.Paragraph("我们遵循「最小必要」原则，仅收集实现产品功能所必需的信息："),
    PBlock.Bullet("· 账号信息：用户名、密码（仅保存 PBKDF2 加盐哈希，不保存明文）、邮箱地址（收集场景：注册、登录、找回密码；必需）"),
    PBlock.Bullet("· 邮箱验证码：6 位数字验证码（收集场景：注册验证、修改密码、换绑邮箱、注销账号；必需）"),
    PBlock.Bullet("· 个人资料：头像图片、性别、出生日期、个性签名、称号（收集场景：你主动在「编辑资料」中填写；非必需）"),
    PBlock.Bullet("· 你发布的内容：帖子标题与正文、评论、图片外链、世界频道消息（收集场景：你主动发布；非必需）"),
    PBlock.Bullet("· 互动记录：点赞、收藏、关注、举报记录（收集场景：你主动操作；非必需）"),
    PBlock.Bullet("· 第三方账号标识：GitHub OAuth 返回的第三方用户 ID 与昵称（收集场景：你选择「使用 GitHub 登录」；非必需）"),
    PBlock.Paragraph("我们不会收集：你的真实姓名、身份证号、手机号、精确地理位置、通讯录、短信、通话记录、相册全量照片、麦克风/摄像头数据、剪贴板内容、已安装应用列表，也不会读取你设备上的其他文件。"),

    // —— 二 ——
    PBlock.Heading("二、我们如何使用你的个人信息"),
    PBlock.Bullet("1. 提供账号服务：注册、登录、找回/修改密码、换绑邮箱、注销账号；"),
    PBlock.Bullet("2. 提供社区功能：发布与展示帖子、评论、世界频道消息，展示互动状态与回复关系；"),
    PBlock.Bullet("3. 安全与风控：邮箱验证、验证码校验、接口频率限制、举报处理、封禁违规账号；"),
    PBlock.Bullet("4. 保障服务运行：排查故障、统计帖子浏览量（仅在服务端计数，不含任何用户标识）。"),
    PBlock.Paragraph("我们不会："),
    PBlock.Bullet("· 将你的个人信息用于广告推送、用户画像或自动化决策；"),
    PBlock.Bullet("· 将你的个人信息出售、出租或以其他方式提供给任何第三方；"),
    PBlock.Bullet("· 将你的个人信息用于本政策未载明的其他目的。"),
    PBlock.Paragraph("如确需将信息用于本政策未载明的其他用途，我们会再次征得你的单独同意。"),

    // —— 三（Android 小节并入，重编号 3.1）——
    PBlock.Heading("三、Cookie 与本地存储"),
    PBlock.Heading("3.1 Android 客户端"),
    PBlock.Paragraph("以下数据保存在应用私有目录中，其他应用无法访问："),
    PBlock.Bullet("· forum_prefs — SharedPreferences：主题偏好（theme_pref）、国庆模式（year_mode）、本地用户信息（user_json）、登录 Cookie（cookie_store）、上次登录用户名（last_name）、更新检查时间与跳过版本"),
    PBlock.Bullet("· cacheDir/updates/ — 应用缓存目录：已下载的更新安装包"),
    PBlock.Bullet("· Coil 磁盘缓存 — 应用缓存目录：帖子图片缓存"),
    PBlock.Paragraph("说明：Android 端的登录 Cookie 以明文形式保存在应用私有 SharedPreferences 中。由于该文件位于应用沙盒内、其他应用无法读取，我们暂未额外加密；卸载应用会一并删除。"),
    PBlock.Paragraph("权限说明（Android）：仅申请「网络访问」与「安装未知来源应用」（用于应用内更新）；不申请通讯录、短信、定位、相机、麦克风等敏感权限。"),

    // —— 四 ——
    PBlock.Heading("四、第三方服务与信息共享"),
    PBlock.Paragraph("为向你提供服务，本论坛在你的设备或请求链路中会触达以下第三方域名/服务："),
    PBlock.Bullet("· cdn.jsdelivr.net（jsDelivr） — 加载 Font Awesome 图标字体（触达端：网页）"),
    PBlock.Bullet("· dlystc.unknownmp.top — 第三方「每日一言」接口，首页展示每日一句（仅文本）（触达端：网页）"),
    PBlock.Bullet("· img.crazying-dev.top — 本项目自建图床，加载赞赏码图片（触达端：三端）"),
    PBlock.Bullet("· qm.qq.com（腾讯 QQ） — 「加入 QQ 群」按钮跳转（触达端：网页）"),
    PBlock.Bullet("· github.com / *.githubusercontent.com / *.githubassets.com — 检查更新、下载新版安装包、查看项目主页（触达端：三端）"),
    PBlock.Bullet("· ghproxy.net / gh-proxy.com / ghfast.top — 第三方 GitHub 加速镜像，直连 GitHub 失败时下载更新包（触达端：三端）"),
    PBlock.Bullet("· dns.alidns.com / doh.pub / cloudflare-dns.com / dns.google — 仅用于解析 github.com 等域名（应对 DNS 污染）（触达端：Windows）"),
    PBlock.Bullet("· smtp.163.com（网易 163 邮箱） — 发送注册、改密、换绑、注销等验证码邮件（触达端：服务端）"),
    PBlock.Bullet("· localhost（本机回环） — GitHub OAuth 授权回调（触达端：Windows）"),
    PBlock.Paragraph("我们不会向上述第三方提供你的账号信息；上述请求仅携带实现该功能所必需的参数（如文件名、帖子 ID）。"),
    PBlock.Paragraph("法定披露：只有在法律法规要求，或司法机关、行政机关依法定程序提出要求时，我们才会提供必要的信息。"),

    // —— 五 ——
    PBlock.Heading("五、信息的存储与保存期限"),
    PBlock.Paragraph("存储位置：本论坛的服务器位于中华人民共和国境内。除服务器所在云服务商外，我们不向境外提供你的个人信息。"),
    PBlock.Paragraph("我们遵循最短必要原则，保存期限如下："),
    PBlock.Bullet("· 账号信息（用户名、邮箱、密码哈希） — 自注销之日起删除；选择「匿名化保留」则仅保留无法识别到你本人的脱敏记录"),
    PBlock.Bullet("· 帖子与评论 — 你主动删除或注销账号时删除；「匿名化保留」模式下保留正文但去除可识别身份"),
    PBlock.Bullet("· 世界频道消息 — 仅保留最近 1000 条，超出后自动滚动删除"),
    PBlock.Bullet("· 邮箱验证码 — 5 分钟，超时自动失效"),
    PBlock.Bullet("· 邮箱验证链接 — 30 分钟，超时自动失效"),
    PBlock.Bullet("· 登录凭证 — 7 天，到期自动失效"),
    PBlock.Bullet("· 举报记录 — 用于风控与违规处理，保留至处理完毕后的合理期限"),
    PBlock.Bullet("· 服务端访问日志 — 仅用于故障排查与安全审计，滚动覆盖"),

    // —— 六 ——
    PBlock.Heading("六、我们如何保护你的信息"),
    PBlock.Bullet("· 密码使用 PBKDF2 加盐哈希存储，任何人（包括管理员）都无法还原出明文；"),
    PBlock.Bullet("· 传输过程尽可能使用 HTTPS；"),
    PBlock.Bullet("· 敏感操作（修改密码、换绑邮箱、注销账号）均需邮箱验证码或密码二次验证；"),
    PBlock.Bullet("· 接口设有频率限制，防止暴力破解与滥用；"),
    PBlock.Bullet("· 服务端数据库不对外开放。"),
    PBlock.Paragraph("尽管我们已采取上述合理措施，但互联网环境并非绝对安全。请你妥善保管账号密码，不要与他人共享。"),
    PBlock.Paragraph("请你特别注意：你在帖子、评论、世界频道或个性签名中主动公开的信息，可能被其他用户或第三方看到、保存、转发，请谨慎发布。"),

    // —— 七 ——
    PBlock.Heading("七、未成年人保护"),
    PBlock.Paragraph("本论坛面向一般公众，不专门面向未成年人。如果你是不满 14 周岁的儿童，请在监护人的陪同下阅读本政策，并在取得监护人同意后使用本论坛。若我们发现在未事先获得可证实的监护人同意的情况下收集了儿童的个人信息，会设法尽快删除相关数据。"),

    // —— 八 ——
    PBlock.Heading("八、你的权利"),
    PBlock.Paragraph("依据《中华人民共和国个人信息保护法》，你对你的个人信息享有以下权利："),
    PBlock.Bullet("1. 查阅、复制：登录后进入「个人主页」即可查看你的全部资料与发布内容；"),
    PBlock.Bullet("2. 更正、补充：在「个人主页 → 编辑资料」中随时修改头像、性别、出生日期、个性签名；"),
    PBlock.Bullet("3. 删除：你可以自行删除自己发布的帖子与评论，也可以在「编辑资料 → 账号安全 → 注销账号」中删除整个账号；"),
    PBlock.Bullet("4. 注销账号：我们提供真正可用的自助注销入口（「个人主页 → 编辑资料 → 账号安全 → 注销账号」）。注销时你可以选择："),
    PBlock.Bullet("　- 彻底删除：删除账号及你发布的全部帖子、评论、点赞、收藏、关注、举报记录，该操作不可恢复；"),
    PBlock.Bullet("　- 匿名化保留：删除邮箱、密码等身份信息，用户名统一显示为「已注销用户」，历史帖子与评论正文保留但无法再关联到你。"),
    PBlock.Bullet("　为保护账号安全，注销前需要通过「账号密码」或「绑定邮箱验证码」（二选一）验证身份，并输入「注销账号」四字确认。"),
    PBlock.Bullet("5. 撤回同意：你可以随时停止使用本论坛，并通过上述方式注销账号；清除浏览器 Cookie 与本地存储可撤回对功能性存储的同意；"),
    PBlock.Bullet("6. 投诉举报：若你认为你的个人信息权利受到侵害，可通过本政策第十部分的联系方式与我们联系，我们将在 15 个工作日内答复。"),

    // —— 九 ——
    PBlock.Heading("九、本政策的更新"),
    PBlock.Paragraph("我们可能会适时修订本政策。当本政策发生重大变更（例如：收集的个人信息类型发生变化、使用目的发生变化、对外共享对象发生变化、你行使权利的方式发生变化）时，我们会在网站首页以显著方式提示，并在你重新登录时再次征得你的同意。"),

    // —— 十 ——
    PBlock.Heading("十、联系我们"),
    PBlock.Paragraph("本论坛为个人公益二创项目，未设立专门的个人信息保护负责人，但会以同等谨慎处理你的请求。"),
    PBlock.Bullet("· 邮箱：3890320020@qq.com"),
    PBlock.Bullet("· 项目主页：https://github.com/crazying-dev"),
    PBlock.Bullet("· 网站：https://crazying-dev.top"),
    PBlock.Paragraph("我们通常会在收到你的请求后 15 个工作日内答复。"),
)
