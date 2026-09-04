from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from string import Formatter
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from pydantic import BaseModel, ValidationError
from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.ai import (
    AIAPIKeyStore,
    AIBudgetExceededError,
    AIConfigurationError,
    AIError,
    AIMessage,
    AIMessageRole,
    AIOutputValidationError,
    AIPermanentProviderError,
    AIProvider,
    AIProviderHealth,
    AIRetryableProviderError,
    AIStructuredRequest,
    EnvironmentAIKeyStore,
    OllamaProvider,
    OpenAICompatibleProvider,
)
from app.core.config import Settings, get_settings
from app.models.ai import (
    AICapabilityTier,
    AIInvocation,
    AIInvocationStatus,
    AIPromptVersion,
    AIProviderConfiguration,
    AIProviderKind,
    AIUsageBudget,
)
from app.schemas.ai import (
    AIPromptVersionCreate,
    AIProviderCreate,
    AIProviderHealthResponse,
    AIUsageBudgetUpdate,
    AIUsageSummary,
)
from app.services.errors import (
    ConflictError,
    InvalidRequestError,
    PersistenceError,
    ResourceNotFoundError,
)

ProviderBuilder = Callable[[AIProviderConfiguration], AIProvider]
SIX_PLACES = Decimal("0.000001")
FIELD_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,99}$")
TIER_RANK = {
    AICapabilityTier.LIGHTWEIGHT.value: 0,
    AICapabilityTier.STANDARD.value: 1,
    AICapabilityTier.ADVANCED.value: 2,
}


@dataclass(frozen=True)
class AIGeneration:
    invocation: AIInvocation
    output: BaseModel


def _commit(db: Session, conflict: str, failure: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(conflict) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise PersistenceError(failure) from exc


def normalize_provider_base_url(
    value: str,
    *,
    provider_kind: AIProviderKind,
    settings: Settings,
) -> str:
    parsed = urlsplit(value.strip())
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise InvalidRequestError("AI provider base URL is invalid")
    hostname = parsed.hostname.lower().rstrip(".")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    is_loopback = hostname == "localhost" or bool(address and address.is_loopback)
    is_explicit_local = hostname in settings.allowed_local_ai_provider_hosts
    is_local = is_loopback or is_explicit_local
    if provider_kind is AIProviderKind.OLLAMA and not is_local:
        raise InvalidRequestError("Ollama must use an approved local base URL")
    if parsed.scheme == "http" and not is_local:
        raise InvalidRequestError("Remote AI providers must use HTTPS")
    if not is_local and hostname not in settings.allowed_ai_provider_hosts:
        raise InvalidRequestError("AI provider host is not allowlisted")
    normalized_path = parsed.path.rstrip("/")
    return urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), normalized_path, "", "")
    )


def create_provider_configuration(
    db: Session,
    *,
    workspace_id: UUID,
    user_id: UUID,
    payload: AIProviderCreate,
    settings: Settings | None = None,
) -> AIProviderConfiguration:
    resolved_settings = settings or get_settings()
    provider_count = db.scalar(
        select(func.count(AIProviderConfiguration.id)).where(
            AIProviderConfiguration.workspace_id == workspace_id
        )
    )
    if (provider_count or 0) >= 20:
        raise InvalidRequestError("A workspace may configure at most 20 AI providers")
    provider = AIProviderConfiguration(
        **payload.model_dump(exclude={"provider_kind", "capability_tier", "base_url"}),
        workspace_id=workspace_id,
        created_by_user_id=user_id,
        provider_kind=payload.provider_kind.value,
        capability_tier=payload.capability_tier.value,
        base_url=normalize_provider_base_url(
            payload.base_url,
            provider_kind=payload.provider_kind,
            settings=resolved_settings,
        ),
    )
    db.add(provider)
    _commit(
        db,
        "An AI provider with this name already exists",
        "Unable to create AI provider configuration",
    )
    db.refresh(provider)
    return provider


def list_provider_configurations(
    db: Session,
    *,
    workspace_id: UUID,
    include_disabled: bool = False,
) -> list[AIProviderConfiguration]:
    statement: Select[tuple[AIProviderConfiguration]] = select(
        AIProviderConfiguration
    ).where(AIProviderConfiguration.workspace_id == workspace_id)
    if not include_disabled:
        statement = statement.where(AIProviderConfiguration.is_enabled.is_(True))
    statement = statement.order_by(
        AIProviderConfiguration.priority.desc(),
        AIProviderConfiguration.created_at,
        AIProviderConfiguration.id,
    )
    return list(db.scalars(statement).all())


def get_provider_configuration(
    db: Session,
    *,
    workspace_id: UUID,
    provider_id: UUID,
) -> AIProviderConfiguration:
    provider = db.scalar(
        select(AIProviderConfiguration).where(
            AIProviderConfiguration.id == provider_id,
            AIProviderConfiguration.workspace_id == workspace_id,
        )
    )
    if provider is None:
        raise ResourceNotFoundError("AI provider configuration not found")
    return provider


def disable_provider_configuration(
    db: Session,
    *,
    workspace_id: UUID,
    provider_id: UUID,
) -> AIProviderConfiguration:
    provider = get_provider_configuration(
        db,
        workspace_id=workspace_id,
        provider_id=provider_id,
    )
    provider.is_enabled = False
    _commit(
        db,
        "Unable to disable AI provider configuration",
        "Unable to disable AI provider configuration",
    )
    db.refresh(provider)
    return provider


def create_prompt_version(
    db: Session,
    *,
    workspace_id: UUID,
    user_id: UUID,
    payload: AIPromptVersionCreate,
) -> AIPromptVersion:
    _validate_template(payload.system_template)
    _validate_template(payload.user_template)
    latest = db.scalar(
        select(func.max(AIPromptVersion.version)).where(
            AIPromptVersion.workspace_id == workspace_id,
            AIPromptVersion.name == payload.name,
        )
    )
    active_versions = list(
        db.scalars(
            select(AIPromptVersion).where(
                AIPromptVersion.workspace_id == workspace_id,
                AIPromptVersion.name == payload.name,
                AIPromptVersion.is_active.is_(True),
            )
        ).all()
    )
    for version in active_versions:
        version.is_active = False
    prompt = AIPromptVersion(
        workspace_id=workspace_id,
        created_by_user_id=user_id,
        name=payload.name,
        version=(latest or 0) + 1,
        system_template=payload.system_template,
        user_template=payload.user_template,
    )
    db.add(prompt)
    _commit(
        db,
        "Unable to allocate a unique AI prompt version",
        "Unable to create AI prompt version",
    )
    db.refresh(prompt)
    return prompt


def list_prompt_versions(
    db: Session,
    *,
    workspace_id: UUID,
    name: str | None = None,
) -> list[AIPromptVersion]:
    statement: Select[tuple[AIPromptVersion]] = select(AIPromptVersion).where(
        AIPromptVersion.workspace_id == workspace_id
    )
    if name is not None:
        statement = statement.where(AIPromptVersion.name == name)
    return list(
        db.scalars(
            statement.order_by(
                AIPromptVersion.name,
                AIPromptVersion.version.desc(),
                AIPromptVersion.id,
            )
        ).all()
    )


def get_active_prompt(
    db: Session,
    *,
    workspace_id: UUID,
    name: str,
) -> AIPromptVersion:
    prompt = db.scalar(
        select(AIPromptVersion)
        .where(
            AIPromptVersion.workspace_id == workspace_id,
            AIPromptVersion.name == name,
            AIPromptVersion.is_active.is_(True),
        )
        .order_by(AIPromptVersion.version.desc())
        .limit(1)
    )
    if prompt is None:
        raise ResourceNotFoundError("Active AI prompt version not found")
    return prompt


def get_prompt_version(
    db: Session,
    *,
    workspace_id: UUID,
    prompt_version_id: UUID,
) -> AIPromptVersion:
    prompt = db.scalar(
        select(AIPromptVersion).where(
            AIPromptVersion.id == prompt_version_id,
            AIPromptVersion.workspace_id == workspace_id,
        )
    )
    if prompt is None:
        raise ResourceNotFoundError("AI prompt version not found")
    return prompt


def upsert_usage_budget(
    db: Session,
    *,
    workspace_id: UUID,
    payload: AIUsageBudgetUpdate,
) -> AIUsageBudget:
    budget = db.scalar(
        select(AIUsageBudget).where(AIUsageBudget.workspace_id == workspace_id)
    )
    if budget is None:
        budget = AIUsageBudget(workspace_id=workspace_id)
        db.add(budget)
    budget.monthly_token_limit = payload.monthly_token_limit
    budget.monthly_cost_limit_usd = payload.monthly_cost_limit_usd
    budget.default_max_output_tokens = payload.default_max_output_tokens
    _commit(
        db,
        "Unable to save AI usage budget",
        "Unable to save AI usage budget",
    )
    db.refresh(budget)
    return budget


def get_usage_budget(db: Session, *, workspace_id: UUID) -> AIUsageBudget | None:
    return db.scalar(
        select(AIUsageBudget).where(AIUsageBudget.workspace_id == workspace_id)
    )


def _month_start(now: datetime | None = None) -> datetime:
    current = now or datetime.now(UTC)
    return current.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def usage_summary(db: Session, *, workspace_id: UUID) -> AIUsageSummary:
    period_start = _month_start()
    row = db.execute(
        select(
            func.coalesce(func.sum(AIInvocation.input_tokens), 0),
            func.coalesce(func.sum(AIInvocation.output_tokens), 0),
            func.coalesce(func.sum(AIInvocation.estimated_cost_usd), 0),
            func.count(AIInvocation.id),
        ).where(
            AIInvocation.workspace_id == workspace_id,
            AIInvocation.status == AIInvocationStatus.SUCCEEDED.value,
            AIInvocation.created_at >= period_start,
        )
    ).one()
    input_tokens = int(row[0])
    output_tokens = int(row[1])
    budget = get_usage_budget(db, workspace_id=workspace_id)
    return AIUsageSummary(
        period_start=period_start,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        estimated_cost_usd=Decimal(str(row[2])).quantize(SIX_PLACES),
        invocation_count=int(row[3]),
        monthly_token_limit=budget.monthly_token_limit if budget else None,
        monthly_cost_limit_usd=(budget.monthly_cost_limit_usd if budget else None),
    )


def list_invocations(
    db: Session,
    *,
    workspace_id: UUID,
    limit: int,
    offset: int,
) -> list[AIInvocation]:
    return list(
        db.scalars(
            select(AIInvocation)
            .where(AIInvocation.workspace_id == workspace_id)
            .order_by(AIInvocation.created_at.desc(), AIInvocation.id.desc())
            .offset(offset)
            .limit(limit)
        ).all()
    )


def _validate_template(template: str) -> set[str]:
    fields: set[str] = set()
    try:
        parsed = Formatter().parse(template)
        for _, field_name, format_spec, conversion in parsed:
            if field_name is None:
                continue
            if FIELD_NAME.fullmatch(field_name) is None or format_spec or conversion:
                raise InvalidRequestError(
                    "AI prompt templates support simple named fields only"
                )
            fields.add(field_name)
    except ValueError as exc:
        raise InvalidRequestError("AI prompt template is invalid") from exc
    return fields


def get_template_fields(template: str) -> set[str]:
    return _validate_template(template)


def _render(template: str, variables: Mapping[str, str]) -> str:
    required = _validate_template(template)
    if required - variables.keys():
        raise InvalidRequestError("AI prompt variables are incomplete")
    return template.format_map(dict(variables))


def _fingerprint(
    *,
    prompt: AIPromptVersion,
    variables: Mapping[str, str],
    output_schema: dict[str, object],
    capability_tier: AICapabilityTier,
    max_output_tokens: int,
) -> str:
    payload = {
        "prompt_version_id": str(prompt.id),
        "variables": dict(sorted(variables.items())),
        "output_schema": output_schema,
        "capability_tier": capability_tier.value,
        "max_output_tokens": max_output_tokens,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _key_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _estimated_input_tokens(messages: tuple[AIMessage, ...]) -> int:
    return sum((len(message.content) + 3) // 4 + 4 for message in messages)


def _cost(
    provider: AIProviderConfiguration,
    *,
    input_tokens: int,
    output_tokens: int,
) -> Decimal:
    value = (
        Decimal(input_tokens) * provider.input_cost_per_million
        + Decimal(output_tokens) * provider.output_cost_per_million
    ) / Decimal(1_000_000)
    return value.quantize(SIX_PLACES, rounding=ROUND_HALF_UP)


def _safe_ai_error(error: AIError) -> AIError:
    code = re.sub(r"[^a-z0-9_.-]", "_", error.code.lower())[:100]
    code = code or "ai_provider_error"
    if isinstance(error, AIBudgetExceededError):
        return AIBudgetExceededError(code, error.safe_message[:500])
    if isinstance(error, AIRetryableProviderError):
        messages = {
            "ai_provider_timeout": "AI provider timed out",
            "ai_provider_unreachable": "AI provider is unavailable",
        }
        return AIRetryableProviderError(
            code,
            messages.get(error.code, "AI provider is temporarily unavailable"),
        )
    if isinstance(error, AIOutputValidationError):
        return AIOutputValidationError(
            code,
            "AI provider returned an invalid structured response",
        )
    if isinstance(error, AIPermanentProviderError):
        return AIPermanentProviderError(
            code,
            "AI provider rejected the request",
        )
    return AIConfigurationError(
        code,
        "AI provider configuration is unavailable",
    )


def _enforce_budget(
    db: Session,
    *,
    workspace_id: UUID,
    projected_tokens: int,
    projected_cost: Decimal,
) -> None:
    current = usage_summary(db, workspace_id=workspace_id)
    if (
        current.monthly_token_limit is not None
        and current.total_tokens + projected_tokens > current.monthly_token_limit
    ):
        raise AIBudgetExceededError(
            "ai_token_budget_exceeded",
            "Workspace AI token budget would be exceeded",
        )
    if (
        current.monthly_cost_limit_usd is not None
        and current.estimated_cost_usd + projected_cost > current.monthly_cost_limit_usd
    ):
        raise AIBudgetExceededError(
            "ai_cost_budget_exceeded",
            "Workspace AI cost budget would be exceeded",
        )


def build_provider(
    configuration: AIProviderConfiguration,
    *,
    key_store: AIAPIKeyStore | None = None,
) -> AIProvider:
    kind = AIProviderKind(configuration.provider_kind)
    timeout = float(configuration.timeout_seconds)
    if kind is AIProviderKind.OLLAMA:
        return OllamaProvider(
            base_url=configuration.base_url,
            timeout_seconds=timeout,
        )
    api_key = None
    if configuration.credential_reference:
        api_key = (key_store or EnvironmentAIKeyStore()).load(
            configuration.credential_reference
        )
    return OpenAICompatibleProvider(
        base_url=configuration.base_url,
        timeout_seconds=timeout,
        api_key=api_key,
    )


def _eligible_providers(
    db: Session,
    *,
    workspace_id: UUID,
    capability_tier: AICapabilityTier,
) -> list[AIProviderConfiguration]:
    minimum = TIER_RANK[capability_tier.value]
    return [
        provider
        for provider in list_provider_configurations(
            db,
            workspace_id=workspace_id,
        )
        if TIER_RANK[provider.capability_tier] >= minimum
    ]


def generate_structured[AIOutput: BaseModel](
    db: Session,
    *,
    workspace_id: UUID,
    user_id: UUID,
    prompt_name: str,
    prompt_version_id: UUID | None = None,
    variables: Mapping[str, str],
    output_type: type[AIOutput],
    idempotency_key: str,
    capability_tier: AICapabilityTier = AICapabilityTier.LIGHTWEIGHT,
    max_output_tokens: int | None = None,
    temperature: float = 0.2,
    provider_builder: ProviderBuilder = build_provider,
    settings: Settings | None = None,
) -> AIGeneration:
    resolved_settings = settings or get_settings()
    if not 8 <= len(idempotency_key) <= 200:
        raise InvalidRequestError(
            "Idempotency key must contain 8 through 200 characters"
        )
    if any(not isinstance(value, str) for value in variables.values()):
        raise InvalidRequestError("AI prompt variables must be strings")
    total_characters = sum(len(value) for value in variables.values())
    if total_characters > resolved_settings.ai_max_input_characters:
        raise InvalidRequestError("AI prompt input exceeds the configured limit")
    prompt = (
        get_prompt_version(
            db,
            workspace_id=workspace_id,
            prompt_version_id=prompt_version_id,
        )
        if prompt_version_id is not None
        else get_active_prompt(
            db,
            workspace_id=workspace_id,
            name=prompt_name,
        )
    )
    if prompt.name != prompt_name:
        raise InvalidRequestError("AI prompt version does not match the prompt name")
    budget = get_usage_budget(db, workspace_id=workspace_id)
    output_limit = max_output_tokens or (
        budget.default_max_output_tokens if budget else 2048
    )
    if not 1 <= output_limit <= 32_768:
        raise InvalidRequestError("AI output token limit is invalid")
    messages = (
        AIMessage(
            role=AIMessageRole.SYSTEM,
            content=_render(prompt.system_template, variables),
        ),
        AIMessage(
            role=AIMessageRole.USER,
            content=_render(prompt.user_template, variables),
        ),
    )
    output_schema = output_type.model_json_schema()
    fingerprint = _fingerprint(
        prompt=prompt,
        variables=variables,
        output_schema=output_schema,
        capability_tier=capability_tier,
        max_output_tokens=output_limit,
    )
    key_hash = _key_hash(idempotency_key)
    existing = db.scalar(
        select(AIInvocation).where(
            AIInvocation.workspace_id == workspace_id,
            AIInvocation.idempotency_key_hash == key_hash,
        )
    )
    if existing is not None:
        if existing.request_fingerprint != fingerprint:
            raise ConflictError("Idempotency key was used for a different AI request")
        if existing.status != AIInvocationStatus.SUCCEEDED.value or not existing.output:
            raise ConflictError("The idempotent AI request previously failed")
        try:
            return AIGeneration(
                invocation=existing,
                output=output_type.model_validate(existing.output),
            )
        except ValidationError as exc:
            raise PersistenceError("Stored AI output is invalid") from exc

    providers = _eligible_providers(
        db,
        workspace_id=workspace_id,
        capability_tier=capability_tier,
    )
    if not providers:
        raise AIConfigurationError(
            "ai_provider_unavailable",
            "No eligible AI provider is configured",
        )
    estimated_input = _estimated_input_tokens(messages)
    last_error: AIError | None = None
    total_attempts = 0
    last_provider: AIProviderConfiguration | None = None

    for configuration in providers:
        projected_cost = _cost(
            configuration,
            input_tokens=estimated_input,
            output_tokens=output_limit,
        )
        try:
            _enforce_budget(
                db,
                workspace_id=workspace_id,
                projected_tokens=estimated_input + output_limit,
                projected_cost=projected_cost,
            )
        except AIBudgetExceededError as exc:
            last_error = exc
            continue
        last_provider = configuration
        request = AIStructuredRequest(
            model=configuration.model_name,
            messages=messages,
            output_schema_name=output_type.__name__[:64],
            output_schema=output_schema,
            max_output_tokens=output_limit,
            temperature=temperature,
        )
        try:
            provider = provider_builder(configuration)
        except AIError as exc:
            last_error = exc
            continue
        except Exception as exc:
            last_error = AIConfigurationError(
                "ai_provider_initialization_failed",
                "AI provider configuration is unavailable",
            )
            last_error.__cause__ = exc
            continue
        for _ in range(configuration.max_attempts):
            total_attempts += 1
            try:
                result = provider.generate_structured(request)
                validated = output_type.model_validate(result.output)
            except AIRetryableProviderError as exc:
                last_error = exc
                continue
            except (AIPermanentProviderError, ValidationError) as exc:
                last_error = (
                    exc
                    if isinstance(exc, AIError)
                    else AIOutputValidationError(
                        "ai_output_schema_mismatch",
                        "AI output did not match the required schema",
                    )
                )
                break
            except Exception as exc:
                last_error = AIRetryableProviderError(
                    "ai_provider_unexpected_failure",
                    "AI provider is temporarily unavailable",
                )
                last_error.__cause__ = exc
                continue
            invocation = AIInvocation(
                workspace_id=workspace_id,
                provider_configuration_id=configuration.id,
                prompt_version_id=prompt.id,
                requested_by_user_id=user_id,
                idempotency_key_hash=key_hash,
                request_fingerprint=fingerprint,
                provider_kind=configuration.provider_kind,
                model_name=configuration.model_name,
                status=AIInvocationStatus.SUCCEEDED.value,
                attempts=total_attempts,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                estimated_cost_usd=_cost(
                    configuration,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                ),
                output=validated.model_dump(mode="json"),
            )
            db.add(invocation)
            _commit(
                db,
                "AI request was already recorded",
                "Unable to record AI usage",
            )
            db.refresh(invocation)
            return AIGeneration(invocation=invocation, output=validated)

    if last_provider is not None:
        safe_error = _safe_ai_error(
            last_error
            or AIConfigurationError(
                "ai_provider_unavailable",
                "AI provider is unavailable",
            )
        )
        invocation = AIInvocation(
            workspace_id=workspace_id,
            provider_configuration_id=last_provider.id,
            prompt_version_id=prompt.id,
            requested_by_user_id=user_id,
            idempotency_key_hash=key_hash,
            request_fingerprint=fingerprint,
            provider_kind=last_provider.provider_kind,
            model_name=last_provider.model_name,
            status=AIInvocationStatus.FAILED.value,
            attempts=max(total_attempts, 1),
            last_error_code=safe_error.code[:100],
            last_error_message=safe_error.safe_message[:500],
        )
        db.add(invocation)
        _commit(
            db,
            "AI request was already recorded",
            "Unable to record AI failure",
        )
    if last_error is not None:
        raise _safe_ai_error(last_error)
    raise AIConfigurationError(
        "ai_provider_unavailable",
        "No AI provider is available within the workspace budget",
    )


def check_provider_health(
    db: Session,
    *,
    workspace_id: UUID,
    provider_builder: ProviderBuilder = build_provider,
) -> list[AIProviderHealthResponse]:
    rows = []
    for configuration in list_provider_configurations(
        db,
        workspace_id=workspace_id,
    ):
        try:
            health: AIProviderHealth = provider_builder(configuration).health_check()
        except Exception:
            health = AIProviderHealth(
                healthy=False,
                safe_message="AI provider configuration is unavailable",
            )
        rows.append(
            AIProviderHealthResponse(
                provider_configuration_id=configuration.id,
                provider_name=configuration.name,
                provider_kind=AIProviderKind(configuration.provider_kind),
                model_name=configuration.model_name,
                healthy=health.healthy,
                safe_message=health.safe_message,
            )
        )
    return rows
