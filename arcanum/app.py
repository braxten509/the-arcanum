"""Application service container and the only default backend composition root."""
from __future__ import annotations

from dataclasses import dataclass
import os

from .ai import AiService, build_default_ai_service
from .assessment.use_cases import AssessmentApplication, MasteryLabApplication
from .jobs import InMemoryJobStore, JobManager, ProcessStore
from .learning import LearningStateStore
from .settings import Settings, load_settings
from .config import read_settings
from .tomes import (project_dir, runtime_for, save_dir, state_path, tome_dir)


@dataclass(frozen=True)
class AppServices:
    settings: Settings
    jobs: JobManager
    processes: ProcessStore
    ai: AiService

    def learning(self, tome_id: str) -> LearningStateStore:
        root = save_dir(tome_id)
        return LearningStateStore(state_path(tome_id), os.path.join(root, "evidence-log.jsonl"))

    def assessment(self, tome_id: str) -> AssessmentApplication:
        return AssessmentApplication(
            ai=self.ai, tome_root=tome_dir(tome_id), save_root=save_dir(tome_id),
            runtime=runtime_for(tome_id), workspace=project_dir(tome_id),
            settings=read_settings(), tome_id=tome_id)

    def mastery_labs(self, tome_id: str) -> MasteryLabApplication:
        return MasteryLabApplication(tome_dir(tome_id), save_dir(tome_id),
                                    runtime_for(tome_id))


def create_app_services(settings: Settings | None = None) -> AppServices:
    return AppServices(settings or load_settings(), JobManager(InMemoryJobStore()),
                       ProcessStore(), build_default_ai_service())
