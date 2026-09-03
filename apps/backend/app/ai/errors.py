class AIError(Exception):
    def __init__(self, code: str, safe_message: str) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message


class AIConfigurationError(AIError):
    pass


class AIBudgetExceededError(AIError):
    pass


class AIProviderError(AIError):
    pass


class AIRetryableProviderError(AIProviderError):
    pass


class AIPermanentProviderError(AIProviderError):
    pass


class AIOutputValidationError(AIPermanentProviderError):
    pass
