"""Stage abstraction and the context shared between stages."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from shipline.config import Config
from shipline.runner import CommandRunner


@dataclass
class PipelineContext:
    cfg: Config
    runner: CommandRunner
    tag: str | None = None
    git_sha: str | None = None
    artifacts: dict[str, Any] = field(default_factory=dict)

    @property
    def image(self) -> str:
        if not self.tag:
            raise RuntimeError("image tag has not been computed yet")
        return f"{self.cfg.aws.image_repo}:{self.tag}"


@dataclass
class StageResult:
    name: str
    ok: bool
    seconds: float
    detail: str = ""


class Stage(ABC):
    name: str = "stage"

    @abstractmethod
    def run(self, ctx: PipelineContext) -> str:
        """Run the stage; return a short human-readable summary. Raise StageError on failure."""

    def execute(self, ctx: PipelineContext) -> StageResult:
        start = time.monotonic()
        detail = self.run(ctx)
        return StageResult(self.name, True, time.monotonic() - start, detail)
