from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Tri-AI Marketplace"
    env: str = "dev"
    api_prefix: str = "/api"
    host: str = "0.0.0.0"
    port: int = 8000

    # Defaults to simulation. Set to true only after wiring real execution.
    real_trading: bool = False
    default_base_asset: str = "SOL"

    # Future provider keys
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    grok_api_key: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
