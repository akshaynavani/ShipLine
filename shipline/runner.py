"""Single choke point for invoking external tools (docker, aws, kubectl, pytest...)."""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from shipline.errors import CommandError
from shipline.logging_utils import get_logger

log = get_logger("runner")


@dataclass
class CommandResult:
    cmd: list[str]
    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0


@dataclass
class CommandRunner:
    """Runs commands, or just logs them when dry_run is set.

    Secrets (such as the ECR login password) are passed through stdin via
    `input_text`, never as arguments, so they never reach the logs or `history`.
    """

    dry_run: bool = False
    env: dict[str, str] | None = None
    history: list[list[str]] = field(default_factory=list)

    def run(
        self,
        cmd: list[str],
        *,
        cwd: str | Path | None = None,
        input_text: str | None = None,
        check: bool = True,
        capture: bool = True,
        mutating: bool = True,
    ) -> CommandResult:
        """Execute `cmd`.

        `mutating=False` marks read-only commands which still execute in dry-run mode
        (e.g. `git rev-parse`, `kubectl get`), so previews stay accurate.
        """
        printable = shlex.join(cmd)
        self.history.append(list(cmd))
        if self.dry_run and mutating:
            log.info("[dry-run] %s", printable)
            return CommandResult(cmd=cmd, returncode=0)

        log.debug("$ %s", printable)
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            input=input_text,
            text=True,
            capture_output=capture,
            env=self.env,
        )
        result = CommandResult(
            cmd=cmd,
            returncode=proc.returncode,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
        )
        if check and not result.ok:
            output = (result.stderr or result.stdout).strip()
            if output:
                log.error("%s", output[-2000:])
            raise CommandError(cmd, result.returncode, output)
        return result

    def output(self, cmd: list[str], *, cwd: str | Path | None = None) -> str:
        """Run a read-only command and return trimmed stdout."""
        return self.run(cmd, cwd=cwd, mutating=False).stdout.strip()
