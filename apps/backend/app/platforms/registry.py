from app.models.channel import Platform
from app.platforms.contracts import PlatformAdapter
from app.services.errors import ConflictError, ResourceNotFoundError


class PlatformAdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[Platform, PlatformAdapter] = {}

    def register(self, adapter: PlatformAdapter) -> None:
        if adapter.platform in self._adapters:
            raise ConflictError(
                f"An adapter is already registered for {adapter.platform.value}"
            )
        self._adapters[adapter.platform] = adapter

    def get(self, platform: Platform) -> PlatformAdapter:
        adapter = self._adapters.get(platform)
        if adapter is None:
            raise ResourceNotFoundError(
                f"No adapter is registered for {platform.value}"
            )
        return adapter

    @property
    def platforms(self) -> frozenset[Platform]:
        return frozenset(self._adapters)
