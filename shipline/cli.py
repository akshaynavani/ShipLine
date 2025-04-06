"""Command-line entry point: `shipline <command>`."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable

from shipline import __version__
from shipline.config import Config, load_config
from shipline.manifests import render_directory, template_vars
from shipline.rollback import rollback
from shipline.errors import ShipLineError
from shipline.logging_utils import get_logger, setup_logging
from shipline.pipeline import Pipeline
from shipline.runner import CommandRunner
from shipline.stages.base import PipelineContext, Stage
from shipline.stages.build import BuildStage
from shipline.stages.checks import ChecksStage
from shipline.stages.deploy import DeployStage, connect, release_store
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
        ("deploy", DeployStage()),
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


@command("ship")
def cmd_ship(args: argparse.Namespace, cfg: Config, runner: CommandRunner) -> int:
    """The full pipeline: checks -> build -> publish -> deploy."""
    ctx = make_context(args, cfg, runner)
    Pipeline(_stages_for(args, "deploy")).run(ctx)
    print(f"shipped {ctx.image}")
    return 0


@command("deploy")
def cmd_deploy(args: argparse.Namespace, cfg: Config, runner: CommandRunner) -> int:
    """Deploy an already-published tag without rebuilding (promotion between envs)."""
    ctx = PipelineContext(cfg=cfg, runner=runner, tag=validate_tag(args.tag))
    Pipeline([DeployStage()]).run(ctx)
    return 0


@command("render")
def cmd_render(args: argparse.Namespace, cfg: Config, runner: CommandRunner) -> int:
    tag = validate_tag(args.tag)
    values = template_vars(
        app=cfg.app,
        namespace=cfg.kube.namespace,
        image=f"{cfg.aws.image_repo}:{tag}",
        tag=tag,
        git_sha=None,
    )
    sys.stdout.write(render_directory(cfg.path(cfg.kube.manifests_dir), values))
    return 0


@command("releases")
def cmd_releases(args: argparse.Namespace, cfg: Config, runner: CommandRunner) -> int:
    store = release_store(cfg, connect(cfg, runner))
    releases = store.list()
    if not releases:
        print("no releases recorded")
        return 0
    print(f"{'DEPLOYED AT':<21} {'KIND':<9} {'STATUS':<10} {'TAG':<34} {'ACTOR':<14} NOTE")
    for r in reversed(releases[-args.limit :]):
        print(f"{r.deployed_at:<21} {r.kind:<9} {r.status:<10} {r.tag:<34} {r.actor:<14} {r.note}")
    return 0


@command("rollback")
def cmd_rollback(args: argparse.Namespace, cfg: Config, runner: CommandRunner) -> int:
    release = rollback(cfg, runner, to=args.to, force=args.force)
    print(f"rolled back to {release.tag}")
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
    _add_release_flags(
        sub.add_parser("ship", help="full pipeline: checks, build, push to ECR, deploy to EKS")
    )

    p_deploy = sub.add_parser("deploy", help="deploy an existing ECR tag to EKS")
    p_deploy.add_argument("--tag", required=True)

    p_render = sub.add_parser("render", help="print rendered manifests for a tag")
    p_render.add_argument("--tag", required=True)

    p_rel = sub.add_parser("releases", help="show release history")
    p_rel.add_argument("-n", "--limit", type=int, default=20)

    p_rb = sub.add_parser("rollback", help="roll back to the previous (or a given) release")
    p_rb.add_argument("--to", help="release tag to roll back to (default: previous good)")
    p_rb.add_argument(
        "--force",
        action="store_true",
        help="allow a --to tag that is not in history if it exists in ECR",
    )
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
