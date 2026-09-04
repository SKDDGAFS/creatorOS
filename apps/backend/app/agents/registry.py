from dataclasses import dataclass

from app.models.agent_run import AgentType
from app.models.ai import AICapabilityTier
from app.services.errors import InvalidRequestError


@dataclass(frozen=True)
class AgentCapability:
    agent_type: AgentType
    prompt_name: str
    capability_tier: AICapabilityTier
    purpose: str
    output_mode: str = "recommendations_only"
    can_publish: bool = False
    can_execute_shell: bool = False


class AgentRegistry:
    def __init__(self) -> None:
        self._capabilities: dict[AgentType, AgentCapability] = {}

    def register(self, capability: AgentCapability) -> None:
        if capability.agent_type in self._capabilities:
            raise InvalidRequestError(
                f"An agent is already registered for {capability.agent_type.value}"
            )
        if capability.can_publish or capability.can_execute_shell:
            raise InvalidRequestError(
                "CreatorOS agents may recommend or prepare actions only"
            )
        self._capabilities[capability.agent_type] = capability

    def get(self, agent_type: AgentType) -> AgentCapability:
        capability = self._capabilities.get(agent_type)
        if capability is None:
            raise InvalidRequestError("Agent type is not registered")
        return capability

    def list(self) -> tuple[AgentCapability, ...]:
        return tuple(
            self._capabilities[key]
            for key in sorted(self._capabilities, key=lambda item: item.value)
        )


def default_agent_registry() -> AgentRegistry:
    registry = AgentRegistry()
    definitions = (
        (
            AgentType.CONTENT_STRATEGIST,
            AICapabilityTier.STANDARD,
            "Plan evidence-aware content themes, priorities, and experiments.",
        ),
        (
            AgentType.COPYWRITER,
            AICapabilityTier.LIGHTWEIGHT,
            "Prepare human-sounding hooks, scripts, and conversion copy.",
        ),
        (
            AgentType.SOCIAL_PLANNER,
            AICapabilityTier.STANDARD,
            "Recommend channel-specific social content and repurposing plans.",
        ),
        (
            AgentType.VIDEO_ANALYST,
            AICapabilityTier.ADVANCED,
            "Analyze referenced video evidence and recommend reproducible edits.",
        ),
        (
            AgentType.TOKEN_OPTIMIZER,
            AICapabilityTier.LIGHTWEIGHT,
            "Reduce prompt and workflow token usage while preserving outcomes.",
        ),
    )
    for agent_type, tier, purpose in definitions:
        registry.register(
            AgentCapability(
                agent_type=agent_type,
                prompt_name=f"agent.{agent_type.value}",
                capability_tier=tier,
                purpose=purpose,
            )
        )
    return registry
