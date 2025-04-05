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
        """Most recent successful release with a different tag than what's running now.

        Walks history newest-first, skipping everything up to and including the most
        recent occurrence of `current_tag`, so repeated rollbacks keep stepping back.
        """
        history = self.successful()
        if current_tag:
            idx = max((i for i, r in enumerate(history) if r.tag == current_tag), default=None)
            if idx is not None:
                # Look strictly before the current release, ignoring re-deploys of it.
                candidates = [r for r in history[:idx] if r.tag != current_tag]
                # Rollback records re-point at older tags; skip tags newer than current
                # that were themselves rolled away from.
                return candidates[-1] if candidates else None
        others = [r for r in history if r.tag != current_tag]
        return others[-1] if others else None


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
