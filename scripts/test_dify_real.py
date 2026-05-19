import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import settings
from app.plugins.email.dify_client import DifyClient


if __name__ == "__main__":
    if not settings.email_dify_api_url or not settings.email_dify_api_key:
        raise SystemExit("EMAIL_DIFY_API_URL and EMAIL_DIFY_API_KEY must be set")
    text = os.getenv("TEST_EMAIL_TEXT", "您好，我想了解一下报价和交付周期，请尽快回复。")
    result = DifyClient(settings.email_dify_api_url, settings.email_dify_api_key).analyze(text)
    print(result)
