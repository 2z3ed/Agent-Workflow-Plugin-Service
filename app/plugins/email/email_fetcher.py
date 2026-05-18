import email
import imaplib
import logging
import os
from email.header import decode_header
from email.utils import parseaddr
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

# RFC 2971 – imaplib does not register ID by default
if "ID" not in imaplib.Commands:
    imaplib.Commands["ID"] = ("AUTH",)

_NETEASE_ID = (
    '("name" "Mozilla Thunderbird" "version" "115.0" '
    '"os" "Linux" "vendor" "Mozilla" "support-email" "support@example.com")'
)


class ImapError(RuntimeError):
    pass


class EmailFetcher:
    @staticmethod
    def _is_netease_server(imap_server: str, email_addr: str) -> bool:
        host = imap_server.lower().split(":")[0]
        domain = email_addr.rsplit("@", 1)[-1].lower() if "@" in email_addr else ""
        netease_hosts = ("imap.163.com", "imap.126.com", "imap.yeah.net", "imap.188.com")
        netease_domains = ("163.com", "126.com", "yeah.net", "188.com", "vip.163.com", "vip.126.com")
        return host in netease_hosts or domain in netease_domains or any(h in host for h in ("163.com", "126.com", "188.com"))

    @staticmethod
    def _send_client_id(mailbox: imaplib.IMAP4_SSL, id_params: str = _NETEASE_ID) -> tuple[str, Any]:
        logger.debug("Sending IMAP ID: %s", id_params)
        return mailbox._simple_command("ID", id_params)
    @staticmethod
    def _decode_imap_data(data: Any) -> str:
        if data is None:
            return ""
        if isinstance(data, bytes):
            return data.decode(errors="replace")
        if isinstance(data, (list, tuple)) and data:
            return EmailFetcher._decode_imap_data(data[0])
        return str(data)

    @staticmethod
    def _check_imap_response(operation: str, status: str, data: Any, *, context: str = "") -> None:
        if status == "OK":
            return
        detail = EmailFetcher._decode_imap_data(data)
        suffix = f" ({context})" if context else ""
        hint = ""
        if "unsafe login" in detail.lower():
            hint = (
                " NetEase (163/126) blocked this client: enable IMAP in web settings, "
                "use a fresh authorization code (not login password), and allow third-party client access."
            )
        raise ImapError(f"IMAP {operation} failed{suffix}: status={status!r}, response={detail!r}.{hint}")

    def _parse_mailbox(self) -> tuple[str, str, str]:
        raw = settings.mailboxes.strip() or os.getenv("MAILBOXES", "").strip()
        if not raw:
            raise ValueError(
                "MAILBOXES is not configured. Set it in .env as email:authorization_code:imap_server "
                "(e.g. user@163.com:ABCD1234:imap.163.com). Use the mailbox authorization code, not the login password."
            )

        first = raw.split(";")[0].strip()
        parts = first.split(":")
        if len(parts) < 3:
            raise ValueError(
                "MAILBOXES format is invalid. Expected email:authorization_code:imap_server "
                f"(got {len(parts)} colon-separated parts)."
            )
        return parts[0], parts[1], ":".join(parts[2:])

    def parse_mailboxes(self) -> list[tuple[str, str, str]]:
        raw = settings.mailboxes.strip() or os.getenv("MAILBOXES", "").strip()
        if not raw:
            return []
        mailboxes = []
        for item in raw.split(";"):
            item = item.strip()
            if not item:
                continue
            parts = item.split(":")
            if len(parts) < 3:
                continue
            mailboxes.append((parts[0], parts[1], ":".join(parts[2:])))
        return mailboxes

    def _connect_and_select_inbox(self, email_addr: str, password: str, imap_server: str) -> imaplib.IMAP4_SSL:
        logger.info("Connecting to IMAP server %s as %s", imap_server, email_addr)
        mailbox = imaplib.IMAP4_SSL(imap_server)
        try:
            try:
                status, data = mailbox.login(email_addr, password)
            except imaplib.IMAP4.error as exc:
                raise ImapError(
                    f"IMAP login failed for {email_addr} on {imap_server}: {exc}. "
                    "Verify MAILBOXES uses the authorization code (not login password), "
                    "IMAP is enabled in mailbox settings, and the code has not expired."
                ) from exc
            self._check_imap_response(
                "LOGIN",
                status,
                data,
                context=f"server={imap_server}, user={email_addr}",
            )
            logger.debug("IMAP login OK: status=%r, data=%r", status, data)

            if self._is_netease_server(imap_server, email_addr):
                try:
                    id_status, id_data = self._send_client_id(mailbox)
                    logger.info("NetEase IMAP ID: status=%r, response=%s", id_status, self._decode_imap_data(id_data))
                    if id_status != "OK":
                        logger.warning("IMAP ID returned non-OK, continuing with SELECT")
                except imaplib.IMAP4.error as exc:
                    logger.warning("IMAP ID command failed (continuing): %s", exc)

            status, data = mailbox.select("INBOX")
            self._check_imap_response(
                "SELECT INBOX",
                status,
                data,
                context=f"server={imap_server}, user={email_addr}",
            )
            logger.info("Selected INBOX: status=%r, message_count=%s", status, self._decode_imap_data(data))
            return mailbox
        except Exception:
            try:
                mailbox.logout()
            except Exception:
                pass
            raise

    def fetch_recent_unread(self, limit: int = 5, lookback_days: int | None = None, only_unread: bool = True) -> list[dict[str, Any]]:
        email_addr, password, imap_server = self._parse_mailbox()
        messages: list[dict[str, Any]] = []
        days = lookback_days if lookback_days is not None else settings.lookback_days

        mailbox = self._connect_and_select_inbox(email_addr, password, imap_server)
        try:
            search_args = ["SINCE", self._format_since(days)]
            if only_unread:
                search_args = ["UNSEEN"] + search_args
            status, data = mailbox.search(None, *search_args)
            self._check_imap_response(
                "SEARCH",
                status,
                data,
                context=f"criteria={search_args!r}",
            )

            raw_ids = data[0] if data and data[0] else b""
            ids = raw_ids.split()[-limit:] if raw_ids else []
            for msg_id in ids:
                status, msg_data = mailbox.fetch(msg_id, "(RFC822)")
                if status != "OK" or not msg_data or not msg_data[0]:
                    logger.warning("Skipping message %s: fetch status=%r", msg_id, status)
                    continue
                raw_email = msg_data[0][1]
                parsed = email.message_from_bytes(raw_email)
                body = self._extract_body(parsed)
                sender = parseaddr(parsed.get("From", ""))[1] or parsed.get("From", "")
                subject = self._decode_mime_header(parsed.get("Subject", ""))
                message_id = parsed.get("Message-ID", "").strip() or msg_id.decode(errors="ignore")
                received_time = parsed.get("Date", "")
                messages.append({
                    "message_id": message_id,
                    "sender": sender,
                    "subject": subject,
                    "body": body,
                    "received_time": received_time,
                    "mailbox_email": email_addr,
                })
        finally:
            try:
                mailbox.logout()
            except Exception:
                pass
        return messages

    def _format_since(self, lookback_days: int) -> str:
        from datetime import datetime, timedelta

        return (datetime.utcnow() - timedelta(days=lookback_days)).strftime("%d-%b-%Y")

    def _decode_mime_header(self, value: str) -> str:
        decoded, charset = decode_header(value)[0]
        if isinstance(decoded, bytes):
            return decoded.decode(charset or "utf-8", errors="ignore")
        return str(decoded)

    def _extract_body(self, msg) -> str:
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type in ("text/plain", "text/html") and not part.get("Content-Disposition"):
                    payload = part.get_payload(decode=True)
                    if payload:
                        return payload.decode(part.get_content_charset() or "utf-8", errors="ignore")
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                return payload.decode(msg.get_content_charset() or "utf-8", errors="ignore")
        return ""
