import csv
import io
import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import requests

BASE_URL = "http://localhost:8000"


def fetch_metrics(params=None):
    response = requests.get(f"{BASE_URL}/api/v1/plugins/metrics", params=params or {}, timeout=10)
    response.raise_for_status()
    return response.json()


def fetch_history(params=None):
    response = requests.get(f"{BASE_URL}/api/v1/plugins/alerts/history", params=params or {}, timeout=10)
    response.raise_for_status()
    return response.json()


def fetch_export(params=None):
    response = requests.get(f"{BASE_URL}/api/v1/plugins/alerts/history/export", params=params or {}, timeout=10)
    return response


def fetch_audit(params=None):
    response = requests.get(f"{BASE_URL}/api/v1/plugins/alerts/export/audit", params=params or {}, timeout=10)
    response.raise_for_status()
    return response.json()


if __name__ == "__main__":
    with patch("app.main._last_alert_sent", {}), patch("app.main.FeishuClient.send_text", return_value=True):
        fetch_metrics({"alert_thresholds": '{"success_rate":0.95}', "send_feishu": "true"})
        fetch_metrics({"alert_thresholds": '{"success_rate":0.95}', "send_feishu": "true"})
        fetch_metrics({"plugin_name": "email", "alert_thresholds": '{"success_rate":0.99}', "send_feishu": "true"})

    history = fetch_history({"plugin_name": "email", "rule": "success_rate"})
    export_json_response = fetch_export({"plugin_name": "email", "rule": "success_rate", "format": "json"})
    export_json_response.raise_for_status()
    export_json = export_json_response.json()
    print("json export:", export_json)
    assert export_json == history["alerts"]

    export_csv_response = fetch_export({"plugin_name": "email", "rule": "success_rate", "format": "csv"})
    export_csv_response.raise_for_status()
    assert export_csv_response.headers["content-type"].startswith("text/csv")
    csv_text = export_csv_response.content.decode("utf-8-sig")
    csv_reader = csv.DictReader(io.StringIO(csv_text))
    csv_rows = list(csv_reader)
    print("csv export rows:", csv_rows)
    assert len(csv_rows) == len(history["alerts"])
    if csv_rows:
        assert set(csv_rows[0].keys()) == {"alert_id", "plugin_name", "rule", "threshold", "actual", "triggered_at", "message_sent"}
        assert csv_rows[0]["plugin_name"] == "email"

    audit_1 = fetch_audit()
    print("audit after export:", audit_1)
    assert audit_1["total"] >= 2
    assert all("params" in item and "export_count" in item for item in audit_1["logs"])
    assert any(item["params"].get("format") == "json" for item in audit_1["logs"])
    assert any(item["params"].get("format") == "csv" for item in audit_1["logs"])

    paged_audit = fetch_audit({"limit": 1, "offset": 0})
    print("paged audit:", paged_audit)
    assert paged_audit["total"] == audit_1["total"]
    assert len(paged_audit["logs"]) == 1

    filtered_audit = fetch_audit({"start_time": audit_1["logs"][-1]["export_time"]})
    print("filtered audit:", filtered_audit)
    assert filtered_audit["total"] <= audit_1["total"]

    bad_format_response = fetch_export({"format": "xlsx"})
    assert bad_format_response.status_code == 400

    big_export_response = fetch_export({"format": "json"})
    if big_export_response.status_code == 400:
        print("large export blocked as expected")
    else:
        print("large export result count:", len(big_export_response.json()))

    print("alert history export validation passed")
