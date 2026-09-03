import os
import re

from pydantic import SecretStr

from app.ai.errors import AIConfigurationError

ENV_REFERENCE = re.compile(r"^env://([A-Z][A-Z0-9_]{1,127})$")


class EnvironmentAIKeyStore:
    """Resolve explicit environment references without persisting key material."""

    def load(self, reference: str) -> SecretStr:
        match = ENV_REFERENCE.fullmatch(reference)
        if match is None:
            raise AIConfigurationError(
                "ai_credential_reference_invalid",
                "AI credential reference must use env://VARIABLE_NAME",
            )
        value = os.environ.get(match.group(1))
        if not value:
            raise AIConfigurationError(
                "ai_credential_unavailable",
                "AI provider credential is not configured",
            )
        return SecretStr(value)
