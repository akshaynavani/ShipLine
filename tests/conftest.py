from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from shipline.config import Config, parse_config
from shipline.errors import CommandError
from shipline.runner import CommandResult, CommandRunner

Responder = Callable[[list[str], str | None], CommandResult | str | None]


class FakeRunner(CommandRunner):
    """Records commands; responses come from (predicate, responder) rules."""

    def __init__(self, dry_run: bool = False) -> None:
        super().__init__(dry_run=dry_run)
        self.rules: list[tuple[Callable[[list[str]], bool], Responder]] = []
        self.inputs: list[str | None] = []

    def on(self, *needle: str, respond: Any = "") -> None:
        def match(cmd: list[str]) -> bool:
            joined = " ".join(cmd)
            return all(n in joined for n in needle)

        responder: Responder = respond if callable(respond) else (lambda c, i: respond)
        self.rules.insert(0, (match, responder))

    def run(self, cmd, *, cwd=None, input_text=None, check=True, capture=True, mutating=True):
        self.history.append(list(cmd))
        self.inputs.append(input_text)
        if self.dry_run and mutating:
            return CommandResult(cmd=cmd, returncode=0)
        out: Any = ""
        for match, responder in self.rules:
            if match(cmd):
                out = responder(cmd, input_text)
                break
        result = out if isinstance(out, CommandResult) else CommandResult(cmd, 0, out or "")
        if check and not result.ok:
            raise CommandError(cmd, result.returncode, result.stderr or result.stdout)
        return result

    def ran(self, *needle: str) -> bool:
        return any(all(n in " ".join(c) for n in needle) for c in self.history)


def fail(stderr: str = "boom", code: int = 1) -> Callable[[list[str], str | None], CommandResult]:
    return lambda cmd, _i: CommandResult(cmd, code, "", stderr)


@pytest.fixture()
def runner() -> FakeRunner:
    return FakeRunner()


RAW_CONFIG = {
    "app": "hello-service",
    "aws": {
        "region": "us-east-1",
        "account_id": "123456789012",
        "eks_cluster": "demo",
    },
    "kube": {"namespace": "hello", "manifests_dir": "k8s"},
}


@pytest.fixture()
def cfg(tmp_path: Path) -> Config:
    k8s = tmp_path / "k8s"
    k8s.mkdir()
    (k8s / "deploy.yaml").write_text(
        "apiVersion: apps/v1\n"
        "kind: Deployment\n"
        "metadata:\n  name: ${APP}\n  namespace: ${NAMESPACE}\n"
        "spec:\n  template:\n    spec:\n      containers:\n"
        "        - name: ${APP}\n          image: ${IMAGE}\n"
    )
    return parse_config(RAW_CONFIG, root=tmp_path, env={})
