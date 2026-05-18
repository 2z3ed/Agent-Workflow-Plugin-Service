import hashlib
import hmac
import base64
import json
import time
from typing import Any

import requests


class FeishuClient:
    def __init__(self, webhook_url: str, secret: str = None):
        self.webhook_url = webhook_url
        self.secret = secret

    def send_text(self, content: str) -> bool:
        """发送纯文本消息到飞书群聊"""
        if not self.webhook_url:
            return True

        payload: dict[str, Any] = {"msg_type": "text", "content": {"text": content}}

        if self.secret:
            timestamp = str(int(time.time()))
            payload["timestamp"] = timestamp
            payload["sign"] = self._sign(timestamp, self.secret)

        response = requests.post(self.webhook_url, json=payload, timeout=15)
        response.raise_for_status()
        data = response.json()
        return data.get("StatusCode", 0) == 0 or data.get("code", 0) == 0

    def _sign(self, timestamp: str, secret: str) -> str:
        string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
        key = secret.encode("utf-8")
        digest = hmac.new(key, string_to_sign, hashlib.sha256).digest()
        return base64.b64encode(digest).decode("utf-8")
