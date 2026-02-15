"""FastAPI-aware registry."""

from sendparcel.registry import PluginRegistry


class FastAPIPluginRegistry(PluginRegistry):
    """Plugin registry with per-provider router support."""

    def __init__(self) -> None:
        super().__init__()
        self._provider_routers: dict[str, object] = {}

    def register_provider_router(self, slug: str, router: object) -> None:
        self._provider_routers[slug] = router

    def get_provider_router(self, slug: str) -> object | None:
        return self._provider_routers.get(slug)
