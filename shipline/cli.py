"""Command-line entry point: `shipline <command>`."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable

from shipline import __version__
from shipline.config import Config, load_config
from shipline.errors import ShipLineError
from shipline.logging_utils import get_logger, setup_logging
from shipline.runner import CommandRunner

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
