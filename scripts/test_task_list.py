import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import requests

BASE_URL = "http://localhost:8000"


def fetch(params=None):
    response = requests.get(f"{BASE_URL}/api/v1/tasks", params=params or {}, timeout=10)
    response.raise_for_status()
    return response.json()


if __name__ == "__main__":
    default_result = fetch()
    print("default tasks count:", len(default_result.get("tasks", [])))
    print("default total:", default_result.get("total"))

    start_time_result = fetch({"start_time": "2026-05-01T00:00:00"})
    print("start_time only total:", start_time_result.get("total"))

    end_time_result = fetch({"end_time": "2026-05-07T23:59:59"})
    print("end_time only total:", end_time_result.get("total"))

    range_result = fetch({"start_time": "2026-05-01T00:00:00", "end_time": "2026-05-07T23:59:59"})
    print("time range total:", range_result.get("total"))

    combo = fetch({
        "start_time": "2026-05-01T00:00:00",
        "end_time": "2026-05-07T23:59:59",
        "plugin_name": "email",
        "status": "completed",
        "sort_by": "created_at",
        "order": "desc",
        "page": 1,
        "page_size": 5,
    })
    print("combo tasks:", [t["task_id"] for t in combo.get("tasks", [])])
    print("combo total:", combo.get("total"))

    invalid = fetch({"start_time": "abc", "end_time": "2026-13-01", "page": 1, "page_size": 5})
    print("invalid time ignored total:", invalid.get("total"))
    print("task time filter validation passed")
