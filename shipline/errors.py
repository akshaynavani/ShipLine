"""Exception hierarchy used across ShipLine."""


class ShipLineError(Exception):
    """Base class for all pipeline errors."""


class ConfigError(ShipLineError):
    """Raised when shipline.yaml is missing or invalid."""


class CommandError(ShipLineError):
    """Raised when an external command exits with a non-zero status."""

    def __init__(self, cmd: list[str], returncode: int, output: str = "") -> None:
        self.cmd = cmd
        self.returncode = returncode
        self.output = output
        super().__init__(f"command failed ({returncode}): {' '.join(cmd)}")


class StageError(ShipLineError):
    """Raised when a pipeline stage fails."""

    def __init__(self, stage: str, message: str) -> None:
        self.stage = stage
        super().__init__(f"[{stage}] {message}")


class DeployError(StageError):
    """Raised when a Kubernetes rollout does not become healthy."""


class RollbackError(ShipLineError):
    """Raised when a rollback cannot be performed."""
