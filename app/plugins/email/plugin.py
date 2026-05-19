import logging
from typing import Any

from app.config import settings
from app.plugins.base import Plugin

from .dify_client import DifyClient
from .email_fetcher import EmailFetcher
from . import repository
from . import reporter
from app.services.feishu_client import FeishuClient

logger = logging.getLogger(__name__)


class EmailPlugin(Plugin):
    name = "email"
    description = "分析多个邮箱的未读邮件，提取客户意向、跟进状态，并生成汇总报告，可推送飞书"
    category = "business"
    docs = """
# 邮件分析插件

从配置的邮箱中读取未读邮件，调用 Dify 分析客户意向、跟进状态，生成汇总报告并可选推送到飞书。

## 输入参数（可选）
- lookback_days: 查询最近N天邮件，默认从环境变量读取
- max_emails_per_box: 每个邮箱最多读取数量
- only_unread: 只读未读邮件，默认 true
- send_feishu: 是否发送飞书通知，默认 true

## 输出示例
{
  "total_emails_fetched": 5,
  "total_new_emails": 3,
  "report": "📧 汇总报告...",
  "used_config": {...}
}
"""

    def __init__(self) -> None:
        if not settings.email_dify_api_url or not settings.email_dify_api_key:
            raise ValueError(
                "EMAIL_DIFY_API_URL and EMAIL_DIFY_API_KEY must be set for email plugin"
            )
        self.fetcher = EmailFetcher()
        self.dify_client = DifyClient(
            settings.email_dify_api_url,
            settings.email_dify_api_key,
        )
        repository.init_email_db()

    def execute(self, task_id: str, **params) -> dict:
        chat_id = params.get("chat_id")
        if chat_id:
            logger.info("Email plugin task %s received chat_id=%s", task_id, chat_id)

        lookback_days = int(params.get("lookback_days") or settings.lookback_days)
        max_emails = int(params.get("max_emails_per_box") or settings.max_emails_per_box)
        only_unread = params.get("only_unread", settings.only_unread)
        send_feishu = params.get("send_feishu", settings.send_feishu)
        if isinstance(only_unread, str):
            only_unread = only_unread.lower() == "true"
        if isinstance(send_feishu, str):
            send_feishu = send_feishu.lower() == "true"

        logger.info(
            "Email plugin config for task %s: lookback_days=%s, max_emails_per_box=%s, only_unread=%s, send_feishu=%s",
            task_id,
            lookback_days,
            max_emails,
            only_unread,
            send_feishu,
        )

        mailboxes = self.fetcher.parse_mailboxes()
        all_analyses: list[dict[str, Any]] = []
        total_emails_fetched = 0
        total_new_emails = 0
        details: list[dict[str, Any]] = []
        errors: list[str] = []

        for mailbox_email, password, imap_server in mailboxes:
            try:
                emails = self._fetch_box_emails(
                    mailbox_email, password, imap_server, max_emails, lookback_days, only_unread
                )
                total_emails_fetched += len(emails)
            except Exception as exc:
                errors.append(f"{mailbox_email}: {exc}")
                logger.exception("Failed to fetch emails for %s", mailbox_email)
                continue

            for email_item in emails:
                message_id = email_item.get("message_id", "")
                if not message_id:
                    continue
                if repository.is_duplicate(message_id):
                    details.append({
                        "message_id": message_id,
                        "mailbox_email": mailbox_email,
                        "subject": email_item.get("subject", ""),
                        "status": "duplicate",
                    })
                    continue

                try:
                    analysis = self.dify_client.analyze(
                        f"From: {email_item['sender']}\nSubject: {email_item['subject']}\nBody:\n{email_item['body']}"
                    )
                    repository.save_processed(
                        message_id=message_id,
                        mailbox_email=mailbox_email,
                        sender=email_item.get("sender", ""),
                        subject=email_item.get("subject", ""),
                        received_time=email_item.get("received_time", ""),
                        analysis_result=analysis,
                    )
                    total_new_emails += 1
                    item = {
                        "message_id": message_id,
                        "mailbox_email": mailbox_email,
                        "sender": email_item.get("sender", ""),
                        "subject": email_item.get("subject", ""),
                        "analysis_result": analysis,
                    }
                    all_analyses.append(item)
                    details.append({**item, "status": "processed"})
                except Exception as exc:
                    errors.append(f"{message_id}: {exc}")
                    logger.exception("Failed to analyze email %s", message_id)
                    continue

        report = reporter.generate_report(all_analyses)
        if errors:
            report = report + "\n\n处理错误：\n" + "\n".join(f"- {item}" for item in errors)

        if send_feishu:
            try:
                client = FeishuClient(
                    webhook_url=settings.feishu_webhook_url or None,
                    secret=settings.feishu_secret or None,
                )
                receive_id = chat_id or settings.feishu_chat_id
                sent = client.send_message(report, receive_id=receive_id or None)
                if sent:
                    logger.info("飞书推送成功，task_id=%s", task_id)
                else:
                    logger.error("飞书推送返回失败，task_id=%s", task_id)
            except Exception as exc:
                logger.error("飞书推送失败: %s", exc)
        else:
            logger.info("根据参数跳过飞书推送，task_id=%s", task_id)

        return {
            "task_id": task_id,
            "chat_id": chat_id,
            "total_emails_fetched": total_emails_fetched,
            "total_new_emails": total_new_emails,
            "report": report,
            "details": details,
            "used_config": {
                "lookback_days": lookback_days,
                "max_emails_per_box": max_emails,
                "only_unread": only_unread,
                "send_feishu": send_feishu,
            },
        }

    def _fetch_box_emails(
        self,
        mailbox_email: str,
        password: str,
        imap_server: str,
        max_emails: int,
        lookback_days: int,
        only_unread: bool,
    ) -> list[dict]:
        """Fetch emails via EmailFetcher (includes NetEase IMAP ID support)."""
        mailbox = self.fetcher._connect_and_select_inbox(mailbox_email, password, imap_server)
        try:
            since = self.fetcher._format_since(lookback_days)
            search_args = ["SINCE", since]
            if only_unread:
                search_args = ["UNSEEN"] + search_args
            status, data = mailbox.search(None, *search_args)
            self.fetcher._check_imap_response("SEARCH", status, data, context=f"criteria={search_args!r}")
            raw_ids = data[0] if data and data[0] else b""
            ids = raw_ids.split()[-max_emails:] if raw_ids else []
            messages: list[dict] = []
            for msg_id in ids:
                status, msg_data = mailbox.fetch(msg_id, "(RFC822)")
                if status != "OK" or not msg_data or not msg_data[0]:
                    continue
                import email as email_lib
                from email.header import decode_header
                from email.utils import parseaddr

                raw_email = msg_data[0][1]
                parsed = email_lib.message_from_bytes(raw_email)
                body = self.fetcher._extract_body(parsed)
                sender = parseaddr(parsed.get("From", ""))[1] or parsed.get("From", "")
                subject = self.fetcher._decode_mime_header(parsed.get("Subject", ""))
                message_id = parsed.get("Message-ID", "").strip() or msg_id.decode(errors="ignore")
                messages.append({
                    "message_id": message_id,
                    "sender": sender,
                    "subject": subject,
                    "body": body,
                    "received_time": parsed.get("Date", ""),
                    "mailbox_email": mailbox_email,
                })
            return messages
        finally:
            try:
                mailbox.logout()
            except Exception:
                pass
