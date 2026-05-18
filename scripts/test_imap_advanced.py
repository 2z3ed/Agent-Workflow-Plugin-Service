#!/usr/bin/env python3
"""Advanced IMAP diagnostic for NetEase (163/126) Unsafe Login issues."""

import imaplib
import os
import ssl
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.plugins.email.email_fetcher import EmailFetcher, ImapError

# imaplib does not register ID by default (RFC 2971)
if "ID" not in imaplib.Commands:
    imaplib.Commands["ID"] = ("AUTH",)

ID_PROFILES = [
    '("name" "Mozilla Thunderbird" "version" "115.0" "os" "Linux" "vendor" "Mozilla")',
    '("name" "Microsoft Outlook" "version" "16.0" "os" "Windows" "vendor" "Microsoft")',
    '("name" "PythonIMAP" "version" "1.0" "vendor" "MyApp")',
]


def _print_step(label: str, status: str, data) -> None:
    text = EmailFetcher._decode_imap_data(data)
    print(f"   status={status!r} response={text!r}")


def _send_id(mailbox: imaplib.IMAP4_SSL, id_str: str) -> tuple[str, object]:
    return mailbox._simple_command("ID", id_str)


def _try_select(mailbox: imaplib.IMAP4_SSL) -> tuple[str, object]:
    return mailbox.select("INBOX")


def _connect_ssl(host: str, port: int = 993, verify: bool = True) -> imaplib.IMAP4_SSL:
    if verify:
        return imaplib.IMAP4_SSL(host, port)
    ctx = ssl._create_unverified_context()
    return imaplib.IMAP4_SSL(host, port, ssl_context=ctx)


def run_flow(mailbox: imaplib.IMAP4_SSL, email_addr: str, password: str, *, label: str) -> bool:
    print(f"\n--- 流程: {label} ---")
    try:
        status, data = mailbox.login(email_addr, password)
        print("✅ 登录成功")
        _print_step("LOGIN", status, data)
    except imaplib.IMAP4.error as exc:
        print(f"❌ 登录失败: {exc}")
        return False

    status, data = mailbox.capability()
    caps = EmailFetcher._decode_imap_data(data)
    print(f"📋 CAPABILITY: {caps[:200]}{'...' if len(caps) > 200 else ''}")
    _print_step("CAPABILITY", status, data)

    for i, id_str in enumerate(ID_PROFILES, 1):
        print(f"📤 发送 ID 命令 (方案 {i}): {id_str}")
        try:
            status, data = _send_id(mailbox, id_str)
            _print_step("ID", status, data)
            if status == "OK":
                print(f"✅ ID 命令响应: OK")
            else:
                print(f"⚠️  ID 非 OK，继续尝试 SELECT")
        except imaplib.IMAP4.error as exc:
            print(f"⚠️  ID 命令异常: {exc}")

        status, data = _try_select(mailbox)
        _print_step("SELECT INBOX", status, data)
        if status == "OK":
            print("✅ SELECT INBOX 成功")
            status, data = mailbox.search(None, "UNSEEN")
            _print_step("SEARCH UNSEEN", status, data)
            count = len(data[0].split()) if status == "OK" and data and data[0] else 0
            print(f"📧 共有 {count} 封未读邮件")
            return True
        print("❌ SELECT INBOX 仍失败，尝试下一个 ID 配置")

    return False


def main() -> int:
    fetcher = EmailFetcher()
    try:
        email_addr, password, imap_server = fetcher._parse_mailbox()
    except ValueError as exc:
        print(f"❌ 配置错误: {exc}")
        return 1

    host = imap_server.split(":")[0]
    port = 993
    if ":" in imap_server:
        _, port_str = imap_server.rsplit(":", 1)
        if port_str.isdigit():
            port = int(port_str)

    print(f"目标: {email_addr} @ {host}:{port}")

    try:
        mailbox = _connect_ssl(host, port, verify=True)
        print("✅ 连接成功 (默认 SSL 校验)")
    except Exception as exc:
        print(f"❌ 连接失败: {exc}")
        return 1

    ok = run_flow(mailbox, email_addr, password, label="默认 SSL + ID + SELECT")
    try:
        mailbox.logout()
    except Exception:
        pass

    if ok:
        return 0

    print("\n--- 回退: 不校验证书 + EmailFetcher 内置流程 ---")
    try:
        mailbox2 = fetcher._connect_and_select_inbox(email_addr, password, imap_server)
        status, data = mailbox2.search(None, "UNSEEN")
        count = len(data[0].split()) if status == "OK" and data and data[0] else 0
        print(f"✅ EmailFetcher 流程成功，未读 {count} 封")
        mailbox2.logout()
        return 0
    except ImapError as exc:
        print(f"❌ EmailFetcher 流程失败: {exc}")
    except Exception as exc:
        print(f"❌ 失败: {exc}")

    print("\n--- 回退: ssl._create_unverified_context ---")
    try:
        mailbox3 = _connect_ssl(host, port, verify=False)
        print("✅ 连接成功 (跳过证书校验)")
        ok3 = run_flow(mailbox3, email_addr, password, label="无证书校验 + ID + SELECT")
        mailbox3.logout()
        return 0 if ok3 else 1
    except Exception as exc:
        print(f"❌ 仍失败: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
