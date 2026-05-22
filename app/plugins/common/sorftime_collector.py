import hashlib
import json
import logging
import re
import time
from typing import Any, Optional

import requests

from app.config import settings

logger = logging.getLogger(__name__)

_SITE_TO_AMZ: dict[str, str] = {
    "com": "US",
    "us": "US",
    "uk": "GB",
    "gb": "GB",
    "de": "DE",
    "fr": "FR",
    "ca": "CA",
    "jp": "JP",
    "es": "ES",
    "it": "IT",
    "mx": "MX",
    "ae": "AE",
    "au": "AU",
    "br": "BR",
    "sa": "SA",
}

# Sorftime MCP 官方工具名映射（业务方法 -> MCP tool）
_TOOL_ALIASES: dict[str, str] = {
    "product_research": "keyword_detail",
    "listing_analysis": "product_detail",
    "keyword_research": "product_traffic_terms",
}


class SorftimeCollector:
    """Sorftime MCP 数据采集器（内存缓存，失败返回 None）。"""

    def __init__(self) -> None:
        self.mcp_url = (settings.sorftime_mcp_url or "https://mcp.sorftime.com").rstrip("/")
        self.api_key = settings.sorftime_api_key or ""
        self.enable_cache = settings.sorftime_enable_cache
        self.cache_ttl = settings.sorftime_cache_ttl
        self._cache: dict[str, tuple[float, Any]] = {}
        self._request_id = 0

    def _cache_key(self, tool_name: str, arguments: dict[str, Any]) -> str:
        raw = json.dumps({"tool": tool_name, "args": arguments}, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _get_cached(self, key: str) -> Optional[Any]:
        if not self.enable_cache:
            return None
        entry = self._cache.get(key)
        if not entry:
            return None
        expires_at, data = entry
        if time.time() > expires_at:
            del self._cache[key]
            return None
        logger.info("Sorftime cache hit tool cache_key=%s", key[:12])
        return data

    def _set_cached(self, key: str, data: Any) -> None:
        if not self.enable_cache:
            return
        self._cache[key] = (time.time() + self.cache_ttl, data)

    def _next_request_id(self) -> int:
        self._request_id += 1
        return self._request_id

    @staticmethod
    def _site_to_amz(site: str) -> str:
        normalized = (site or "com").strip().lower()
        return _SITE_TO_AMZ.get(normalized, normalized.upper() if len(normalized) == 2 else "US")

    def _build_mcp_arguments(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        mcp_tool = _TOOL_ALIASES.get(tool_name, tool_name)
        args = dict(arguments)

        if tool_name == "product_research":
            keyword = args.pop("keyword", "")
            site = args.pop("site", "com")
            amz_site = self._site_to_amz(str(site))
            return {
                "keyword": keyword,
                "keywordSupportSite": amz_site,
                "amzSite": amz_site,
            }
        if tool_name == "listing_analysis":
            asin = args.pop("asin", "")
            site = args.pop("site", "com")
            return {"asin": asin, "amzSite": self._site_to_amz(str(site))}
        if tool_name == "keyword_research":
            asin = args.pop("asin", "")
            site = args.pop("site", "com")
            return {"asin": asin, "amzSite": self._site_to_amz(str(site))}

        return args

    def _parse_sse_or_json(self, text: str) -> Optional[Any]:
        if not text or not text.strip():
            return None

        stripped = text.strip()
        if stripped.startswith("{"):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                pass

        payloads: list[Any] = []
        for line in stripped.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            chunk = line[5:].strip()
            if not chunk or chunk == "[DONE]":
                continue
            try:
                payloads.append(json.loads(chunk))
            except json.JSONDecodeError:
                continue

        if not payloads:
            return None
        return payloads[-1]

    def _extract_tool_result(self, payload: Any) -> Optional[dict[str, Any]]:
        if payload is None:
            return None

        if isinstance(payload, list):
            for item in reversed(payload):
                result = self._extract_tool_result(item)
                if result is not None:
                    return result
            return None

        if not isinstance(payload, dict):
            return None

        if "error" in payload:
            logger.warning("Sorftime MCP error: %s", payload.get("error"))
            return None

        result = payload.get("result")
        if isinstance(result, dict):
            if result.get("isError"):
                logger.warning("Sorftime MCP tool error: %s", result.get("content"))
                return None
            content = result.get("content")
            if isinstance(content, list):
                texts: list[str] = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("text")
                        if isinstance(text, str):
                            texts.append(text)
                if texts:
                    combined = "\n".join(texts)
                    try:
                        parsed = json.loads(combined)
                        if isinstance(parsed, dict):
                            return parsed
                    except json.JSONDecodeError:
                        return {"raw_text": combined}
            if isinstance(content, str):
                try:
                    parsed = json.loads(content)
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    return {"raw_text": content}
            if isinstance(result, dict) and len(result) > 1:
                return result

        if "data" in payload and isinstance(payload["data"], dict):
            return self._extract_tool_result(payload["data"])

        return payload if isinstance(payload, dict) else None

    def _call_mcp(self, tool_name: str, arguments: dict[str, Any]) -> Optional[dict[str, Any]]:
        if not self.api_key:
            logger.debug("Sorftime API key not configured, skip MCP call tool=%s", tool_name)
            return None

        cache_key = self._cache_key(tool_name, arguments)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        mcp_tool = _TOOL_ALIASES.get(tool_name, tool_name)
        mcp_args = self._build_mcp_arguments(tool_name, arguments)

        url = f"{self.mcp_url}?key={self.api_key}"
        body = {
            "jsonrpc": "2.0",
            "id": self._next_request_id(),
            "method": "tools/call",
            "params": {"name": mcp_tool, "arguments": mcp_args},
        }

        try:
            response = requests.post(
                url,
                headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
                json=body,
                timeout=60,
            )
        except requests.Timeout:
            logger.warning("Sorftime MCP timeout tool=%s", tool_name)
            return None
        except requests.RequestException as exc:
            logger.warning("Sorftime MCP request failed tool=%s: %s", tool_name, exc)
            return None

        if not response.ok:
            logger.warning(
                "Sorftime MCP non-2xx tool=%s status=%s body=%s",
                tool_name,
                response.status_code,
                (response.text or "")[:300],
            )
            return None

        raw_preview = (response.text or "")[:500]
        logger.info(
            "Sorftime MCP raw response tool=%s mcp_tool=%s preview=%s",
            tool_name,
            mcp_tool,
            raw_preview,
        )
        payload = self._parse_sse_or_json(response.text)
        data = self._extract_tool_result(payload)
        if not data:
            logger.warning("Sorftime MCP empty result tool=%s mcp_tool=%s", tool_name, mcp_tool)
            return None

        normalized = self._normalize_product_research(data) if tool_name == "product_research" else data
        self._set_cached(cache_key, normalized)
        logger.info(
            "Sorftime MCP success tool=%s mcp_tool=%s keys=%s",
            tool_name,
            mcp_tool,
            list(normalized.keys())[:8],
        )
        return normalized

    @staticmethod
    def _normalize_product_research(data: dict[str, Any]) -> dict[str, Any]:
        """将 Sorftime keyword_detail 字段映射为统一结构，保留原始字段。"""
        if data.get("raw_text") in ("没有相关数据", "无数据", ""):
            return data
        normalized = dict(data)
        mappings = {
            "market_capacity": ("月搜索量", "周搜索量"),
            "search_trend": ("词搜索量旺季", "周搜索排名"),
            "competition": ("搜索结果竞品数量",),
            "keyword": ("关键词",),
            "cpc_bid": ("推荐cpc竞价",),
        }
        for target, sources in mappings.items():
            if target in normalized:
                continue
            for src in sources:
                if src in data and data[src]:
                    normalized[target] = data[src]
                    break
        return normalized

    def product_research(self, keyword: str, site: str = "com") -> Optional[dict[str, Any]]:
        keyword = (keyword or "").strip()
        if not keyword:
            return None
        return self._call_mcp("product_research", {"keyword": keyword, "site": site})

    def listing_analysis(self, asin: str, site: str = "com") -> Optional[dict[str, Any]]:
        asin = (asin or "").strip().upper()
        if not asin:
            return None
        return self._call_mcp("listing_analysis", {"asin": asin, "site": site})

    def keyword_research(self, asin: str, site: str = "com") -> Optional[dict[str, Any]]:
        asin = (asin or "").strip().upper()
        if not asin:
            return None
        return self._call_mcp("keyword_research", {"asin": asin, "site": site})


_ASIN_RE = re.compile(r"^(B0[A-Z0-9]{8}|[A-Z0-9]{10})$", re.IGNORECASE)


def looks_like_asin(text: str) -> bool:
    candidate = (text or "").strip().upper()
    return bool(_ASIN_RE.match(candidate))
