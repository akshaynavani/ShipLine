"""Command-line entry point: `shipline <command>`."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable

from shipline import __version__
from shipline.config import Config, load_config
from shipline.errors import ShipLineError
from shipline.logging_utils import get_logger, setup_logging
from shipline.pipeline import Pipeline
from shipline.runner import CommandRunner
from shipline.stages.base import PipelineContext, Stage
from shipline.stages.build import BuildStage
from shipline.stages.checks import ChecksStage
from shipline.stages.publish import PublishStage
from shipline.tagging import git_sha, make_tag, validate_tag

log = get_logger("cli")

Handler = Callable[[argparse.Namespace, Config, CommandRunner], int]
_HANDLERS: dict[str, Handler] = {}


def command(name: str) -> Callable[[Handler], Handler]:
    def register(fn: Handler) -> Handler:
        _HANDLERS[name] = fn
        return fn

    return register


@command("validate")
def cmd_validate(args: argparse.Namespace, cfg: Config, runner: CommandRunner) -> int:
    print(f"app:        {cfg.app}")
    print(f"image repo: {cfg.aws.image_repo}")
    print(f"cluster:    {cfg.aws.eks_cluster} ({cfg.aws.region})")
    print(f"namespace:  {cfg.kube.namespace}")
    print(f"manifests:  {cfg.path(cfg.kube.manifests_dir)}")
    print("config OK")
    return 0


@command("check")
def cmd_check(args: argparse.Namespace, cfg: Config, runner: CommandRunner) -> int:
    Pipeline([ChecksStage()]).run(PipelineContext(cfg=cfg, runner=runner))
    return 0


def make_context(args: argparse.Namespace, cfg: Config, runner: CommandRunner) -> PipelineContext:
    sha = git_sha(runner, cfg.root)
    tag = validate_tag(args.tag) if getattr(args, "tag", None) else make_tag(sha)
    log.info("release tag: %s", tag)
    return PipelineContext(cfg=cfg, runner=runner, tag=tag, git_sha=sha)


def _stages_for(args: argparse.Namespace, upto: str) -> list[Stage]:
    order: list[tuple[str, Stage]] = [
        ("checks", ChecksStage()),
        ("build", BuildStage()),
        ("publish", PublishStage()),
    ]
    stages: list[Stage] = []
    for name, stage in order:
        if name == "checks" and getattr(args, "skip_checks", False):
            log.warning("skipping checks stage (--skip-checks)")
        else:
            stages.append(stage)
        if name == upto:
            break
    return stages


@command("build")
def cmd_build(args: argparse.Namespace, cfg: Config, runner: CommandRunner) -> int:
    ctx = make_context(args, cfg, runner)
    Pipeline(_stages_for(args, "build")).run(ctx)
    print(ctx.image)
    return 0


@command("publish")
def cmd_publish(args: argparse.Namespace, cfg: Config, runner: CommandRunner) -> int:
    ctx = make_context(args, cfg, runner)
    Pipeline(_stages_for(args, "publish")).run(ctx)
    print(ctx.image)
    return 0


def _add_release_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("--tag", help="override the generated image tag")
    p.add_argument("--skip-checks", action="store_true", help="skip lint/typecheck/tests")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shipline",
        description="Test, build, push to ECR and deploy to EKS with tagged rollbacks.",
    )
    parser.add_argument("--version", action="version", version=f"shipline {__version__}")
    parser.add_argument("-c", "--config", default=None, help="path to shipline.yaml")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print mutating commands instead of running them",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("validate", help="validate shipline.yaml and print resolved settings")
    sub.add_parser("check", help="run static analysis and pytest only")
    _add_release_flags(sub.add_parser("build", help="checks + docker build"))
    _add_release_flags(sub.add_parser("publish", help="checks + build + push to ECR"))
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    setup_logging(args.verbose)
    try:
        cfg = load_config(args.config)
        runner = CommandRunner(dry_run=args.dry_run)
        return _HANDLERS[args.command](args, cfg, runner)
    except ShipLineError as exc:
        log.error("%s", exc)
        return 1
    except KeyboardInterrupt:
        log.error("interrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main())
