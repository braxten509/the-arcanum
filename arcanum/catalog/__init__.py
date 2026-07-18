"""Installed tome discovery, manifest access, and learner-safe assembly."""

from .filesystem import ManifestRepository
from .paths import TomePaths
from .service import TomeCatalogService
from arcanum.settings import load_settings
from runtimes import RuntimeRegistry


def create_catalog(root: str | None = None) -> TomeCatalogService:
    paths = TomePaths(load_settings(root))
    return TomeCatalogService(paths, ManifestRepository(paths),
                              RuntimeRegistry.from_root(paths.settings.root))


__all__ = ["ManifestRepository", "TomeCatalogService", "TomePaths", "create_catalog"]
