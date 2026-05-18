import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.plugins.email.email_fetcher import EmailFetcher


if __name__ == "__main__":
    fetcher = EmailFetcher()
    messages = fetcher.fetch_recent_unread(limit=5)
    print(messages)
