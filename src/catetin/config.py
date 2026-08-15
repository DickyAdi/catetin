from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed, validated application configuration. No os.getenv outside this module."""

    model_config = SettingsConfigDict(env_prefix="CATETIN_", env_file=".env", extra="ignore")

    telegram_bot_token: SecretStr
    telegram_webhook_secret: SecretStr
    webhook_path: str = "/webhook/telegram/{secret}"
    database_url: str = "sqlite+aiosqlite:///./catetin.db"
    db_reader_pool_size: int = 3
    redis_url: str | None = None
    expected_db_revision: str = "0001_initial"
    log_level: str = "INFO"
    body_max_bytes: int = 256_000

    ops_username: str
    ops_password: SecretStr

    # Phase 2 placeholders (LLM gateway)
    llm_base_url: str = "http://localhost:20128/v1"
    llm_api_key: SecretStr | None = None
    llm_monthly_budget_idr: int = 0

    pdf_max_per_user_hour: int = 5
    digest_enabled_default: bool = True
    timezone: str = "Asia/Jakarta"

    digest_hour_local: int = 21
    backup_dir: str = "./backups"
    backup_keep_n: int = 7
