import json
import logging
import re
from typing import Any

import requests

from app.config import settings
from app.plugins.base import Plugin
from app.plugins.email.dify_client import DifyClient

logger = logging.getLogger(__name__)

PRODUCT_FIELDS = ("score", "summary", "suggestion")


class ProductDifyClient(DifyClient):
    """Dify client for product_analyzer workflow (input: keyword)."""

    def analyze_keyword(self, keyword: str) -> dict[str, Any]:
        payload = {
            "inputs": {"keyword": keyword},
            "response_mode": "blocking",
            "user": "agent-workflow-plugin-service",
        }
        response = requests.post(
            self.api_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=120,
        )
        if not response.ok:
            raise RuntimeError(
                f"Dify API error {response.status_code}: {response.text[:500]}"
            )
        raw = response.json()
        outputs = self._extract_outputs(raw)
        if not outputs:
            logger.warning("Product Dify response has no outputs, raw keys=%s", list(raw.keys()))
            return {"mode": "dify", "_raw": raw}

        analysis, report = _parse_product_outputs(outputs)
        return {
            "mode": "dify",
            "analysis": analysis,
            "report": report,
        }


def _parse_product_outputs(outputs: dict[str, Any]) -> tuple[dict[str, Any], str]:
    analysis: dict[str, Any] = {}
    report = ""

    for field in PRODUCT_FIELDS:
        if field in outputs:
            analysis[field] = outputs[field]

    for key in ("report", "text", "result", "answer", "output"):
        value = outputs.get(key)
        if isinstance(value, str) and value.strip():
            if not report:
                report = value.strip()
            if len(analysis) < len(PRODUCT_FIELDS):
                parsed_json, parsed_report = _split_json_and_report(value)
                if parsed_json:
                    for field in PRODUCT_FIELDS:
                        if field in parsed_json and field not in analysis:
                            analysis[field] = parsed_json[field]
                    if parsed_report and not report:
                        report = parsed_report
            break

    if not report:
        for value in outputs.values():
            if isinstance(value, str) and value.strip():
                _, parsed_report = _split_json_and_report(value)
                if parsed_report:
                    report = parsed_report
                    break

    if analysis.get("score") is not None:
        try:
            analysis["score"] = int(analysis["score"])
        except (TypeError, ValueError):
            pass

    if not report and analysis:
        report = (
            f"【选品分析】\n"
            f"{analysis.get('summary', '')}\n"
            f"建议：{analysis.get('suggestion', '')}\n"
            f"综合评分：{analysis.get('score', 'N/A')}/100"
        ).strip()

    return analysis, report


def _split_json_and_report(text: str) -> tuple[dict[str, Any] | None, str]:
    cleaned = text.strip()
    if not cleaned.startswith("{"):
        return None, cleaned

    try:
        obj, idx = json.JSONDecoder().raw_decode(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{[^{}]*\}", cleaned, re.DOTALL)
        if not match:
            return None, cleaned
        try:
            obj = json.loads(match.group(0))
            idx = match.end()
        except json.JSONDecodeError:
            return None, cleaned

    if not isinstance(obj, dict):
        return None, cleaned

    rest = cleaned[idx:].strip()
    rest = re.sub(r"^[\s\n]+", "", rest)
    return obj, rest


def _mock_result(keyword: str) -> dict[str, Any]:
    analysis = {
        "score": 72,
        "summary": f"「{keyword}」市场关注度中等，竞争适中，适合细分切入。",
        "suggestion": "建议从小批量测款起步，关注差异化卖点与评价维护。",
    }
    report = (
        f"【选品分析·{keyword}】\n"
        f"{analysis['summary']}\n"
        f"建议：{analysis['suggestion']}\n"
        f"综合评分：{analysis['score']}/100（模拟数据）"
    )
    return {
        "keyword": keyword,
        "analysis": analysis,
        "report": report,
        "mode": "mock",
    }


class ProductPlugin(Plugin):
    name = "product"
    description = "根据关键词调用 Dify 工作流，生成模拟选品分析报告"
    category = "business"
    docs = """
# 选品分析插件

针对飞书群指令「选品分析 <关键词>」，调用 Dify 工作流 product_analyzer 生成模拟选品建议。

## 输入参数
- keyword: 选品关键词（必填）
- chat_id: 飞书群 chat_id（可选，由指令入口传入）

## 输出示例
{
  "keyword": "无线耳机",
  "analysis": {"score": 75, "summary": "...", "suggestion": "..."},
  "report": "纯文本总结（发飞书）",
  "mode": "dify"
}
"""

    def __init__(self) -> None:
        if not settings.product_dify_api_url or not settings.product_dify_api_key:
            raise ValueError(
                "PRODUCT_DIFY_API_URL and PRODUCT_DIFY_API_KEY must be set for product plugin"
            )
        self.dify_client = ProductDifyClient(
            settings.product_dify_api_url,
            settings.product_dify_api_key,
        )

    def execute(self, task_id: str, **params) -> dict:
        keyword = (params.get("keyword") or "").strip()
        if not keyword:
            raise ValueError("keyword is required")

        chat_id = params.get("chat_id")
        logger.info("Product plugin task %s keyword=%r chat_id=%s", task_id, keyword, chat_id)

        try:
            dify_result = self.dify_client.analyze_keyword(keyword)
        except Exception as exc:
            logger.warning("Product Dify call failed, using mock: %s", exc)
            result = _mock_result(keyword)
            result["dify_error"] = str(exc)
            return result

        if dify_result.get("_use_mock") or dify_result.get("mode") == "mock":
            return _mock_result(keyword)

        analysis = dify_result.get("analysis") or {}
        report = (dify_result.get("report") or "").strip()
        if not report:
            result = _mock_result(keyword)
            result["mode"] = "mock_fallback"
            result["dify_raw"] = dify_result.get("_raw")
            return result

        if not analysis:
            parsed_json, parsed_report = _split_json_and_report(report)
            if parsed_json:
                analysis = {k: parsed_json[k] for k in PRODUCT_FIELDS if k in parsed_json}
                if parsed_report:
                    report = parsed_report

        if not analysis:
            result = _mock_result(keyword)
            result["mode"] = "mock_fallback"
            return result

        return {
            "keyword": keyword,
            "chat_id": chat_id,
            "analysis": analysis,
            "report": report,
            "mode": dify_result.get("mode", "dify"),
            "task_id": task_id,
        }
