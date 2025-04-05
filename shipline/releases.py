"""Release history, stored in a ConfigMap in the target namespace (or a local file).

Keeping history in the cluster means any CI runner or operator can roll back without
shared local state.
"""

from __future__ import annotations

import getpass
import json
import os
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shipline.kube import Kubectl

SUCCEEDED = "succeeded"
FAILED = "failed"


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def current_actor() -> str:
    for var in ("GITHUB_ACTOR", "GITLAB_USER_LOGIN", "BUILD_USER", "USER"):
        if os.environ.get(var):
            return os.environ[var]
    try:
        return getpass.getuser()
    except Exception:  # pragma: no cover - platform dependent
        return "unknown"


@dataclass
class Release:
    tag: str
    image: str
    git_sha: str | None = None
    status: str = SUCCEEDED
    kind: str = "deploy"  # "deploy" or "rollback"
    deployed_at: str = field(default_factory=_now)
    actor: str = field(default_factory=current_actor)
    note: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Release:
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)


class ReleaseStore(ABC):
    def __init__(self, limit: int = 20) -> None:
        self.limit = limit

    @abstractmethod
    def _load(self) -> list[dict[str, Any]]: ...

    @abstractmethod
    def _save(self, records: list[dict[str, Any]]) -> None: ...

    def list(self) -> list[Release]:
        """Releases oldest first."""
        return [Release.from_dict(r) for r in self._load()]

    def record(self, release: Release) -> None:
        records = self._load()
        records.append(asdict(release))
        self._save(records[-self.limit :])

    def successful(self) -> list[Release]:
        return [r for r in self.list() if r.status == SUCCEEDED]

    def find(self, tag: str) -> Release | None:
        for r in reversed(self.list()):
            if r.tag == tag:
                return r
        return None

    def previous_good(self, current_tag: str | None) -> Release | None:
        """Pick the release to roll back to from the one currently running.

        Only successful *deploy* records count as candidates (rollback records just
        re-point at older tags). The target is the newest successful deploy made before
        `current_tag` was first deployed, so repeated rollbacks keep stepping back
        (C -> B -> A) instead of bouncing between the two newest releases.
        """
        deploys = [r for r in self.successful() if r.kind == "deploy"]
        if current_tag:
            first = next((i for i, r in enumerate(deploys) if r.tag == current_tag), None)
            if first is not None:
                deploys = deploys[:first]
        candidates = [r for r in deploys if r.tag != current_tag]
        return candidates[-1] if candidates else None


class LocalReleaseStore(ReleaseStore):
    def __init__(self, path: Path, limit: int = 20) -> None:
        super().__init__(limit)
        self.path = path

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        data = json.loads(self.path.read_text() or "[]")
        return list(data)

    def _save(self, records: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(records, indent=2) + "\n")


class ConfigMapReleaseStore(ReleaseStore):
    def __init__(self, kubectl: Kubectl, app: str, limit: int = 20) -> None:
        super().__init__(limit)
        self.kubectl = kubectl
        self.name = f"shipline-releases-{app}"

    def _load(self) -> list[dict[str, Any]]:
        cm = self.kubectl.get_json("configmap", self.name)
        if not cm:
            return []
        raw = cm.get("data", {}).get("releases.json", "[]")
        return list(json.loads(raw))

    def _save(self, records: list[dict[str, Any]]) -> None:
        manifest = {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": self.name,
                "namespace": self.kubectl.namespace,
                "labels": {"app.kubernetes.io/managed-by": "shipline"},
            },
            "data": {"releases.json": json.dumps(records, indent=2)},
        }
        self.kubectl.apply(json.dumps(manifest))
