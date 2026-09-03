import json
from decimal import Decimal
from uuid import UUID

import httpx2
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai import (
    AIBudgetExceededError,
    AIMessage,
    AIMessageRole,
    AIProviderHealth,
    AIProviderResult,
    AIRetryableProviderError,
    AIStructuredRequest,
    OllamaProvider,
    OpenAICompatibleProvider,
)
from app.core.config import Settings
from app.models.ai import (
    AIInvocation,
    AIPromptVersion,
    AIProviderConfiguration,
    AIProviderKind,
)
from app.schemas.ai import (
    AIPromptVersionCreate,
    AIProviderCreate,
    AIUsageBudgetUpdate,
)
from app.services import ai_service
from app.services.errors import ConflictError, InvalidRequestError
from tests.test_core_apis import headers, register


class HookOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hook: str


class FakeProvider:
    def __init__(
        self,
        outcomes: list[AIProviderResult | Exception],
        *,
        healthy: bool = True,
    ) -> None:
        self.outcomes = outcomes
        self.calls = 0
        self.healthy = healthy

    def generate_structured(
        self,
        request: AIStructuredRequest,
    ) -> AIProviderResult:
        assert request.output_schema["type"] == "object"
        outcome = self.outcomes[min(self.calls, len(self.outcomes) - 1)]
        self.calls += 1
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def health_check(self) -> AIProviderHealth:
        return AIProviderHealth(
            healthy=self.healthy,
            safe_message="Provider ready" if self.healthy else "Provider unavailable",
        )


def _create_provider(
    db: Session,
    auth: dict,
    *,
    name: str,
    priority: int,
    max_attempts: int = 2,
    input_cost: Decimal = Decimal("0"),
    output_cost: Decimal = Decimal("0"),
) -> AIProviderConfiguration:
    return ai_service.create_provider_configuration(
        db,
        workspace_id=UUID(auth["workspace_id"]),
        user_id=UUID(auth["user"]["id"]),
        payload=AIProviderCreate(
            name=name,
            provider_kind="ollama",
            base_url="http://127.0.0.1:11434",
            model_name=f"{name}-model",
            priority=priority,
            max_attempts=max_attempts,
            input_cost_per_million=input_cost,
            output_cost_per_million=output_cost,
        ),
        settings=Settings(database_url="sqlite+pysqlite:///:memory:"),
    )


def _create_prompt(db: Session, auth: dict) -> AIPromptVersion:
    return ai_service.create_prompt_version(
        db,
        workspace_id=UUID(auth["workspace_id"]),
        user_id=UUID(auth["user"]["id"]),
        payload=AIPromptVersionCreate(
            name="short-form-hook",
            system_template="Return a factual hook for {platform}.",
            user_template="Topic: {topic}",
        ),
    )


def test_provider_routes_are_safe_and_workspace_scoped(
    client: TestClient,
) -> None:
    owner = register(client, "ai-owner@example.com")
    created = client.post(
        "/api/ai/providers",
        headers=headers(owner, write=True),
        json={
            "name": "Local Ollama",
            "provider_kind": "ollama",
            "base_url": "http://localhost:11434/",
            "model_name": "gemma3",
        },
    )

    assert created.status_code == 201
    assert created.json()["base_url"] == "http://localhost:11434"
    assert created.json()["requires_api_key"] is False
    assert "credential_reference" not in created.json()

    compatible = client.post(
        "/api/ai/providers",
        headers=headers(owner, write=True),
        json={
            "name": "Local compatible",
            "provider_kind": "openai_compatible",
            "base_url": "http://127.0.0.1:1234/v1",
            "model_name": "local-model",
            "credential_reference": "env://LOCAL_MODEL_KEY",
        },
    )
    assert compatible.status_code == 201
    assert compatible.json()["requires_api_key"] is True
    assert "credential_reference" not in compatible.json()

    blocked = client.post(
        "/api/ai/providers",
        headers=headers(owner, write=True),
        json={
            "name": "Unsafe endpoint",
            "provider_kind": "openai_compatible",
            "base_url": "http://169.254.169.254/latest/meta-data",
            "model_name": "model",
        },
    )
    assert blocked.status_code == 422

    other = register(client, "ai-other@example.com")
    hidden = client.get("/api/ai/providers", headers=headers(other))
    assert hidden.status_code == 200
    assert hidden.json() == []

    assert (
        ai_service.normalize_provider_base_url(
            "http://host.docker.internal:11434",
            provider_kind=AIProviderKind.OLLAMA,
            settings=Settings(
                database_url="sqlite+pysqlite:///:memory:",
                ai_allowed_local_provider_hosts="host.docker.internal",
            ),
        )
        == "http://host.docker.internal:11434"
    )


def test_prompt_versions_are_immutable_and_single_active(
    client: TestClient,
    db_session: Session,
) -> None:
    auth = register(client, "ai-prompts@example.com")
    first = _create_prompt(db_session, auth)
    second = ai_service.create_prompt_version(
        db_session,
        workspace_id=UUID(auth["workspace_id"]),
        user_id=UUID(auth["user"]["id"]),
        payload=AIPromptVersionCreate(
            name="short-form-hook",
            system_template="Write one honest {platform} hook.",
            user_template="Subject: {topic}",
        ),
    )

    db_session.refresh(first)
    assert first.is_active is False
    assert second.version == 2
    assert second.is_active is True
    with pytest.raises(InvalidRequestError):
        ai_service.create_prompt_version(
            db_session,
            workspace_id=UUID(auth["workspace_id"]),
            user_id=UUID(auth["user"]["id"]),
            payload=AIPromptVersionCreate(
                name="invalid-template",
                system_template="Do {person.name}",
                user_template="Topic: {topic}",
            ),
        )


def test_router_retries_falls_back_validates_and_reuses_result(
    client: TestClient,
    db_session: Session,
) -> None:
    auth = register(client, "ai-router@example.com")
    workspace_id = UUID(auth["workspace_id"])
    user_id = UUID(auth["user"]["id"])
    first = _create_provider(
        db_session,
        auth,
        name="first",
        priority=100,
        max_attempts=2,
    )
    second = _create_provider(
        db_session,
        auth,
        name="second",
        priority=50,
        input_cost=Decimal("1"),
        output_cost=Decimal("2"),
    )
    prompt = _create_prompt(db_session, auth)
    retry = AIRetryableProviderError(
        "ai_provider_timeout",
        "AI provider timed out",
    )
    first_fake = FakeProvider([retry])
    second_fake = FakeProvider(
        [
            AIProviderResult(
                output={"hook": "The quiet metric most creators miss"},
                input_tokens=12,
                output_tokens=5,
            )
        ]
    )
    providers = {first.id: first_fake, second.id: second_fake}

    def builder(configuration: AIProviderConfiguration):
        return providers[configuration.id]

    generated = ai_service.generate_structured(
        db_session,
        workspace_id=workspace_id,
        user_id=user_id,
        prompt_name=prompt.name,
        variables={"platform": "TikTok", "topic": "retention"},
        output_type=HookOutput,
        idempotency_key="ai-router-request-1",
        provider_builder=builder,
    )
    repeated = ai_service.generate_structured(
        db_session,
        workspace_id=workspace_id,
        user_id=user_id,
        prompt_name=prompt.name,
        variables={"platform": "TikTok", "topic": "retention"},
        output_type=HookOutput,
        idempotency_key="ai-router-request-1",
        provider_builder=builder,
    )

    assert generated.output == HookOutput(hook="The quiet metric most creators miss")
    assert generated.invocation.provider_configuration_id == second.id
    assert generated.invocation.attempts == 3
    assert generated.invocation.estimated_cost_usd == Decimal("0.000022")
    assert repeated.invocation.id == generated.invocation.id
    assert first_fake.calls == 2
    assert second_fake.calls == 1
    assert db_session.scalar(select(func.count(AIInvocation.id))) == 1
    usage = ai_service.usage_summary(db_session, workspace_id=workspace_id)
    assert usage.total_tokens == 17
    assert usage.invocation_count == 1

    with pytest.raises(ConflictError):
        ai_service.generate_structured(
            db_session,
            workspace_id=workspace_id,
            user_id=user_id,
            prompt_name=prompt.name,
            variables={"platform": "YouTube", "topic": "retention"},
            output_type=HookOutput,
            idempotency_key="ai-router-request-1",
            provider_builder=builder,
        )


def test_budget_blocks_calls_before_provider_execution(
    client: TestClient,
    db_session: Session,
) -> None:
    auth = register(client, "ai-budget@example.com")
    provider = _create_provider(
        db_session,
        auth,
        name="budgeted",
        priority=100,
    )
    prompt = _create_prompt(db_session, auth)
    ai_service.upsert_usage_budget(
        db_session,
        workspace_id=UUID(auth["workspace_id"]),
        payload=AIUsageBudgetUpdate(
            monthly_token_limit=10,
            default_max_output_tokens=8,
        ),
    )
    fake = FakeProvider(
        [AIProviderResult(output={"hook": "unused"}, input_tokens=1, output_tokens=1)]
    )

    with pytest.raises(AIBudgetExceededError):
        ai_service.generate_structured(
            db_session,
            workspace_id=UUID(auth["workspace_id"]),
            user_id=UUID(auth["user"]["id"]),
            prompt_name=prompt.name,
            variables={"platform": "TikTok", "topic": "retention"},
            output_type=HookOutput,
            idempotency_key="ai-budget-request",
            provider_builder=lambda configuration: fake,
        )

    assert provider.id is not None
    assert fake.calls == 0


def test_failed_provider_details_are_not_persisted(
    client: TestClient,
    db_session: Session,
) -> None:
    auth = register(client, "ai-safe-errors@example.com")
    _create_provider(
        db_session,
        auth,
        name="failing",
        priority=100,
        max_attempts=1,
    )
    prompt = _create_prompt(db_session, auth)
    fake = FakeProvider(
        [
            AIRetryableProviderError(
                "provider_internal_failure",
                "secret provider response body",
            )
        ]
    )

    with pytest.raises(AIRetryableProviderError) as error:
        ai_service.generate_structured(
            db_session,
            workspace_id=UUID(auth["workspace_id"]),
            user_id=UUID(auth["user"]["id"]),
            prompt_name=prompt.name,
            variables={"platform": "Instagram", "topic": "shares"},
            output_type=HookOutput,
            idempotency_key="ai-safe-error-request",
            provider_builder=lambda configuration: fake,
        )

    invocation = db_session.scalar(select(AIInvocation))
    assert invocation is not None
    assert invocation.status == "failed"
    assert invocation.last_error_message == "AI provider is temporarily unavailable"
    assert "secret provider" not in invocation.last_error_message
    assert "secret provider" not in error.value.safe_message


def test_schema_mismatch_falls_back_and_health_is_safe(
    client: TestClient,
    db_session: Session,
) -> None:
    auth = register(client, "ai-schema-fallback@example.com")
    first = _create_provider(
        db_session,
        auth,
        name="invalid-output",
        priority=100,
    )
    second = _create_provider(
        db_session,
        auth,
        name="valid-output",
        priority=50,
    )
    prompt = _create_prompt(db_session, auth)
    first_fake = FakeProvider(
        [AIProviderResult(output={"wrong": "shape"}, input_tokens=4, output_tokens=2)],
        healthy=False,
    )
    second_fake = FakeProvider(
        [
            AIProviderResult(
                output={"hook": "Validated"}, input_tokens=5, output_tokens=2
            )
        ]
    )
    providers = {first.id: first_fake, second.id: second_fake}

    result = ai_service.generate_structured(
        db_session,
        workspace_id=UUID(auth["workspace_id"]),
        user_id=UUID(auth["user"]["id"]),
        prompt_name=prompt.name,
        variables={"platform": "YouTube", "topic": "watch time"},
        output_type=HookOutput,
        idempotency_key="ai-schema-fallback",
        provider_builder=lambda configuration: providers[configuration.id],
    )
    health = ai_service.check_provider_health(
        db_session,
        workspace_id=UUID(auth["workspace_id"]),
        provider_builder=lambda configuration: providers[configuration.id],
    )

    assert result.output == HookOutput(hook="Validated")
    assert first_fake.calls == 1
    assert second_fake.calls == 1
    assert [item.healthy for item in health] == [False, True]
    assert health[0].safe_message == "Provider unavailable"


def test_provider_transports_send_structured_schema_and_parse_usage() -> None:
    seen: list[httpx2.Request] = []

    def ollama_handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        if request.url.path == "/api/tags":
            return httpx2.Response(200, json={"models": []})
        return httpx2.Response(
            200,
            headers={"x-request-id": "ollama-request"},
            json={
                "message": {"role": "assistant", "content": '{"hook":"Local"}'},
                "done_reason": "stop",
                "prompt_eval_count": 9,
                "eval_count": 2,
            },
        )

    request = AIStructuredRequest(
        model="gemma3",
        messages=(AIMessage(role=AIMessageRole.USER, content="Write a hook"),),
        output_schema_name="HookOutput",
        output_schema=HookOutput.model_json_schema(),
        max_output_tokens=100,
    )
    with httpx2.Client(
        base_url="http://127.0.0.1:11434/",
        transport=httpx2.MockTransport(ollama_handler),
    ) as client:
        ollama = OllamaProvider(
            base_url="http://127.0.0.1:11434",
            timeout_seconds=10,
            client=client,
        )
        result = ollama.generate_structured(request)
        health = ollama.health_check()

    assert result.output == {"hook": "Local"}
    assert result.input_tokens == 9
    assert result.output_tokens == 2
    assert health.healthy is True
    assert seen[0].url.path == "/api/chat"
    assert json.loads(seen[0].content)["format"]["type"] == "object"

    def compatible_handler(request: httpx2.Request) -> httpx2.Response:
        assert request.headers["authorization"] == "Bearer optional-key"
        if request.url.path == "/v1/models":
            return httpx2.Response(200, json={"data": []})
        assert request.url.path == "/v1/chat/completions"
        return httpx2.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": '{"hook":"Compatible"}'},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 11, "completion_tokens": 3},
            },
        )

    with httpx2.Client(
        base_url="https://models.example/v1/",
        transport=httpx2.MockTransport(compatible_handler),
    ) as client:
        compatible = OpenAICompatibleProvider(
            base_url="https://models.example/v1",
            timeout_seconds=10,
            api_key=SecretStr("optional-key"),
            client=client,
        )
        compatible_result = compatible.generate_structured(request)
        compatible_health = compatible.health_check()

    assert compatible_result.output == {"hook": "Compatible"}
    assert compatible_result.input_tokens == 11
    assert compatible_result.output_tokens == 3
    assert compatible_health.healthy is True
