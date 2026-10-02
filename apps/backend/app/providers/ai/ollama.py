import importlib
import json
from contextlib import suppress
from ipaddress import ip_address
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from app.providers.ai.base import AIProviderError


class FasterWhisperTranscriber:
    def __init__(self, model_size: str = "small") -> None:
        self.model_size = model_size
        self._model: Any = None

    def transcribe(self, media_path: Path) -> str:
        try:
            whisper = importlib.import_module("faster_whisper")
        except ImportError as error:
            raise AIProviderError(
                "Install faster-whisper to enable local transcription"
            ) from error

        if self._model is None:
            self._model = whisper.WhisperModel(
                self.model_size,
                device="cpu",
                compute_type="int8",
            )
        segments, _ = self._model.transcribe(str(media_path), vad_filter=True)
        transcript = " ".join(segment.text.strip() for segment in segments).strip()
        if not transcript:
            raise AIProviderError("No speech was detected in this video")
        return transcript


class OllamaProvider:
    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "llama3.2",
        transcriber: FasterWhisperTranscriber | None = None,
    ) -> None:
        parsed_url = urlsplit(base_url)
        hostname = parsed_url.hostname
        is_loopback = hostname == "localhost"
        if hostname is not None:
            with suppress(ValueError):
                is_loopback = is_loopback or ip_address(hostname).is_loopback
        if parsed_url.scheme != "http" or not is_loopback:
            raise ValueError("Ollama must use a local loopback HTTP endpoint")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.transcriber = transcriber or FasterWhisperTranscriber()

    def transcribe(self, media_path: Path) -> str:
        return self.transcriber.transcribe(media_path)

    def analyze_video(self, transcript: str) -> dict[str, object]:
        return self._generate_json(
            "Analyze this video transcript. Return JSON with summary, hook, "
            "topics (array), key_points (array), and content_type. Do not "
            "claim visual details that are not present in the transcript.\n\n"
            f"Transcript:\n{transcript[:30000]}"
        )

    def generate_metadata(
        self,
        transcript: str,
        analysis: dict[str, object],
        platform: str,
    ) -> dict[str, object]:
        return self._generate_json(
            f"Create an editable metadata draft for {platform}. Use only the "
            "provided transcript and analysis. Return a JSON object with the "
            "relevant fields among title, description, tags, caption, hashtags. "
            "Do not claim the draft is verified or publish it.\n\n"
            f"Transcript:\n{transcript[:20000]}\n\n"
            f"Analysis:\n{json.dumps(analysis, ensure_ascii=True)}"
        )

    def research_topic(self, topic: str) -> dict[str, object]:
        result = self._generate_json(
            "Create an offline brainstorming brief for this topic. Do not claim "
            "to have searched the web or verified current facts. Return JSON "
            "with angles (array), questions (array), and verification_needed "
            "(array).\n\n"
            f"Topic:\n{topic[:4000]}"
        )
        result["source"] = "local_model_unverified"
        return result

    def recommend_time(
        self,
        metrics: list[dict[str, object]],
        timezone: str,
    ) -> dict[str, object]:
        return {
            "available": False,
            "reason": "Validated comparable-metric analysis is not available yet",
            "sample_count": len(metrics),
            "timezone": timezone,
        }

    def _generate_json(self, prompt: str) -> dict[str, object]:
        body = json.dumps(
            {"model": self.model, "prompt": prompt, "stream": False, "format": "json"}
        ).encode("utf-8")
        request = Request(
            f"{self.base_url}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=120) as response:
                payload = json.loads(response.read().decode("utf-8"))
            result = json.loads(payload["response"])
        except (HTTPError, URLError, TimeoutError) as error:
            raise AIProviderError(
                "Ollama is unavailable; start the local service and check its model"
            ) from error
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise AIProviderError("Ollama returned an invalid JSON response") from error
        if not isinstance(result, dict):
            raise AIProviderError("Ollama returned an unexpected response shape")
        return result
