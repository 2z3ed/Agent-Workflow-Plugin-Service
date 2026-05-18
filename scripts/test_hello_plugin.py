import time
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import requests

BASE_URL = "http://localhost:8000"


def wait_for_task(task_id: str, timeout: int = 20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = requests.get(f"{BASE_URL}/api/v1/tasks/{task_id}", timeout=10)
        response.raise_for_status()
        task = response.json()
        if task["status"] in {"completed", "failed"}:
            return task
        time.sleep(1)
    raise TimeoutError(f"Task {task_id} did not finish in time")


if __name__ == "__main__":
    create_response = requests.post(
        f"{BASE_URL}/api/v1/hello/tasks",
        json={"name": "Agent"},
        timeout=10,
    )
    create_response.raise_for_status()
    task = create_response.json()
    task_id = task["task_id"]
    print("created task:", task)

    final_task = wait_for_task(task_id)
    print("final task:", final_task)

    list_response = requests.get(f"{BASE_URL}/api/v1/tasks?limit=10", timeout=10)
    list_response.raise_for_status()
    print("task list:", list_response.json())
