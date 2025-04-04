"""kubectl wrapper scoped to one context + namespace."""

from __future__ import annotations

import json
from typing import Any

from shipline.errors import CommandError
from shipline.logging_utils import get_logger
from shipline.runner import CommandRunner

log = get_logger("kube")


class Kubectl:
    def __init__(self, runner: CommandRunner, namespace: str, context: str | None = None) -> None:
        self.runner = runner
        self.namespace = namespace
        self.context = context

    def _base(self, namespaced: bool = True) -> list[str]:
        cmd = ["kubectl"]
        if self.context:
            cmd += ["--context", self.context]
        if namespaced:
            cmd += ["--namespace", self.namespace]
        return cmd

    def ensure_namespace(self) -> None:
        try:
            self.runner.output(self._base(False) + ["get", "namespace", self.namespace])
        except CommandError:
            log.info("creating namespace %s", self.namespace)
            self.runner.run(self._base(False) + ["create", "namespace", self.namespace])

    def apply(self, manifest_yaml: str) -> str:
        result = self.runner.run(self._base() + ["apply", "-f", "-"], input_text=manifest_yaml)
        return result.stdout.strip()

    def diff(self, manifest_yaml: str) -> str:
        # `kubectl diff` exits 1 when there are differences, which is not an error.
        result = self.runner.run(
            self._base() + ["diff", "-f", "-"],
            input_text=manifest_yaml,
            check=False,
            mutating=False,
        )
        if result.returncode > 1:
            raise CommandError(result.cmd, result.returncode, result.stderr)
        return result.stdout

    def rollout_status(self, deployment: str, timeout: str) -> bool:
        result = self.runner.run(
            self._base()
            + ["rollout", "status", f"deployment/{deployment}", f"--timeout={timeout}"],
            check=False,
            capture=False,
        )
        return result.ok

    def rollout_undo(self, deployment: str) -> None:
        self.runner.run(self._base() + ["rollout", "undo", f"deployment/{deployment}"])

    def set_image(self, deployment: str, container: str, image: str) -> None:
        self.runner.run(
            self._base() + ["set", "image", f"deployment/{deployment}", f"{container}={image}"]
        )

    def annotate_deployment(self, deployment: str, annotations: dict[str, str]) -> None:
        pairs = [f"{k}={v}" for k, v in sorted(annotations.items())]
        self.runner.run(
            self._base() + ["annotate", f"deployment/{deployment}", "--overwrite", *pairs]
        )

    def get_json(self, kind: str, name: str) -> dict[str, Any] | None:
        try:
            raw = self.runner.output(self._base() + ["get", kind, name, "-o", "json"])
        except CommandError as exc:
            if "NotFound" in exc.output or "not found" in exc.output:
                return None
            raise
        data: dict[str, Any] = json.loads(raw)
        return data

    def current_image(self, deployment: str, container: str) -> str | None:
        dep = self.get_json("deployment", deployment)
        if not dep:
            return None
        for c in dep.get("spec", {}).get("template", {}).get("spec", {}).get("containers", []):
            if c.get("name") == container:
                return str(c.get("image"))
        return None
