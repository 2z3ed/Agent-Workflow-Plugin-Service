import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "agent-workflow-plugin-service")
    host: str = os.getenv("APP_HOST", "0.0.0.0")
    port: int = int(os.getenv("APP_PORT", "8000"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    mailboxes: str = os.getenv("MAILBOXES", "")
    dify_api_url: str = os.getenv("DIFY_API_URL", "")
    dify_api_key: str = os.getenv("DIFY_API_KEY", "")
    database_path: str = os.getenv("DATABASE_PATH", "./data/tasks.db")
    max_emails_per_box: int = int(os.getenv("MAX_EMAILS_PER_BOX", "20"))
    lookback_days: int = int(os.getenv("LOOKBACK_DAYS", "1"))
    feishu_webhook_url: str = os.getenv("FEISHU_WEBHOOK_URL", "")
    feishu_secret: str = os.getenv("FEISHU_SECRET", "")
    feishu_app_id: str = os.getenv("FEISHU_APP_ID", "")
    feishu_app_secret: str = os.getenv("FEISHU_APP_SECRET", "")
    feishu_chat_id: str = os.getenv("FEISHU_CHAT_ID", "")
    feishu_receiver_type: str = os.getenv("FEISHU_RECEIVER_TYPE", "chat")
    feishu_enable_long_conn: bool = os.getenv("FEISHU_ENABLE_LONG_CONN", "true").lower() == "true"
    only_unread: bool = os.getenv("ONLY_UNREAD", "true").lower() == "true"
    send_feishu: bool = os.getenv("SEND_FEISHU", "true").lower() == "true"
    alert_frequency_limit_minutes: int = int(os.getenv("ALERT_FREQUENCY_LIMIT_MINUTES", "10"))


settings = Settings()
