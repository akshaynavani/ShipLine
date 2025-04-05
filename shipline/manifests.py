"""Render Kubernetes manifests from a directory using ${VAR} substitution."""

from __future__ import annotations

import os
from pathlib import Path
from string import Template

import yaml

from shipline.errors import ShipLineError

VAR_PREFIX = "SHIPLINE_VAR_"


def template_vars(
    *, app: str, namespace: str, image: str, tag: str, git_sha: str | None,
    env: dict[str, str] | None = None,
) -> dict[str, str]:
    """Built-in variables plus any SHIPLINE_VAR_<NAME> environment variables."""
    env = dict(os.environ if env is None else env)
    values = {
        "APP": app,
        "NAMESPACE": namespace,
        "IMAGE": image,
        "TAG": tag,
        "GIT_SHA": git_sha or "unknown",
    }
    for key, value in env.items():
        if key.startswith(VAR_PREFIX):
            values[key[len(VAR_PREFIX):]] = value
    return values


def manifest_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        raise ShipLineError(f"manifests directory not found: {directory}")
    files = sorted(p for p in directory.iterdir() if p.suffix in {".yaml", ".yml"})
    if not files:
        raise ShipLineError(f"no .yaml manifests in {directory}")
    return files


def render_file(path: Path, values: dict[str, str]) -> str:
    try:
        rendered = Template(path.read_text()).substitute(values)
    except KeyError as exc:
        raise ShipLineError(f"{path.name}: undefined template variable ${{{exc.args[0]}}}") from exc
    except ValueError as exc:
        raise ShipLineError(f"{path.name}: bad template syntax: {exc}") from exc
    try:
        docs = [d for d in yaml.safe_load_all(rendered) if d is not None]
    except yaml.YAMLError as exc:
        raise ShipLineError(f"{path.name}: rendered YAML is invalid: {exc}") from exc
    for doc in docs:
        if not isinstance(doc, dict) or "kind" not in doc or "apiVersion" not in doc:
            raise ShipLineError(f"{path.name}: every document needs apiVersion and kind")
    return rendered.strip()


def render_directory(directory: Path, values: dict[str, str]) -> str:
    """Render every manifest in `directory` into one multi-document YAML stream."""
    parts = [render_file(p, values) for p in manifest_files(directory)]
    return "\n---\n".join(parts) + "\n"
