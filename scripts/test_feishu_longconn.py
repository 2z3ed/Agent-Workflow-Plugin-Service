#!/usr/bin/env python3
"""测试飞书长连接接收与 App 认证发送消息。"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.services.feishu_client import FeishuAppClient, FeishuLongConnClient, set_message_handler


def main() -> int:
    parser = argparse.ArgumentParser(description="Feishu long connection test")
    parser.add_argument(
        "--send-only",
        action="store_true",
        help="Only send a test message via App API (no WebSocket listen)",
    )
    parser.add_argument(
        "--listen-seconds",
        type=int,
        default=60,
        help="How long to listen for incoming messages (default: 60)",
    )
    args = parser.parse_args()

    if not settings.feishu_app_id or not settings.feishu_app_secret:
        print("❌ 未配置 FEISHU_APP_ID / FEISHU_APP_SECRET")
        return 1

    app_client = FeishuAppClient()

    if args.send_only or not settings.feishu_enable_long_conn:
        if not settings.feishu_chat_id:
            print("❌ 未配置 FEISHU_CHAT_ID")
            return 1
        print(f"📤 使用 App API 发送测试消息到 {settings.feishu_chat_id} ...")
        ok = app_client.send_text("🧪 测试消息：飞书 App API 发送成功（plugin-service）")
        if ok:
            print("✅ 消息发送成功，请在飞书群中查看")
            return 0
        print("❌ 消息发送失败，请检查应用权限（im:message）与机器人是否已加入群")
        return 1

    received: list[dict] = []
    connected = False

    def on_message(payload: dict) -> None:
        received.append(payload)
        print(f"📩 收到消息: chat_id={payload.get('chat_id')} text={payload.get('text')}")

    set_message_handler(on_message)
    client = FeishuLongConnClient()
    print("🔌 启动飞书长连接 WebSocket（请在群中 @机器人 发消息）...")
    client.start_websocket()

    for _ in range(15):
        time.sleep(1)
        if client._state.running and client._ws_client is not None:
            connected = True
            break

    if connected:
        print("✅ WebSocket 长连接已建立")
    else:
        print("❌ WebSocket 未能建立，请检查开放平台是否启用「长连接接收事件」")
        return 1

    print("📤 发送测试消息...")
    if settings.feishu_chat_id:
        app_client.send_text("🧪 长连接测试：服务已启动，请 @机器人 回复任意消息")
    else:
        print("⚠️  未配置 FEISHU_CHAT_ID，跳过发送测试")

    print(f"⏳ 监听 {args.listen_seconds} 秒（请在飞书群中 @机器人 发送消息）...")
    try:
        time.sleep(args.listen_seconds)
    except KeyboardInterrupt:
        print("\n中断监听")

    client.stop()
    print(f"\n✅ 测试结束，共收到 {len(received)} 条消息")
    if not received:
        print("ℹ️  若未收到消息，请确认机器人已加入群且已订阅 im.message.receive_v1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
