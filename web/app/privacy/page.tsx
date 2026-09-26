
import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata({
  title: "隐私政策",
  description: "妖精论坛隐私政策：说明我们如何收集、使用、存储和保护您的个人信息。",
  path: "/privacy",
});

export default function PrivacyPage() {
  return (
    <>
      <div className="privacy-page">
        <div className="privacy-header">
          <h2><i className="fa fa-shield"></i> 隐私政策</h2>
          <p className="privacy-intro">
            妖精论坛非常重视您的隐私保护。本隐私政策旨在说明我们如何收集、使用、存储和保护您的个人信息，以及您享有的相关权利。
          </p>
          <span className="privacy-updated"><i className="fa fa-clock-o"></i> 最后更新：2026年8月29日</span>
        </div>

        <div className="privacy-section">
          <h3><span className="section-icon"><i className="fa fa-database"></i></span>我们收集的信息</h3>
          <p>为了向您提供服务，我们会收集以下信息：</p>
          <ul className="privacy-list">
            <li><b>账号资料</b>：注册时填写的用户名、邮箱，以及您主动完善的头像、性别、生日、个性签名等；</li>
            <li><b>内容数据</b>：您发布的帖子、评论、收藏、关注关系、入馆申请与会馆互动等公开互动数据；</li>
            <li><b>技术信息</b>：访问日志中的 IP 地址、浏览器类型（User-Agent）、访问时间等，用于安全防护与体验优化；</li>
            <li><b>本地存储</b>：登录会话 Cookie 与浏览器本地存储中的主题偏好等。</li>
          </ul>
        </div>

        <div className="privacy-section">
          <h3><span className="section-icon"><i className="fa fa-cogs"></i></span>信息的使用</h3>
          <p>我们收集的信息仅用于：</p>
          <ul className="privacy-list">
            <li>向您提供核心功能（登录、发帖、评论、收藏、会馆等）；</li>
            <li>保障账号与社区安全（登录校验、风控限流、反滥用检测）；</li>
            <li>记住您的偏好（如明/暗主题），改善使用体验；</li>
            <li>以汇总、匿名形式进行统计分析，帮助我们改进服务。</li>
          </ul>
          <p>我们<b>不会</b>出售、出租或向无关第三方转让您的个人信息。</p>
        </div>

        <div className="privacy-section">
          <h3><span className="section-icon"><i className="fa fa-lock"></i></span>信息的存储与保护</h3>
          <ul className="privacy-list">
            <li>全站通过 HTTPS 加密传输；</li>
            <li>密码经 bcrypt 安全哈希存储，任何情况下我们都不会以明文保存密码；</li>
            <li>会话 Cookie 设置 HttpOnly / SameSite 等安全属性；</li>
            <li>验证码、验证链接等敏感数据设有严格有效期，过期自动清理。</li>
          </ul>
        </div>

        <div className="privacy-section">
          <h3><span className="section-icon"><i className="fa fa-coffee"></i></span>Cookie 与本地存储</h3>
          <ul className="privacy-list">
            <li><b>登录会话</b>：Cookie 用于保持您的登录状态；</li>
            <li><b>主题偏好</b>：localStorage 记录明/暗主题选择（仅存本机）；</li>
            <li><b>PWA 缓存</b>：安装客户端后，Service Worker 会缓存部分静态资源以加速访问；</li>
            <li>您可以在浏览器设置中清除 Cookie 或本地存储，不影响基础浏览。</li>
          </ul>
        </div>

        <div className="privacy-section">
          <h3><span className="section-icon"><i className="fa fa-exchange"></i></span>第三方服务</h3>
          <ul className="privacy-list">
            <li><b>邮件服务</b>：注册验证码、密码重置等邮件通过邮件服务商发送，仅传递必要的账号信息；</li>
            <li><b>会馆数据</b>：本站会馆为站内功能，会馆内容与服务均适用本隐私政策；</li>
            <li><b>外部链接</b>：站点内的「WIKI」及站外跳转链接为第三方站点，离开本站后适用对方隐私政策；</li>
            <li><b>CDN 资源</b>：部分字体、头像等静态资源可能由内容分发网络提供。</li>
          </ul>
        </div>

        <div className="privacy-section">
          <h3><span className="section-icon"><i className="fa fa-user-circle"></i></span>您的权利</h3>
          <ul className="privacy-list">
            <li><b>访问与更正</b>：您可在个人中心随时查看、修改自己的资料；</li>
            <li><b>注销账号</b>：如需注销账号或删除全部数据，请通过下方方式联系我们处理。</li>
          </ul>
        </div>

        <div className="privacy-section">
          <h3><span className="section-icon"><i className="fa fa-child"></i></span>未成年人保护</h3>
          <p>若您未满 14 周岁，请在监护人指导下使用本站。我们不会有意收集未成年人的个人信息。</p>
        </div>

        <div className="privacy-section">
          <h3><span className="section-icon"><i className="fa fa-refresh"></i></span>政策的更新</h3>
          <p>我们可能适时更新本政策。重大变更会通过站内公告或页面提示告知，更新后继续使用本站即视为接受更新后的政策。本文档顶部会标注最近更新日期。</p>
        </div>

        <div className="privacy-section privacy-contact">
          <h3><span className="section-icon"><i className="fa fa-envelope"></i></span>联系我们</h3>
          <p>如对本隐私政策有任何疑问、建议或投诉，请通过以下方式与我们联系：</p>
          <div className="privacy-contact-actions">
            <a className="privacy-contact-btn" href="mailto:3890320020@qq.com"><i className="fa fa-envelope-o"></i> 3890320020@qq.com</a>
            <a className="privacy-contact-btn" href="https://github.com/crazying-dev" target="_blank" rel="noopener"><i className="fa fa-github"></i> GitHub: crazying-dev</a>
          </div>
        </div>

        <div className="privacy-footer">
          <p><i className="fa fa-info-circle"></i> 感谢您对妖精论坛的信任。在社区里的每一次分享都很珍贵，我们承诺会妥善保管您的每一份数据。</p>
        </div>
      </div>
    </>
  );
}
