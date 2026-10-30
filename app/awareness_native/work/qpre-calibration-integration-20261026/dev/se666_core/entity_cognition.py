"""Strict contracts for durable, Entity-bound cognition.

These contracts describe evidence, memory, objectives, attention, capability
names, and candidate admission.  They perform no I/O, grant no authority, and
cannot execute an effect.  Durable persistence and execution boundaries live
in the adjacent cognition store and capability gateway modules.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from .canonical_contracts import canonical_sha256

ENTITY_COGNITION_CONTRACT_VERSION = "se6-entity-cognition-v1"

_HASH = r"^[0-9a-f]{64}$"
_ENTITY_ID = r"^instance_[0-9a-f]{64}$"
_IDENTITY_ID = r"^identity_[0-9a-f]{64}$"
_ENTITY_STATE_ID = r"^entity_state_[0-9a-f]{64}$"
_EVIDENCE_ID = r"^cognition_evidence_[0-9a-f]{64}$"
_MEMORY_ID = r"^cognition_memory_[0-9a-f]{64}$"
_OBJECTIVE_RECORD_ID = r"^cognition_objective_record_[0-9a-f]{64}$"
_ATTENTION_ID = r"^cognition_attention_[0-9a-f]{64}$"
_CANDIDATE_ID = r"^cognition_candidate_[0-9a-f]{64}$"
_ADMISSION_ID = r"^cognition_admission_[0-9a-f]{64}$"
_REFERENCE = r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,511}$"


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class MemoryStatus(str, Enum):
    OBSERVATION = "OBSERVATION"
    HYPOTHESIS = "HYPOTHESIS"
    INFERENCE = "INFERENCE"
    PROVISIONAL = "PROVISIONAL"
    VERIFIED_FACT = "VERIFIED_FACT"
    CONTRADICTED = "CONTRADICTED"
    SUPERSEDED = "SUPERSEDED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class EvidenceSourceKind(str, Enum):
    SYSTEM_OBSERVATION = "SYSTEM_OBSERVATION"
    OWNER_STATEMENT = "OWNER_STATEMENT"
    MODEL_OUTPUT = "MODEL_OUTPUT"
    EXTERNAL_RETRIEVAL = "EXTERNAL_RETRIEVAL"
    EXECUTION_RECEIPT = "EXECUTION_RECEIPT"
    INDEPENDENT_VERIFIER = "INDEPENDENT_VERIFIER"


class ObjectiveStatus(str, Enum):
    REQUESTED = "REQUESTED"
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    WITHDRAWN = "WITHDRAWN"


class ObjectiveOrigin(str, Enum):
    OWNER = "OWNER"
    ENTITY_DERIVED = "ENTITY_DERIVED"
    SYSTEM = "SYSTEM"


class CapabilityType(str, Enum):
    WEB_SEARCH = "web.search"
    HTTP_READ_ALLOWLISTED = "http.read.allowlisted"
    API_READ = "api.read"
    API_WRITE = "api.write"
    COMMUNICATION_PREPARE = "communication.prepare"
    COMMUNICATION_SEND = "communication.send"
    CODE_READ = "code.read"
    CODE_PREPARE = "code.prepare"
    CODE_EXECUTE_SANDBOX = "code.execute.sandbox"
    FILESYSTEM_READ_BOUNDED = "filesystem.read.bounded"
    FILESYSTEM_WRITE_BOUNDED = "filesystem.write.bounded"


class PiBDecision(str, Enum):
    ALLOW = "ALLOW"
    PAUSE = "PAUSE"
    REPAIR = "REPAIR"
    REFUSE = "REFUSE"


class CandidateRisk(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class CandidateIrreversibility(str, Enum):
    NONE = "NONE"
    LOCAL_APPEND_ONLY = "LOCAL_APPEND_ONLY"
    EXTERNAL_IRREVERSIBLE = "EXTERNAL_IRREVERSIBLE"


class CandidateSelection(str, Enum):
    SELECTED = "SELECTED"
    NO_OP = "NO_OP"
    REJECTED = "REJECTED"


class EvidenceReference(_Contract):
    schema_version: Literal["se6-cognition-evidence-v1"] = (
        "se6-cognition-evidence-v1"
    )
    evidence_id: StrictStr = Field(pattern=_EVIDENCE_ID)
    entity_id: StrictStr = Field(pattern=_ENTITY_ID)
    source_kind: EvidenceSourceKind
    source_id: StrictStr = Field(min_length=1, max_length=512, pattern=_REFERENCE)
    content_hash: StrictStr = Field(pattern=_HASH)
    observed_at_utc: datetime
    independently_verified: StrictBool
    verification_reference: StrictStr | None = Field(
        default=None, max_length=512, pattern=_REFERENCE
    )
    authority_effect: Literal["NONE"] = "NONE"

    @field_validator("observed_at_utc")
    @classmethod
    def time_is_aware(cls, value: datetime) -> datetime:
        return _utc(value, "observed_at_utc")

    @model_validator(mode="after")
    def evidence_is_canonical(self) -> EvidenceReference:
        if self.independently_verified != (self.verification_reference is not None):
            raise ValueError(
                "independent verification requires one verification reference"
            )
        if (
            self.source_kind is EvidenceSourceKind.MODEL_OUTPUT
            and self.independently_verified
        ):
            raise ValueError("model output cannot verify itself")
        expected = canonical_sha256(self.material_fields())
        if self.evidence_id != f"cognition_evidence_{expected}":
            raise ValueError("evidence_id must derive from evidence material")
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"evidence_id"})


class DurableMemoryRecord(_Contract):
    schema_version: Literal["se6-cognition-memory-v1"] = (
        "se6-cognition-memory-v1"
    )
    memory_id: StrictStr = Field(pattern=_MEMORY_ID)
    entity_id: StrictStr = Field(pattern=_ENTITY_ID)
    identity_state_id: StrictStr = Field(pattern=_IDENTITY_ID)
    entity_state_id: StrictStr = Field(pattern=_ENTITY_STATE_ID)
    previous_memory_id: StrictStr | None = Field(default=None, pattern=_MEMORY_ID)
    subject: StrictStr = Field(min_length=1, max_length=256)
    content_summary: StrictStr = Field(min_length=1, max_length=4_000)
    content_hash: StrictStr = Field(pattern=_HASH)
    status: MemoryStatus
    confidence_basis_points: StrictInt = Field(ge=0, le=10_000)
    provenance: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=64)
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=64)
    objective_ids: tuple[StrictStr, ...] = Field(default=(), max_length=64)
    recorded_at_utc: datetime
    valid_until_utc: datetime | None = None
    supersedes_memory_id: StrictStr | None = Field(default=None, pattern=_MEMORY_ID)
    contradicted_by_evidence_id: StrictStr | None = Field(
        default=None, pattern=_EVIDENCE_ID
    )
    revoked_by_authority_reference: StrictStr | None = Field(
        default=None, max_length=512, pattern=_REFERENCE
    )
    transition_reason: StrictStr | None = Field(default=None, max_length=1_000)
    authority_effect: Literal["NONE"] = "NONE"

    @field_validator("recorded_at_utc", "valid_until_utc")
    @classmethod
    def times_are_aware(cls, value: datetime | None) -> datetime | None:
        return _utc(value, "memory timestamp") if value is not None else None

    @model_validator(mode="after")
    def memory_is_bound_and_safe(self) -> DurableMemoryRecord:
        references = (*self.provenance, *self.evidence)
        if any(item.entity_id != self.entity_id for item in references):
            raise ValueError("memory evidence must bind the same Entity")
        if len(self.objective_ids) != len(set(self.objective_ids)):
            raise ValueError("memory objective links must be unique")
        if self.content_hash != canonical_sha256(
            {"subject": self.subject, "content_summary": self.content_summary}
        ):
            raise ValueError("memory content_hash mismatch")
        if self.status is MemoryStatus.VERIFIED_FACT:
            verified = tuple(
                item
                for item in self.evidence
                if item.independently_verified
                and item.source_kind is not EvidenceSourceKind.MODEL_OUTPUT
            )
            if not verified:
                raise ValueError(
                    "VERIFIED_FACT requires independent verified evidence"
                )
        if self.status is MemoryStatus.CONTRADICTED and (
            self.previous_memory_id is None
            or self.contradicted_by_evidence_id is None
            or self.contradicted_by_evidence_id
            not in {item.evidence_id for item in self.evidence}
        ):
            raise ValueError("CONTRADICTED memory requires ancestry and evidence")
        if self.status is MemoryStatus.SUPERSEDED and (
            self.previous_memory_id is None
            or self.supersedes_memory_id != self.previous_memory_id
        ):
            raise ValueError("SUPERSEDED memory requires exact ancestry")
        if self.status is MemoryStatus.REVOKED and (
            self.previous_memory_id is None
            or self.revoked_by_authority_reference is None
        ):
            raise ValueError("REVOKED memory requires attributable authority")
        if self.status is MemoryStatus.EXPIRED and (
            self.previous_memory_id is None
            or self.valid_until_utc is None
            or self.valid_until_utc > self.recorded_at_utc
        ):
            raise ValueError("EXPIRED memory requires ancestry and expiry")
        if self.previous_memory_id == self.memory_id:
            raise ValueError("memory cannot descend from itself")
        expected = canonical_sha256(self.material_fields())
        if self.memory_id != f"cognition_memory_{expected}":
            raise ValueError("memory_id must derive from memory material")
        return self

    @property
    def active(self) -> bool:
        return self.status not in {
            MemoryStatus.CONTRADICTED,
            MemoryStatus.SUPERSEDED,
            MemoryStatus.REVOKED,
            MemoryStatus.EXPIRED,
        }

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"memory_id"})


class DurableObjectiveRecord(_Contract):
    schema_version: Literal["se6-cognition-objective-v1"] = (
        "se6-cognition-objective-v1"
    )
    objective_record_id: StrictStr = Field(pattern=_OBJECTIVE_RECORD_ID)
    objective_id: StrictStr = Field(min_length=1, max_length=256, pattern=_REFERENCE)
    entity_id: StrictStr = Field(pattern=_ENTITY_ID)
    identity_state_id: StrictStr = Field(pattern=_IDENTITY_ID)
    entity_state_id: StrictStr = Field(pattern=_ENTITY_STATE_ID)
    revision: StrictInt = Field(ge=1)
    previous_objective_record_id: StrictStr | None = Field(
        default=None, pattern=_OBJECTIVE_RECORD_ID
    )
    parent_objective_id: StrictStr | None = Field(
        default=None, max_length=256, pattern=_REFERENCE
    )
    description: StrictStr = Field(min_length=1, max_length=4_000)
    origin: ObjectiveOrigin
    priority: StrictInt = Field(ge=0, le=100)
    status: ObjectiveStatus
    governing_authority_reference: StrictStr = Field(
        min_length=1, max_length=512, pattern=_REFERENCE
    )
    authority_scope: tuple[StrictStr, ...] = Field(default=(), max_length=64)
    required_capabilities: tuple[CapabilityType, ...] = Field(
        default=(), max_length=32
    )
    constraints: tuple[StrictStr, ...] = Field(default=(), max_length=64)
    progress_summary: StrictStr = Field(default="Not started.", max_length=4_000)
    evidence_references: tuple[StrictStr, ...] = Field(default=(), max_length=64)
    completion_condition: StrictStr = Field(min_length=1, max_length=2_000)
    created_at_utc: datetime
    updated_at_utc: datetime
    derived: StrictBool = False
    authority_effect: Literal["NONE"] = "NONE"

    @field_validator("created_at_utc", "updated_at_utc")
    @classmethod
    def times_are_aware(cls, value: datetime) -> datetime:
        return _utc(value, "objective timestamp")

    @model_validator(mode="after")
    def objective_is_canonical(self) -> DurableObjectiveRecord:
        if self.updated_at_utc < self.created_at_utc:
            raise ValueError("objective update cannot precede creation")
        if self.revision == 1 and self.previous_objective_record_id is not None:
            raise ValueError("first objective revision cannot have a predecessor")
        if self.revision > 1 and self.previous_objective_record_id is None:
            raise ValueError("objective revision requires a predecessor")
        if self.derived != (self.parent_objective_id is not None):
            raise ValueError("derived objective requires exactly one parent")
        if self.derived and self.origin is not ObjectiveOrigin.ENTITY_DERIVED:
            raise ValueError("derived objective origin must be ENTITY_DERIVED")
        if len(self.authority_scope) != len(set(self.authority_scope)):
            raise ValueError("objective authority scope must be unique")
        if len(self.required_capabilities) != len(set(self.required_capabilities)):
            raise ValueError("objective capabilities must be unique")
        expected = canonical_sha256(self.material_fields())
        if self.objective_record_id != f"cognition_objective_record_{expected}":
            raise ValueError("objective_record_id must derive from objective material")
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"objective_record_id"})


class AttentionDimensions(_Contract):
    relevance: StrictInt = Field(ge=0, le=100)
    change: StrictInt = Field(ge=0, le=100)
    uncertainty: StrictInt = Field(ge=0, le=100)
    risk: StrictInt = Field(ge=0, le=100)
    deadline: StrictInt = Field(ge=0, le=100)
    novelty: StrictInt = Field(ge=0, le=100)
    recurrence: StrictInt = Field(ge=0, le=100)
    owner_priority: StrictInt = Field(ge=0, le=100)


class AttentionResourceEnvelope(_Contract):
    maximum_work_items: StrictInt = Field(ge=1, le=64)
    maximum_events: StrictInt = Field(ge=1, le=256)
    maximum_elapsed_ms: StrictInt = Field(ge=1, le=60_000)
    maximum_tool_calls: StrictInt = Field(default=0, ge=0, le=64)
    maximum_network_calls: Literal[0] = 0


class DurableAttentionRecord(_Contract):
    schema_version: Literal["se6-cognition-attention-v1"] = (
        "se6-cognition-attention-v1"
    )
    attention_id: StrictStr = Field(pattern=_ATTENTION_ID)
    entity_id: StrictStr = Field(pattern=_ENTITY_ID)
    identity_state_id: StrictStr = Field(pattern=_IDENTITY_ID)
    entity_state_id: StrictStr = Field(pattern=_ENTITY_STATE_ID)
    subject: StrictStr = Field(min_length=1, max_length=512)
    dimensions: AttentionDimensions
    score: StrictInt = Field(ge=0, le=100)
    objective_ids: tuple[StrictStr, ...] = Field(default=(), max_length=64)
    evidence_references: tuple[StrictStr, ...] = Field(default=(), max_length=64)
    resources: AttentionResourceEnvelope
    recorded_at_utc: datetime
    deadline_at_utc: datetime | None = None
    expires_at_utc: datetime | None = None
    supersedes_attention_id: StrictStr | None = Field(
        default=None, pattern=_ATTENTION_ID
    )
    current: StrictBool = True
    authority_effect: Literal["NONE"] = "NONE"

    @field_validator("recorded_at_utc", "deadline_at_utc", "expires_at_utc")
    @classmethod
    def times_are_aware(cls, value: datetime | None) -> datetime | None:
        return _utc(value, "attention timestamp") if value is not None else None

    @model_validator(mode="after")
    def attention_is_canonical(self) -> DurableAttentionRecord:
        values = self.dimensions.model_dump(mode="python").values()
        if self.score != sum(values) // 8:
            raise ValueError("attention score must be the deterministic mean")
        if self.expires_at_utc is not None and self.expires_at_utc < self.recorded_at_utc:
            raise ValueError("attention expiry cannot precede recording")
        if not self.current and self.supersedes_attention_id is None:
            raise ValueError("inactive attention requires a supersession reference")
        if len(self.objective_ids) != len(set(self.objective_ids)):
            raise ValueError("attention objective links must be unique")
        expected = canonical_sha256(self.material_fields())
        if self.attention_id != f"cognition_attention_{expected}":
            raise ValueError("attention_id must derive from attention material")
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"attention_id"})


class FourPillarsAttestation(_Contract):
    authenticity: StrictBool
    integrity: StrictBool
    responsibility: StrictBool
    enrichment: StrictBool

    @property
    def holds(self) -> bool:
        return all(
            (
                self.authenticity,
                self.integrity,
                self.responsibility,
                self.enrichment,
            )
        )


class HardBoundaryAttestation(_Contract):
    safety: StrictBool
    law: StrictBool
    consent: StrictBool
    authority: StrictBool
    privacy: StrictBool
    emergency_stop_clear: StrictBool

    @property
    def holds(self) -> bool:
        return all(self.model_dump(mode="python").values())


class CandidateCost(_Contract):
    work_units: StrictInt = Field(ge=0, le=64)
    maximum_events: StrictInt = Field(ge=0, le=2_112)
    maximum_elapsed_ms: StrictInt = Field(ge=0, le=300_000)
    tool_calls: StrictInt = Field(default=0, ge=0, le=64)
    network_calls: Literal[0] = 0


class BoundedCognitionCandidate(_Contract):
    schema_version: Literal["se6-cognition-candidate-v1"] = (
        "se6-cognition-candidate-v1"
    )
    candidate_id: StrictStr = Field(pattern=_CANDIDATE_ID)
    candidate_hash: StrictStr = Field(pattern=_HASH)
    entity_id: StrictStr = Field(pattern=_ENTITY_ID)
    identity_state_id: StrictStr = Field(pattern=_IDENTITY_ID)
    entity_state_id: StrictStr = Field(pattern=_ENTITY_STATE_ID)
    summary: StrictStr = Field(min_length=1, max_length=1_000)
    provenance_references: tuple[StrictStr, ...] = Field(min_length=1, max_length=32)
    expected_value_basis_points: StrictInt = Field(ge=0, le=10_000)
    cost: CandidateCost
    risk: CandidateRisk
    irreversibility: CandidateIrreversibility
    required_capabilities: tuple[CapabilityType, ...] = Field(default=(), max_length=32)
    authority_requirements: tuple[StrictStr, ...] = Field(min_length=1, max_length=32)
    pi_b_decision: PiBDecision
    hard_boundaries: HardBoundaryAttestation
    four_pillars: FourPillarsAttestation
    selection: CandidateSelection
    selection_reason_codes: tuple[StrictStr, ...] = Field(min_length=1, max_length=32)
    created_at_utc: datetime
    authority_effect: Literal["NONE"] = "NONE"

    @field_validator("created_at_utc")
    @classmethod
    def time_is_aware(cls, value: datetime) -> datetime:
        return _utc(value, "created_at_utc")

    @model_validator(mode="after")
    def candidate_is_bounded_and_canonical(self) -> BoundedCognitionCandidate:
        if len(self.required_capabilities) != len(set(self.required_capabilities)):
            raise ValueError("candidate capabilities must be unique")
        if len(self.authority_requirements) != len(set(self.authority_requirements)):
            raise ValueError("candidate authority requirements must be unique")
        admissible = (
            self.pi_b_decision is PiBDecision.ALLOW
            and self.hard_boundaries.holds
            and self.four_pillars.holds
        )
        if self.selection is CandidateSelection.SELECTED and not admissible:
            raise ValueError("selected candidate must be admissible")
        if self.selection is CandidateSelection.REJECTED and admissible:
            raise ValueError("admissible candidate cannot be marked rejected")
        if (
            self.irreversibility is CandidateIrreversibility.EXTERNAL_IRREVERSIBLE
            or self.cost.network_calls != 0
        ):
            raise ValueError("offline cognition candidate cannot require external effect")
        expected = canonical_sha256(self.material_fields())
        if self.candidate_hash != expected:
            raise ValueError("candidate_hash mismatch")
        if self.candidate_id != f"cognition_candidate_{expected}":
            raise ValueError("candidate_id mismatch")
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(
            mode="python", exclude={"candidate_id", "candidate_hash"}
        )


class CandidateAdmission(_Contract):
    schema_version: Literal["se6-cognition-candidate-admission-v1"] = (
        "se6-cognition-candidate-admission-v1"
    )
    admission_id: StrictStr = Field(pattern=_ADMISSION_ID)
    entity_id: StrictStr = Field(pattern=_ENTITY_ID)
    candidate_id: StrictStr = Field(min_length=1, max_length=512, pattern=_REFERENCE)
    candidate_hash: StrictStr = Field(pattern=_HASH)
    pi_b_decision: PiBDecision
    hard_boundaries: HardBoundaryAttestation
    four_pillars: FourPillarsAttestation
    admitted: StrictBool
    reason_codes: tuple[StrictStr, ...] = Field(default=(), max_length=32)
    evaluated_at_utc: datetime
    authority_effect: Literal["NONE"] = "NONE"

    @field_validator("evaluated_at_utc")
    @classmethod
    def time_is_aware(cls, value: datetime) -> datetime:
        return _utc(value, "evaluated_at_utc")

    @model_validator(mode="after")
    def admission_is_conjunctive_and_canonical(self) -> CandidateAdmission:
        expected_admitted = (
            self.pi_b_decision is PiBDecision.ALLOW
            and self.hard_boundaries.holds
            and self.four_pillars.holds
        )
        if self.admitted != expected_admitted:
            raise ValueError("candidate admission must be conjunctive")
        if self.admitted != (not self.reason_codes):
            raise ValueError("admission reason codes must match the decision")
        expected = canonical_sha256(self.material_fields())
        if self.admission_id != f"cognition_admission_{expected}":
            raise ValueError("admission_id must derive from admission material")
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"admission_id"})


def create_evidence_reference(
    *,
    entity_id: str,
    source_kind: EvidenceSourceKind,
    source_id: str,
    content_hash: str,
    observed_at_utc: datetime,
    independently_verified: bool,
    verification_reference: str | None,
) -> EvidenceReference:
    material = {
        "schema_version": "se6-cognition-evidence-v1",
        "entity_id": entity_id,
        "source_kind": source_kind,
        "source_id": source_id,
        "content_hash": content_hash,
        "observed_at_utc": _utc(observed_at_utc, "observed_at_utc"),
        "independently_verified": independently_verified,
        "verification_reference": verification_reference,
        "authority_effect": "NONE",
    }
    return EvidenceReference(
        evidence_id=f"cognition_evidence_{canonical_sha256(material)}", **material
    )


def create_memory_record(
    *,
    entity_id: str,
    identity_state_id: str,
    entity_state_id: str,
    subject: str,
    content_summary: str,
    status: MemoryStatus,
    confidence_basis_points: int,
    provenance: tuple[EvidenceReference, ...],
    evidence: tuple[EvidenceReference, ...],
    objective_ids: tuple[str, ...],
    recorded_at_utc: datetime,
    previous_memory_id: str | None = None,
    valid_until_utc: datetime | None = None,
    supersedes_memory_id: str | None = None,
    contradicted_by_evidence_id: str | None = None,
    revoked_by_authority_reference: str | None = None,
    transition_reason: str | None = None,
) -> DurableMemoryRecord:
    material = {
        "schema_version": "se6-cognition-memory-v1",
        "entity_id": entity_id,
        "identity_state_id": identity_state_id,
        "entity_state_id": entity_state_id,
        "previous_memory_id": previous_memory_id,
        "subject": subject,
        "content_summary": content_summary,
        "content_hash": canonical_sha256(
            {"subject": subject, "content_summary": content_summary}
        ),
        "status": status,
        "confidence_basis_points": confidence_basis_points,
        "provenance": provenance,
        "evidence": evidence,
        "objective_ids": objective_ids,
        "recorded_at_utc": _utc(recorded_at_utc, "recorded_at_utc"),
        "valid_until_utc": (
            _utc(valid_until_utc, "valid_until_utc")
            if valid_until_utc is not None
            else None
        ),
        "supersedes_memory_id": supersedes_memory_id,
        "contradicted_by_evidence_id": contradicted_by_evidence_id,
        "revoked_by_authority_reference": revoked_by_authority_reference,
        "transition_reason": transition_reason,
        "authority_effect": "NONE",
    }
    normalized = DurableMemoryRecord.model_construct(
        memory_id=f"cognition_memory_{'0' * 64}", **material
    ).material_fields()
    return DurableMemoryRecord(
        memory_id=f"cognition_memory_{canonical_sha256(normalized)}", **material
    )


def create_objective_record(**fields: Any) -> DurableObjectiveRecord:
    material = {
        "schema_version": "se6-cognition-objective-v1",
        "authority_effect": "NONE",
        **fields,
    }
    return DurableObjectiveRecord(
        objective_record_id=(
            f"cognition_objective_record_{canonical_sha256(material)}"
        ),
        **material,
    )


def create_attention_record(**fields: Any) -> DurableAttentionRecord:
    dimensions = fields["dimensions"]
    if not isinstance(dimensions, AttentionDimensions):
        raise TypeError("dimensions must be AttentionDimensions")
    material = {
        "schema_version": "se6-cognition-attention-v1",
        "score": sum(dimensions.model_dump(mode="python").values()) // 8,
        "authority_effect": "NONE",
        **fields,
    }
    normalized = DurableAttentionRecord.model_construct(
        attention_id=f"cognition_attention_{'0' * 64}", **material
    ).material_fields()
    return DurableAttentionRecord(
        attention_id=f"cognition_attention_{canonical_sha256(normalized)}",
        **material,
    )


def evaluate_candidate_admission(
    *,
    entity_id: str,
    candidate_id: str,
    candidate_hash: str,
    pi_b_decision: PiBDecision,
    hard_boundaries: HardBoundaryAttestation,
    four_pillars: FourPillarsAttestation,
    evaluated_at_utc: datetime,
) -> CandidateAdmission:
    reasons: list[str] = []
    if pi_b_decision is not PiBDecision.ALLOW:
        reasons.append(f"PI_B_{pi_b_decision.value}")
    for name, allowed in hard_boundaries.model_dump(mode="python").items():
        if not allowed:
            reasons.append(f"HARD_BOUNDARY_{name.upper()}")
    for name, holds in four_pillars.model_dump(mode="python").items():
        if not holds:
            reasons.append(f"FOUR_PILLARS_{name.upper()}")
    material = {
        "schema_version": "se6-cognition-candidate-admission-v1",
        "entity_id": entity_id,
        "candidate_id": candidate_id,
        "candidate_hash": candidate_hash,
        "pi_b_decision": pi_b_decision,
        "hard_boundaries": hard_boundaries,
        "four_pillars": four_pillars,
        "admitted": not reasons,
        "reason_codes": tuple(reasons),
        "evaluated_at_utc": _utc(evaluated_at_utc, "evaluated_at_utc"),
        "authority_effect": "NONE",
    }
    normalized = CandidateAdmission.model_construct(
        admission_id=f"cognition_admission_{'0' * 64}", **material
    ).material_fields()
    return CandidateAdmission(
        admission_id=f"cognition_admission_{canonical_sha256(normalized)}",
        **material,
    )


def create_bounded_cognition_candidate(**fields: Any) -> BoundedCognitionCandidate:
    material = {
        "schema_version": "se6-cognition-candidate-v1",
        "authority_effect": "NONE",
        **fields,
    }
    normalized = BoundedCognitionCandidate.model_construct(
        candidate_id=f"cognition_candidate_{'0' * 64}",
        candidate_hash="0" * 64,
        **material,
    ).material_fields()
    digest = canonical_sha256(normalized)
    return BoundedCognitionCandidate(
        candidate_id=f"cognition_candidate_{digest}",
        candidate_hash=digest,
        **material,
    )


def _utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


__all__ = [
    "ENTITY_COGNITION_CONTRACT_VERSION",
    "AttentionDimensions",
    "AttentionResourceEnvelope",
    "BoundedCognitionCandidate",
    "CandidateAdmission",
    "CandidateCost",
    "CandidateIrreversibility",
    "CandidateRisk",
    "CandidateSelection",
    "CapabilityType",
    "DurableAttentionRecord",
    "DurableMemoryRecord",
    "DurableObjectiveRecord",
    "EvidenceReference",
    "EvidenceSourceKind",
    "FourPillarsAttestation",
    "HardBoundaryAttestation",
    "MemoryStatus",
    "ObjectiveOrigin",
    "ObjectiveStatus",
    "PiBDecision",
    "create_attention_record",
    "create_bounded_cognition_candidate",
    "create_evidence_reference",
    "create_memory_record",
    "create_objective_record",
    "evaluate_candidate_admission",
]