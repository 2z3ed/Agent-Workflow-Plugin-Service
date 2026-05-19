#!/usr/bin/env python3
"""手动测试选品分析插件（不经过飞书长连接）"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.plugins.product.plugin import ProductPlugin


def main() -> int:
    keyword = sys.argv[1] if len(sys.argv) > 1 else "无线耳机"
    plugin = ProductPlugin()
    result = plugin.execute("test-task-id", keyword=keyword)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if not result.get("report"):
        print("❌ 缺少 report 字段")
        return 1

    analysis = result.get("analysis") or {}
    for field in ("score", "summary", "suggestion"):
        if field not in analysis:
            print(f"⚠️ analysis 缺少字段: {field}")

    print("\n--- 飞书将发送的纯文本 ---")
    print(result["report"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
