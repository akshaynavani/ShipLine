"""Thin wrappers around the AWS CLI for ECR and EKS.

The AWS CLI is used instead of boto3 so credentials resolve exactly as they do for an
operator's shell or a CI job (env vars, SSO profile, OIDC-assumed role, instance profile).
"""

from __future__ import annotations

import json

from shipline.config import AwsConfig
from shipline.errors import CommandError, ShipLineError
from shipline.logging_utils import get_logger
from shipline.runner import CommandRunner

log = get_logger("aws")


class AwsClient:
    def __init__(self, cfg: AwsConfig, runner: CommandRunner) -> None:
        self.cfg = cfg
        self.runner = runner

    def _aws(self, *args: str) -> list[str]:
        return ["aws", *args, "--region", self.cfg.region, "--output", "json"]

    # --- identity -----------------------------------------------------------------

    def verify_identity(self) -> str:
        """Fail fast if credentials are missing or point at the wrong account."""
        if self.runner.dry_run:
            return "dry-run"
        try:
            raw = self.runner.output(self._aws("sts", "get-caller-identity"))
        except (CommandError, FileNotFoundError) as exc:
            raise ShipLineError("AWS credentials unavailable (aws sts get-caller-identity)") from exc
        identity = json.loads(raw)
        account = str(identity.get("Account"))
        if account != self.cfg.account_id:
            raise ShipLineError(
                f"AWS credentials belong to account {account}, config expects {self.cfg.account_id}"
            )
        return str(identity.get("Arn"))

    # --- ECR ------------------------------------------------------------------------

    def ecr_repository_exists(self) -> bool:
        try:
            self.runner.output(
                self._aws(
                    "ecr", "describe-repositories", "--repository-names", self.cfg.ecr_repository
                )
            )
            return True
        except CommandError as exc:
            if "RepositoryNotFoundException" in exc.output:
                return False
            raise

    def ensure_ecr_repository(self) -> bool:
        """Create the repository with immutable tags and scan-on-push if missing.

        Returns True if a repository was created.
        """
        if self.runner.dry_run or self.ecr_repository_exists():
            return False
        log.info("creating ECR repository %s", self.cfg.ecr_repository)
        self.runner.run(
            self._aws(
                "ecr",
                "create-repository",
                "--repository-name",
                self.cfg.ecr_repository,
                "--image-tag-mutability",
                "IMMUTABLE",
                "--image-scanning-configuration",
                "scanOnPush=true",
            )
        )
        return True

    def ecr_login(self) -> None:
        """docker login to ECR; the password is passed on stdin, never as an argument."""
        if self.runner.dry_run:
            self.runner.run(["docker", "login", "--username", "AWS", "--password-stdin",
                             self.cfg.registry])
            return
        password = self.runner.output(self._aws("ecr", "get-login-password"))
        self.runner.run(
            ["docker", "login", "--username", "AWS", "--password-stdin", self.cfg.registry],
            input_text=password,
        )

    def image_exists(self, tag: str) -> bool:
        try:
            self.runner.output(
                self._aws(
                    "ecr",
                    "describe-images",
                    "--repository-name",
                    self.cfg.ecr_repository,
                    "--image-ids",
                    f"imageTag={tag}",
                )
            )
            return True
        except CommandError as exc:
            if "ImageNotFoundException" in exc.output:
                return False
            raise

    def list_image_tags(self) -> list[str]:
        raw = self.runner.output(
            self._aws(
                "ecr",
                "describe-images",
                "--repository-name",
                self.cfg.ecr_repository,
                "--query",
                "sort_by(imageDetails,&imagePushedAt)[].imageTags[]",
            )
        )
        tags = json.loads(raw or "[]")
        return [str(t) for t in tags]

    # --- EKS ------------------------------------------------------------------------

    def update_kubeconfig(self, alias: str | None = None) -> None:
        cmd = ["aws", "eks", "update-kubeconfig", "--region", self.cfg.region,
               "--name", self.cfg.eks_cluster]
        if alias:
            cmd += ["--alias", alias]
        self.runner.run(cmd)
