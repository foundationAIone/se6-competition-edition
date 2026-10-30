"""Strict, content-addressed contracts for SE6 LIVE LOOP v0.1.

These models describe proposals, authority, receipts, and derived state.  They
do not execute tools, approve actions, contact providers, or mutate storage.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from .canonical_contracts import canonical_json, canonical_sha256
from .live_loop_config import LIVE_LOOP_ADAPTER
from .live_loop_diff import SanitizedCandidateDiff

LIVE_LOOP_CONTRACT_VERSION = "0.1"
_HASH_PATTERN = r"^[0-9a-f]{64}$"


class LiveLoopStage(str, Enum):
    DORMANT = "DORMANT"
    GERMINATING = "GERMINATING"
    ROOTING = "ROOTING"
    OBSERVING = "OBSERVING"
    MAPPING = "MAPPING"
    PROPOSING = "PROPOSING"
    VERIFYING_PROPOSAL = "VERIFYING_PROPOSAL"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    EXECUTING = "EXECUTING"
    VERIFYING_CONSEQUENCE = "VERIFYING_CONSEQUENCE"
    ASSIMILATING = "ASSIMILATING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"


class LiveEvidenceStatus(str, Enum):
    OBSERVED = "OBSERVED"
    INFERRED = "INFERRED"
    PREDICTED = "PREDICTED"
    VERIFIED = "VERIFIED"
    CONTRADICTED = "CONTRADICTED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


class LiveBoundaryDecision(str, Enum):
    ALLOW = "ALLOW"
    REPAIR = "REPAIR"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    PAUSE = "PAUSE"
    REFUSE = "REFUSE"


class LiveTransactionDecision(str, Enum):
    COMMIT = "COMMIT"
    REPAIR = "REPAIR"
    PAUSE = "PAUSE"
    REFUSE = "REFUSE"


class LiveApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    CONSUMED = "CONSUMED"
    EXPIRED = "EXPIRED"
    INVALID = "INVALID"


class LiveLoopControl(str, Enum):
    CONTINUE = "CONTINUE"
    PAUSE = "PAUSE"
    STOP = "STOP"


class LiveRiskClass(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class LiveReceiptType(str, Enum):
    START = "START"
    OBSERVATION = "OBSERVATION"
    CANDIDATE = "CANDIDATE"
    BOUNDARY = "BOUNDARY"
    APPROVAL = "APPROVAL"
    EXECUTION = "EXECUTION"
    CONSEQUENCE = "CONSEQUENCE"
    VERIFICATION = "VERIFICATION"
    ASSIMILATION = "ASSIMILATION"
    NEXT_STATE = "NEXT_STATE"
    FINAL_TRANSACTION = "FINAL_TRANSACTION"
    PAUSE = "PAUSE"
    STOP = "STOP"
    FAILURE = "FAILURE"


class LiveContract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


def _id(prefix: str, material: object) -> str:
    return f"{prefix}_{canonical_sha256(material)}"


class LiveLoopBudget(LiveContract):
    max_cycles: StrictInt = Field(default=3, ge=1, le=3)
    max_model_calls: StrictInt = Field(default=3, ge=0, le=3)
    max_tokens: StrictInt = Field(default=12_000, ge=0, le=12_000)
    max_tool_calls: StrictInt = Field(default=4, ge=1, le=4)
    max_runtime_seconds: StrictInt = Field(default=30, ge=1, le=30)
    max_files: StrictInt = Field(default=3, ge=1, le=3)
    max_file_bytes: StrictInt = Field(default=64_000, ge=1, le=64_000)
    max_output_bytes: StrictInt = Field(default=30_000, ge=1, le=30_000)
    max_repairs_per_candidate: StrictInt = Field(default=2, ge=0, le=2)
    max_real_effect_adapters: StrictInt = Field(default=1, ge=0, le=1)


class LiveLoopUsage(LiveContract):
    cycles: StrictInt = Field(default=0, ge=0)
    model_calls: StrictInt = Field(default=0, ge=0)
    tokens: StrictInt = Field(default=0, ge=0)
    tool_calls: StrictInt = Field(default=0, ge=0)
    runtime_milliseconds: StrictInt = Field(default=0, ge=0)
    files: StrictInt = Field(default=0, ge=0)
    bytes_written: StrictInt = Field(default=0, ge=0)
    output_bytes: StrictInt = Field(default=0, ge=0)
    repair_attempts: StrictInt = Field(default=0, ge=0)
    real_effect_adapters: StrictInt = Field(default=0, ge=0)

    def within(self, budget: LiveLoopBudget) -> bool:
        return (
            self.cycles <= budget.max_cycles
            and self.model_calls <= budget.max_model_calls
            and self.tokens <= budget.max_tokens
            and self.tool_calls <= budget.max_tool_calls
            and self.runtime_milliseconds <= budget.max_runtime_seconds * 1000
            and self.files <= budget.max_files
            and self.bytes_written <= budget.max_files * budget.max_file_bytes
            and self.output_bytes <= budget.max_output_bytes
            and self.repair_attempts <= budget.max_repairs_per_candidate
            and self.real_effect_adapters <= budget.max_real_effect_adapters
        )


class ProductionAuthorityAnchor(LiveContract):
    anchor_id: StrictStr = Field(pattern=r"^anchor_[0-9a-f]{64}$")
    instance_id: StrictStr = Field(min_length=1)
    owner_id: StrictStr = Field(min_length=1)
    runtime_session_id: StrictStr = Field(min_length=1)
    base_identity_state_id: StrictStr = Field(min_length=1)
    base_identity_state_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    seed_id: StrictStr = Field(min_length=1)
    seed_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    constitution_version: StrictStr = Field(min_length=1)
    constitution_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    lifecycle_state: StrictStr = Field(min_length=1)
    emergency_stop_status: StrictStr = Field(pattern=r"^ARMED$")
    production_integrity_verified: bool
    # This is an opaque, process-local binding for the actual authenticated
    # browser session.  It is deliberately not derivable from owner/runtime
    # identifiers, so a later login cannot reuse a prepared approval.
    owner_session_binding_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    owner_authority_expires_at_utc: datetime
    authority_verified_at_utc: datetime

    @field_validator(
        "owner_authority_expires_at_utc", "authority_verified_at_utc"
    )
    @classmethod
    def time_is_aware(cls, value: datetime) -> datetime:
        return _aware(value)

    @model_validator(mode="after")
    def verify_anchor(self) -> ProductionAuthorityAnchor:
        if not self.production_integrity_verified:
            raise ValueError("production authority must be independently verified")
        if self.owner_authority_expires_at_utc <= self.authority_verified_at_utc:
            raise ValueError("owner authority must be valid when anchored")
        if self.anchor_id != _id("anchor", self.material_fields()):
            raise ValueError("anchor_id mismatch")
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"anchor_id"})


def create_authority_anchor(**fields: Any) -> ProductionAuthorityAnchor:
    material = dict(fields)
    material.pop("anchor_id", None)
    return ProductionAuthorityAnchor(
        anchor_id=_id("anchor", material),
        **material,
    )


class OwnerGoal(LiveContract):
    goal_id: StrictStr = Field(pattern=r"^goal_[0-9a-f]{64}$")
    transaction_id: StrictStr = Field(pattern=r"^txn_[0-9a-f]{64}$")
    cycle_id: StrictStr = Field(pattern=r"^cycle_[0-9a-f]{64}$")
    owner_id: StrictStr = Field(min_length=1)
    statement: StrictStr = Field(min_length=1, max_length=2_000)
    submitted_at_utc: datetime

    @field_validator("submitted_at_utc")
    @classmethod
    def time_is_aware(cls, value: datetime) -> datetime:
        return _aware(value)

    @model_validator(mode="after")
    def verify_id(self) -> OwnerGoal:
        if self.goal_id != _id("goal", self.material_fields()):
            raise ValueError("goal_id mismatch")
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"goal_id"})


def create_owner_goal(**fields: Any) -> OwnerGoal:
    material = dict(fields)
    material.pop("goal_id", None)
    return OwnerGoal(goal_id=_id("goal", material), **material)


class LiveObservationPacket(LiveContract):
    observation_id: StrictStr = Field(pattern=r"^observation_[0-9a-f]{64}$")
    transaction_id: StrictStr
    cycle_id: StrictStr
    identity_state_before_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    workspace_id: StrictStr = Field(min_length=1)
    permitted_relative_files: tuple[StrictStr, ...] = Field(min_length=1)
    observations: tuple[StrictStr, ...] = Field(min_length=1)
    evidence_status: LiveEvidenceStatus = LiveEvidenceStatus.OBSERVED
    observed_at_utc: datetime
    content_hashes: dict[StrictStr, StrictStr]

    @field_validator("observed_at_utc")
    @classmethod
    def time_is_aware(cls, value: datetime) -> datetime:
        return _aware(value)

    @model_validator(mode="after")
    def verify_id(self) -> LiveObservationPacket:
        if self.evidence_status is not LiveEvidenceStatus.OBSERVED:
            raise ValueError("observation packets must remain OBSERVED")
        if any(len(value) != 64 for value in self.content_hashes.values()):
            raise ValueError("observation content hashes must be SHA-256")
        if self.observation_id != _id("observation", self.material_fields()):
            raise ValueError("observation_id mismatch")
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"observation_id"})


def create_observation(**fields: Any) -> LiveObservationPacket:
    material = dict(fields)
    material.pop("observation_id", None)
    material.setdefault("evidence_status", LiveEvidenceStatus.OBSERVED)
    return LiveObservationPacket(
        observation_id=_id("observation", material),
        **material,
    )


class ExpectedConsequence(LiveContract):
    proposition: StrictStr = Field(min_length=1, max_length=1_000)
    measurement: StrictStr = Field(min_length=1, max_length=1_000)
    success_criteria: tuple[StrictStr, ...] = Field(min_length=1)
    verification_method: StrictStr = Field(min_length=1, max_length=500)
    verification_scope: StrictStr = Field(min_length=1, max_length=500)
    independent_verification_required: bool = True

    @model_validator(mode="after")
    def independent_is_required(self) -> ExpectedConsequence:
        if not self.independent_verification_required:
            raise ValueError("independent consequence verification is mandatory")
        return self


class CandidateCost(LiveContract):
    model_calls: StrictInt = Field(default=0, ge=0, le=3)
    tokens: StrictInt = Field(default=0, ge=0, le=12_000)
    tool_calls: StrictInt = Field(default=1, ge=0, le=4)
    runtime_seconds: StrictInt = Field(default=10, ge=0, le=30)
    files_touched: StrictInt = Field(default=1, ge=0, le=3)
    output_bytes: StrictInt = Field(default=10_000, ge=0, le=30_000)


class CandidateTransition(LiveContract):
    candidate_id: StrictStr = Field(pattern=r"^candidate_[0-9a-f]{64}$")
    transaction_id: StrictStr
    cycle_id: StrictStr
    goal_id: StrictStr
    proposal_id: StrictStr = Field(pattern=r"^proposal_[0-9a-f]{64}$")
    action_type: StrictStr = Field(pattern=r"^sandbox_python_repair$")
    adapter: StrictStr = Field(pattern=r"^sandbox_python_repair$")
    summary: StrictStr = Field(min_length=1, max_length=1_000)
    target: StrictStr = Field(min_length=1, max_length=260)
    canonical_target_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    structured_arguments: dict[StrictStr, Any]
    structured_arguments_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    expected_consequence: ExpectedConsequence
    required_authority: StrictStr = Field(pattern=r"^PRODUCTION_LOCAL_OWNER$")
    risk_classification: LiveRiskClass
    risk_class: LiveRiskClass
    estimated_cost: CandidateCost
    uncertainty: float = Field(ge=0.0, le=1.0)
    assumptions: tuple[StrictStr, ...] = ()
    evidence_refs: tuple[StrictStr, ...] = Field(min_length=1)
    prohibited_side_effects: tuple[StrictStr, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def verify_material(self) -> CandidateTransition:
        canonical_json(self.structured_arguments)
        if self.risk_classification is not self.risk_class:
            raise ValueError("risk classification must match candidate risk class")
        if self.action_type != LIVE_LOOP_ADAPTER or self.adapter != LIVE_LOOP_ADAPTER:
            raise ValueError("unregistered live-loop adapter")
        normalized = self.target.replace("\\", "/")
        if (
            not normalized
            or normalized.startswith(("/", "//"))
            or ":" in normalized
            or any(part in {"", ".", ".."} for part in normalized.split("/"))
        ):
            raise ValueError("target must be a normalized relative workspace path")
        if canonical_sha256({"target": normalized}) != self.canonical_target_hash:
            raise ValueError("canonical_target_hash mismatch")
        if canonical_sha256(self.structured_arguments) != self.structured_arguments_hash:
            raise ValueError("structured_arguments_hash mismatch")
        if self.proposal_id != _id(
            "proposal",
            {
                "transaction_id": self.transaction_id,
                "cycle_id": self.cycle_id,
                "goal_id": self.goal_id,
                "target_hash": self.canonical_target_hash,
                "arguments_hash": self.structured_arguments_hash,
            },
        ):
            raise ValueError("proposal_id mismatch")
        if self.candidate_id != _id("candidate", self.material_fields()):
            raise ValueError("candidate_id mismatch")
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"candidate_id"})


def create_candidate(**fields: Any) -> CandidateTransition:
    material = dict(fields)
    material.pop("candidate_id", None)
    target = str(material["target"]).replace("\\", "/")
    arguments = material["structured_arguments"]
    material.setdefault("action_type", LIVE_LOOP_ADAPTER)
    material.setdefault("adapter", LIVE_LOOP_ADAPTER)
    material.setdefault("risk_classification", material.get("risk_class"))
    material.setdefault("assumptions", ())
    material.setdefault("canonical_target_hash", canonical_sha256({"target": target}))
    material.setdefault("structured_arguments_hash", canonical_sha256(arguments))
    material.setdefault(
        "proposal_id",
        _id(
            "proposal",
            {
                "transaction_id": material["transaction_id"],
                "cycle_id": material["cycle_id"],
                "goal_id": material["goal_id"],
                "target_hash": material["canonical_target_hash"],
                "arguments_hash": material["structured_arguments_hash"],
            },
        ),
    )
    draft = CandidateTransition.model_construct(
        candidate_id="candidate_" + "0" * 64,
        **material,
    )
    return CandidateTransition(
        candidate_id=_id("candidate", draft.material_fields()),
        **material,
    )


class CandidateScore(LiveContract):
    candidate_id: StrictStr
    goal_relevance: float = Field(ge=0.0, le=1.0)
    evidence_support: float = Field(ge=0.0, le=1.0)
    authority_compatibility: float = Field(ge=0.0, le=1.0)
    expected_value: float = Field(ge=0.0, le=1.0)
    reversibility: float = Field(ge=0.0, le=1.0)
    verification_strength: float = Field(ge=0.0, le=1.0)
    risk: float = Field(ge=0.0, le=1.0)
    cost: float = Field(ge=0.0, le=1.0)
    uncertainty: float = Field(ge=0.0, le=1.0)
    total: float
    selected: bool = False
    rejection_reasons: tuple[StrictStr, ...] = ()

    @model_validator(mode="after")
    def score_is_inspectable(self) -> CandidateScore:
        expected = (
            self.goal_relevance
            + self.evidence_support
            + self.authority_compatibility
            + self.expected_value
            + self.reversibility
            + self.verification_strength
            - self.risk
            - self.cost
            - self.uncertainty
        )
        if abs(self.total - expected) > 1e-9:
            raise ValueError("candidate total does not match score dimensions")
        return self


class AuthorityScope(LiveContract):
    workspace_id: StrictStr
    adapter: StrictStr = Field(pattern=r"^sandbox_python_repair$")
    target: StrictStr
    max_files: StrictInt = Field(ge=1, le=3)
    max_file_bytes: StrictInt = Field(ge=1, le=64_000)
    max_runtime_seconds: StrictInt = Field(ge=1, le=30)
    max_output_bytes: StrictInt = Field(ge=1, le=30_000)
    network_allowed: bool = False
    shell_allowed: bool = False

    @model_validator(mode="after")
    def deny_broader_authority(self) -> AuthorityScope:
        if self.network_allowed or self.shell_allowed:
            raise ValueError("v0.1 scope never authorizes network or shell")
        return self


class LiveApprovalBindingSummary(LiveContract):
    """Complete non-secret material shown before owner authorization."""

    transaction_id: StrictStr
    cycle_id: StrictStr
    candidate_id: StrictStr = Field(pattern=r"^candidate_[0-9a-f]{64}$")
    action_type: StrictStr = Field(pattern=r"^sandbox_python_repair$")
    canonical_target_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    structured_arguments_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    expected_consequence: StrictStr = Field(min_length=1, max_length=1_000)
    expected_consequence_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    verification_method: StrictStr = Field(min_length=1, max_length=500)
    verification_method_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    required_authority: StrictStr = Field(pattern=r"^PRODUCTION_LOCAL_OWNER$")
    risk_classification: LiveRiskClass
    approval_policy_version: StrictStr = Field(min_length=1, max_length=180)
    approval_expires_at: datetime
    maximum_uses: StrictInt = Field(default=1, ge=1, le=1)
    owner_session_bound: bool = True
    owner_session_binding_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    adapter: StrictStr = Field(pattern=r"^sandbox_python_repair$")
    authority_scope: AuthorityScope
    sanitized_diff_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    binding_hash: StrictStr = Field(pattern=_HASH_PATTERN)

    @field_validator("approval_expires_at")
    @classmethod
    def expiration_is_aware(cls, value: datetime) -> datetime:
        return _aware(value)

    @model_validator(mode="after")
    def verify_complete_binding(self) -> LiveApprovalBindingSummary:
        if not self.owner_session_bound:
            raise ValueError("owner session binding is mandatory")
        if self.authority_scope.adapter != self.adapter:
            raise ValueError("approval adapter does not match authority scope")
        if self.authority_scope.network_allowed or self.authority_scope.shell_allowed:
            raise ValueError("approval scope cannot authorize network or shell")
        normalized = self.authority_scope.target.replace("\\", "/")
        if canonical_sha256({"target": normalized}) != self.canonical_target_hash:
            raise ValueError("approval target hash mismatch")
        if canonical_sha256(
            {"verification_method": self.verification_method}
        ) != self.verification_method_hash:
            raise ValueError("approval verification method hash mismatch")
        if canonical_sha256(
            {"expected_consequence": self.expected_consequence}
        ) != self.expected_consequence_hash:
            raise ValueError("approval expected consequence hash mismatch")
        if canonical_sha256(self.material_fields()) != self.binding_hash:
            raise ValueError("approval binding hash mismatch")
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"binding_hash"})


def create_approval_binding_summary(**fields: Any) -> LiveApprovalBindingSummary:
    material = dict(fields)
    material.pop("binding_hash", None)
    draft = LiveApprovalBindingSummary.model_construct(
        binding_hash="0" * 64,
        **material,
    )
    return LiveApprovalBindingSummary(
        binding_hash=canonical_sha256(draft.material_fields()),
        **material,
    )


class LiveBoundaryResult(LiveContract):
    boundary_decision_id: StrictStr = Field(pattern=r"^boundary_[0-9a-f]{64}$")
    transaction_id: StrictStr
    cycle_id: StrictStr
    candidate_id: StrictStr
    decision: LiveBoundaryDecision
    reason_codes: tuple[StrictStr, ...] = Field(min_length=1)
    repair_instructions: tuple[StrictStr, ...] = ()
    approved_adapter: StrictStr | None = None
    authority_scope: AuthorityScope | None = None
    policy_version: StrictStr = Field(min_length=1)
    evaluated_at_utc: datetime

    @field_validator("evaluated_at_utc")
    @classmethod
    def time_is_aware(cls, value: datetime) -> datetime:
        return _aware(value)

    @model_validator(mode="after")
    def verify_id(self) -> LiveBoundaryResult:
        if self.decision in {
            LiveBoundaryDecision.ALLOW,
            LiveBoundaryDecision.REQUIRE_APPROVAL,
        } and (self.approved_adapter != LIVE_LOOP_ADAPTER or self.authority_scope is None):
            raise ValueError("executable boundary decisions require exact scope")
        if self.boundary_decision_id != _id("boundary", self.material_fields()):
            raise ValueError("boundary_decision_id mismatch")
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"boundary_decision_id"})


def create_boundary_result(**fields: Any) -> LiveBoundaryResult:
    material = dict(fields)
    material.pop("boundary_decision_id", None)
    material.setdefault("repair_instructions", ())
    material.setdefault("approved_adapter", None)
    material.setdefault("authority_scope", None)
    draft = LiveBoundaryResult.model_construct(
        boundary_decision_id="boundary_" + "0" * 64,
        **material,
    )
    return LiveBoundaryResult(
        boundary_decision_id=_id("boundary", draft.material_fields()), **material
    )


class LiveApproval(LiveContract):
    approval_id: StrictStr = Field(pattern=r"^live_approval_[0-9a-f]{64}$")
    transaction_id: StrictStr
    cycle_id: StrictStr
    candidate_id: StrictStr
    action_type: StrictStr = Field(pattern=r"^sandbox_python_repair$")
    exact_target: StrictStr
    canonical_target_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    structured_arguments_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    expected_consequence_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    verification_method_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    owner_id: StrictStr
    approval_policy_version: StrictStr
    approval_binding_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    approval_status: LiveApprovalStatus
    issued_at_utc: datetime
    expires_at_utc: datetime
    maximum_uses: StrictInt = Field(default=1, ge=1, le=1)
    current_uses: StrictInt = Field(default=0, ge=0, le=1)
    approval_material_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    approval_receipt_hash: StrictStr = Field(pattern=_HASH_PATTERN)

    @field_validator("issued_at_utc", "expires_at_utc")
    @classmethod
    def time_is_aware(cls, value: datetime) -> datetime:
        return _aware(value)

    @model_validator(mode="after")
    def validate_approval(self) -> LiveApproval:
        if self.expires_at_utc <= self.issued_at_utc:
            raise ValueError("approval expiration must follow issuance")
        material = self.binding_fields()
        if canonical_sha256(material) != self.approval_material_hash:
            raise ValueError("approval material hash mismatch")
        receipt_material = {
            "approval_material_hash": self.approval_material_hash,
            "approval_status": self.approval_status,
            "issued_at_utc": self.issued_at_utc,
            "expires_at_utc": self.expires_at_utc,
        }
        if canonical_sha256(receipt_material) != self.approval_receipt_hash:
            raise ValueError("approval receipt hash mismatch")
        if self.approval_id != f"live_approval_{self.approval_receipt_hash}":
            raise ValueError("approval_id mismatch")
        return self

    def binding_fields(self) -> dict[str, Any]:
        return self.model_dump(
            mode="python",
            include={
                "transaction_id", "cycle_id", "candidate_id", "action_type",
                "exact_target", "canonical_target_hash",
                "structured_arguments_hash", "expected_consequence_hash",
                "verification_method_hash", "owner_id",
                "approval_policy_version", "approval_binding_hash",
                "maximum_uses", "issued_at_utc", "expires_at_utc",
            },
        )


def create_live_approval(**fields: Any) -> LiveApproval:
    material = dict(fields)
    for key in ("approval_id", "approval_material_hash", "approval_receipt_hash"):
        material.pop(key, None)
    material.setdefault("maximum_uses", 1)
    material.setdefault("current_uses", 0)
    material.setdefault("action_type", LIVE_LOOP_ADAPTER)
    binding_keys = {
        "transaction_id", "cycle_id", "candidate_id", "action_type",
        "exact_target", "canonical_target_hash", "structured_arguments_hash",
        "expected_consequence_hash", "verification_method_hash", "owner_id",
        "approval_policy_version", "approval_binding_hash", "maximum_uses",
        "issued_at_utc", "expires_at_utc",
    }
    binding = {key: material[key] for key in binding_keys}
    approval_material_hash = canonical_sha256(binding)
    receipt_hash = canonical_sha256(
        {
            "approval_material_hash": approval_material_hash,
            "approval_status": material["approval_status"],
            "issued_at_utc": material["issued_at_utc"],
            "expires_at_utc": material["expires_at_utc"],
        }
    )
    return LiveApproval(
        approval_id=f"live_approval_{receipt_hash}",
        approval_material_hash=approval_material_hash,
        approval_receipt_hash=receipt_hash,
        **material,
    )


class LiveExecutionReceipt(LiveContract):
    execution_receipt_id: StrictStr = Field(pattern=r"^execution_[0-9a-f]{64}$")
    transaction_id: StrictStr
    cycle_id: StrictStr
    candidate_id: StrictStr
    approval_id: StrictStr
    adapter: StrictStr = Field(pattern=r"^sandbox_python_repair$")
    workspace_id: StrictStr
    target: StrictStr
    exact_argv_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    before_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    after_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    proposed_content_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    diff_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    return_code: StrictInt
    stdout_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    stderr_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    scope_confined: bool
    shell_used: bool = False
    network_used: bool = False
    started_at_utc: datetime
    completed_at_utc: datetime

    @field_validator("started_at_utc", "completed_at_utc")
    @classmethod
    def time_is_aware(cls, value: datetime) -> datetime:
        return _aware(value)

    @model_validator(mode="after")
    def validate_receipt(self) -> LiveExecutionReceipt:
        if self.completed_at_utc < self.started_at_utc:
            raise ValueError("execution receipt time order invalid")
        if self.shell_used or self.network_used or not self.scope_confined:
            raise ValueError("execution escaped v0.1 authority scope")
        if self.execution_receipt_id != _id("execution", self.material_fields()):
            raise ValueError("execution_receipt_id mismatch")
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"execution_receipt_id"})


def create_execution_receipt(**fields: Any) -> LiveExecutionReceipt:
    material = dict(fields)
    material.pop("execution_receipt_id", None)
    material.setdefault("shell_used", False)
    material.setdefault("network_used", False)
    material.setdefault("adapter", LIVE_LOOP_ADAPTER)
    return LiveExecutionReceipt(
        execution_receipt_id=_id("execution", material),
        **material,
    )


class ConsequenceVerificationReceipt(LiveContract):
    verification_receipt_id: StrictStr = Field(pattern=r"^verification_[0-9a-f]{64}$")
    transaction_id: StrictStr
    cycle_id: StrictStr
    candidate_id: StrictStr
    execution_receipt_id: StrictStr
    expected_consequence: StrictStr
    independently_observed_consequence: StrictStr
    verification_method: StrictStr
    fresh_process: bool
    file_read_back: bool
    expected_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    observed_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    test_return_code: StrictInt
    passed: bool
    verified_scope: StrictStr
    excluded_claims: tuple[StrictStr, ...] = Field(min_length=1)
    verified_at_utc: datetime

    @field_validator("verified_at_utc")
    @classmethod
    def time_is_aware(cls, value: datetime) -> datetime:
        return _aware(value)

    @model_validator(mode="after")
    def validate_verification(self) -> ConsequenceVerificationReceipt:
        evidence_passed = (
            self.fresh_process
            and self.file_read_back
            and self.expected_hash == self.observed_hash
            and self.test_return_code == 0
        )
        if self.passed != evidence_passed:
            raise ValueError("verification conclusion does not match evidence")
        if self.verification_receipt_id != _id("verification", self.material_fields()):
            raise ValueError("verification_receipt_id mismatch")
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"verification_receipt_id"})


def create_verification_receipt(**fields: Any) -> ConsequenceVerificationReceipt:
    material = dict(fields)
    material.pop("verification_receipt_id", None)
    return ConsequenceVerificationReceipt(
        verification_receipt_id=_id("verification", material),
        **material,
    )


class DurableFact(LiveContract):
    fact_id: StrictStr = Field(pattern=r"^fact_[0-9a-f]{64}$")
    proposition: StrictStr = Field(min_length=1, max_length=1_000)
    status: LiveEvidenceStatus
    evidence_references: tuple[StrictStr, ...] = Field(min_length=1)
    source_transaction: StrictStr
    verification_method: StrictStr = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    created_at_utc: datetime
    verified_at_utc: datetime | None = None
    review_or_expiration_policy: StrictStr = Field(min_length=1)
    contradiction_references: tuple[StrictStr, ...] = ()
    revocation_history: tuple[StrictStr, ...] = ()

    @field_validator("created_at_utc", "verified_at_utc")
    @classmethod
    def time_is_aware(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _aware(value)

    @model_validator(mode="after")
    def verify_fact(self) -> DurableFact:
        if self.status is LiveEvidenceStatus.VERIFIED and self.verified_at_utc is None:
            raise ValueError("VERIFIED fact requires verified_at")
        if self.status is not LiveEvidenceStatus.VERIFIED and self.verified_at_utc is not None:
            raise ValueError("only VERIFIED facts carry verified_at")
        if self.status is LiveEvidenceStatus.CONTRADICTED and not self.contradiction_references:
            raise ValueError("contradicted facts retain contradiction references")
        if self.status is LiveEvidenceStatus.REVOKED and not self.revocation_history:
            raise ValueError("revoked facts retain revocation history")
        if self.fact_id != _id("fact", self.material_fields()):
            raise ValueError("fact_id mismatch")
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"fact_id"})


def create_durable_fact(**fields: Any) -> DurableFact:
    material = dict(fields)
    material.pop("fact_id", None)
    material.setdefault("verified_at_utc", None)
    material.setdefault("contradiction_references", ())
    material.setdefault("revocation_history", ())
    return DurableFact(fact_id=_id("fact", material), **material)


class AssimilationProposal(LiveContract):
    assimilation_receipt_id: StrictStr = Field(pattern=r"^assimilation_[0-9a-f]{64}$")
    transaction_id: StrictStr
    cycle_id: StrictStr
    verification_receipt_id: StrictStr
    proposed_facts: tuple[DurableFact, ...]
    non_assimilated_claims: tuple[StrictStr, ...]
    similarity_score_metadata: float | None = Field(default=None, ge=0.0, le=1.0)
    proposed_at_utc: datetime

    @field_validator("proposed_at_utc")
    @classmethod
    def time_is_aware(cls, value: datetime) -> datetime:
        return _aware(value)

    @model_validator(mode="after")
    def only_verified_is_durable(self) -> AssimilationProposal:
        if any(fact.status is not LiveEvidenceStatus.VERIFIED for fact in self.proposed_facts):
            raise ValueError("only VERIFIED facts may be proposed for durable assimilation")
        if self.assimilation_receipt_id != _id("assimilation", self.material_fields()):
            raise ValueError("assimilation_receipt_id mismatch")
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"assimilation_receipt_id"})


def create_assimilation_proposal(**fields: Any) -> AssimilationProposal:
    material = dict(fields)
    material.pop("assimilation_receipt_id", None)
    material.setdefault("similarity_score_metadata", None)
    draft = AssimilationProposal.model_construct(
        assimilation_receipt_id="assimilation_" + "0" * 64,
        **material,
    )
    return AssimilationProposal(
        assimilation_receipt_id=_id("assimilation", draft.material_fields()),
        **material,
    )


class DerivedIdentityState(LiveContract):
    identity_state_id: StrictStr = Field(pattern=r"^live_identity_[0-9a-f]{64}$")
    state_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    instance_id: StrictStr
    owner_id: StrictStr
    base_identity_state_id: StrictStr
    base_identity_state_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    previous_identity_state_id: StrictStr
    previous_state_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    constitution_version: StrictStr
    constitution_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    seed_id: StrictStr
    seed_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    source_transaction: StrictStr
    verified_fact_ids: tuple[StrictStr, ...]
    goal_status: StrictStr
    unresolved_issues: tuple[StrictStr, ...] = ()
    verified_resource_changes: dict[StrictStr, Any] = Field(default_factory=dict)
    contradiction_updates: tuple[StrictStr, ...] = ()
    next_justified_action: StrictStr | None = None
    stop_reason: StrictStr | None = None
    created_at_utc: datetime

    @field_validator("created_at_utc")
    @classmethod
    def time_is_aware(cls, value: datetime) -> datetime:
        return _aware(value)

    @model_validator(mode="after")
    def verify_state(self) -> DerivedIdentityState:
        material = self.material_fields()
        if canonical_sha256(material) != self.state_hash:
            raise ValueError("derived identity state_hash mismatch")
        if self.identity_state_id != f"live_identity_{self.state_hash}":
            raise ValueError("derived identity_state_id mismatch")
        if not self.verified_fact_ids:
            raise ValueError("derived identity requires a verified fact")
        if bool(self.next_justified_action) == bool(self.stop_reason):
            raise ValueError("derived identity requires exactly one next action or stop reason")
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"identity_state_id", "state_hash"})


def create_derived_identity_state(**fields: Any) -> DerivedIdentityState:
    material = dict(fields)
    material.pop("identity_state_id", None)
    material.pop("state_hash", None)
    material.setdefault("unresolved_issues", ())
    material.setdefault("verified_resource_changes", {})
    material.setdefault("contradiction_updates", ())
    material.setdefault("next_justified_action", None)
    material.setdefault("stop_reason", None)
    digest = canonical_sha256(material)
    return DerivedIdentityState(
        identity_state_id=f"live_identity_{digest}",
        state_hash=digest,
        **material,
    )


class LiveReceipt(LiveContract):
    receipt_id: StrictStr = Field(pattern=r"^live_receipt_[0-9a-f]{64}$")
    receipt_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    previous_receipt_hash: StrictStr | None = Field(default=None, pattern=_HASH_PATTERN)
    transaction_id: StrictStr
    cycle_id: StrictStr
    identity_state_before_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    receipt_type: LiveReceiptType
    stage: LiveLoopStage
    payload: dict[StrictStr, Any]
    payload_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    created_at_utc: datetime

    @field_validator("created_at_utc")
    @classmethod
    def time_is_aware(cls, value: datetime) -> datetime:
        return _aware(value)

    @model_validator(mode="after")
    def verify_receipt(self) -> LiveReceipt:
        canonical_json(self.payload)
        if canonical_sha256(self.payload) != self.payload_hash:
            raise ValueError("receipt payload hash mismatch")
        if canonical_sha256(self.material_fields()) != self.receipt_hash:
            raise ValueError("receipt hash mismatch")
        if self.receipt_id != f"live_receipt_{self.receipt_hash}":
            raise ValueError("receipt_id mismatch")
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"receipt_id", "receipt_hash"})


def create_live_receipt(**fields: Any) -> LiveReceipt:
    material = dict(fields)
    material.pop("receipt_id", None)
    material.pop("receipt_hash", None)
    material.setdefault("previous_receipt_hash", None)
    material.setdefault("payload_hash", canonical_sha256(material["payload"]))
    digest = canonical_sha256(material)
    return LiveReceipt(
        receipt_id=f"live_receipt_{digest}",
        receipt_hash=digest,
        **material,
    )


class LiveParityReport(LiveContract):
    compatibility_outcome: StrictStr
    canonical_outcome: StrictStr
    boundary_result: LiveBoundaryDecision
    proposed_action: StrictStr
    uncertainty: float = Field(ge=0.0, le=1.0)
    resource_estimate: CandidateCost
    final_authoritative_result: StrictStr
    material_disagreement: bool
    disagreement_reasons: tuple[StrictStr, ...] = ()


class LiveTransactionBundle(LiveContract):
    transaction_id: StrictStr
    cycle_id: StrictStr
    identity_state_before_id: StrictStr
    identity_state_before_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    authority_anchor: ProductionAuthorityAnchor
    goal: OwnerGoal
    observation: LiveObservationPacket
    candidates: tuple[CandidateTransition, ...] = Field(min_length=1)
    candidate_scores: tuple[CandidateScore, ...] = Field(min_length=1)
    selected_candidate: CandidateTransition
    boundary: LiveBoundaryResult
    approval: LiveApproval
    execution: LiveExecutionReceipt
    verification: ConsequenceVerificationReceipt
    assimilation: AssimilationProposal
    proposed_next_state: DerivedIdentityState
    parity: LiveParityReport
    budget: LiveLoopBudget
    usage: LiveLoopUsage
    receipts: tuple[LiveReceipt, ...]


class LiveTransactionValidationResult(LiveContract):
    decision: LiveTransactionDecision
    reason_codes: tuple[StrictStr, ...] = Field(min_length=1)
    transaction_id: StrictStr
    cycle_id: StrictStr
    identity_state_after_hash: StrictStr | None = Field(default=None, pattern=_HASH_PATTERN)
    immutable_invariants_verified: bool
    receipts_verified: bool
    approval_verified: bool
    execution_verified: bool
    consequence_verified: bool
    budgets_verified: bool
    validated_at_utc: datetime

    @field_validator("validated_at_utc")
    @classmethod
    def time_is_aware(cls, value: datetime) -> datetime:
        return _aware(value)

    @model_validator(mode="after")
    def commit_requires_every_gate(self) -> LiveTransactionValidationResult:
        gates = (
            self.immutable_invariants_verified,
            self.receipts_verified,
            self.approval_verified,
            self.execution_verified,
            self.consequence_verified,
            self.budgets_verified,
        )
        if self.decision is LiveTransactionDecision.COMMIT:
            if not all(gates) or self.identity_state_after_hash is None:
                raise ValueError("COMMIT requires every validator gate")
        elif self.identity_state_after_hash is not None:
            raise ValueError("non-COMMIT result cannot advance identity")
        return self


class LiveLoopDashboardProjection(LiveContract):
    enabled: bool
    authoritative: bool
    stage: LiveLoopStage
    instance_id_redacted: StrictStr | None = None
    production_base_identity_hash: StrictStr | None = None
    identity_state_before_hash: StrictStr | None = None
    identity_state_after_hash: StrictStr | None = None
    serving_provider: StrictStr = "none-offline"
    serving_model: StrictStr = "deterministic-v0.1"
    active_goal: StrictStr | None = None
    cycle_id: StrictStr | None = None
    transaction_id: StrictStr | None = None
    current_candidate: StrictStr | None = None
    candidate_id: StrictStr | None = None
    candidate_action_type: StrictStr | None = None
    candidate_adapter: StrictStr | None = None
    candidate_target: StrictStr | None = None
    canonical_target_hash: StrictStr | None = Field(
        default=None, pattern=_HASH_PATTERN
    )
    structured_arguments_hash: StrictStr | None = Field(
        default=None, pattern=_HASH_PATTERN
    )
    verification_method: StrictStr | None = None
    required_authority: StrictStr | None = None
    risk_classification: LiveRiskClass | None = None
    candidate_score: float | None = None
    boundary_decision: LiveBoundaryDecision | None = None
    boundary_reason_codes: tuple[StrictStr, ...] = ()
    approval_status: LiveApprovalStatus | None = None
    approval_policy_version: StrictStr | None = None
    approval_maximum_uses: StrictInt | None = Field(default=None, ge=1, le=1)
    approval_expires_at: datetime | None = None
    approval_time_status: StrictStr | None = Field(
        default=None, pattern=r"^(ACTIVE|EXPIRED)$"
    )
    approval_binding_summary: LiveApprovalBindingSummary | None = None
    approval_binding_hash: StrictStr | None = Field(
        default=None, pattern=_HASH_PATTERN
    )
    max_runtime_seconds: StrictInt | None = Field(default=None, ge=1, le=30)
    max_files: StrictInt | None = Field(default=None, ge=1, le=3)
    max_file_size_bytes: StrictInt | None = Field(
        default=None, ge=1, le=64_000
    )
    max_output_bytes: StrictInt | None = Field(default=None, ge=1, le=30_000)
    network_allowed: bool | None = None
    shell_allowed: bool | None = None
    sanitized_diff: SanitizedCandidateDiff | None = None
    approval_ready: bool = False
    approval_blockers: tuple[StrictStr, ...] = ()
    pending_approval_durable: bool = False
    restart_warning: StrictStr | None = None
    adapter_status: StrictStr = "NOT_STARTED"
    expected_consequence: StrictStr | None = None
    observed_consequence: StrictStr | None = None
    verification_result: StrictStr = "NOT_VERIFIED"
    assimilation_result: StrictStr = "NOT_ASSIMILATED"
    usage: LiveLoopUsage = Field(default_factory=LiveLoopUsage)
    remaining_cycles: StrictInt = Field(default=3, ge=0, le=3)
    stop_or_pause_reason: StrictStr | None = None
    integrity_status: StrictStr = "NOT_INITIALIZED"
    receipt_references: tuple[StrictStr, ...] = ()
    compatibility_disagreement: bool = False

    @field_validator("approval_expires_at")
    @classmethod
    def approval_expiration_is_aware(
        cls, value: datetime | None
    ) -> datetime | None:
        return None if value is None else _aware(value)

    @model_validator(mode="after")
    def approval_readiness_is_backend_complete(self) -> LiveLoopDashboardProjection:
        if self.approval_ready and self.stage is not LiveLoopStage.AWAITING_APPROVAL:
            raise ValueError("approval cannot be ready outside AWAITING_APPROVAL")
        if self.stage is not LiveLoopStage.AWAITING_APPROVAL:
            return self
        if self.pending_approval_durable:
            raise ValueError("v0.1 pending approval must remain non-durable")
        if self.restart_warning != (
            "PENDING APPROVAL IS NOT DURABLE. STOP LIVE LOOP BEFORE RESTARTING."
        ):
            raise ValueError("pending restart warning is mandatory")
        if not self.approval_ready:
            if not self.approval_blockers:
                raise ValueError("non-ready approval requires blockers")
            return self
        if self.approval_blockers:
            raise ValueError("ready approval cannot contain blockers")
        required = (
            self.transaction_id,
            self.cycle_id,
            self.candidate_id,
            self.candidate_action_type,
            self.candidate_adapter,
            self.candidate_target,
            self.canonical_target_hash,
            self.structured_arguments_hash,
            self.expected_consequence,
            self.verification_method,
            self.required_authority,
            self.risk_classification,
            self.approval_policy_version,
            self.approval_expires_at,
            self.approval_time_status,
            self.approval_binding_summary,
            self.approval_binding_hash,
            self.max_runtime_seconds,
            self.max_files,
            self.max_file_size_bytes,
            self.max_output_bytes,
            self.network_allowed,
            self.shell_allowed,
            self.sanitized_diff,
        )
        if any(value is None for value in required):
            raise ValueError("ready approval projection is incomplete")
        assert self.approval_binding_summary is not None
        assert self.sanitized_diff is not None
        if self.approval_time_status != "ACTIVE":
            raise ValueError("ready approval must be active")
        if self.network_allowed is not False or self.shell_allowed is not False:
            raise ValueError("ready approval cannot authorize network or shell")
        if self.approval_maximum_uses != 1:
            raise ValueError("ready approval must be single use")
        if self.boundary_decision is not LiveBoundaryDecision.REQUIRE_APPROVAL:
            raise ValueError("ready approval requires boundary approval decision")
        if self.candidate_adapter != LIVE_LOOP_ADAPTER:
            raise ValueError("ready approval requires the fixed adapter")
        if not self.sanitized_diff.authorization_complete:
            raise ValueError("ready approval requires a complete sanitized diff")
        summary = self.approval_binding_summary
        matching = (
            summary.transaction_id == self.transaction_id
            and summary.cycle_id == self.cycle_id
            and summary.candidate_id == self.candidate_id
            and summary.action_type == self.candidate_action_type
            and summary.adapter == self.candidate_adapter
            and summary.authority_scope.target == self.candidate_target
            and summary.canonical_target_hash == self.canonical_target_hash
            and summary.structured_arguments_hash == self.structured_arguments_hash
            and summary.expected_consequence == self.expected_consequence
            and summary.verification_method == self.verification_method
            and summary.required_authority == self.required_authority
            and summary.risk_classification == self.risk_classification
            and summary.approval_expires_at == self.approval_expires_at
            and summary.maximum_uses == self.approval_maximum_uses
            and summary.binding_hash == self.approval_binding_hash
            and summary.authority_scope.max_runtime_seconds == self.max_runtime_seconds
            and summary.authority_scope.max_files == self.max_files
            and summary.authority_scope.max_file_bytes == self.max_file_size_bytes
            and summary.authority_scope.max_output_bytes == self.max_output_bytes
            and summary.authority_scope.network_allowed is False
            and summary.authority_scope.shell_allowed is False
            and summary.sanitized_diff_hash == self.sanitized_diff.canonical_diff_hash
            and self.sanitized_diff.candidate_id == self.candidate_id
            and self.sanitized_diff.target == self.candidate_target
            and self.sanitized_diff.canonical_target_hash == self.canonical_target_hash
        )
        if not matching:
            raise ValueError("ready approval projection bindings differ")
        return self


class LiveCycleResult(LiveContract):
    projection: LiveLoopDashboardProjection
    validation: LiveTransactionValidationResult | None = None
    loop_control: LiveLoopControl
    approval_id: StrictStr | None = None
    transaction_receipt_id: StrictStr | None = None
    transaction_receipt_hash: StrictStr | None = Field(default=None, pattern=_HASH_PATTERN)


__all__ = [
    "LIVE_LOOP_CONTRACT_VERSION",
    "AssimilationProposal",
    "AuthorityScope",
    "CandidateCost",
    "CandidateScore",
    "CandidateTransition",
    "ConsequenceVerificationReceipt",
    "DerivedIdentityState",
    "DurableFact",
    "ExpectedConsequence",
    "LiveApproval",
    "LiveApprovalBindingSummary",
    "LiveApprovalStatus",
    "LiveBoundaryDecision",
    "LiveBoundaryResult",
    "LiveContract",
    "LiveCycleResult",
    "LiveEvidenceStatus",
    "LiveExecutionReceipt",
    "LiveLoopBudget",
    "LiveLoopControl",
    "LiveLoopDashboardProjection",
    "LiveLoopStage",
    "LiveLoopUsage",
    "LiveObservationPacket",
    "LiveParityReport",
    "LiveReceipt",
    "LiveReceiptType",
    "LiveRiskClass",
    "LiveTransactionBundle",
    "LiveTransactionDecision",
    "LiveTransactionValidationResult",
    "OwnerGoal",
    "ProductionAuthorityAnchor",
    "create_approval_binding_summary",
    "create_assimilation_proposal",
    "create_authority_anchor",
    "create_boundary_result",
    "create_candidate",
    "create_derived_identity_state",
    "create_durable_fact",
    "create_execution_receipt",
    "create_live_approval",
    "create_live_receipt",
    "create_observation",
    "create_owner_goal",
    "create_verification_receipt",
]
