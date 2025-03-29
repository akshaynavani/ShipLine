"""Runs a sequence of stages and reports a summary."""

from __future__ import annotations

from collections.abc import Sequence

from shipline.errors import StageError
from shipline.logging_utils import banner, get_logger
from shipline.stages.base import PipelineContext, Stage, StageResult

log = get_logger("pipeline")


class Pipeline:
    def __init__(self, stages: Sequence[Stage]) -> None:
        self.stages = list(stages)

    def run(self, ctx: PipelineContext) -> list[StageResult]:
        results: list[StageResult] = []
        for stage in self.stages:
            log.info(banner(f"stage: {stage.name}"))
            try:
                result = stage.execute(ctx)
            except StageError:
                results.append(StageResult(stage.name, False, 0.0, "failed"))
                log.error(format_summary(results))
                raise
            log.info("%s ok in %.1fs - %s", stage.name, result.seconds, result.detail)
            results.append(result)
        log.info(format_summary(results))
        return results


def format_summary(results: Sequence[StageResult]) -> str:
    lines = ["pipeline summary:"]
    for r in results:
        status = "OK  " if r.ok else "FAIL"
        lines.append(f"  {status} {r.name:<10} {r.seconds:6.1f}s  {r.detail}")
    return "\n".join(lines)
