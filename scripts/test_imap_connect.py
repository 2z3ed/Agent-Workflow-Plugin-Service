#!/usr/bin/env python3
"""Minimal IMAP connectivity test (login + SELECT INBOX)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.plugins.email.email_fetcher import EmailFetcher, ImapError


def main() -> int:
    fetcher = EmailFetcher()
    try:
        email_addr, password, imap_server = fetcher._parse_mailbox()
    except ValueError as exc:
        print(f"❌ 配置错误: {exc}")
        return 1

    print(f"测试连接: {email_addr} @ {imap_server}")
    if EmailFetcher._is_netease_server(imap_server, email_addr):
        print("ℹ️  检测到网易邮箱，将自动发送 IMAP ID 命令")
    try:
        mailbox = fetcher._connect_and_select_inbox(email_addr, password, imap_server)
        status, data = mailbox.search(None, "UNSEEN")
        unseen = len(data[0].split()) if status == "OK" and data and data[0] else 0
        mailbox.logout()
        print("✅ IMAP 登录并选择 INBOX 成功")
        print(f"📧 未读邮件: {unseen} 封")
        return 0
    except ImapError as exc:
        print(f"❌ IMAP 错误: {exc}")
        return 1
    except Exception as exc:
        print(f"❌ 连接失败: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
