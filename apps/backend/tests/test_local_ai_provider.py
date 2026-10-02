import json

import pytest

from app.providers.ai.ollama import OllamaProvider


class FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


def test_ollama_provider_requests_local_structured_output(monkeypatch) -> None:
    requests: list[tuple[str, dict[str, object], int]] = []

    def fake_urlopen(request, timeout: int) -> FakeResponse:
        requests.append(
            (
                request.full_url,
                json.loads(request.data.decode("utf-8")),
                timeout,
            )
        )
        return FakeResponse(b'{"response":"{\\"summary\\":\\"local\\"}"}')

    monkeypatch.setattr("app.providers.ai.ollama.urlopen", fake_urlopen)
    provider = OllamaProvider()

    result = provider.analyze_video("Transcript text")

    assert result == {"summary": "local"}
    url, payload, timeout = requests[0]
    assert url == "http://127.0.0.1:11434/api/generate"
    assert payload["format"] == "json"
    assert "Transcript text" in payload["prompt"]
    assert timeout == 120


def test_recommendation_is_unavailable_until_metrics_are_comparable() -> None:
    result = OllamaProvider().recommend_time(
        [{"views": 0}] * 4,
        "America/Los_Angeles",
    )

    assert result == {
        "available": False,
        "reason": "Validated comparable-metric analysis is not available yet",
        "sample_count": 4,
        "timezone": "America/Los_Angeles",
    }


def test_ollama_provider_rejects_remote_urls() -> None:
    with pytest.raises(ValueError, match="local loopback"):
        OllamaProvider(base_url="https://example.com")


def test_local_topic_brief_is_labeled_unverified(monkeypatch) -> None:
    monkeypatch.setattr(
        OllamaProvider,
        "_generate_json",
        lambda self, prompt: {"angles": ["angle"]},
    )

    result = OllamaProvider().research_topic("local topic")

    assert result["source"] == "local_model_unverified"
