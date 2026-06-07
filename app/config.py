from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str = ""
    openai_api_key: str = ""
    openai_model: str = "gpt-5.5"
    openai_image_model: str = "gpt-image-1"
    openai_image_size: str = "1024x1024"
    openai_image_quality: str = "low"
    openai_image_format: str = "png"
    admin_api_key: str = ""
    app_base_url: str = ""
    render_external_url: str = ""
    telegram_webhook_secret: str = ""
    default_manager_chat_id: int | None = None
    payment_provider_token: str = ""
    payment_currency: str = "RUB"
    init_database_on_start: bool = True
    seed_database_on_start: bool = False
    database_url: str

    @field_validator("default_manager_chat_id", mode="before")
    @classmethod
    def empty_chat_id_to_none(cls, value):
        if value == "":
            return None
        return value

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
