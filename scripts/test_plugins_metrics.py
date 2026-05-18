import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import requests

BASE_URL = "http://localhost:8000"


def fetch_metrics(params=None):
    response = requests.get(f"{BASE_URL}/api/v1/plugins/metrics", params=params or {}, timeout=10)
    response.raise_for_status()
    return response.json().get("plugins", [])


if __name__ == "__main__":
    all_metrics = fetch_metrics()
    print("all metrics:", all_metrics)

    for metric in all_metrics:
        assert "plugin_name" in metric
        assert "total_tasks" in metric
        assert "completed_tasks" in metric
        assert "failed_tasks" in metric
        assert "running_tasks" in metric
        assert "pending_tasks" in metric
        assert "last_execution_at" in metric
        assert "avg_execution_seconds" in metric
        assert "success_rate" in metric
        assert "status_breakdown" in metric
        assert set(metric["status_breakdown"].keys()) == {"completed", "failed", "running", "pending"}
        assert metric["status_breakdown"]["completed"] == metric["completed_tasks"]
        assert metric["status_breakdown"]["failed"] == metric["failed_tasks"]
        assert metric["status_breakdown"]["running"] == metric["running_tasks"]
        assert metric["status_breakdown"]["pending"] == metric["pending_tasks"]
        assert sum(metric["status_breakdown"].values()) == metric["total_tasks"]
        if metric["total_tasks"] > 0:
            assert 0 <= metric["success_rate"] <= 1

    email_metrics = fetch_metrics({"plugin_name": "email"})
    print("plugin_name=email:", email_metrics)
    if email_metrics:
        assert len(email_metrics) == 1
        email_metric = email_metrics[0]
        if email_metric["total_tasks"] > 0:
            expected = email_metric["completed_tasks"] / email_metric["total_tasks"]
            assert abs(email_metric["success_rate"] - expected) < 1e-9

    hello_metrics = fetch_metrics({"plugin_name": "hello", "start_time": "2026-05-01T00:00:00", "end_time": "2026-05-31T23:59:59"})
    print("plugin_name=hello with time filter:", hello_metrics)
    for metric in hello_metrics:
        assert sum(metric["status_breakdown"].values()) == metric["total_tasks"]

    unknown_metrics = fetch_metrics({"plugin_name": "unknown"})
    print("plugin_name=unknown:", unknown_metrics)
    assert unknown_metrics == []

    invalid_time_metrics = fetch_metrics({"start_time": "abc", "end_time": "2026-13-01"})
    print("invalid time metrics:", invalid_time_metrics)

    print("plugin metrics status breakdown validation passed")
