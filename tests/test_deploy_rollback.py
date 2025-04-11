import json

import pytest

from shipline.errors import DeployError, RollbackError
from shipline.releases import FAILED, LocalReleaseStore, Release
from shipline.rollback import rollback, tag_of
from shipline.stages.base import PipelineContext
from shipline.stages.deploy import DeployStage
from tests.conftest import FakeRunner, fail

REPO = "123456789012.dkr.ecr.us-east-1.amazonaws.com/hello-service"


@pytest.fixture(autouse=True)
def local_env(monkeypatch):
    monkeypatch.setenv("SHIPLINE_SKIP_KUBECONFIG", "1")
    monkeypatch.setenv("SHIPLINE_RELEASE_STORE", "local")
    monkeypatch.setenv("USER", "tester")


def running(runner: FakeRunner, tag: str | None) -> None:
    if tag is None:
        runner.on("get", "deployment", respond=fail('deployments "x" NotFound'))
        return
    body = {"spec": {"template": {"spec": {"containers": [
        {"name": "hello-service", "image": f"{REPO}:{tag}"}]}}}}
    runner.on("get", "deployment", respond=json.dumps(body))


def history(cfg):
    return LocalReleaseStore(cfg.root / ".shipline" / "releases-hello-service.json")


def deploy(cfg, runner, tag):
    ctx = PipelineContext(cfg=cfg, runner=runner, tag=tag, git_sha="abc")
    return DeployStage().run(ctx)


def test_deploy_applies_and_records(cfg, runner):
    running(runner, None)
    deploy(cfg, runner, "t1")
    apply_idx = next(i for i, c in enumerate(runner.history) if "apply" in c)
    assert f"image: {REPO}:t1" in runner.inputs[apply_idx]
    assert runner.ran("rollout", "status", "deployment/hello-service")
    assert [r.tag for r in history(cfg).list()] == ["t1"]


def test_failed_rollout_reverts_and_records_failure(cfg, runner):
    running(runner, "t1")
    calls = {"n": 0}

    def status(cmd, _i):
        calls["n"] += 1
        return fail()(cmd, _i) if calls["n"] == 1 else ""

    runner.on("rollout", "status", respond=status)
    with pytest.raises(DeployError):
        deploy(cfg, runner, "t2")
    assert runner.ran("rollout", "undo")
    [rec] = history(cfg).list()
    assert rec.status == FAILED and "auto-reverted" in rec.note


def test_first_deploy_failure_does_not_undo(cfg, runner):
    running(runner, None)
    runner.on("rollout", "status", respond=fail())
    with pytest.raises(DeployError):
        deploy(cfg, runner, "t1")
    assert not runner.ran("rollout", "undo")


def test_dry_run_deploy_touches_nothing(cfg):
    runner = FakeRunner(dry_run=True)
    detail = deploy(cfg, runner, "t1")
    assert detail.startswith("dry-run")
    assert runner.history == []


def test_rollback_to_previous(cfg, runner):
    s = history(cfg)
    for t in ("t1", "t2"):
        s.record(Release(tag=t, image=f"{REPO}:{t}"))
    running(runner, "t2")
    rec = rollback(cfg, runner)
    assert rec.tag == "t1" and rec.kind == "rollback"
    assert runner.ran("set", "image", f"hello-service={REPO}:t1")
    assert history(cfg).list()[-1].kind == "rollback"


def test_rollback_to_explicit_tag_must_be_known(cfg, runner):
    history(cfg).record(Release(tag="t1", image=f"{REPO}:t1"))
    running(runner, "t1")
    with pytest.raises(RollbackError, match="already running"):
        rollback(cfg, runner, to="t1")
    with pytest.raises(RollbackError, match="not in release history"):
        rollback(cfg, runner, to="t0")


def test_forced_rollback_checks_ecr(cfg, runner):
    running(runner, "t2")
    runner.on("describe-images", respond=fail("ImageNotFoundException"))
    with pytest.raises(RollbackError, match="not found in ECR"):
        rollback(cfg, runner, to="t0", force=True)


def test_rollback_without_history_fails(cfg, runner):
    running(runner, "t1")
    with pytest.raises(RollbackError, match="no earlier"):
        rollback(cfg, runner)


def test_tag_of():
    assert tag_of(f"{REPO}:t1") == "t1"
    assert tag_of("localhost:5000/app") is None
    assert tag_of(None) is None
