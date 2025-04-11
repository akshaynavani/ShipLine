import json

import pytest

from shipline.errors import StageError
from shipline.pipeline import Pipeline
from shipline.stages.base import PipelineContext
from shipline.stages.build import BuildStage, build_command
from shipline.stages.checks import ChecksStage
from shipline.stages.publish import PublishStage
from tests.conftest import fail

TAG = "abc1234-20260101T000000Z"


def ctx_for(cfg, runner):
    return PipelineContext(cfg=cfg, runner=runner, tag=TAG, git_sha="abc1234")


def test_checks_runs_lint_and_pytest_with_junit(cfg, runner):
    ctx = ctx_for(cfg, runner)
    detail = ChecksStage().run(ctx)
    assert detail == "passed: lint, tests"
    assert runner.history[0][:2] == ["ruff", "check"]
    assert runner.history[1][0] == "pytest"
    assert runner.history[1][-1].startswith("--junitxml=")
    assert "junit_xml" in ctx.artifacts


def test_checks_failure_stops_pipeline(cfg, runner):
    runner.on("pytest", respond=fail("1 failed"))
    with pytest.raises(StageError, match="tests failed"):
        Pipeline([ChecksStage(), BuildStage()]).run(ctx_for(cfg, runner))
    assert not runner.ran("docker", "build")


def test_build_command_tags_and_labels(cfg, runner):
    cmd = build_command(ctx_for(cfg, runner))
    image = f"123456789012.dkr.ecr.us-east-1.amazonaws.com/hello-service:{TAG}"
    assert cmd[:2] == ["docker", "build"]
    assert cmd[cmd.index("-t") + 1] == image
    assert f"APP_VERSION={TAG}" in cmd
    assert "org.opencontainers.image.revision=abc1234" in cmd


def test_publish_logs_in_via_stdin_and_pushes(cfg, runner):
    runner.on("sts", "get-caller-identity",
              respond=json.dumps({"Account": "123456789012", "Arn": "arn:aws:iam::x"}))
    runner.on("ecr", "describe-repositories", respond="{}")
    runner.on("ecr", "get-login-password", respond="s3cret\n")
    PublishStage().run(ctx_for(cfg, runner))

    login_idx = next(i for i, c in enumerate(runner.history) if c[:2] == ["docker", "login"])
    assert "s3cret" not in " ".join(runner.history[login_idx])
    assert runner.inputs[login_idx] == "s3cret"
    assert runner.ran("docker", "push", TAG)
    assert not runner.ran("create-repository")


def test_publish_creates_missing_repository(cfg, runner):
    runner.on("sts", respond=json.dumps({"Account": "123456789012", "Arn": "a"}))
    runner.on("describe-repositories", respond=fail("RepositoryNotFoundException"))
    PublishStage().run(ctx_for(cfg, runner))
    assert runner.ran("create-repository", "IMMUTABLE")


def test_publish_rejects_wrong_account(cfg, runner):
    runner.on("sts", respond=json.dumps({"Account": "000000000001", "Arn": "a"}))
    with pytest.raises(StageError, match="account"):
        PublishStage().run(ctx_for(cfg, runner))
    assert not runner.ran("docker", "push")
