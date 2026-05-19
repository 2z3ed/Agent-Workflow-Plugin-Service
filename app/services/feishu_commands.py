"""Handle Feishu bot commands received via long connection."""

import logging
import re
import threading
from typing import Optional

from app.services.feishu_client import FeishuAppClient
from app.task_manager import task_manager

logger = logging.getLogger(__name__)

EMAIL_COMMAND_KEYWORDS = ("分析邮件", "邮件报告", "跑邮件")
PRODUCT_COMMAND_PATTERN = re.compile(r"^选品分析\s+(.+)$")
LISTING_COMMAND_PATTERN = re.compile(r"^Listing 优化\s+(.+)$", re.IGNORECASE)
AD_COMMAND_PATTERN = re.compile(r"^(广告报告|广告优化)$")

_MENTION_PATTERN = re.compile(r"@_\S+\s*")


def _normalize_message_text(text: str) -> str:
    cleaned = _MENTION_PATTERN.sub("", text or "").strip()
    return cleaned


def is_email_analysis_command(text: str) -> bool:
    normalized = _normalize_message_text(text)
    return any(keyword in normalized for keyword in EMAIL_COMMAND_KEYWORDS)


def parse_product_keyword(text: str) -> Optional[str]:
    normalized = _normalize_message_text(text)
    match = PRODUCT_COMMAND_PATTERN.match(normalized)
    if not match:
        return None
    keyword = match.group(1).strip()
    return keyword or None


def parse_listing_product_input(text: str) -> Optional[str]:
    normalized = _normalize_message_text(text)
    match = LISTING_COMMAND_PATTERN.match(normalized)
    if not match:
        return None
    product_input = match.group(1).strip()
    return product_input or None


def is_ad_report_command(text: str) -> bool:
    normalized = _normalize_message_text(text)
    return bool(AD_COMMAND_PATTERN.match(normalized))


def handle_feishu_message(payload: dict) -> None:
    """Entry point registered on Feishu long-connection message events."""
    chat_id = payload.get("chat_id")
    text = payload.get("text", "")
    if not chat_id:
        logger.debug("Ignore Feishu message without chat_id")
        return

    if is_ad_report_command(text):
        logger.info("Feishu ad command detected in chat_id=%s", chat_id)
        app_client = FeishuAppClient()
        if not app_client.send_text("正在获取广告数据...", receive_id=chat_id):
            logger.error("Failed to send Feishu ack for ad chat_id=%s", chat_id)
            return

        thread = threading.Thread(
            target=_run_ad_report_and_reply,
            args=(chat_id,),
            name=f"feishu-ad-cmd-{chat_id[:8]}",
            daemon=True,
        )
        thread.start()
        return

    listing_input = parse_listing_product_input(text)
    if listing_input:
        logger.info(
            "Feishu listing command detected in chat_id=%s product_input=%r",
            chat_id,
            listing_input[:100],
        )
        app_client = FeishuAppClient()
        if not app_client.send_text("正在分析 Listing...", receive_id=chat_id):
            logger.error("Failed to send Feishu ack for listing chat_id=%s", chat_id)
            return

        thread = threading.Thread(
            target=_run_listing_analysis_and_reply,
            args=(chat_id, listing_input),
            name=f"feishu-listing-cmd-{chat_id[:8]}",
            daemon=True,
        )
        thread.start()
        return

    product_keyword = parse_product_keyword(text)
    if product_keyword:
        logger.info(
            "Feishu product command detected in chat_id=%s keyword=%r",
            chat_id,
            product_keyword,
        )
        app_client = FeishuAppClient()
        if not app_client.send_text("正在分析中...", receive_id=chat_id):
            logger.error("Failed to send Feishu ack for product chat_id=%s", chat_id)
            return

        thread = threading.Thread(
            target=_run_product_analysis_and_reply,
            args=(chat_id, product_keyword),
            name=f"feishu-product-cmd-{chat_id[:8]}",
            daemon=True,
        )
        thread.start()
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


def _run_ad_report_and_reply(chat_id: str) -> None:
    app_client = FeishuAppClient()
    params = {"chat_id": chat_id}
    task_id: Optional[str] = None
    try:
        task_id, _created_at = task_manager.create_task("ad", params)
        task_manager.execute_plugin_task(task_id, "ad", params)
        task = task_manager.get_task(task_id)
        if task is None:
            raise RuntimeError("任务记录未找到")

        if task.get("status") == "failed":
            raise RuntimeError(task.get("error") or "广告报告任务失败")

        result = task.get("result") or {}
        report = result.get("report") or "广告报告生成完成，但未生成报告内容。"
        if not app_client.send_text(report, receive_id=chat_id):
            raise RuntimeError("广告报告发送失败")
        logger.info(
            "Ad report command completed for chat_id=%s task_id=%s",
            chat_id,
            task_id,
        )
    except Exception as exc:
        logger.exception("Ad report command failed for chat_id=%s: %s", chat_id, exc)
        app_client.send_text(f"❌ 广告报告失败: {exc}", receive_id=chat_id)


def _run_listing_analysis_and_reply(chat_id: str, product_input: str) -> None:
    app_client = FeishuAppClient()
    params = {
        "chat_id": chat_id,
        "product_input": product_input,
    }
    task_id: Optional[str] = None
    try:
        task_id, _created_at = task_manager.create_task("listing", params)
        task_manager.execute_plugin_task(task_id, "listing", params)
        task = task_manager.get_task(task_id)
        if task is None:
            raise RuntimeError("任务记录未找到")

        if task.get("status") == "failed":
            raise RuntimeError(task.get("error") or "Listing 优化任务失败")

        result = task.get("result") or {}
        report = result.get("report") or "Listing 优化完成，但未生成报告。"
        if not app_client.send_text(report, receive_id=chat_id):
            raise RuntimeError("Listing 报告发送失败")
        logger.info(
            "Listing analysis command completed for chat_id=%s task_id=%s product_input=%r",
            chat_id,
            task_id,
            product_input[:100],
        )
    except Exception as exc:
        logger.exception("Listing analysis command failed for chat_id=%s: %s", chat_id, exc)
        app_client.send_text(f"❌ Listing 优化失败: {exc}", receive_id=chat_id)


def _run_product_analysis_and_reply(chat_id: str, keyword: str) -> None:
    app_client = FeishuAppClient()
    params = {
        "chat_id": chat_id,
        "keyword": keyword,
    }
    task_id: Optional[str] = None
    try:
        task_id, _created_at = task_manager.create_task("product", params)
        task_manager.execute_plugin_task(task_id, "product", params)
        task = task_manager.get_task(task_id)
        if task is None:
            raise RuntimeError("任务记录未找到")

        if task.get("status") == "failed":
            raise RuntimeError(task.get("error") or "选品分析任务失败")

        result = task.get("result") or {}
        report = result.get("report") or "选品分析完成，但未生成报告。"
        if not app_client.send_text(report, receive_id=chat_id):
            raise RuntimeError("选品报告发送失败")
        logger.info(
            "Product analysis command completed for chat_id=%s task_id=%s keyword=%r",
            chat_id,
            task_id,
            keyword,
        )
    except Exception as exc:
        logger.exception("Product analysis command failed for chat_id=%s: %s", chat_id, exc)
        app_client.send_text(f"❌ 选品分析失败: {exc}", receive_id=chat_id)


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
