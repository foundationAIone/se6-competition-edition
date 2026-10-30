"""Public-safe SE6 Competition Edition contracts.

No private SE6 imports.
No network.
No model provider.
No execution authority.
"""

from dataclasses import dataclass, field
from typing import Any

EPISTEMIC_STATES = {
    "MODEL_OUTPUT",
    "HYPOTHESIS",
    "OBSERVATION",
    "INDEPENDENT_EVIDENCE",
    "VERIFIED",
    "CONTRADICTED",
    "SUPERSEDED",
    "UNRESOLVED",
}

BOUNDARY_DECISIONS = {
    "ALLOW",
    "PAUSE",
    "REFUSE",
    "NEEDS_HUMAN_APPROVAL",
}


@dataclass(frozen=True)
class JudgeCase:
    case_id: str
    task: str
    model_output: str | None = None
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class JudgeResult:
    case_id: str
    epistemic_state: str
    boundary_decision: str
    execution_authority: bool
    evidence_refs: tuple[str, ...]
    provenance: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if type(self.execution_authority) is not bool:
            raise ValueError("execution_authority must be boolean")
        if self.epistemic_state not in EPISTEMIC_STATES:
            raise ValueError("invalid epistemic state")

        if self.boundary_decision not in BOUNDARY_DECISIONS:
            raise ValueError("invalid boundary decision")

        if self.execution_authority:
            raise ValueError(
                "Competition Edition contract cannot grant execution authority"
            )
