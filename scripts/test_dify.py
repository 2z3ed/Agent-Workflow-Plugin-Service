#!/usr/bin/env python3
"""测试 Dify 工作流调用（自托管 / 云版）"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.plugins.email.dify_client import DifyClient, REQUIRED_OUTPUT_FIELDS


def main():
    if not settings.email_dify_api_url or not settings.email_dify_api_key:
        print("❌ 未配置 EMAIL_DIFY_API_URL 或 EMAIL_DIFY_API_KEY，请在 .env 中设置")
        return 1

    api_url = settings.email_dify_api_url
    print(f"📡 请求 URL: {api_url}")
    print(f"🔑 API Key: {settings.email_dify_api_key[:8]}...{settings.email_dify_api_key[-4:]}")

    client = DifyClient(api_url=settings.email_dify_api_url, api_key=settings.email_dify_api_key)
    assert client.api_url == api_url, "DifyClient 未使用 settings 中的 URL"

    test_email_text = """发件人: 张三 <zhangsan@example.com>
主题: 询价和库存情况
正文: 你好，请问你们的产品 A 还有库存吗？价格能否优惠？我们需要采购 100 件，希望今天能得到回复。"""

    print("📤 调用 Dify 分析测试邮件 (response_mode=blocking)...")
    try:
        result = client.analyze(test_email_text)
    except Exception as exc:
        print(f"❌ 调用失败: {exc}")
        err = str(exc)
        if "401" in err or "unauthorized" in err.lower():
            print("ℹ️  请检查 EMAIL_DIFY_API_KEY 是否为邮件工作流的 API Key")
        elif "Connection" in err or "localhost" in api_url:
            print("ℹ️  请确认自托管 Dify 服务已启动且 URL 可访问")
        return 1

    print("\n✅ 分析结果 (JSON):")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    missing = [f for f in REQUIRED_OUTPUT_FIELDS if f not in result]
    if missing:
        print(f"\n⚠️ 缺少字段: {missing}")
        return 1

    print("\n✅ 所有必要字段均存在")
    return 0


if __name__ == "__main__":
    sys.exit(main())
