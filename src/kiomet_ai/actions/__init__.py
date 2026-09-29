from dataclasses import dataclass, asdict
from typing import Literal

@dataclass(frozen=True)
class Action:
    kind: Literal["MoveForce", "UpgradeTower", "SetSupplyLine", "MoveKing", "Wait"]
    source: int | None = None
    destination: int | None = None
    amount: int | None = None
    upgrade: str | None = None
    reason: str = ""

    def to_dict(self):
        return asdict(self)

@dataclass(frozen=True)
class ExecutionResult:
    accepted: bool
    message: str

@dataclass(frozen=True)
class VerificationResult:
    status: Literal["SUCCESS", "FAILED", "CANCELLED"]
    message: str
