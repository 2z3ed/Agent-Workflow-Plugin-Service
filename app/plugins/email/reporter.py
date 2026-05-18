from collections import Counter


def _intent_bucket(analysis_result: dict) -> str:
    text = str(analysis_result).lower()
    if any(word in text for word in ["high", "高", "urgent", "hot", "强"]):
        return "高"
    if any(word in text for word in ["medium", "中", "warm", "跟进"]):
        return "中"
    if any(word in text for word in ["low", "低", "cold"]):
        return "低"
    return "未知"


def generate_report(analyses: list) -> str:
    total = len(analyses)
    intents = Counter(_intent_bucket(item.get("analysis_result", {})) for item in analyses)

    high_followups = []
    urgent_emails = []
    followup_tips = []

    for item in analyses:
        analysis = item.get("analysis_result", {})
        text = str(analysis)
        intent = _intent_bucket(analysis)
        subject = item.get("subject", "")
        sender = item.get("sender", "")
        mailbox_email = item.get("mailbox_email", "")

        if intent == "高":
            high_followups.append(f"- {sender} | {subject} | {mailbox_email}")
        if any(word in text.lower() for word in ["urgent", "紧急", "asap", "立即"]):
            urgent_emails.append(f"- {sender} | {subject} | {mailbox_email}")
        if any(word in text.lower() for word in ["follow up", "跟进", "reply", "回复"]):
            followup_tips.append(f"- 建议尽快跟进：{sender} | {subject}")

    if not followup_tips and total > 0:
        followup_tips.append("- 建议对高意向邮件在 24 小时内完成首次回复。")
        followup_tips.append("- 对未明确意向的邮件，先进行一次简短确认。")

    lines = [
        f"本次共处理新邮件：{total} 封",
        "",
        f"意向分布：高 {intents.get('高', 0)} / 中 {intents.get('中', 0)} / 低 {intents.get('低', 0)} / 未知 {intents.get('未知', 0)}",
        "",
        "高意向未跟进客户列表：",
        *(high_followups or ["- 无"]),
        "",
        "紧急邮件列表：",
        *(urgent_emails or ["- 无"]),
        "",
        "下次跟进时间提醒：",
        *(followup_tips or ["- 无"]),
        "",
        "简短建议：",
        "- 优先处理高意向和紧急邮件。",
        "- 保持每日增量处理，避免重复分析。",
        "- 对同类咨询邮件统一回复模板，提升效率。",
    ]
    return "\n".join(lines)
