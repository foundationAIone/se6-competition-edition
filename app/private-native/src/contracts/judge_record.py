from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from hashlib import sha256
from typing import Any

EPISTEMIC_STATES = frozenset(
    {
        "MODEL_OUTPUT",
        "HYPOTHESIS",
        "OBSERVATION",
        "INDEPENDENT_EVIDENCE",
        "VERIFIED",
        "CONTRADICTED",
        "SUPERSEDED",
        "UNRESOLVED",
    }
)

BOUNDARY_DECISIONS = frozenset(
    {
        "ALLOW",
        "PAUSE",
        "REFUSE",
        "NEEDS_HUMAN_APPROVAL",
    }
)

EVIDENCE_CLASSES = frozenset(
    {
        "MODEL_OUTPUT",
        "OWNER_STATEMENT",
        "OBSERVATION",
        "INDEPENDENT_EVIDENCE",
        "EXECUTION_RECEIPT",
    }
)


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def canonical_hash(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _require_boolean(value: Any, field_name: str, *, nullable: bool = False) -> None:
    if value is None and nullable:
        return
    if type(value) is not bool:
        suffix = " or null" if nullable else ""
        raise ValueError(f"{field_name} must be boolean{suffix}")


@dataclass(frozen=True)
class PublicEvidence:
    evidence_id: str
    evidence_class: str
    supports_claim: bool = False
    contradicts_claim: bool = False
    provenance: str | None = None

    def __post_init__(self) -> None:
        _require_boolean(self.supports_claim, "supports_claim")
        _require_boolean(self.contradicts_claim, "contradicts_claim")
        if not self.evidence_id.strip():
            raise ValueError("evidence_id required")

        if self.evidence_class not in EVIDENCE_CLASSES:
            raise ValueError("invalid evidence_class")

        if self.supports_claim and self.contradicts_claim:
            raise ValueError(
                "one evidence item cannot both support and contradict"
            )


@dataclass(frozen=True)
class ModelAloneLane:
    retained_claim: str | None
    claimed_verification: bool
    action: str | None
    result: str | None

    def __post_init__(self) -> None:
        _require_boolean(self.claimed_verification, "claimed_verification")


@dataclass(frozen=True)
class SE6Lane:
    epistemic_state: str
    boundary_decision: str
    evidence_refs: tuple[str, ...]
    execution_authority: bool = False
    verified_consequence: str | None = None
    state_transition: str | None = None
    restart_reconstructed: bool | None = None

    def __post_init__(self) -> None:
        _require_boolean(self.execution_authority, "execution_authority")
        _require_boolean(self.restart_reconstructed, "restart_reconstructed", nullable=True)
        if self.epistemic_state not in EPISTEMIC_STATES:
            raise ValueError("invalid epistemic_state")

        if self.boundary_decision not in BOUNDARY_DECISIONS:
            raise ValueError("invalid boundary_decision")

        # Competition Edition records authority.
        # It cannot grant authority.
        if self.execution_authority:
            raise ValueError(
                "Competition Edition cannot grant execution authority"
            )

        if (
            self.verified_consequence is not None
            and self.epistemic_state != "VERIFIED"
        ):
            raise ValueError(
                "verified consequence requires VERIFIED epistemic state"
            )


@dataclass(frozen=True)
class JudgeComparison:
    same_model_output: bool
    retention_changed: bool
    model_alone_claimed_verification: bool
    se6_epistemic_state: str
    se6_boundary_decision: str
    se6_restart_reconstructed: bool | None
    overall_verdict: None = None


@dataclass(frozen=True)
class JudgeRecord:
    schema_version: str
    case_id: str
    task: str
    provider: str
    model_id: str
    model_output: str
    evidence: tuple[PublicEvidence, ...]
    model_alone: ModelAloneLane
    se6: SE6Lane
    comparison: JudgeComparison
    synthetic: bool
    record_hash: str = field(default="")

    def __post_init__(self) -> None:
        _require_boolean(self.synthetic, "synthetic")

    def payload(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("record_hash", None)
        return value

    def verify_hash(self) -> bool:
        return self.record_hash == canonical_hash(self.payload())
