import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header

# 阿里云邮件推送配置
SMTP_HOST = "smtpdm.aliyun.com"
SMTP_PORT = 465
SMTP_USER = "maomi@email.yjlt.top"
SMTP_PASSWORD = "LiMingGe120615"

SENDER = "maomi@email.yjlt.top"
SENDER_NAME = "妖精论坛"
RECEIVER = "1103060396@qq.com"


def send_email(content: str, subject: str = "测试邮件", receiver_list: list = None) -> bool:
    if receiver_list is None:
        receiver_list = [RECEIVER]
    try:
        msg = MIMEMultipart()
        # 正确设置发件人，避免乱码
        msg["From"] = Header(SENDER_NAME, "utf-8").encode() + f" <{SENDER}>"
        msg["To"] = ",".join(receiver_list)
        msg["Subject"] = Header(subject, "utf-8").encode()

        # 纯文本正文
        text_part = MIMEText(content, "plain", "utf-8")
        msg.attach(text_part)

        # SSL安全上下文
        context = ssl.create_default_context()
        server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context)
        server.set_debuglevel(0)  # 1开启详细调试日志，正式环境改为0

        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SENDER, receiver_list, msg.as_string())
        server.quit()

        print("✅ 邮件发送成功")
        print(f"发件人: {SENDER}")
        print(f"收件人: {receiver_list}")
        print(f"主题: {subject}")
        print(f"内容: {content}")
        return True

    except smtplib.SMTPAuthenticationError:
        print("❌ 认证失败：SMTP账号或独立SMTP密码错误")
        return False
    except smtplib.SMTPException as e:
        print(f"❌ SMTP发送异常: {e}")
        return False
    except Exception as e:
        print(f"❌ 未知错误：{e}")
        return False


if __name__ == "__main__":
    send_email("这是妖精论坛系统测试消息", "妖精论坛测试邮件")
