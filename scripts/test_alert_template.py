import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import requests

BASE_URL = "http://localhost:8000"


def fetch(params=None):
    response = requests.get(f"{BASE_URL}/api/v1/plugins/metrics", params=params or {}, timeout=10)
    return response


if __name__ == "__main__":
    default_response = fetch({"alert_thresholds": '{"success_rate":0.95}', "send_feishu": "true"})
    default_response.raise_for_status()
    default_data = default_response.json()
    print("default data:", default_data)

    with patch("app.main.FeishuClient.send_text", return_value=True) as mock_send:
        template = "🚨 告警：{plugin_name} 的 {rule} 异常！当前值 {actual} 低于阈值 {threshold}，请及时处理。"
        response = fetch({"alert_thresholds": '{"success_rate":0.95}', "send_feishu": "true", "alert_message_template": template})
        response.raise_for_status()
        data = response.json()
        print("template data:", data)
        assert mock_send.called
        sent_message = mock_send.call_args[0][0]
        assert "告警：" in sent_message
        assert "success_rate" in sent_message or "failed_tasks" in sent_message

    with patch("app.main.FeishuClient.send_text", return_value=True) as mock_send:
        response = fetch({"alert_thresholds": '{"success_rate":0.95}', "send_feishu": "true", "alert_message_template": "{plugin_name}-{unknown}-{rule}"})
        response.raise_for_status()
        data = response.json()
        print("unknown var data:", data)
        assert mock_send.called
        sent_message = mock_send.call_args[0][0]
        assert "{unknown}" in sent_message

    with patch("app.main.FeishuClient.send_text", return_value=True) as mock_send:
        response = fetch({"alert_thresholds": '{"success_rate":0.95}', "send_feishu": "true", "alert_message_template": ""})
        response.raise_for_status()
        data = response.json()
        print("empty template data:", data)
        assert mock_send.called
        sent_message = mock_send.call_args[0][0]
        assert "【插件报警】" in sent_message

    print("alert template validation passed")
