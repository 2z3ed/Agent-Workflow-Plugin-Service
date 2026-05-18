import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import requests

BASE_URL = "http://localhost:8000"


def get_history(params=None):
    response = requests.get(f"{BASE_URL}/api/v1/plugins/alerts/history", params=params or {}, timeout=10)
    response.raise_for_status()
    return response.json()


def delete_history(params=None):
    response = requests.delete(f"{BASE_URL}/api/v1/plugins/alerts/history", params=params or {}, timeout=10)
    response.raise_for_status()
    return response.json()


def get_stats(params=None):
    response = requests.get(f"{BASE_URL}/api/v1/plugins/alerts/history/stats", params=params or {}, timeout=10)
    response.raise_for_status()
    return response.json()


if __name__ == "__main__":
    with patch("app.main._last_alert_sent", {}), patch("app.main.FeishuClient.send_text", return_value=True):
        requests.get(
            f"{BASE_URL}/api/v1/plugins/metrics",
            params={"alert_thresholds": '{"success_rate":0.95}', "send_feishu": "true"},
            timeout=10,
        ).raise_for_status()
        requests.get(
            f"{BASE_URL}/api/v1/plugins/metrics",
            params={"plugin_name": "hello", "alert_thresholds": '{"failed_tasks":0}', "send_feishu": "true"},
            timeout=10,
        ).raise_for_status()

    before = get_history()
    before_stats = get_stats()
    print("before:", before)
    print("before_stats:", before_stats)
    assert before["total"] >= 2

    deleted_all = delete_history()
    print("deleted all:", deleted_all)
    assert deleted_all["deleted_count"] == before["total"]

    after = get_history()
    after_stats = get_stats()
    print("after:", after)
    print("after_stats:", after_stats)
    assert after["total"] == 0
    assert after_stats["total_alerts"] == 0

    with patch("app.main._last_alert_sent", {}), patch("app.main.FeishuClient.send_text", return_value=True):
        requests.get(
            f"{BASE_URL}/api/v1/plugins/metrics",
            params={"alert_thresholds": '{"success_rate":0.95}', "send_feishu": "true"},
            timeout=10,
        ).raise_for_status()
        requests.get(
            f"{BASE_URL}/api/v1/plugins/metrics",
            params={"plugin_name": "hello", "alert_thresholds": '{"failed_tasks":0}', "send_feishu": "true"},
            timeout=10,
        ).raise_for_status()

    filtered_before = get_history({"plugin_name": "hello"})
    filtered_deleted = delete_history({"plugin_name": "hello"})
    print("filtered_before:", filtered_before)
    print("filtered_deleted:", filtered_deleted)
    assert filtered_deleted["deleted_count"] == filtered_before["total"]
    filtered_after = get_history({"plugin_name": "hello"})
    print("filtered_after:", filtered_after)
    assert filtered_after["total"] == 0

    print("alert delete validation passed")
