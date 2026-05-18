import csv
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import requests

BASE_URL = "http://localhost:8000"


def fetch(params=None, raw=False):
    response = requests.get(f"{BASE_URL}/api/v1/plugins/metrics", params=params or {}, timeout=10)
    response.raise_for_status()
    return response.text if raw else response.json()


if __name__ == "__main__":
    json_result = fetch({"bucket": "day", "plugin_name": "email"})
    print("json result:", json_result)
    assert "trend" in json_result

    csv_response = requests.get(
        f"{BASE_URL}/api/v1/plugins/metrics",
        params={"bucket": "day", "plugin_name": "email", "export_format": "csv"},
        timeout=10,
    )
    csv_response.raise_for_status()
    print("csv headers:", csv_response.headers.get("Content-Type"), csv_response.headers.get("Content-Disposition"))
    assert csv_response.headers.get("Content-Type", "").startswith("text/csv")
    reader = csv.reader(io.StringIO(csv_response.text))
    rows = list(reader)
    assert rows[0][:6] == ["bucket_date", "plugin_name", "total_tasks", "completed_tasks", "failed_tasks", "success_rate"]

    csv_norm_response = requests.get(
        f"{BASE_URL}/api/v1/plugins/metrics",
        params={"bucket": "day", "plugin_name": "email", "normalize": "true", "export_format": "csv"},
        timeout=10,
    )
    csv_norm_response.raise_for_status()
    norm_rows = list(csv.reader(io.StringIO(csv_norm_response.text)))
    assert "normalized_total_tasks" in norm_rows[0]

    compare_csv_response = requests.get(
        f"{BASE_URL}/api/v1/plugins/metrics",
        params={"bucket": "day", "compare_plugins": "email,hello", "export_format": "csv"},
        timeout=10,
    )
    compare_csv_response.raise_for_status()
    compare_rows = list(csv.reader(io.StringIO(compare_csv_response.text)))
    assert compare_rows[0][0] == "bucket_date"
    assert any(col.startswith("email_") for col in compare_rows[0])
    assert any(col.startswith("hello_") for col in compare_rows[0])

    json_export = fetch({"bucket": "day", "plugin_name": "email", "export_format": "json"})
    assert json_export == json_result

    print("trend export validation passed")
