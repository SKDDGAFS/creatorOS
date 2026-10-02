from functools import lru_cache

from app.core.config import get_settings
from app.providers.ai.base import AIProvider
from app.providers.ai.ollama import FasterWhisperTranscriber, OllamaProvider


@lru_cache
def get_ai_provider() -> AIProvider:
    settings = get_settings()
    return OllamaProvider(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
        transcriber=FasterWhisperTranscriber(settings.whisper_model),
    )
