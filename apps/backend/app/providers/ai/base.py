from pathlib import Path
from typing import Protocol


class AIProviderError(RuntimeError):
    pass


class AIProvider(Protocol):
    def transcribe(self, media_path: Path) -> str: ...

    def analyze_video(self, transcript: str) -> dict[str, object]: ...

    def generate_metadata(
        self,
        transcript: str,
        analysis: dict[str, object],
        platform: str,
    ) -> dict[str, object]: ...

    def research_topic(self, topic: str) -> dict[str, object]: ...

    def recommend_time(
        self,
        metrics: list[dict[str, object]],
        timezone: str,
    ) -> dict[str, object]: ...
