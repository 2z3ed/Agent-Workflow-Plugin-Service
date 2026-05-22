import json
import logging
import re
from typing import Any

import requests

from app.config import settings
from app.plugins.base import Plugin
from app.plugins.common.sorftime_collector import SorftimeCollector
from app.plugins.email.dify_client import DifyClient

logger = logging.getLogger(__name__)

PRODUCT_FIELDS = ("score", "summary", "suggestion")


class ProductDifyClient(DifyClient):
    """Dify client for product_analyzer workflow (input: product_input)."""

    def analyze_keyword(self, keyword: str) -> dict[str, Any]:
        # 工作流 Start 节点变量名为 product_input（非 keyword）
        product_input = keyword[:9900] if len(keyword) > 9900 else keyword
        payload = {
            "inputs": {"product_input": product_input},
            "response_mode": "blocking",
            "user": "agent-workflow-plugin-service",
        }
        logger.info(
            "Calling Dify product workflow url=%s product_input_len=%s",
            self.api_url,
            len(product_input),
        )
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
        report = _clean_dify_report(report)
        logger.info(
            "Dify product workflow done output_keys=%s analysis_keys=%s report_len=%s",
            list(outputs.keys()),
            list(analysis.keys()),
            len(report),
        )
        return {
            "mode": "dify",
            "analysis": analysis,
            "report": report,
            "_raw": raw,
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


def _clean_dify_report(text: str) -> str:
    """移除 Dify LLM 思考块，保留可发飞书的正文。"""
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    parts = re.split(r"</think>", cleaned, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) > 1:
        cleaned = parts[1]
    return cleaned.strip()


def _is_valid_sorftime_data(data: dict[str, Any] | None) -> bool:
    if not data:
        return False
    if data.get("raw_text") in ("没有相关数据", "无数据", ""):
        return False
    if len(data) == 1 and "raw_text" in data:
        return False
    return True


def _sorftime_summary_report(keyword: str, market_data: dict[str, Any]) -> str:
    """Sorftime 有数据但 Dify 失败时，用真实数据生成临时报告。"""
    lines = [f"【选品分析·{keyword}】（基于 Sorftime 真实市场数据）"]
    field_labels = (
        ("关键词", "关键词"),
        ("周搜索量", "周搜索量"),
        ("月搜索量", "月搜索量"),
        ("周搜索排名", "周搜索排名"),
        ("推荐cpc竞价", "推荐 CPC 竞价"),
        ("搜索结果竞品数量", "搜索结果竞品数"),
        ("词搜索量旺季", "搜索量旺季"),
    )
    for key, label in field_labels:
        value = market_data.get(key)
        if value:
            lines.append(f"- {label}：{value}")
    if len(lines) == 1:
        preview = json.dumps(market_data, ensure_ascii=False)[:1500]
        lines.append(preview)
    return "\n".join(lines)


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


def _build_dify_keyword_input(keyword: str, market_data: dict[str, Any] | None) -> str:
    if not market_data:
        return keyword
    data_json = json.dumps(market_data, ensure_ascii=False)
    if len(data_json) > 8000:
        data_json = data_json[:8000] + "…"
    return (
        f"选品关键词：{keyword}\n\n"
        f"以下为 Sorftime 真实市场数据（JSON），请结合数据生成选品分析报告：\n"
        f"{data_json}"
    )


def _fetch_sorftime_market_data(keyword: str) -> dict[str, Any] | None:
    api_key = settings.sorftime_api_key or ""
    if not api_key:
        logger.info("Sorftime API key not configured, skip product_research")
        return None
    logger.info(
        "Calling Sorftime product_research for keyword=%r site=com api_key_prefix=%s",
        keyword,
        api_key[:8] + "...",
    )
    try:
        data = SorftimeCollector().product_research(keyword, site="com")
    except Exception as exc:
        logger.warning("Sorftime product_research failed for %r: %s", keyword, exc)
        return None
    if not _is_valid_sorftime_data(data):
        preview = json.dumps(data, ensure_ascii=False)[:200] if data else "None"
        logger.warning(
            "Sorftime product_research returned no usable data for %r: %s",
            keyword,
            preview,
        )
        return None
    logger.info(
        "Sorftime product_research success for %r keys=%s preview=%s",
        keyword,
        list(data.keys())[:8],
        json.dumps(data, ensure_ascii=False)[:200],
    )
    return data


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
        api_key_prefix = (settings.sorftime_api_key or "")[:8] + "..." if settings.sorftime_api_key else "(empty)"
        logger.info(
            "Product plugin task %s keyword=%r chat_id=%s sorftime_api_key=%s",
            task_id,
            keyword,
            chat_id,
            api_key_prefix,
        )

        market_data = _fetch_sorftime_market_data(keyword)
        dify_input = _build_dify_keyword_input(keyword, market_data)
        logger.info(
            "Product plugin task %s sorftime_ok=%s dify_input_len=%s entering Dify",
            task_id,
            market_data is not None,
            len(dify_input),
        )

        try:
            dify_result = self.dify_client.analyze_keyword(dify_input)
        except Exception as exc:
            logger.error("Product Dify call failed task=%s: %s", task_id, exc, exc_info=True)
            if market_data:
                return {
                    "keyword": keyword,
                    "chat_id": chat_id,
                    "analysis": {},
                    "report": _sorftime_summary_report(keyword, market_data),
                    "mode": "sorftime_fallback",
                    "task_id": task_id,
                    "dify_error": str(exc),
                }
            result = _mock_result(keyword)
            result["dify_error"] = str(exc)
            return result

        if dify_result.get("_use_mock") or dify_result.get("mode") == "mock":
            logger.warning("Product plugin task %s Dify returned mock mode", task_id)
            if market_data:
                return {
                    "keyword": keyword,
                    "chat_id": chat_id,
                    "analysis": {},
                    "report": _sorftime_summary_report(keyword, market_data),
                    "mode": "sorftime_fallback",
                    "task_id": task_id,
                }
            return _mock_result(keyword)

        analysis = dify_result.get("analysis") or {}
        report = _clean_dify_report((dify_result.get("report") or "").strip())
        logger.info(
            "Product plugin task %s Dify result analysis_keys=%s report_len=%s",
            task_id,
            list(analysis.keys()),
            len(report),
        )

        if not report:
            logger.warning("Product plugin task %s Dify empty report, fallback", task_id)
            if market_data:
                return {
                    "keyword": keyword,
                    "chat_id": chat_id,
                    "analysis": {},
                    "report": _sorftime_summary_report(keyword, market_data),
                    "mode": "sorftime_fallback",
                    "task_id": task_id,
                    "dify_raw": dify_result.get("_raw"),
                }
            result = _mock_result(keyword)
            result["mode"] = "mock_fallback"
            result["dify_raw"] = dify_result.get("_raw")
            return result

        if not analysis:
            parsed_json, parsed_report = _split_json_and_report(report)
            if parsed_json:
                analysis = {k: parsed_json[k] for k in PRODUCT_FIELDS if k in parsed_json}
                if parsed_report:
                    report = _clean_dify_report(parsed_report)

        if not analysis and report:
            logger.info(
                "Product plugin task %s using Dify text report without structured analysis",
                task_id,
            )
            return {
                "keyword": keyword,
                "chat_id": chat_id,
                "analysis": {},
                "report": report,
                "mode": dify_result.get("mode", "dify"),
                "task_id": task_id,
            }

        if not analysis:
            logger.warning("Product plugin task %s no analysis and no report text", task_id)
            if market_data:
                return {
                    "keyword": keyword,
                    "chat_id": chat_id,
                    "analysis": {},
                    "report": _sorftime_summary_report(keyword, market_data),
                    "mode": "sorftime_fallback",
                    "task_id": task_id,
                }
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
