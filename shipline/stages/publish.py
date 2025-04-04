"""Push the built image to AWS ECR."""

from __future__ import annotations

from shipline.aws import AwsClient
from shipline.errors import CommandError, ShipLineError, StageError
from shipline.logging_utils import get_logger
from shipline.stages.base import PipelineContext, Stage

log = get_logger("publish")


class PublishStage(Stage):
    name = "publish"

    def __init__(self, aws: AwsClient | None = None) -> None:
        self._aws = aws

    def run(self, ctx: PipelineContext) -> str:
        aws = self._aws or AwsClient(ctx.cfg.aws, ctx.runner)
        try:
            who = aws.verify_identity()
            log.info("authenticated as %s", who)
            if aws.ensure_ecr_repository():
                log.info("created repository %s", ctx.cfg.aws.ecr_repository)
            aws.ecr_login()
            ctx.runner.run(["docker", "push", ctx.image], capture=False)
        except CommandError as exc:
            raise StageError(self.name, f"push failed: {exc}") from exc
        except ShipLineError as exc:
            raise StageError(self.name, str(exc)) from exc
        ctx.artifacts["pushed"] = ctx.image
        return f"pushed {ctx.image}"
