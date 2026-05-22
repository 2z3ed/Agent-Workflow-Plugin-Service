import logging
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "agent-workflow-plugin-service")
    host: str = os.getenv("APP_HOST", "0.0.0.0")
    port: int = int(os.getenv("APP_PORT", "8000"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    mailboxes: str = os.getenv("MAILBOXES", "")
    email_dify_api_url: str = os.getenv("EMAIL_DIFY_API_URL", "")
    email_dify_api_key: str = os.getenv("EMAIL_DIFY_API_KEY", "")
    product_dify_api_url: str = os.getenv("PRODUCT_DIFY_API_URL", "")
    product_dify_api_key: str = os.getenv("PRODUCT_DIFY_API_KEY", "")
    listing_dify_api_url: str = os.getenv("LISTING_DIFY_API_URL", "")
    listing_dify_api_key: str = os.getenv("LISTING_DIFY_API_KEY", "")
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
    sorftime_mcp_url: str = os.getenv("SORFTIME_MCP_URL", "https://mcp.sorftime.com")
    sorftime_api_key: str = os.getenv("SORFTIME_API_KEY", "")
    sorftime_enable_cache: bool = os.getenv("SORFTIME_ENABLE_CACHE", "true").lower() == "true"
    sorftime_cache_ttl: int = int(os.getenv("SORFTIME_CACHE_TTL", "3600"))


settings = Settings()


def warn_missing_dify_config() -> None:
    if not settings.email_dify_api_url or not settings.email_dify_api_key:
        logger.warning(
            "EMAIL_DIFY_API_URL and EMAIL_DIFY_API_KEY are required for the email plugin"
        )
    if not settings.product_dify_api_url or not settings.product_dify_api_key:
        logger.warning(
            "PRODUCT_DIFY_API_URL and PRODUCT_DIFY_API_KEY are required for the product plugin"
        )
    if not settings.listing_dify_api_url or not settings.listing_dify_api_key:
        logger.warning(
            "LISTING_DIFY_API_URL and LISTING_DIFY_API_KEY are required for the listing plugin"
        )
