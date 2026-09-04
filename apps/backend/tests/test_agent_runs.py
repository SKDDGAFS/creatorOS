from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import AgentCapability, AgentRegistry, default_agent_registry
from app.ai import (
    AIProviderHealth,
    AIProviderResult,
    AIRetryableProviderError,
    AIStructuredRequest,
)
from app.jobs import AgentWorkerDependencies, JobRegistry, register_agent_jobs, run_once
from app.models.ai import AICapabilityTier, AIProviderConfiguration
from app.models.publishing import ActivityEvent
from app.schemas.agent_run import AgentRunCreate
from app.schemas.ai import AIPromptVersionCreate, AIProviderCreate
from app.services import agent_run_service, ai_service
from app.services.errors import InvalidRequestError
from tests.test_core_apis import create_channel, headers, register


class FakeProvider:
    def __init__(self, outcomes: list[AIProviderResult | Exception]) -> None:
        self.outcomes = outcomes
        self.calls = 0
        self.requests: list[AIStructuredRequest] = []

    def generate_structured(self, request: AIStructuredRequest) -> AIProviderResult:
        self.requests.append(request)
        outcome = self.outcomes[min(self.calls, len(self.outcomes) - 1)]
        self.calls += 1
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def health_check(self) -> AIProviderHealth:
        return AIProviderHealth(healthy=True, safe_message="Provider ready")


def _configure_agent(
    db: Session,
    auth: dict,
    *,
    system_template: str = "You are bounded. {output_contract}",
    user_template: str = "Objective: {objective}\nRefs: {input_references}",
) -> tuple[AIProviderConfiguration, UUID]:
    workspace_id = UUID(auth["workspace_id"])
    user_id = UUID(auth["user"]["id"])
    provider = ai_service.create_provider_configuration(
        db,
        workspace_id=workspace_id,
        user_id=user_id,
        payload=AIProviderCreate(
            name="Local agent model",
            provider_kind="ollama",
            base_url="http://127.0.0.1:11434",
            model_name="qwen-local",
            capability_tier="advanced",
            max_attempts=1,
        ),
    )
    prompt = ai_service.create_prompt_version(
        db,
        workspace_id=workspace_id,
        user_id=user_id,
        payload=AIPromptVersionCreate(
            name="agent.copywriter",
            system_template=system_template,
            user_template=user_template,
        ),
    )
    return provider, prompt.id


def _output() -> AIProviderResult:
    return AIProviderResult(
        output={
            "summary": "A concise direction",
            "recommendations": [
                {
                    "title": "Lead with the result",
                    "rationale": "It gives the viewer immediate context.",
                    "confidence": "0.8500",
                }
            ],
            "assumptions": ["The audience knows the category"],
            "next_steps": ["Draft three hook variations"],
            "overall_confidence": "0.8200",
        },
        input_tokens=40,
        output_tokens=60,
    )


def test_agent_registry_is_closed_and_disallows_powerful_capabilities() -> None:
    registry = default_agent_registry()
    capabilities = registry.list()

    assert {item.agent_type.value for item in capabilities} == {
        "content_strategist",
        "copywriter",
        "social_planner",
        "token_optimizer",
        "video_analyst",
    }
    assert all(not item.can_publish for item in capabilities)
    assert all(not item.can_execute_shell for item in capabilities)
    with pytest.raises(InvalidRequestError):
        registry.register(capabilities[0])
    with pytest.raises(InvalidRequestError):
        AgentRegistry().register(
            AgentCapability(
                agent_type=capabilities[0].agent_type,
                prompt_name="unsafe",
                capability_tier=AICapabilityTier.LIGHTWEIGHT,
                purpose="Unsafe test",
                can_execute_shell=True,
            )
        )


def test_agent_run_route_is_idempotent_and_workspace_scoped(
    client: TestClient,
    db_session: Session,
) -> None:
    owner = register(client, "agent-owner@example.com")
    _configure_agent(db_session, owner)
    owner_channel = create_channel(client, owner)
    payload = {
        "agent_type": "copywriter",
        "objective": "Prepare three honest hooks",
        "input_references": [],
    }
    first = client.post(
        "/api/agent-runs",
        headers={**headers(owner, write=True), "Idempotency-Key": "agent-route-1"},
        json=payload,
    )
    repeated = client.post(
        "/api/agent-runs",
        headers={**headers(owner, write=True), "Idempotency-Key": "agent-route-1"},
        json=payload,
    )

    assert first.status_code == 202
    assert repeated.status_code == 202
    assert repeated.json()["id"] == first.json()["id"]
    assert first.json()["status"] == "queued"

    other = register(client, "agent-other@example.com")
    _configure_agent(db_session, other)
    hidden = client.get("/api/agent-runs", headers=headers(other))
    assert hidden.status_code == 200
    assert hidden.json() == []
    missing = client.get(
        f"/api/agent-runs/{first.json()['id']}",
        headers=headers(other),
    )
    assert missing.status_code == 404
    foreign_reference = client.post(
        "/api/agent-runs",
        headers={
            **headers(other, write=True),
            "Idempotency-Key": "agent-foreign-reference",
        },
        json={
            **payload,
            "input_references": [
                {
                    "kind": "channel",
                    "resource_id": owner_channel["id"],
                    "label": "Not mine",
                }
            ],
        },
    )
    assert foreign_reference.status_code == 404


def test_worker_uses_captured_prompt_version_and_records_output(
    client: TestClient,
    db_session: Session,
) -> None:
    auth = register(client, "agent-worker@example.com")
    _, first_prompt_id = _configure_agent(
        db_session,
        auth,
        user_template="FIRST VERSION: {objective}",
    )
    run = agent_run_service.schedule_run(
        db_session,
        workspace_id=UUID(auth["workspace_id"]),
        requested_by_user_id=UUID(auth["user"]["id"]),
        payload=AgentRunCreate(
            agent_type="copywriter",
            objective="Explain retention simply",
        ),
        idempotency_key="agent-worker-1",
    )
    ai_service.create_prompt_version(
        db_session,
        workspace_id=UUID(auth["workspace_id"]),
        user_id=UUID(auth["user"]["id"]),
        payload=AIPromptVersionCreate(
            name="agent.copywriter",
            system_template="SECOND SYSTEM {output_contract}",
            user_template="SECOND VERSION: {objective}",
        ),
    )
    fake = FakeProvider([_output()])
    registry = JobRegistry()
    register_agent_jobs(
        registry,
        db_session,
        dependencies=AgentWorkerDependencies(provider_builder=lambda _: fake),
    )

    job = run_once(db_session, registry=registry, worker_id="agent-worker")
    db_session.refresh(run)

    assert job is not None
    assert job.status == "succeeded"
    assert run.status == "succeeded"
    assert run.prompt_version_id == first_prompt_id
    assert run.ai_invocation_id is not None
    assert run.model_name == "qwen-local"
    assert run.confidence == Decimal("0.8200")
    assert run.output is not None
    assert run.output["summary"] == "A concise direction"
    assert "FIRST VERSION" in fake.requests[0].messages[1].content
    assert "SECOND VERSION" not in fake.requests[0].messages[1].content
    event_types = set(
        db_session.scalars(
            select(ActivityEvent.event_type).where(ActivityEvent.agent_run_id == run.id)
        ).all()
    )
    assert event_types == {
        "agent_run_scheduled",
        "agent_run_started",
        "agent_run_succeeded",
    }


def test_retryable_provider_failure_schedules_safe_retry(
    client: TestClient,
    db_session: Session,
) -> None:
    auth = register(client, "agent-retry@example.com")
    _configure_agent(db_session, auth)
    run = agent_run_service.schedule_run(
        db_session,
        workspace_id=UUID(auth["workspace_id"]),
        requested_by_user_id=UUID(auth["user"]["id"]),
        payload=AgentRunCreate(
            agent_type="copywriter",
            objective="Draft a clear hook",
            max_attempts=2,
        ),
        idempotency_key="agent-retry-1",
    )
    fake = FakeProvider(
        [
            AIRetryableProviderError(
                "ai_provider_timeout",
                "secret upstream details",
            ),
            _output(),
        ]
    )
    registry = JobRegistry()
    register_agent_jobs(
        registry,
        db_session,
        dependencies=AgentWorkerDependencies(provider_builder=lambda _: fake),
    )

    first_job = run_once(db_session, registry=registry, worker_id="agent-retry")
    db_session.refresh(run)
    assert first_job is not None
    assert first_job.status == "retry_scheduled"
    assert run.status == "retry_scheduled"
    assert run.last_error_message == "AI provider timed out"
    assert "secret upstream" not in run.last_error_message

    first_job.scheduled_for = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()
    second_job = run_once(db_session, registry=registry, worker_id="agent-retry")
    db_session.refresh(run)
    assert second_job is not None
    assert second_job.status == "succeeded"
    assert run.status == "succeeded"


def test_admin_can_cancel_queued_run(
    client: TestClient,
    db_session: Session,
) -> None:
    auth = register(client, "agent-cancel@example.com")
    _configure_agent(db_session, auth)
    run = agent_run_service.schedule_run(
        db_session,
        workspace_id=UUID(auth["workspace_id"]),
        requested_by_user_id=UUID(auth["user"]["id"]),
        payload=AgentRunCreate(
            agent_type="copywriter",
            objective="Prepare a draft",
        ),
        idempotency_key=f"agent-cancel-{uuid4()}",
    )

    response = client.post(
        f"/api/agent-runs/{run.id}/cancel",
        headers=headers(auth, write=True),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    db_session.refresh(run)
    assert run.durable_job.status == "cancelled"
