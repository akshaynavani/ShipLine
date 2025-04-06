"""Tagged rollbacks: point the deployment back at a previously released image."""

from __future__ import annotations

from shipline.aws import AwsClient
from shipline.config import Config
from shipline.errors import RollbackError
from shipline.logging_utils import get_logger
from shipline.releases import Release, ReleaseStore
from shipline.runner import CommandRunner
from shipline.stages.deploy import connect, release_store, wait_or_revert
from shipline.tagging import validate_tag

log = get_logger("rollback")


def tag_of(image: str | None) -> str | None:
    if not image or ":" not in image.rsplit("/", 1)[-1]:
        return None
    return image.rsplit(":", 1)[1]


def choose_target(store: ReleaseStore, current_tag: str | None, to: str | None) -> Release:
    if to:
        validate_tag(to)
        if to == current_tag:
            raise RollbackError(f"{to} is already running")
        found = store.find(to)
        if found is None:
            raise RollbackError(
                f"tag {to} is not in release history; pass --force to deploy it anyway"
            )
        return found
    target = store.previous_good(current_tag)
    if target is None:
        raise RollbackError("no earlier successful release to roll back to")
    return target


def rollback(cfg: Config, runner: CommandRunner, to: str | None = None,
             force: bool = False) -> Release:
    kubectl = connect(cfg, runner)
    store = release_store(cfg, kubectl)
    current_image = kubectl.current_image(cfg.deployment_name, cfg.container_name)
    if current_image is None and not runner.dry_run:
        raise RollbackError(f"deployment/{cfg.deployment_name} not found in {cfg.kube.namespace}")
    current_tag = tag_of(current_image)
    log.info("current tag: %s", current_tag)

    if to and force and store.find(to) is None:
        aws = AwsClient(cfg.aws, runner)
        if not aws.image_exists(to):
            raise RollbackError(f"image tag {to} not found in ECR {cfg.aws.ecr_repository}")
        target = Release(tag=to, image=f"{cfg.aws.image_repo}:{to}")
    else:
        target = choose_target(store, current_tag, to)

    log.info("rolling back %s: %s -> %s", cfg.deployment_name, current_tag, target.tag)
    kubectl.set_image(cfg.deployment_name, cfg.container_name, target.image)
    kubectl.annotate_deployment(
        cfg.deployment_name,
        {"kubernetes.io/change-cause": f"shipline rollback {current_tag} -> {target.tag}"},
    )
    record = Release(
        tag=target.tag,
        image=target.image,
        git_sha=target.git_sha,
        kind="rollback",
        note=f"from {current_tag}",
    )
    if runner.dry_run:
        return record
    wait_or_revert(kubectl, cfg, store, record, had_previous=True)
    store.record(record)
    return record
