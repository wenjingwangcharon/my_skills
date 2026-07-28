#!/usr/bin/env python3
"""
QQ 邮箱 IMAP 邮件获取脚本
对应 Coze 工作流 email_interview 的 get_email_list 插件节点

用法:
  python fetch_emails.py --email <邮箱地址> --auth-code <授权码> [--count 30] [--output output.json]

依赖: 仅 Python 标准库 (imaplib, email, json)
"""

import argparse
import imaplib
import email
import email.message
import json
import sys
from email.header import decode_header
from email.utils import parsedate_to_datetime
from datetime import datetime, timedelta


IMAP_SERVER = "imap.qq.com"
IMAP_PORT = 993


def _decode_str(value: str) -> str:
    """解码邮件头部字段（Subject, From 等）"""
    if value is None:
        return ""
    parts = decode_header(value)
    result = []
    for content, charset in parts:
        if isinstance(content, bytes):
            try:
                result.append(content.decode(charset or "utf-8", errors="replace"))
            except (LookupError, TypeError):
                result.append(content.decode("utf-8", errors="replace"))
        else:
            result.append(content)
    return "".join(result)


def _get_email_body(msg: email.message.Message) -> str:
    """提取邮件正文，优先纯文本，其次 HTML"""
    if msg.is_multipart():
        text_part = None
        html_part = None
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain" and text_part is None:
                text_part = part
            elif ct == "text/html" and html_part is None:
                html_part = part
        chosen = text_part or html_part
        if chosen:
            return _decode_payload(chosen)
        return ""
    else:
        return _decode_payload(msg)


def _decode_payload(part: email.message.Message) -> str:
    """解码单个邮件部分的 payload"""
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except (LookupError, TypeError):
        return payload.decode("utf-8", errors="replace")


def _strip_html(html: str) -> str:
    """简单去除 HTML 标签"""
    import re
    text = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def fetch_emails(
    email_addr: str,
    auth_code: str,
    count: int = 30,
    mailbox: str = "INBOX",
) -> list[dict]:
    """
    从 QQ 邮箱 IMAP 服务器拉取最新邮件

    Args:
        email_addr: QQ 邮箱地址
        auth_code: IMAP 授权码（非 QQ 密码）
        count: 拉取数量（默认 30）
        mailbox: 邮箱目录（默认 INBOX）

    Returns:
        邮件列表，每封邮件包含: subject, from, date, content
    """
    mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
    try:
        mail.login(email_addr, auth_code)
        mail.select(mailbox)

        status, data = mail.search(None, "ALL")
        if status != "OK":
            return []

        mail_ids = data[0].split()
        fetch_ids = mail_ids[-count:] if len(mail_ids) >= count else mail_ids

        emails = []
        for mail_id in reversed(fetch_ids):
            status, msg_data = mail.fetch(mail_id, "(RFC822)")
            if status != "OK":
                continue

            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            subject = _decode_str(msg.get("Subject", ""))
            from_addr = _decode_str(msg.get("From", ""))
            date_str = msg.get("Date", "")

            try:
                date_obj = parsedate_to_datetime(date_str)
                date_formatted = date_obj.strftime("%Y-%m-%d %H:%M:%S") if date_obj else date_str
            except Exception:
                date_formatted = date_str

            content = _get_email_body(msg)
            # 如果内容是 HTML，简单转为纯文本
            if content and "<html" in content.lower():
                content = _strip_html(content)

            emails.append({
                "subject": subject,
                "from": from_addr,
                "date": date_formatted,
                "content": content,
            })

        return emails

    finally:
        try:
            mail.logout()
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="QQ 邮箱 IMAP 邮件获取")
    parser.add_argument("--email", required=True, help="QQ 邮箱地址")
    parser.add_argument("--auth-code", required=True, help="IMAP 授权码（非 QQ 密码）")
    parser.add_argument("--count", type=int, default=30, help="拉取数量（默认 30）")
    parser.add_argument("--output", default=None, help="输出 JSON 文件路径（默认输出到 stdout）")
    args = parser.parse_args()

    # Windows 终端编码处理
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    print(f"正在连接 {IMAP_SERVER}:{IMAP_PORT} ...", file=sys.stderr)
    try:
        emails = fetch_emails(
            email_addr=args.email,
            auth_code=args.auth_code,
            count=args.count,
        )
    except imaplib.IMAP4.error as e:
        print(f"IMAP 认证失败: {e}", file=sys.stderr)
        print("请检查邮箱地址和授权码是否正确（授权码非 QQ 密码，需在 QQ 邮箱设置中开启 IMAP 并生成）", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"获取邮件失败: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"成功获取 {len(emails)} 封邮件", file=sys.stderr)

    output = json.dumps(emails, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"已保存到 {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
