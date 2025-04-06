"""Deploy rendered manifests to EKS and wait for the rollout to become healthy."""

from __future__ import annotations

import os

from shipline.aws import AwsClient
from shipline.config import Config
from shipline.errors import CommandError, DeployError, ShipLineError, StageError
from shipline.kube import Kubectl
from shipline.logging_utils import get_logger
from shipline.manifests import render_directory, template_vars
from shipline.releases import (
    FAILED,
    ConfigMapReleaseStore,
    LocalReleaseStore,
    Release,
    ReleaseStore,
)
from shipline.runner import CommandRunner
from shipline.stages.base import PipelineContext, Stage

log = get_logger("deploy")


def connect(cfg: Config, runner: CommandRunner) -> Kubectl:
    """Point kubectl at the configured EKS cluster and return a namespaced client.

    Set SHIPLINE_SKIP_KUBECONFIG=1 to use the current kubeconfig as-is (e.g. a local
    kind/minikube cluster or a pre-configured CI runner).
    """
    context = cfg.kube.context
    if os.environ.get("SHIPLINE_SKIP_KUBECONFIG") != "1":
        context = context or f"shipline-{cfg.aws.eks_cluster}"
        AwsClient(cfg.aws, runner).update_kubeconfig(alias=context)
    return Kubectl(runner, namespace=cfg.kube.namespace, context=context)


def release_store(cfg: Config, kubectl: Kubectl) -> ReleaseStore:
    if os.environ.get("SHIPLINE_RELEASE_STORE", "configmap") == "local":
        path = cfg.root / ".shipline" / f"releases-{cfg.app}.json"
        return LocalReleaseStore(path, limit=cfg.history_limit)
    return ConfigMapReleaseStore(kubectl, cfg.app, limit=cfg.history_limit)


def wait_or_revert(
    kubectl: Kubectl,
    cfg: Config,
    store: ReleaseStore | None,
    release: Release,
    had_previous: bool,
) -> None:
    """Wait for rollout; on failure undo (if enabled), record the failure and raise."""
    if kubectl.rollout_status(cfg.deployment_name, cfg.kube.rollout_timeout):
        return
    note = "rollout did not become ready"
    if cfg.kube.auto_rollback and had_previous:
        log.warning("rollout failed, reverting deployment/%s", cfg.deployment_name)
        kubectl.rollout_undo(cfg.deployment_name)
        reverted = kubectl.rollout_status(cfg.deployment_name, cfg.kube.rollout_timeout)
        note += "; auto-reverted" if reverted else "; auto-revert ALSO failed"
    release.status = FAILED
    release.note = note
    if store is not None:
        store.record(release)
    raise DeployError("deploy", f"{release.tag}: {note}")


class DeployStage(Stage):
    name = "deploy"

    def run(self, ctx: PipelineContext) -> str:
        cfg = ctx.cfg
        if not ctx.tag:
            raise StageError(self.name, "no image tag to deploy")
        values = template_vars(
            app=cfg.app,
            namespace=cfg.kube.namespace,
            image=ctx.image,
            tag=ctx.tag,
            git_sha=ctx.git_sha,
        )
        try:
            rendered = render_directory(cfg.path(cfg.kube.manifests_dir), values)
        except ShipLineError as exc:
            raise StageError(self.name, str(exc)) from exc

        if ctx.runner.dry_run:
            log.info("[dry-run] rendered manifests:\n%s", rendered)
            ctx.artifacts["manifests"] = rendered
            return f"dry-run: would deploy {ctx.image}"

        try:
            kubectl = connect(cfg, ctx.runner)
            kubectl.ensure_namespace()
            store = release_store(cfg, kubectl)
            previous = kubectl.current_image(cfg.deployment_name, cfg.container_name)
            log.info("currently running: %s", previous or "<nothing>")

            print(kubectl.apply(rendered))
            kubectl.annotate_deployment(
                cfg.deployment_name,
                {"kubernetes.io/change-cause": f"shipline deploy {ctx.tag}"},
            )
            release = Release(tag=ctx.tag, image=ctx.image, git_sha=ctx.git_sha)
            wait_or_revert(kubectl, cfg, store, release, had_previous=previous is not None)
            store.record(release)
        except CommandError as exc:
            raise StageError(self.name, str(exc)) from exc
        return f"{cfg.deployment_name} running {ctx.tag}"
