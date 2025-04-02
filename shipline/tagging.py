"""Immutable image tag generation: <short-sha>-<UTC timestamp>."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from shipline.errors import CommandError, ShipLineError
from shipline.runner import CommandRunner

# Docker tag grammar: [A-Za-z0-9_][A-Za-z0-9_.-]{0,127}
TAG_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")
_TS_FORMAT = "%Y%m%dT%H%M%SZ"


def validate_tag(tag: str) -> str:
    if not TAG_RE.match(tag):
        raise ShipLineError(f"invalid image tag: {tag!r}")
    if tag == "latest":
        raise ShipLineError("refusing to use mutable tag 'latest'; tags must be immutable")
    return tag


def git_sha(runner: CommandRunner, cwd: Path) -> str:
    try:
        sha = runner.output(["git", "rev-parse", "--short=7", "HEAD"], cwd=cwd)
    except (CommandError, FileNotFoundError):
        return "nogit"
    try:
        dirty = runner.output(["git", "status", "--porcelain", "--untracked-files=no"], cwd=cwd)
    except CommandError:
        dirty = ""
    return f"{sha}-dirty" if dirty else sha


def make_tag(sha: str, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    return validate_tag(f"{sha}-{now.strftime(_TS_FORMAT)}")


def parse_tag_time(tag: str) -> datetime | None:
    """Recover the build timestamp from a ShipLine tag, if it has one."""
    stamp = tag.rsplit("-", 1)[-1]
    try:
        return datetime.strptime(stamp, _TS_FORMAT).replace(tzinfo=UTC)
    except ValueError:
        return None
