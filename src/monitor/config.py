"""Configuration, loaded from the environment and .env."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql://monitor:monitor@localhost:55432/monitor"

    # Simulator or real provider base URLs. Both providers are read through
    # the same UsageSource interface, so switching is a config change.
    anthropic_base_url: str = "http://localhost:8001/anthropic"
    openai_base_url: str = "http://localhost:8001/openai"

    # Admin keys. With the simulator, any non-empty string passes its auth check.
    anthropic_admin_key: str = ""
    openai_admin_key: str = ""

    # Alerting. Empty means the console sink.
    slack_webhook_url: str = ""

    # Dead-man's switch. Pinged at the end of every healthy cycle.
    healthchecks_ping_url: str = ""

    # Simulator seed, so generated data is reproducible across runs.
    seed: int = 42


settings = Settings()
