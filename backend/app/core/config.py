from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Adversarial Security Platform"
    version: str = "0.1.0"

    # MongoDB — override with MONGODB_URL / MONGODB_DB environment variables.
    # Never hard-code credentials here; use a .env file or host environment.
    mongodb_url: str = "mongodb://localhost:27017"
    mongodb_db: str = "clairsec"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
