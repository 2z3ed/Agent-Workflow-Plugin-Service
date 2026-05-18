"""Handle Feishu bot commands received via long connection."""

import logging
import re
import threading
from typing import Optional

from app.config import settings
from app.services.feishu_client import FeishuAppClient
from app.task_manager import task_manager

logger = logging.getLogger(__name__)

EMAIL_COMMAND_KEYWORDS = ("分析邮件", "邮件报告", "跑邮件")

_MENTION_PATTERN = re.compile(r"@_\S+\s*")


def _normalize_message_text(text: str) -> str:
    cleaned = _MENTION_PATTERN.sub("", text or "").strip()
    return cleaned


def is_email_analysis_command(text: str) -> bool:
    normalized = _normalize_message_text(text)
    return any(keyword in normalized for keyword in EMAIL_COMMAND_KEYWORDS)


def handle_feishu_message(payload: dict) -> None:
    """Entry point registered on Feishu long-connection message events."""
    chat_id = payload.get("chat_id")
    text = payload.get("text", "")
    if not chat_id:
        logger.debug("Ignore Feishu message without chat_id")
        return
    if not is_email_analysis_command(text):
        return

    logger.info("Feishu email command detected in chat_id=%s text=%r", chat_id, text[:100])
    app_client = FeishuAppClient()

    if not app_client.send_text("📧 正在分析邮件，请稍候...", receive_id=chat_id):
        logger.error("Failed to send Feishu ack for chat_id=%s", chat_id)
        return

    thread = threading.Thread(
        target=_run_email_analysis_and_reply,
        args=(chat_id,),
        name=f"feishu-email-cmd-{chat_id[:8]}",
        daemon=True,
    )
    thread.start()


def _run_email_analysis_and_reply(chat_id: str) -> None:
    app_client = FeishuAppClient()
    params = {
        "chat_id": chat_id,
        "send_feishu": False,
    }
    task_id: Optional[str] = None
    try:
        task_id, _created_at = task_manager.create_task("email", params)
        task_manager.execute_plugin_task(task_id, "email", params)
        task = task_manager.get_task(task_id)
        if task is None:
            raise RuntimeError("任务记录未找到")

        if task.get("status") == "failed":
            raise RuntimeError(task.get("error") or "邮件分析任务失败")

        result = task.get("result") or {}
        report = result.get("report") or "本次无新邮件需要分析。"
        if not app_client.send_text(report, receive_id=chat_id):
            raise RuntimeError("汇总报告发送失败")
        logger.info("Email analysis command completed for chat_id=%s task_id=%s", chat_id, task_id)
    except Exception as exc:
        logger.exception("Email analysis command failed for chat_id=%s: %s", chat_id, exc)
        app_client.send_text(f"❌ 分析失败: {exc}", receive_id=chat_id)
