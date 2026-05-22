#!/usr/bin/env python3
"""验证 Sorftime MCP 采集器（需配置 SORFTIME_API_KEY）。"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from app.config import settings
from app.plugins.common.sorftime_collector import SorftimeCollector


def main() -> int:
    print(f"SORFTIME_MCP_URL={settings.sorftime_mcp_url}")
    print(f"SORFTIME_ENABLE_CACHE={settings.sorftime_enable_cache}")
    print(f"SORFTIME_CACHE_TTL={settings.sorftime_cache_ttl}")

    if not settings.sorftime_api_key:
        print("⚠️ SORFTIME_API_KEY 未配置，请在 .env 中设置后重试。")
        return 0

    keyword = sys.argv[1] if len(sys.argv) > 1 else "wireless earbuds"
    collector = SorftimeCollector()
    print(f"\n调用 product_research(keyword={keyword!r}, site='com') ...")
    result = collector.product_research(keyword, site="com")

    if result is None:
        print("❌ 未获取到数据（超时、非 2xx 或无有效响应），请查看服务日志。")
        return 1

    text = json.dumps(result, ensure_ascii=False)
    preview = text[:200] + ("…" if len(text) > 200 else "")
    print(f"✅ 调用成功，结果前 200 字符：\n{preview}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
