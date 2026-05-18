import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import requests

BASE_URL = "http://localhost:8000"


def fetch(params=None):
    response = requests.get(f"{BASE_URL}/api/v1/plugins/market", params=params or {}, timeout=10)
    response.raise_for_status()
    return response.json()


if __name__ == "__main__":
    data = fetch()
    all_plugins = data["plugins"]
    print("all plugins:", [p["name"] for p in all_plugins])
    assert [p["name"] for p in all_plugins] == ["email", "hello", "timestamp"]

    paged = fetch({"page": 1, "page_size": 2})
    print("page=1&page_size=2:", [p["name"] for p in paged["plugins"]], paged.get("total"), paged.get("page"), paged.get("page_size"))
    assert len(paged["plugins"]) == 2
    assert paged["total"] == 3
    assert paged["page"] == 1
    assert paged["page_size"] == 2

    second_page = fetch({"page": 2, "page_size": 2})
    print("page=2&page_size=2:", [p["name"] for p in second_page["plugins"]])
    assert len(second_page["plugins"]) == 1

    all_by_large_page = fetch({"page": 1, "page_size": 100})
    print("page=1&page_size=100:", [p["name"] for p in all_by_large_page["plugins"]])
    assert len(all_by_large_page["plugins"]) == 3

    combo = fetch({"q": "邮件", "page": 1, "page_size": 1})
    print("q=邮件&page=1&page_size=1:", [p["name"] for p in combo["plugins"]])
    assert [p["name"] for p in combo["plugins"]] == ["email"]

    sorted_page = fetch({"sort": "name", "page": 1, "page_size": 2})
    print("sort=name&page=1&page_size=2:", [p["name"] for p in sorted_page["plugins"]])
    assert [p["name"] for p in sorted_page["plugins"]] == ["email", "hello"]

    print("plugin market pagination validation passed")
