from functools import lru_cache

from openai import OpenAI

from app.config import settings


class OpenAIConfigurationError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def get_openai_client() -> OpenAI:
    if not settings.openai_api_key:
        raise OpenAIConfigurationError("OPENAI_API_KEY is empty.")

    return OpenAI(api_key=settings.openai_api_key)
