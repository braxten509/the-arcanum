"""Application service container and the only default backend composition root."""
from __future__ import annotations

from dataclasses import dataclass
import os

from runtimes import RuntimeRegistry

from .ai import AiService, build_default_ai_service
from .authoring.services import BinderService, ForgeService, LegacyGradingService
from .assessment.use_cases import AssessmentApplication, MasteryLabApplication
from .catalog import ManifestRepository, TomeCatalogService, TomePaths
from .execution import ExecutionService
from .jobs import InMemoryJobStore, JobManager, ProcessStore
from .learning import LearnerStateService, LearningStateStore
from .settings import Settings, UserSettingsStore, load_settings
from .workspace import WorkspaceService


@dataclass(frozen=True)
class AppServices:
    settings: Settings
    runtimes: RuntimeRegistry
    catalog: TomeCatalogService
    workspaces: WorkspaceService
    user_settings: UserSettingsStore
    jobs: JobManager
    processes: ProcessStore
    ai: AiService
    states: LearnerStateService
    execution: ExecutionService
    legacy_grading: LegacyGradingService
    binder: BinderService
    forge: ForgeService

    def learning(self, tome_id: str) -> LearningStateStore:
        root = self.workspaces.ensure_save(tome_id)
        return LearningStateStore(self.workspaces.state_path(tome_id),
                                  os.path.join(root, "evidence-log.jsonl"))

    def assessment(self, tome_id: str) -> AssessmentApplication:
        return AssessmentApplication(
            ai=self.ai, tome_root=self.catalog.paths.tome(tome_id),
            save_root=self.workspaces.ensure_save(tome_id),
            runtime=self.catalog.runtime(tome_id),
            workspace=self.workspaces.project_dir(tome_id),
            settings=self.user_settings.read(), tome_id=tome_id)

    def mastery_labs(self, tome_id: str) -> MasteryLabApplication:
        return MasteryLabApplication(
            self.catalog.paths.tome(tome_id), self.workspaces.ensure_save(tome_id),
            self.catalog.runtime(tome_id), tome_id)


def create_app_services(settings: Settings | None = None) -> AppServices:
    settings = settings or load_settings()
    os.makedirs(settings.cache_root, exist_ok=True)
    os.makedirs(settings.tomes_root, exist_ok=True)
    paths = TomePaths(settings)
    runtime_registry = RuntimeRegistry.from_root(settings.root)
    catalog = TomeCatalogService(paths, ManifestRepository(paths), runtime_registry)
    workspaces = WorkspaceService(catalog, paths)
    jobs = JobManager(InMemoryJobStore())
    user_settings = UserSettingsStore(settings.user_settings_path)
    processes = ProcessStore()
    ai = build_default_ai_service()
    states = LearnerStateService(workspaces, jobs, user_settings)
    execution = ExecutionService(catalog, workspaces)
    legacy_grading = LegacyGradingService(jobs, catalog, workspaces, ai)
    binder = BinderService(jobs, processes, ai)
    forge = ForgeService(settings, jobs, processes, catalog)
    return AppServices(settings, runtime_registry, catalog, workspaces, user_settings,
                       jobs, processes, ai, states, execution, legacy_grading, binder,
                       forge)
