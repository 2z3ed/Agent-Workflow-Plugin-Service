import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import requests

BASE_URL = "http://localhost:8000"


if __name__ == "__main__":
    response = requests.get(f"{BASE_URL}/api/v1/plugins", timeout=10)
    response.raise_for_status()
    payload = response.json()
    print(payload)

    plugins = payload.get("plugins", [])
    names = {item.get("name") for item in plugins}
    assert "email" in names, "email plugin not found"
    assert "hello" in names, "hello plugin not found"
    for plugin in plugins:
        assert "name" in plugin
        assert "description" in plugin
        assert "enabled" in plugin
    print("plugin list check passed")
