"""Loading and validating shipline.yaml."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from shipline.errors import ConfigError

DEFAULT_CONFIG_NAME = "shipline.yaml"


@dataclass(frozen=True)
class ChecksConfig:
    lint: list[str] = field(default_factory=lambda: ["ruff", "check", "."])
    typecheck: list[str] | None = None
    tests: list[str] = field(default_factory=lambda: ["pytest", "-q"])
    junit_xml: str | None = "reports/junit.xml"


@dataclass(frozen=True)
class DockerConfig:
    context: str = "."
    dockerfile: str = "Dockerfile"
    platform: str = "linux/amd64"
    build_args: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class AwsConfig:
    region: str
    account_id: str
    ecr_repository: str
    eks_cluster: str

    @property
    def registry(self) -> str:
        return f"{self.account_id}.dkr.ecr.{self.region}.amazonaws.com"

    @property
    def image_repo(self) -> str:
        return f"{self.registry}/{self.ecr_repository}"


@dataclass(frozen=True)
class KubeConfig:
    namespace: str = "default"
    manifests_dir: str = "k8s"
    deployment: str | None = None
    container: str | None = None
    rollout_timeout: str = "180s"
    context: str | None = None
    auto_rollback: bool = True


@dataclass(frozen=True)
class Config:
    app: str
    root: Path
    aws: AwsConfig
    kube: KubeConfig
    docker: DockerConfig = field(default_factory=DockerConfig)
    checks: ChecksConfig = field(default_factory=ChecksConfig)
    history_limit: int = 20

    @property
    def deployment_name(self) -> str:
        return self.kube.deployment or self.app

    @property
    def container_name(self) -> str:
        return self.kube.container or self.app

    def path(self, relative: str) -> Path:
        return (self.root / relative).resolve()


def _require(data: dict[str, Any], key: str, section: str) -> Any:
    value = data.get(key)
    if value in (None, ""):
        raise ConfigError(f"missing required key '{section}.{key}'")
    return value


def _as_cmd(value: Any, key: str) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value.split()
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return list(value)
    raise ConfigError(f"'checks.{key}' must be a string or list of strings")


def parse_config(data: dict[str, Any], root: Path, env: dict[str, str] | None = None) -> Config:
    """Build a Config from a parsed YAML mapping, applying environment overrides."""
    env = dict(os.environ if env is None else env)
    if not isinstance(data, dict):
        raise ConfigError("config root must be a mapping")

    app = _require(data, "app", "")
    aws_raw = dict(data.get("aws") or {})
    # Environment variables win, so account ids never have to be committed.
    if env.get("AWS_REGION"):
        aws_raw["region"] = env["AWS_REGION"]
    if env.get("AWS_ACCOUNT_ID"):
        aws_raw["account_id"] = env["AWS_ACCOUNT_ID"]
    if env.get("SHIPLINE_EKS_CLUSTER"):
        aws_raw["eks_cluster"] = env["SHIPLINE_EKS_CLUSTER"]

    aws = AwsConfig(
        region=str(_require(aws_raw, "region", "aws")),
        account_id=str(_require(aws_raw, "account_id", "aws")),
        ecr_repository=str(aws_raw.get("ecr_repository") or app),
        eks_cluster=str(_require(aws_raw, "eks_cluster", "aws")),
    )
    if not aws.account_id.isdigit() or len(aws.account_id) != 12:
        raise ConfigError("aws.account_id must be a 12-digit AWS account id")

    kube_raw = dict(data.get("kube") or {})
    if env.get("SHIPLINE_NAMESPACE"):
        kube_raw["namespace"] = env["SHIPLINE_NAMESPACE"]
    try:
        kube = KubeConfig(**kube_raw)
    except TypeError as exc:
        raise ConfigError(f"invalid kube section: {exc}") from exc

    docker_raw = dict(data.get("docker") or {})
    try:
        docker = DockerConfig(**docker_raw)
    except TypeError as exc:
        raise ConfigError(f"invalid docker section: {exc}") from exc

    checks_raw = dict(data.get("checks") or {})
    defaults = ChecksConfig()
    checks = ChecksConfig(
        lint=_as_cmd(checks_raw.get("lint"), "lint") or defaults.lint,
        typecheck=_as_cmd(checks_raw.get("typecheck"), "typecheck"),
        tests=_as_cmd(checks_raw.get("tests"), "tests") or defaults.tests,
        junit_xml=checks_raw.get("junit_xml", defaults.junit_xml),
    )

    history_limit = int(data.get("history_limit", 20))
    if history_limit < 1:
        raise ConfigError("history_limit must be >= 1")

    return Config(
        app=str(app),
        root=root,
        aws=aws,
        kube=kube,
        docker=docker,
        checks=checks,
        history_limit=history_limit,
    )


def load_config(path: str | Path | None = None, env: dict[str, str] | None = None) -> Config:
    config_path = Path(path or DEFAULT_CONFIG_NAME).resolve()
    if not config_path.is_file():
        raise ConfigError(f"config file not found: {config_path}")
    try:
        data = yaml.safe_load(config_path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"could not parse {config_path}: {exc}") from exc
    return parse_config(data, root=config_path.parent, env=env)
