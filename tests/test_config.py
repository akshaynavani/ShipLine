import copy

import pytest

from shipline.config import load_config, parse_config
from shipline.errors import ConfigError
from tests.conftest import RAW_CONFIG


def test_parse_defaults(tmp_path):
    cfg = parse_config(RAW_CONFIG, root=tmp_path, env={})
    assert cfg.aws.ecr_repository == "hello-service"
    assert cfg.aws.image_repo == "123456789012.dkr.ecr.us-east-1.amazonaws.com/hello-service"
    assert cfg.deployment_name == "hello-service"
    assert cfg.checks.tests == ["pytest", "-q"]
    assert cfg.kube.auto_rollback is True


def test_env_overrides(tmp_path):
    env = {
        "AWS_REGION": "eu-west-1",
        "AWS_ACCOUNT_ID": "999999999999",
        "SHIPLINE_NAMESPACE": "staging",
    }
    cfg = parse_config(RAW_CONFIG, root=tmp_path, env=env)
    assert cfg.aws.region == "eu-west-1"
    assert cfg.aws.account_id == "999999999999"
    assert cfg.kube.namespace == "staging"


def test_string_check_commands_are_split(tmp_path):
    raw = copy.deepcopy(RAW_CONFIG)
    raw["checks"] = {"lint": "ruff check app", "typecheck": "mypy app"}
    cfg = parse_config(raw, root=tmp_path, env={})
    assert cfg.checks.lint == ["ruff", "check", "app"]
    assert cfg.checks.typecheck == ["mypy", "app"]


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda r: r.pop("app"), "app"),
        (lambda r: r["aws"].pop("eks_cluster"), "aws.eks_cluster"),
        (lambda r: r["aws"].update(account_id="12345"), "12-digit"),
        (lambda r: r["kube"].update(bogus=1), "kube"),
    ],
)
def test_invalid_config(tmp_path, mutate, message):
    raw = copy.deepcopy(RAW_CONFIG)
    mutate(raw)
    with pytest.raises(ConfigError, match=message):
        parse_config(raw, root=tmp_path, env={})


def test_load_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.yaml")
