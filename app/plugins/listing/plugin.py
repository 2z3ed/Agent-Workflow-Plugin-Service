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

# ASIN：10 位大写字母数字，或 B 开头 + 9 位（亚马逊常见格式）
_ASIN_PATTERNS = (
    re.compile(r"^[A-Z0-9]{10}$"),
    re.compile(r"^B[0-9A-Z]{9}$"),
)

LISTING_JSON_FIELDS = (
    "title_optimized",
    "bullet_points",
    "description_structured",
    "backend_keywords",
    "aplus_suggestions",
    "score",
    "score_reasons",
    "differentiation",
)


class ListingDifyClient(DifyClient):
    """Dify client for listing_optimizer workflow (input: product_input)."""

    def analyze_product_input(self, product_input: str) -> dict[str, Any]:
        logger.info(
            "Calling Dify listing workflow url=%s product_input=%r",
            self.api_url,
            product_input[:100],
        )
        payload = {
            "inputs": {"product_input": product_input[:9900]},
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
            logger.warning(
                "Listing Dify response has no outputs, raw keys=%s", list(raw.keys())
            )
            return {"mode": "dify", "_raw": raw}

        analysis, report = _parse_listing_outputs(outputs)
        report = _clean_dify_report(report)
        logger.info(
            "Dify listing workflow done output_keys=%s analysis_keys=%s report_len=%s",
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


def _split_json_and_report(text: str) -> tuple[dict[str, Any] | None, str]:
    cleaned = text.strip()
    if not cleaned.startswith("{"):
        return None, cleaned

    try:
        obj, idx = json.JSONDecoder().raw_decode(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
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


def _merge_parsed_json(analysis: dict[str, Any], parsed_json: dict[str, Any]) -> None:
    for field in LISTING_JSON_FIELDS:
        if field in parsed_json and field not in analysis:
            analysis[field] = parsed_json[field]
    for key, value in parsed_json.items():
        if key not in analysis:
            analysis[key] = value


def _extract_text_from_string_value(value: str) -> tuple[dict[str, Any], str]:
    """Split combined JSON+text Dify output; prefer trailing text for Feishu."""
    parsed_json, parsed_report = _split_json_and_report(value)
    analysis: dict[str, Any] = {}
    if parsed_json:
        _merge_parsed_json(analysis, parsed_json)
    report = parsed_report.strip()
    if not report and parsed_json and not value.strip().startswith("{"):
        report = value.strip()
    return analysis, report


def _parse_listing_outputs(outputs: dict[str, Any]) -> tuple[dict[str, Any], str]:
    analysis: dict[str, Any] = {}
    report = ""

    for field in LISTING_JSON_FIELDS:
        if field in outputs:
            analysis[field] = outputs[field]

    for key in ("report", "text", "result", "answer", "output"):
        value = outputs.get(key)
        if isinstance(value, str) and value.strip():
            chunk_analysis, chunk_report = _extract_text_from_string_value(value)
            _merge_parsed_json(analysis, chunk_analysis)
            if chunk_report:
                report = chunk_report
            break

    if not report:
        for value in outputs.values():
            if isinstance(value, str) and value.strip():
                chunk_analysis, chunk_report = _extract_text_from_string_value(value)
                _merge_parsed_json(analysis, chunk_analysis)
                if chunk_report:
                    report = chunk_report
                    break

    if analysis.get("score") is not None:
        try:
            analysis["score"] = int(analysis["score"])
        except (TypeError, ValueError):
            pass

    if not report and analysis and _has_listing_schema(analysis):
        report = _format_report_from_analysis(analysis, product_input="")

    return analysis, report


def _has_listing_schema(analysis: dict[str, Any]) -> bool:
    required_keys = (
        "title_optimized",
        "bullet_points",
        "backend_keywords",
        "score",
        "differentiation",
    )
    return sum(1 for k in required_keys if analysis.get(k)) >= 5


def _is_json_blob(text: str) -> bool:
    stripped = text.strip()
    if not stripped.startswith("{"):
        return False
    try:
        json.loads(stripped)
        return True
    except json.JSONDecodeError:
        parsed_json, parsed_report = _split_json_and_report(stripped)
        return bool(parsed_json) and not parsed_report


def _format_report_from_analysis(analysis: dict[str, Any], product_input: str) -> str:
    title = analysis.get("title_optimized", "")
    bullets = analysis.get("bullet_points") or []
    if isinstance(bullets, str):
        bullets = [bullets]
    keywords = analysis.get("backend_keywords") or []
    if isinstance(keywords, str):
        keywords = [keywords]
    score = analysis.get("score", "N/A")
    differentiation = analysis.get("differentiation", "")
    description = analysis.get("description_structured", "")
    aplus = analysis.get("aplus_suggestions", "")
    score_reasons = analysis.get("score_reasons", "")

    lines = ["📦 Listing 优化报告"]
    if product_input:
        lines.append(f"输入：{product_input[:80]}{'…' if len(product_input) > 80 else ''}")
    lines.append("")
    if title:
        lines.append(f"🏷️ 优化标题\n{title}")
    if bullets:
        lines.append("\n✨ 五点卖点")
        for i, point in enumerate(bullets[:5], 1):
            lines.append(f"{i}. {point}")
    if description:
        lines.append(f"\n📝 描述结构\n{description}")
    if keywords:
        kw_text = "、".join(str(k) for k in keywords[:15])
        lines.append(f"\n🔑 后台关键词\n{kw_text}")
    if aplus:
        lines.append(f"\n🖼️ A+ 建议\n{aplus}")
    lines.append(f"\n📊 综合评分：{score}/100")
    if score_reasons:
        lines.append(f"评分说明：{score_reasons}")
    if differentiation:
        lines.append(f"\n🎯 差异化建议\n{differentiation}")

    return "\n".join(lines).strip()


def _detect_input_type(user_input: str) -> str:
    """返回 'asin' 或 'keyword'。"""
    candidate = (user_input or "").strip().upper()
    for pattern in _ASIN_PATTERNS:
        if pattern.match(candidate):
            return "asin"
    return "keyword"


def _clean_dify_report(text: str) -> str:
    """移除 Dify LLM 思考块，保留可发飞书的正文。"""
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    parts = re.split(r"</think>", cleaned, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) > 1:
        cleaned = parts[1]
    return cleaned.strip()


def _is_valid_sorftime_data(data: dict[str, Any] | None, input_type: str = "keyword") -> bool:
    if not data:
        return False
    if data.get("error") == "sorftime_no_data":
        return False
    raw = data.get("raw_text", "")
    if raw in ("没有相关数据", "无数据", ""):
        return False
    if isinstance(raw, str) and (
        "请指定查询的站点" in raw or "没有相关数据" in raw
    ):
        return False
    if input_type == "asin":
        return bool(
            data.get("title")
            or data.get("asin")
            or (isinstance(raw, str) and "标题" in raw and len(raw) > 80)
        )
    if len(data) == 1 and "raw_text" in data:
        return isinstance(raw, str) and len(raw) > 50 and "关键词" in raw
    return True


def _build_dify_product_input(
    user_input: str,
    market_data: dict[str, Any] | None,
    input_type: str,
) -> str:
    if not market_data:
        return user_input
    data_json = json.dumps(market_data, ensure_ascii=False, indent=2)
    if len(data_json) > 8000:
        data_json = data_json[:8000] + "…"
    data_label = "ASIN 商品详情（product_detail）" if input_type == "asin" else "品类关键词市场数据"
    return (
        f"用户要求优化以下产品：{user_input}\n\n"
        f"【真实市场数据（来自 Sorftime · {data_label}）】\n"
        f"{data_json}\n\n"
        f"请基于以上真实数据，生成 Listing 优化报告（包括标题、五点、后台关键词、描述结构、A+ 建议、评分与差异化建议等）。"
    )


def _fetch_sorftime_listing_data(
    user_input: str,
) -> tuple[dict[str, Any] | None, str, str]:
    """
    按输入类型调用 Sorftime。
    返回 (market_data, input_type, sorftime_method)。
    """
    input_type = _detect_input_type(user_input)
    api_key = settings.sorftime_api_key or ""
    if not api_key:
        logger.info(
            "Listing Sorftime API key not configured, skip (input_type=%s)",
            input_type,
        )
        return None, input_type, ""

    collector = SorftimeCollector()
    if input_type == "asin":
        asin = user_input.strip().upper()
        method = "product_detail"
        logger.info(
            "Listing input detected as ASIN=%s, calling Sorftime product_detail site=com api_key_prefix=%s",
            asin,
            api_key[:8] + "...",
        )
        try:
            data = collector.product_detail(asin, site="com")
        except Exception as exc:
            logger.warning("Sorftime product_detail failed for %r: %s", asin, exc)
            return None, input_type, method
    else:
        method = "product_research"
        logger.info(
            "Listing input detected as keyword=%r, calling Sorftime product_research site=com api_key_prefix=%s",
            user_input,
            api_key[:8] + "...",
        )
        try:
            data = collector.product_research(user_input, site="com")
        except Exception as exc:
            logger.warning("Sorftime product_research failed for %r: %s", user_input, exc)
            return None, input_type, method

    if not _is_valid_sorftime_data(data, input_type=input_type):
        preview = json.dumps(data, ensure_ascii=False)[:200] if data else "None"
        logger.warning(
            "Sorftime %s returned no usable data for %r: %s",
            method,
            user_input,
            preview,
        )
        return None, input_type, method

    logger.info(
        "Sorftime %s success for %r keys=%s preview=%s",
        method,
        user_input,
        list(data.keys())[:8],
        json.dumps(data, ensure_ascii=False)[:200],
    )
    return data, input_type, method


def _sorftime_fallback_report(
    user_input: str,
    market_data: dict[str, Any],
    input_type: str,
) -> str:
    label = "ASIN 竞品数据" if input_type == "asin" else "品类市场数据"
    lines = [
        f"📦 Listing 优化报告（基于 Sorftime 真实{label}）",
        f"输入：{user_input}",
        "",
    ]
    preview = json.dumps(market_data, ensure_ascii=False, indent=2)[:2000]
    lines.append(preview)
    return "\n".join(lines)


def _mock_result(product_input: str, reason: str = "") -> dict[str, Any]:
    report = (
        f"【Listing 优化·模拟】\n"
        f"关键词：{product_input}\n\n"
        f"当前无法从 Dify 获取分析结果，以上为占位内容。\n"
        f"请检查 LISTING_DIFY_API_URL / LISTING_DIFY_API_KEY 及工作流输出格式。"
    )
    if reason:
        report += f"\n\n原因：{reason[:200]}"
    return {
        "product_input": product_input,
        "analysis": {},
        "report": report,
        "mode": "mock",
    }


class ListingOptimizerPlugin(Plugin):
    name = "listing"
    description = "根据商品信息调用 Dify listing_optimizer 工作流，生成 Listing 优化建议"
    category = "business"
    docs = """
# Listing 优化插件

针对飞书群指令「Listing 优化 <商品关键词或 Listing 文本>」，调用 Dify 工作流 listing_optimizer。

## 输入参数
- product_input: 商品关键词或现有 Listing 文本（必填）
- chat_id: 飞书群 chat_id（可选）

## 输出示例
{
  "product_input": "无线耳机",
  "analysis": {"title_optimized": "...", "bullet_points": [...], "score": 85, ...},
  "report": "纯文本总结（发飞书）",
  "mode": "dify"
}
"""

    def __init__(self) -> None:
        if not settings.listing_dify_api_url or not settings.listing_dify_api_key:
            raise ValueError(
                "LISTING_DIFY_API_URL and LISTING_DIFY_API_KEY must be set for listing plugin"
            )
        logger.info(
            "ListingOptimizerPlugin initialized with Dify url=%s",
            settings.listing_dify_api_url,
        )
        self.dify_client = ListingDifyClient(
            settings.listing_dify_api_url,
            settings.listing_dify_api_key,
        )

    def execute(self, task_id: str, **params) -> dict:
        product_input = (params.get("product_input") or "").strip()
        if not product_input:
            raise ValueError("product_input is required")

        chat_id = params.get("chat_id")
        input_type = _detect_input_type(product_input)
        api_key_prefix = (
            (settings.sorftime_api_key or "")[:8] + "..."
            if settings.sorftime_api_key
            else "(empty)"
        )
        logger.info(
            "Listing plugin task %s product_input=%r input_type=%s chat_id=%s sorftime_api_key=%s",
            task_id,
            product_input[:100],
            input_type,
            chat_id,
            api_key_prefix,
        )

        market_data, detected_type, sorftime_method = _fetch_sorftime_listing_data(product_input)
        dify_product_input = _build_dify_product_input(
            product_input, market_data, detected_type
        )
        logger.info(
            "Listing plugin task %s sorftime_method=%s sorftime_ok=%s dify_input_len=%s entering Dify",
            task_id,
            sorftime_method or "(skipped)",
            market_data is not None,
            len(dify_product_input),
        )

        try:
            dify_result = self.dify_client.analyze_product_input(dify_product_input)
        except Exception as exc:
            logger.error(
                "Listing Dify call failed task=%s: %s", task_id, exc, exc_info=True
            )
            if market_data:
                return {
                    "product_input": product_input,
                    "chat_id": chat_id,
                    "analysis": {},
                    "report": _sorftime_fallback_report(
                        product_input, market_data, detected_type
                    ),
                    "mode": "sorftime_fallback",
                    "task_id": task_id,
                    "dify_error": str(exc),
                }
            result = _mock_result(product_input, reason=str(exc))
            result["dify_error"] = str(exc)
            return result

        analysis = dify_result.get("analysis") or {}
        report = _clean_dify_report((dify_result.get("report") or "").strip())
        logger.info(
            "Listing plugin task %s Dify result analysis_keys=%s report_len=%s",
            task_id,
            list(analysis.keys()),
            len(report),
        )

        if _is_json_blob(report):
            _, report = _split_json_and_report(report)
            report = _clean_dify_report(report)

        if not report:
            raw = dify_result.get("_raw") or {}
            data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
            outputs = data.get("outputs") if isinstance(data.get("outputs"), dict) else {}
            for value in outputs.values():
                if isinstance(value, str) and value.strip():
                    chunk_analysis, chunk_report = _extract_text_from_string_value(value)
                    _merge_parsed_json(analysis, chunk_analysis)
                    if chunk_report:
                        report = _clean_dify_report(chunk_report)
                        break

        if not report:
            logger.warning(
                "Listing plugin task %s Dify empty report, fallback (analysis_keys=%s)",
                task_id,
                list(analysis.keys()),
            )
            if market_data:
                return {
                    "product_input": product_input,
                    "chat_id": chat_id,
                    "analysis": {},
                    "report": _sorftime_fallback_report(
                        product_input, market_data, detected_type
                    ),
                    "mode": "sorftime_fallback",
                    "task_id": task_id,
                }
            result = _mock_result(product_input, reason="Dify 响应中未解析出纯文本报告")
            result["mode"] = "mock_fallback"
            return result

        if not analysis and report:
            logger.info(
                "Listing plugin task %s using Dify text report without structured analysis",
                task_id,
            )
            return {
                "product_input": product_input,
                "chat_id": chat_id,
                "analysis": {},
                "report": report,
                "mode": dify_result.get("mode", "dify"),
                "task_id": task_id,
            }

        if _has_listing_schema(analysis):
            logger.info(
                "Listing task %s: using Dify report (listing schema present)", task_id
            )
        else:
            logger.info(
                "Listing task %s: using Dify report (generic schema, keys=%s)",
                task_id,
                list(analysis.keys())[:8],
            )

        return {
            "product_input": product_input,
            "chat_id": chat_id,
            "analysis": analysis,
            "report": report,
            "mode": dify_result.get("mode", "dify"),
            "task_id": task_id,
        }
