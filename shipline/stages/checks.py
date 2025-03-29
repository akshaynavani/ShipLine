"""Quality gate: static analysis, type checking and pytest."""

from __future__ import annotations

from shipline.errors import CommandError, StageError
from shipline.logging_utils import get_logger
from shipline.stages.base import PipelineContext, Stage

log = get_logger("checks")


class ChecksStage(Stage):
    name = "checks"

    def run(self, ctx: PipelineContext) -> str:
        cfg = ctx.cfg
        steps: list[tuple[str, list[str]]] = [("lint", cfg.checks.lint)]
        if cfg.checks.typecheck:
            steps.append(("typecheck", cfg.checks.typecheck))

        tests = list(cfg.checks.tests)
        if cfg.checks.junit_xml and tests and tests[0].endswith("pytest"):
            junit = cfg.path(cfg.checks.junit_xml)
            junit.parent.mkdir(parents=True, exist_ok=True)
            tests.append(f"--junitxml={junit}")
            ctx.artifacts["junit_xml"] = str(junit)
        steps.append(("tests", tests))

        passed = []
        for label, cmd in steps:
            log.info("running %s: %s", label, " ".join(cmd))
            try:
                # Checks are read-only, so they still run under --dry-run.
                ctx.runner.run(cmd, cwd=cfg.root, mutating=False, capture=False)
            except CommandError as exc:
                raise StageError(self.name, f"{label} failed (exit {exc.returncode})") from exc
            except FileNotFoundError as exc:
                raise StageError(self.name, f"{label} tool not installed: {cmd[0]}") from exc
            passed.append(label)
        return "passed: " + ", ".join(passed)
