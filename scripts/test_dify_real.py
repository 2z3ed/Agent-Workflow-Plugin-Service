import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.plugins.email.dify_client import DifyClient


if __name__ == "__main__":
    text = os.getenv("TEST_EMAIL_TEXT", "您好，我想了解一下报价和交付周期，请尽快回复。")
    result = DifyClient().analyze(text)
    print(result)
