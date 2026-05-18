import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.plugins.email.plugin import EmailPlugin


if __name__ == "__main__":
    plugin = EmailPlugin()
    result = plugin.execute(task_id="test-001", chat_id="test")
    print("total_emails_fetched:", result.get("total_emails_fetched"))
    print("total_new_emails:", result.get("total_new_emails"))
    print("report:\n", result.get("report"))
    print("details:", result.get("details"))
