"""Docker image build stage."""

from __future__ import annotations

from datetime import UTC, datetime

from shipline.errors import CommandError, StageError
from shipline.stages.base import PipelineContext, Stage


def build_command(ctx: PipelineContext) -> list[str]:
    cfg = ctx.cfg
    context_dir = cfg.path(cfg.docker.context)
    dockerfile = cfg.path(cfg.docker.dockerfile)
    cmd = [
        "docker",
        "build",
        "--platform",
        cfg.docker.platform,
        "-f",
        str(dockerfile),
        "-t",
        ctx.image,
        "--label",
        f"org.opencontainers.image.revision={ctx.git_sha or 'unknown'}",
        "--label",
        f"org.opencontainers.image.created={datetime.now(UTC).isoformat()}",
        "--label",
        f"shipline.app={cfg.app}",
        "--build-arg",
        f"APP_VERSION={ctx.tag}",
    ]
    for key, value in sorted(cfg.docker.build_args.items()):
        cmd += ["--build-arg", f"{key}={value}"]
    cmd.append(str(context_dir))
    return cmd


class BuildStage(Stage):
    name = "build"

    def run(self, ctx: PipelineContext) -> str:
        cmd = build_command(ctx)
        try:
            ctx.runner.run(cmd, cwd=ctx.cfg.root, capture=False)
        except CommandError as exc:
            raise StageError(self.name, f"docker build failed (exit {exc.returncode})") from exc
        except FileNotFoundError as exc:
            raise StageError(self.name, "docker is not installed or not on PATH") from exc
        ctx.artifacts["image"] = ctx.image
        return ctx.image
