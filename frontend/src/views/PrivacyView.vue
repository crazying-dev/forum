<script setup>
// 隐私政策（完整版 v2.0）：对标《个人信息保护法》结构，逐项列出第三方域名与本地存储。
// 三端文案同源（Web / Windows / Android），本文件为网页端版本。
const TOC = [
  { id: 'policy-intro', text: '引言与适用范围' },
  { id: 'policy-1', text: '我们收集哪些个人信息' },
  { id: 'policy-2', text: '我们如何使用你的个人信息' },
  { id: 'policy-3', text: 'Cookie 与本地存储' },
  { id: 'policy-4', text: '第三方服务与信息共享' },
  { id: 'policy-5', text: '信息的存储与保存期限' },
  { id: 'policy-6', text: '我们如何保护你的信息' },
  { id: 'policy-7', text: '未成年人保护' },
  { id: 'policy-8', text: '你的权利' },
  { id: 'policy-9', text: '本政策的更新' },
  { id: 'policy-10', text: '联系我们' },
]
</script>

<template>
  <div class="page">
    <div class="card">
      <h2 class="card-title" style="margin-bottom:12px;"><i class="fa fa-shield"></i> 妖精论坛 · 隐私政策</h2>

      <div class="policy">
        <div class="policy-meta">
          <span>生效日期：2026 年 10 月 1 日</span>
          <span>最近更新：2026 年 10 月 4 日</span>
          <span>版本：2.1</span>
          <span>适用：网页端 / Windows 客户端 / Android 客户端</span>
        </div>

        <nav class="policy-toc">
          <div class="policy-toc-title">目录</div>
          <ol>
            <li v-for="t in TOC" :key="t.id"><a :href="'#' + t.id">{{ t.text }}</a></li>
          </ol>
        </nav>

        <!-- 引言 -->
        <section id="policy-intro" class="policy-sec">
          <h3><span class="policy-num">0</span>引言与适用范围</h3>
          <p>
            「妖精论坛」（以下简称「本论坛」）是《罗小黑战记》的粉丝非官方二创项目，由个人开发者以公益、非营利方式运营，
            不隶属于任何官方机构，也不进行任何商业变现。
          </p>
          <p>
            我们深知个人信息对你的重要性，并将按照《中华人民共和国个人信息保护法》《中华人民共和国网络安全法》
            《信息安全技术 个人信息安全规范》等法律法规与国家标准的要求，采取相应的安全保护措施保护你的个人信息。
          </p>
          <p><strong>本政策适用于以下三端产品：</strong></p>
          <ol>
            <li>网页端：<code>crazying-dev.top</code> 及其子域下的全部页面；</li>
            <li>Windows 桌面客户端（CrForum，妖精论坛 Windows 版）；</li>
            <li>Android 客户端（妖精论坛 Android 版）。</li>
          </ol>
          <div class="policy-note">
            <strong>本政策不适用于</strong>通过本论坛跳转的第三方网站或服务（如 GitHub、哔哩哔哩、小红书等），
            它们的信息处理行为适用其各自的隐私政策。
          </div>
          <p>
            请你在使用本论坛前仔细阅读并充分理解本政策。当你注册账号、登录或继续使用本论坛服务时，
            即表示你已同意本政策。
          </p>
        </section>

        <!-- 一 -->
        <section id="policy-1" class="policy-sec">
          <h3><span class="policy-num">1</span>我们收集哪些个人信息</h3>
          <p>我们遵循「最小必要」原则，仅收集实现产品功能所必需的信息：</p>
          <div class="policy-table-wrap">
            <table class="policy-table">
              <thead>
                <tr><th>信息类型</th><th>具体内容</th><th>收集场景</th><th>是否必需</th></tr>
              </thead>
              <tbody>
                <tr>
                  <td>账号信息</td>
                  <td>用户名、密码（仅保存 PBKDF2 加盐哈希，不保存明文）、邮箱地址</td>
                  <td>注册、登录、找回密码</td>
                  <td>必需</td>
                </tr>
                <tr>
                  <td>邮箱验证码</td>
                  <td>6 位数字验证码</td>
                  <td>注册验证、修改密码、换绑邮箱、注销账号</td>
                  <td>必需</td>
                </tr>
                <tr>
                  <td>个人资料</td>
                  <td>头像图片、性别、出生日期、个性签名、称号</td>
                  <td>你主动在「编辑资料」中填写</td>
                  <td>否</td>
                </tr>
                <tr>
                  <td>你发布的内容</td>
                  <td>帖子标题与正文、评论、图片外链、世界频道消息</td>
                  <td>你主动发布</td>
                  <td>否</td>
                </tr>
                <tr>
                  <td>互动记录</td>
                  <td>点赞、收藏、关注、举报记录</td>
                  <td>你主动操作</td>
                  <td>否</td>
                </tr>
                <tr>
                  <td>第三方账号标识</td>
                  <td>GitHub OAuth 返回的第三方用户 ID 与昵称</td>
                  <td>你选择「使用 GitHub 登录」</td>
                  <td>否</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="policy-note">
            <strong>我们不会收集：</strong>你的真实姓名、身份证号、手机号、精确地理位置、通讯录、短信、通话记录、
            相册全量照片、麦克风/摄像头数据、剪贴板内容、已安装应用列表，也不会读取你设备上的其他文件。
          </div>
        </section>

        <!-- 二 -->
        <section id="policy-2" class="policy-sec">
          <h3><span class="policy-num">2</span>我们如何使用你的个人信息</h3>
          <ol>
            <li>提供账号服务：注册、登录、找回/修改密码、换绑邮箱、注销账号；</li>
            <li>提供社区功能：发布与展示帖子、评论、世界频道消息，展示互动状态与回复关系；</li>
            <li>安全与风控：邮箱验证、验证码校验、接口频率限制、举报处理、封禁违规账号；</li>
            <li>保障服务运行：排查故障、统计帖子浏览量（仅在服务端计数，不含任何用户标识）。</li>
          </ol>
          <p><strong>我们不会：</strong></p>
          <ul>
            <li>将你的个人信息用于广告推送、用户画像或自动化决策；</li>
            <li>将你的个人信息出售、出租或以其他方式提供给任何第三方；</li>
            <li>将你的个人信息用于本政策未载明的其他目的。</li>
          </ul>
          <p>如确需将信息用于本政策未载明的其他用途，我们会再次征得你的单独同意。</p>
        </section>

        <!-- 三 -->
        <section id="policy-3" class="policy-sec">
          <h3><span class="policy-num">3</span>Cookie 与本地存储</h3>
          <p class="policy-sub">3.1 网页端</p>
          <div class="policy-table-wrap">
            <table class="policy-table">
              <thead>
                <tr><th>名称</th><th>类型</th><th>用途</th><th>有效期</th></tr>
              </thead>
              <tbody>
                <tr><td>token / ID</td><td>Cookie</td><td>登录凭证（会话保持，HttpOnly）</td><td>7 天</td></tr>
                <tr><td>forum-year-mode</td><td>Cookie</td><td>记住国庆主题配色偏好</td><td>365 天</td></tr>
                <tr><td>forum-theme</td><td>localStorage</td><td>深色/浅色主题偏好</td><td>永久（除非清除）</td></tr>
                <tr><td>forum-announce-dismissed</td><td>localStorage</td><td>记录站点公告弹窗已关闭</td><td>永久</td></tr>
                <tr><td>forum-navmode</td><td>localStorage</td><td>记录导航栏形态偏好</td><td>永久</td></tr>
                <tr><td>forum_world_width / forum_world_collapsed</td><td>localStorage</td><td>记录世界频道面板宽度与收起状态</td><td>永久</td></tr>
                <tr><td>pwa_installed</td><td>localStorage</td><td>标记 PWA 是否已安装</td><td>永久</td></tr>
                <tr><td>forum-new-v7</td><td>Service Worker CacheStorage</td><td>离线缓存静态资源（页面外壳、图标、CSS、JS）</td><td>随版本更新重建</td></tr>
              </tbody>
            </table>
          </div>
          <p>
            上述 Cookie 与本地存储均属「必需/功能性」，不用于广告投放或跨站追踪。
            你可以通过浏览器设置清除或禁用，但清除后需要重新登录，部分偏好会恢复默认。
          </p>
          <p class="policy-sub">3.2 Windows 客户端</p>
          <p>数据根目录：<code>%USERPROFILE%\.Cr\forum\</code></p>
          <div class="policy-table-wrap">
            <table class="policy-table">
              <thead><tr><th>文件 / 目录</th><th>内容</th><th>说明</th></tr></thead>
              <tbody>
                <tr><td>config.json</td><td>界面偏好（主题、窗口尺寸等）</td><td>仅存本机</td></tr>
                <tr><td>account.bin</td><td>登录凭证</td><td>使用本机指纹派生的密钥加密后存储</td></tr>
                <tr><td>cache/avatar/、cache/image/</td><td>头像与图片缓存</td><td>仅存本机，可随时删除</td></tr>
                <tr><td>cache/post/</td><td>帖子正文与元数据缓存</td><td>最多 300 条</td></tr>
                <tr><td>logs/</td><td>客户端运行日志</td><td>仅保留最近 14 天，不含密码</td></tr>
                <tr><td>update/、tmp/</td><td>更新包与临时文件</td><td>仅存本机</td></tr>
              </tbody>
            </table>
          </div>
          <p>注册表项（均可在设置中关闭或还原）：</p>
          <div class="policy-table-wrap">
            <table class="policy-table">
              <thead><tr><th>位置</th><th>用途</th><th>是否必需</th></tr></thead>
              <tbody>
                <tr><td>HKCU\...\Run\CrForum</td><td>开机自启动</td><td>否</td></tr>
                <tr><td>HKCU\Control Panel\Cursors</td><td>自定义鼠标指针</td><td>否</td></tr>
                <tr><td>HKCU\Software\Classes\Crforum</td><td>注册 crforum:// 协议</td><td>否</td></tr>
              </tbody>
            </table>
          </div>
          <p class="policy-sub">3.3 Android 客户端</p>
          <p>以下数据保存在应用私有目录中，其他应用无法访问：</p>
          <div class="policy-table-wrap">
            <table class="policy-table">
              <thead><tr><th>名称</th><th>类型</th><th>内容</th></tr></thead>
              <tbody>
                <tr>
                  <td>forum_prefs</td><td>SharedPreferences</td>
                  <td>主题偏好（theme_pref）、国庆模式（year_mode）、本地用户信息（user_json）、登录 Cookie（cookie_store）、上次登录用户名（last_name）、更新检查时间与跳过版本</td>
                </tr>
                <tr><td>cacheDir/updates/</td><td>应用缓存目录</td><td>已下载的更新安装包</td></tr>
                <tr><td>Coil 磁盘缓存</td><td>应用缓存目录</td><td>帖子图片缓存</td></tr>
              </tbody>
            </table>
          </div>
          <div class="policy-note">
            说明：Android 端的登录 Cookie 以明文形式保存在应用私有 SharedPreferences 中。
            由于该文件位于应用沙盒内、其他应用无法读取，我们暂未额外加密；卸载应用会一并删除。
          </div>
          <p>
            <strong>权限说明（Android）：</strong>仅申请「网络访问」与「安装未知来源应用」（用于应用内更新）；
            不申请通讯录、短信、定位、相机、麦克风等敏感权限。
          </p>
        </section>

        <!-- 四 -->
        <section id="policy-4" class="policy-sec">
          <h3><span class="policy-num">4</span>第三方服务与信息共享</h3>
          <p>为向你提供服务，本论坛在你的设备或请求链路中会触达以下第三方域名/服务：</p>
          <div class="policy-table-wrap">
            <table class="policy-table">
              <thead><tr><th>域名 / 服务方</th><th>用途</th><th>触达端</th></tr></thead>
              <tbody>
                <tr><td>cdn.jsdelivr.net（jsDelivr）</td><td>加载 Font Awesome 图标字体</td><td>网页</td></tr>
                <tr><td>dlystc.unknownmp.top</td><td>第三方「每日一言」接口，首页展示每日一句（仅文本）</td><td>网页</td></tr>
                <tr><td>img.crazying-dev.top</td><td>本项目自建图床，加载赞赏码图片</td><td>三端</td></tr>
                <tr><td>qm.qq.com（腾讯 QQ）</td><td>「加入 QQ 群」按钮跳转</td><td>网页</td></tr>
                <tr><td>github.com / *.githubusercontent.com / *.githubassets.com</td><td>检查更新、下载新版安装包、查看项目主页</td><td>三端</td></tr>
                <tr><td>ghproxy.net / gh-proxy.com / ghfast.top</td><td>第三方 GitHub 加速镜像，直连 GitHub 失败时下载更新包</td><td>三端</td></tr>
                <tr><td>dns.alidns.com / doh.pub / cloudflare-dns.com / dns.google</td><td>仅用于解析 github.com 等域名（应对 DNS 污染）</td><td>Windows</td></tr>
                <tr><td>challenges.cloudflare.com（Cloudflare Turnstile）</td><td>提供人机验证（登录 / 注册 / 改密等操作前校验）；本论坛仅接收一次性验证令牌，不接收该服务的原始采集数据</td><td>三端</td></tr>
                <tr><td>smtp.163.com（网易 163 邮箱）</td><td>发送注册、改密、换绑、注销等验证码邮件</td><td>服务端</td></tr>
                <tr><td>localhost（本机回环）</td><td>GitHub OAuth 授权回调</td><td>Windows</td></tr>
              </tbody>
            </table>
          </div>
          <p>
            我们不会向上述第三方提供你的账号信息；上述请求仅携带实现该功能所必需的参数（如文件名、帖子 ID）。
          </p>
          <p>
            <strong>法定披露：</strong>只有在法律法规要求，或司法机关、行政机关依法定程序提出要求时，
            我们才会提供必要的信息。
          </p>
        </section>

        <!-- 五 -->
        <section id="policy-5" class="policy-sec">
          <h3><span class="policy-num">5</span>信息的存储与保存期限</h3>
          <p>
            存储位置：本论坛的服务器位于中华人民共和国境内。除服务器所在云服务商外，
            我们不向境外提供你的个人信息。
          </p>
          <p>
            <strong>境外传输提示：</strong>人机验证由 Cloudflare, Inc.（美国）提供。在你触发人机验证时，
            你的设备会直接向 challenges.cloudflare.com 发起请求，该请求可能包含你的
            IP 地址与浏览器环境信息，但不包含你的账号信息；验证完成后 Cloudflare 即时
            作废本次令牌，本论坛仅接收「通过 / 不通过」的结果。
          </p>
          <p>我们遵循最短必要原则，保存期限如下：</p>
          <div class="policy-table-wrap">
            <table class="policy-table">
              <thead><tr><th>数据</th><th>保存期限</th></tr></thead>
              <tbody>
                <tr><td>账号信息（用户名、邮箱、密码哈希）</td><td>自注销之日起删除；选择「匿名化保留」则仅保留无法识别到你本人的脱敏记录</td></tr>
                <tr><td>帖子与评论</td><td>你主动删除或注销账号时删除；「匿名化保留」模式下保留正文但去除可识别身份</td></tr>
                <tr><td>世界频道消息</td><td>仅保留最近 1000 条，超出后自动滚动删除</td></tr>
                <tr><td>邮箱验证码</td><td>5 分钟，超时自动失效</td></tr>
                <tr><td>邮箱验证链接</td><td>30 分钟，超时自动失效</td></tr>
                <tr><td>登录凭证</td><td>7 天，到期自动失效</td></tr>
                <tr><td>举报记录</td><td>用于风控与违规处理，保留至处理完毕后的合理期限</td></tr>
                <tr><td>服务端访问日志</td><td>仅用于故障排查与安全审计，滚动覆盖</td></tr>
              </tbody>
            </table>
          </div>
        </section>

        <!-- 六 -->
        <section id="policy-6" class="policy-sec">
          <h3><span class="policy-num">6</span>我们如何保护你的信息</h3>
          <ul>
            <li>密码使用 PBKDF2 加盐哈希存储，任何人（包括管理员）都无法还原出明文；</li>
            <li>传输过程尽可能使用 HTTPS；</li>
            <li>敏感操作（修改密码、换绑邮箱、注销账号）均需邮箱验证码或密码二次验证；</li>
            <li>接口设有频率限制，防止暴力破解与滥用；</li>
            <li>登录 / 注册 / 改密 / 换绑邮箱 / 注销等敏感操作启用 Cloudflare Turnstile 人机验证，验证令牌一次性有效；</li>
            <li>服务端数据库不对外开放。</li>
          </ul>
          <p>尽管我们已采取上述合理措施，但互联网环境并非绝对安全。请你妥善保管账号密码，不要与他人共享。</p>
          <div class="policy-note">
            <strong>请你特别注意：</strong>你在帖子、评论、世界频道或个性签名中主动公开的信息，
            可能被其他用户或第三方看到、保存、转发，请谨慎发布。
          </div>
        </section>

        <!-- 七 -->
        <section id="policy-7" class="policy-sec">
          <h3><span class="policy-num">7</span>未成年人保护</h3>
          <p>
            本论坛面向一般公众，不专门面向未成年人。如果你是不满 14 周岁的儿童，请在监护人的陪同下阅读本政策，
            并在取得监护人同意后使用本论坛。若我们发现在未事先获得可证实的监护人同意的情况下收集了儿童的个人信息，
            会设法尽快删除相关数据。
          </p>
        </section>

        <!-- 八 -->
        <section id="policy-8" class="policy-sec">
          <h3><span class="policy-num">8</span>你的权利</h3>
          <p>依据《中华人民共和国个人信息保护法》，你对你的个人信息享有以下权利：</p>
          <ol>
            <li><strong>查阅、复制</strong>：登录后进入「个人主页」即可查看你的全部资料与发布内容；</li>
            <li><strong>更正、补充</strong>：在「个人主页 → 编辑资料」中随时修改头像、性别、出生日期、个性签名；</li>
            <li><strong>删除</strong>：你可以自行删除自己发布的帖子与评论，也可以在「编辑资料 → 账号安全 → 注销账号」中删除整个账号；</li>
            <li>
              <strong>注销账号</strong>：我们提供真正可用的自助注销入口
              （「个人主页 → 编辑资料 → 账号安全 → 注销账号」）。注销时你可以选择：
              <ul>
                <li>
                  <strong>彻底删除</strong>：删除账号及你发布的全部帖子、评论、点赞、收藏、关注、举报记录，
                  <strong>该操作不可恢复</strong>；
                </li>
                <li>
                  <strong>匿名化保留</strong>：删除邮箱、密码等身份信息，用户名统一显示为「已注销用户」，
                  历史帖子与评论正文保留但无法再关联到你。
                </li>
              </ul>
              为保护账号安全，注销前需要通过「账号密码」或「绑定邮箱验证码」（二选一）验证身份，
              并输入「注销账号」四字确认。
            </li>
            <li><strong>撤回同意</strong>：你可以随时停止使用本论坛，并通过上述方式注销账号；清除浏览器 Cookie 与本地存储可撤回对功能性存储的同意；</li>
            <li><strong>投诉举报</strong>：若你认为你的个人信息权利受到侵害，可通过本政策第十部分的联系方式与我们联系，我们将在 15 个工作日内答复。</li>
          </ol>
        </section>

        <!-- 九 -->
        <section id="policy-9" class="policy-sec">
          <h3><span class="policy-num">9</span>本政策的更新</h3>
          <p>
            我们可能会适时修订本政策。当本政策发生<strong>重大变更</strong>（例如：收集的个人信息类型发生变化、
            使用目的发生变化、对外共享对象发生变化、你行使权利的方式发生变化）时，
            我们会在网站首页以显著方式提示，并在你重新登录时再次征得你的同意。
          </p>
        </section>

        <!-- 十 -->
        <section id="policy-10" class="policy-sec">
          <h3><span class="policy-num">10</span>联系我们</h3>
          <p>本论坛为个人公益二创项目，未设立专门的个人信息保护负责人，但会以同等谨慎处理你的请求。</p>
          <ul class="policy-contact">
            <li>邮箱：<a href="mailto:3890320020@qq.com">3890320020@qq.com</a></li>
            <li>项目主页：<a href="https://github.com/crazying-dev" target="_blank" rel="noopener">https://github.com/crazying-dev</a></li>
            <li>网站：<a href="https://crazying-dev.top" target="_blank" rel="noopener">https://crazying-dev.top</a></li>
          </ul>
          <p>我们通常会在收到你的请求后 15 个工作日内答复。</p>
        </section>
      </div>
    </div>
  </div>
</template>
