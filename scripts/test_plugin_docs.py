import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import requests

BASE_URL = "http://localhost:8000"


if __name__ == "__main__":
    response = requests.get(f"{BASE_URL}/api/v1/plugins/market", timeout=10)
    response.raise_for_status()
    plugins = response.json().get("plugins", [])
    for plugin in plugins:
        print(f"[{plugin['name']}] docs preview:\n{plugin['docs'][:200]}\n")
