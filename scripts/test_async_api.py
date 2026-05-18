import time
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


BASE_URL = "http://localhost:8000"


if __name__ == "__main__":
    response = requests.post(f"{BASE_URL}/api/v1/email/tasks", json={}, timeout=10)
    response.raise_for_status()
    task = response.json()
    task_id = task["task_id"]
    print("task_id:", task_id)
    print("initial_status:", task["status"])

    for _ in range(60):
        time.sleep(1)
        detail = requests.get(f"{BASE_URL}/api/v1/tasks/{task_id}", timeout=10)
        detail.raise_for_status()
        payload = detail.json()
        print("poll_status:", payload["status"])
        if payload["status"] in {"completed", "failed"}:
            print("final_result:", payload.get("result"))
            print("error:", payload.get("error"))
            break
