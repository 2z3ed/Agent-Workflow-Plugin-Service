import base64
import hashlib
import hmac
import json
import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

import requests

from app.config import settings

logger = logging.getLogger(__name__)

_message_handler: Optional[Callable[[dict], None]] = None
_long_conn_singleton: Optional["FeishuLongConnClient"] = None


def set_message_handler(handler: Optional[Callable[[dict], None]]) -> None:
    global _message_handler
    _message_handler = handler


@dataclass
class LongConnState:
    running: bool = False
    thread: threading.Thread | None = None


class FeishuLongConnClient:
    def __init__(self, app_id: Optional[str] = None, app_secret: Optional[str] = None):
        self.app_id = app_id or settings.feishu_app_id
        self.app_secret = app_secret or settings.feishu_app_secret
        self._state = LongConnState()
        self._ws_client = None

    def start_websocket(self) -> None:
        if self._state.running:
            return
        if not self.app_id or not self.app_secret:
            logger.info("Feishu long connection skipped: missing FEISHU_APP_ID or FEISHU_APP_SECRET")
            return

        def _runner() -> None:
            try:
                self._run_long_conn()
            except Exception as exc:
                logger.exception("Feishu long connection exited: %s", exc)
            finally:
                self._state.running = False

        self._state.running = True
        self._state.thread = threading.Thread(target=_runner, name="feishu-longconn", daemon=True)
        self._state.thread.start()
        logger.info("Feishu long connection thread started (app_id=%s)", self.app_id)

    def _run_long_conn(self) -> None:
        try:
            from lark_oapi import Client as LarkClient
            from lark_oapi.api.im.v1.model.p2_im_message_receive_v1 import P2ImMessageReceiveV1
            from lark_oapi.core.enum import LogLevel
            from lark_oapi.event.dispatcher_handler import EventDispatcherHandler
            from lark_oapi.ws import Client as WsClient
        except ImportError as exc:
            logger.warning("lark-oapi not installed, skip Feishu long connection: %s", exc)
            return

        def on_message(event: P2ImMessageReceiveV1) -> None:
            payload = self._event_to_dict(event)
            logger.info(
                "Received Feishu message: chat_id=%s type=%s text=%s",
                payload.get("chat_id"),
                payload.get("message_type"),
                payload.get("text", "")[:200],
            )
            if _message_handler:
                try:
                    _message_handler(payload)
                except Exception:
                    logger.exception("Feishu message handler failed")

        handler = (
            EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(on_message)
            .build()
        )
        log_level = LogLevel.INFO
        if settings.log_level.upper() == "DEBUG":
            log_level = LogLevel.DEBUG

        self._ws_client = WsClient(
            self.app_id,
            self.app_secret,
            event_handler=handler,
            log_level=log_level,
        )
        logger.info("Connecting Feishu WebSocket long connection...")
        self._ws_client.start()

    @staticmethod
    def _event_to_dict(event: object) -> dict:
        message = getattr(getattr(event, "event", None), "message", None)
        sender = getattr(getattr(event, "event", None), "sender", None)
        text = ""
        if message and message.content:
            try:
                content = json.loads(message.content)
                text = content.get("text", message.content)
            except (json.JSONDecodeError, TypeError):
                text = str(message.content)
        return {
            "message_id": getattr(message, "message_id", None),
            "chat_id": getattr(message, "chat_id", None),
            "message_type": getattr(message, "message_type", None),
            "text": text,
            "sender_id": getattr(getattr(sender, "sender_id", None), "open_id", None)
            or getattr(getattr(sender, "sender_id", None), "user_id", None),
            "raw_content": getattr(message, "content", None),
        }

    def stop(self) -> None:
        self._state.running = False
        logger.info("Feishu long connection stop requested")


def get_long_conn_client() -> FeishuLongConnClient:
    global _long_conn_singleton
    if _long_conn_singleton is None:
        _long_conn_singleton = FeishuLongConnClient()
    return _long_conn_singleton


class FeishuAppClient:
    """Send messages via Feishu App credentials (tenant token)."""

    def __init__(
        self,
        app_id: Optional[str] = None,
        app_secret: Optional[str] = None,
        chat_id: Optional[str] = None,
        receiver_type: Optional[str] = None,
    ):
        self.app_id = app_id or settings.feishu_app_id
        self.app_secret = app_secret or settings.feishu_app_secret
        self.chat_id = chat_id or settings.feishu_chat_id
        self.receiver_type = (receiver_type or settings.feishu_receiver_type or "chat").lower()

    def send_text(self, message: str, receive_id: Optional[str] = None) -> bool:
        target_id = receive_id or self.chat_id
        if not self.app_id or not self.app_secret:
            logger.error("Feishu App credentials not configured")
            return False
        if not target_id:
            logger.error("Feishu receive_id / FEISHU_CHAT_ID not configured")
            return False

        try:
            from lark_oapi import Client
            from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody
            from lark_oapi.core.enum import LogLevel
        except ImportError as exc:
            logger.error("lark-oapi not installed: %s", exc)
            return False

        client = (
            Client.builder()
            .app_id(self.app_id)
            .app_secret(self.app_secret)
            .log_level(LogLevel.INFO)
            .build()
        )
        receive_id_type = "chat_id" if self.receiver_type == "chat" else "open_id"
        body = (
            CreateMessageRequestBody.builder()
            .receive_id(target_id)
            .msg_type("text")
            .content(json.dumps({"text": message}, ensure_ascii=False))
            .build()
        )
        request = (
            CreateMessageRequest.builder()
            .receive_id_type(receive_id_type)
            .request_body(body)
            .build()
        )
        response = client.im.v1.message.create(request)
        if not response.success():
            logger.error(
                "Feishu send failed: code=%s msg=%s",
                response.code,
                response.msg,
            )
            return False
        logger.info("Feishu message sent to %s (%s)", target_id, receive_id_type)
        return True


class FeishuClient:
    def __init__(self, webhook_url: Optional[str] = None, secret: Optional[str] = None):
        self.webhook_url = webhook_url or settings.feishu_webhook_url
        self.secret = secret or settings.feishu_secret

    def send_text(self, message: str) -> bool:
        if self.webhook_url:
            return self._send_webhook_text(message)
        return FeishuAppClient().send_text(message)

    def send_message(self, message: str, receive_id: Optional[str] = None) -> bool:
        if self.webhook_url:
            return self._send_webhook_text(message)
        return FeishuAppClient().send_text(message, receive_id=receive_id)

    def _send_webhook_text(self, message: str) -> bool:
        if not self.webhook_url:
            return False
        payload = {
            "msg_type": "text",
            "content": {"text": message},
        }
        if self.secret:
            timestamp = str(int(time.time()))
            sign = self._sign(timestamp)
            payload["timestamp"] = timestamp
            payload["sign"] = sign
        response = requests.post(self.webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        return True

    def _sign(self, timestamp: str) -> str:
        string_to_sign = f"{timestamp}\n{self.secret}"
        hmac_code = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
        return base64.b64encode(hmac_code).decode("utf-8")
