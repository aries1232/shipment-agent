from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Only the API key comes from the environment; the rest are hardcoded POC defaults."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gemini_api_key: str = ""

    extractor_model: str = "gemini-3.1-flash-lite"
    text_model: str = "gemini-3.1-flash-lite"
    confidence_threshold: float = 0.7
    db_path: str = "nova.db"
    rules_path: str = "rules/acme_imports.yaml"


settings = Settings()
