# import sys
# from pathlib import Path
# from unittest.mock import patch

# ROOT = Path(__file__).resolve().parents[1]
# sys.path.insert(0, str(ROOT))

# import requests

# BASE_URL = "http://localhost:8000"


# def fetch_metrics(params=None):
#     response = requests.get(f"{BASE_URL}/api/v1/plugins/metrics", params=params or {}, timeout=10)
#     response.raise_for_status()
#     return response.json()


# def fetch_history(params=None):
#     response = requests.get(f"{BASE_URL}/api/v1/plugins/alerts/history", params=params or {}, timeout=10)
#     response.raise_for_status()
#     return response.json()


# def fetch_stats(params=None):
#     response = requests.get(f"{BASE_URL}/api/v1/plugins/alerts/history/stats", params=params or {}, timeout=10)
#     response.raise_for_status()
#     return response.json()


# def delete_history(params=None):
#     response = requests.delete(f"{BASE_URL}/api/v1/plugins/alerts/history", params=params or {}, timeout=10)
#     response.raise_for_status()
#     return response.json()


# if __name__ == "__main__":
#     with patch("app.main._last_alert_sent", {}), patch("app.main.FeishuClient.send_text", return_value=True):
#         fetch_metrics({"alert_thresholds": '{"success_rate":0.95}', "send_feishu": "true"})
#         fetch_metrics({"alert_thresholds": '{"success_rate":0.95}', "send_feishu": "true"})
#         fetch_metrics({"alert_thresholds": '{"success_rate":0.95}', "send_feishu": "true"})
#         fetch_metrics({"plugin_name": "hello", "alert_thresholds": '{"failed_tasks":0}', "send_feishu": "true"})

#     history = fetch_history()
#     print("history:", history)
#     stats = fetch_stats()
#     print("stats:", stats)
#     assert stats["total_alerts"] == history["total"]
#     assert stats["sent_alerts"] + stats["blocked_alerts"] == stats["total_alerts"]
#     assert sum(stats["by_rule"].values()) == stats["total_alerts"]

#     filtered_stats = fetch_stats({"plugin_name": "email", "rule": "success_rate"})
#     print("filtered stats:", filtered_stats)
#     filtered_history = fetch_history({"plugin_name": "email", "rule": "success_rate"})
#     assert filtered_stats["total_alerts"] == filtered_history["total"]
#     assert filtered_stats["sent_alerts"] + filtered_stats["blocked_alerts"] == filtered_stats["total_alerts"]

#     empty_stats = fetch_stats({"plugin_name": "not-exists"})
#     print("empty stats:", empty_stats)
#     assert empty_stats["total_alerts"] == 0
#     assert empty_stats["sent_alerts"] == 0
#     assert empty_stats["blocked_alerts"] == 0
#     assert empty_stats["by_rule"] == {}

#     delete_result = delete_history({"plugin_name": "email", "rule": "success_rate"})
#     print("delete result:", delete_result)
#     assert delete_result["deleted_count"] >= 0

#     after_delete_history = fetch_history({"plugin_name": "email", "rule": "success_rate"})
#     after_delete_stats = fetch_stats({"plugin_name": "email", "rule": "success_rate"})
#     print("after delete history:", after_delete_history)
#     print("after delete stats:", after_delete_stats)
#     assert after_delete_history["total"] == after_delete_stats["total_alerts"]

#     remaining = fetch_history()
#     delete_all_result = delete_history()
#     print("delete all result:", delete_all_result)
#     assert delete_all_result["deleted_count"] == remaining["total"]
#     assert fetch_history()["total"] == 0
#     assert fetch_stats()["total_alerts"] == 0

#     print("alert history delete validation passed")
#!/usr/bin/env python3
"""测试报警历史记录与清理"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import time

BASE_URL = "http://localhost:8000"

def test_history():
    # 触发几次报警（需要先有任务失败）
    print("请确保已经通过 /api/v1/email/tasks 产生了任务，并手动触发报警")
    print("查询报警历史...")
    resp = requests.get(f"{BASE_URL}/api/v1/plugins/alerts/history")
    if resp.status_code == 200:
        data = resp.json()
        print(f"总报警数: {data['total']}")
        for alert in data['alerts'][:3]:
            print(f"  - {alert['plugin_name']} {alert['rule']} at {alert['triggered_at']}")
    else:
        print("查询失败")

if __name__ == "__main__":
    test_history()