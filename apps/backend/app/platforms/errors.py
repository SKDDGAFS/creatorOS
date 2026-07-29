class PlatformAdapterError(Exception):
    def __init__(
        self,
        code: str,
        safe_message: str,
        *,
        retryable: bool,
        provider_request_id: str | None = None,
    ) -> None:
        super().__init__(safe_message)
        self.code = code[:100]
        self.safe_message = safe_message[:500]
        self.retryable = retryable
        self.provider_request_id = provider_request_id


class PlatformAuthenticationError(PlatformAdapterError):
    def __init__(self, code: str, safe_message: str) -> None:
        super().__init__(code, safe_message, retryable=False)


class PlatformCredentialExpiredError(PlatformAuthenticationError):
    pass


class PlatformRateLimitError(PlatformAdapterError):
    def __init__(
        self,
        code: str,
        safe_message: str,
        *,
        retry_after_seconds: int | None,
        provider_request_id: str | None = None,
    ) -> None:
        super().__init__(
            code,
            safe_message,
            retryable=True,
            provider_request_id=provider_request_id,
        )
        self.retry_after_seconds = retry_after_seconds


class PlatformTransientError(PlatformAdapterError):
    def __init__(
        self,
        code: str,
        safe_message: str,
        *,
        provider_request_id: str | None = None,
    ) -> None:
        super().__init__(
            code,
            safe_message,
            retryable=True,
            provider_request_id=provider_request_id,
        )


class PlatformPermanentError(PlatformAdapterError):
    def __init__(
        self,
        code: str,
        safe_message: str,
        *,
        provider_request_id: str | None = None,
    ) -> None:
        super().__init__(
            code,
            safe_message,
            retryable=False,
            provider_request_id=provider_request_id,
        )


class PlatformCapabilityError(PlatformPermanentError):
    pass
