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
    with patch("app.main._last_alert_sent", {}), patch("app.main.FeishuClient.send_text", return_value=True) as mock_send:
        first = fetch({"alert_thresholds": '{"success_rate":0.95,"failed_tasks":0}', "send_feishu": "true"})
        first.raise_for_status()
        print("first:", first.json())
        assert mock_send.called

    with patch("app.main.time.time", return_value=10 * 60 + 1), patch("app.main.FeishuClient.send_text", return_value=True) as mock_send:
        second = fetch({"alert_thresholds": '{"success_rate":0.95,"failed_tasks":0}', "send_feishu": "true"})
        second.raise_for_status()
        print("second:", second.json())
        assert not mock_send.called

    with patch("app.main.time.time", return_value=15 * 60 + 1), patch("app.main.FeishuClient.send_text", return_value=True) as mock_send:
        third = fetch({"alert_thresholds": '{"success_rate":0.95,"failed_tasks":0}', "send_feishu": "true"})
        third.raise_for_status()
        print("third:", third.json())
        assert mock_send.called

    with patch("app.main._last_alert_sent", {}), patch("app.main.settings.alert_frequency_limit_minutes", 0), patch("app.main.FeishuClient.send_text", return_value=True) as mock_send:
        unlimited = fetch({"alert_thresholds": '{"success_rate":0.95,"failed_tasks":0}', "send_feishu": "true"})
        unlimited.raise_for_status()
        print("unlimited:", unlimited.json())
        assert mock_send.called

    print("alert frequency validation passed")
