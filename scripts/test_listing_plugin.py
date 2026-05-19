#!/usr/bin/env python3
"""手动测试 Listing 优化插件（不经过飞书长连接）"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.plugins.listing.plugin import ListingOptimizerPlugin

REQUIRED_ANALYSIS_KEYS = (
    "title_optimized",
    "bullet_points",
    "backend_keywords",
    "score",
    "differentiation",
)


def main() -> int:
    product_input = sys.argv[1] if len(sys.argv) > 1 else "无线耳机"
    plugin = ListingOptimizerPlugin()
    result = plugin.execute("test-task-id", product_input=product_input)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if not result.get("report"):
        print("❌ 缺少 report 字段")
        return 1

    analysis = result.get("analysis") or {}
    if result.get("mode") == "dify" and result.get("report"):
        print("✅ Dify 纯文本报告已解析")
    else:
        for field in REQUIRED_ANALYSIS_KEYS:
            if field not in analysis:
                print(f"⚠️ analysis 缺少字段: {field}")

    report = result["report"]
    if report.strip().startswith("{"):
        print("❌ report 不应为 JSON 格式")
        return 1

    print(f"\n--- 模式: {result.get('mode')} ---")
    print("\n--- 飞书将发送的纯文本 ---")
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
