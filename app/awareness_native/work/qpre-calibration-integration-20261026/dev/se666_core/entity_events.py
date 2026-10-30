"""Typed, non-secret events for the shadow SE6 three-loop architecture.

Events are immutable descriptions.  Publishing an event never grants
authority, executes an effect, verifies a claim, persists production state, or
changes identity.  The event bus in :mod:`se666_core.three_loop_entity` is
bounded and in-memory; persistence policies are descriptive requests for a
future authoritative store.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import Enum
from typing import (
    Annotated,
    Any,
    Literal,
)

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

from .canonical_contracts import BoundaryDecision, ExecutionStatus, canonical_sha256
from .epistemic_status import EpistemicStatus

EVENT_SCHEMA_VERSION = "se6-entity-event-v1"
_EVENT_ID_PATTERN = r"^entity_event_[0-9a-f]{64}$"
_REFERENCE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$"
_SECRET_LIKE_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{12,}=*\b", re.IGNORECASE),
    re.compile(
        r"\b(?:api[_ -]?key|password|passwd|private[_ -]?key|seed phrase|"
        r"access[_ -]?token|refresh[_ -]?token)\s*[:=]",
        re.IGNORECASE,
    ),
)


class LoopName(str, Enum):
    """The three computational rhythms plus non-loop event origins."""

    PRESENCE = "InteractivePresenceLoop"
    AWARENESS = "OperationalAwarenessLoop"
    BECOMING = "DevelopmentalAssimilationLoop"
    COORDINATOR = "COORDINATOR"
    EXTERNAL = "EXTERNAL"


class EventType(str, Enum):
    USER_MESSAGE = "UserMessageEvent"
    INTERACTION = "InteractionEvent"
    NOTIFICATION = "NotificationEvent"
    INTERRUPTION = "InterruptionEvent"
    OBSERVATION = "ObservationEvent"
    ENVIRONMENT_CHANGE = "EnvironmentChangeEvent"
    ATTENTION = "AttentionEvent"
    RELEVANCE = "RelevanceEvent"
    AWARENESS_UPDATE = "AwarenessUpdateEvent"
    PERSPECTIVE_REQUEST = "PerspectiveRequestEvent"
    CONTRADICTION = "ContradictionEvent"
    OBJECTIVE = "ObjectiveEvent"
    PROPOSAL = "ProposalEvent"
    CAPABILITY_REQUEST = "CapabilityRequestEvent"
    OWNER_AUTHORITY_REQUEST = "OwnerAuthorityRequestEvent"
    APPROVAL = "ApprovalEvent"
    EXECUTION = "ExecutionEvent"
    OBSERVED_CONSEQUENCE = "ObservedConsequenceEvent"
    VERIFICATION = "VerificationEvent"
    ASSIMILATION = "AssimilationEvent"
    MEMORY_CANDIDATE = "MemoryCandidateEvent"
    MEMORY_CONSOLIDATION = "MemoryConsolidationEvent"
    MEMORY_REVOCATION = "MemoryRevocationEvent"
    MEMORY_STALE = "MemoryStaleEvent"
    MEMORY_EXPIRED = "MemoryExpiredEvent"
    MEMORY_CONTRADICTED = "MemoryContradictedEvent"
    DEVELOPMENT_NEED = "DevelopmentNeedEvent"
    DEVELOPMENT_CANDIDATE = "DevelopmentCandidateEvent"
    GERMINATION_REQUEST = "GerminationRequestEvent"
    EMBODIMENT_REQUEST = "EmbodimentRequestEvent"
    LIFECYCLE = "LifecycleEvent"
    REST = "RestEvent"
    PAUSE = "PauseEvent"
    RESUME = "ResumeEvent"
    STOP = "StopEvent"
    RECOVERY = "RecoveryEvent"
    MODEL_TERMINAL_CHANGED = "ModelTerminalChangedEvent"
    LOCAL_EVENT_BUDGET_RENEWAL = "LocalEventBudgetRenewalEvent"
    INTERACTIVE_PROOF_CONTROL = "InteractiveProofControlEvent"


class EventSourceKind(str, Enum):
    SE6 = "SE6"
    PROGRAMMERONE = "PROGRAMMERONE"
    SYSTEM = "SYSTEM"
    COMPONENT = "COMPONENT"
    MODEL_TERMINAL = "MODEL_TERMINAL"
    EXTERNAL_SOURCE = "EXTERNAL_SOURCE"


class ObservationProvenance(str, Enum):
    SYSTEM_OBSERVED = "SYSTEM_OBSERVED"
    USER_REPORTED = "USER_REPORTED"
    MODEL_INFERRED = "MODEL_INFERRED"
    MODEL_PREDICTED = "MODEL_PREDICTED"
    EXTERNAL_RETRIEVED = "EXTERNAL_RETRIEVED"
    INDEPENDENTLY_VERIFIED = "INDEPENDENTLY_VERIFIED"
    CONTRADICTED = "CONTRADICTED"
    UNKNOWN = "UNKNOWN"


class AuthorityStatus(str, Enum):
    NOT_REQUIRED = "NOT_REQUIRED"
    NONE = "NONE"
    REQUIRED = "REQUIRED"
    REQUESTED = "REQUESTED"
    GRANTED_RECORDED = "GRANTED_RECORDED"
    DENIED_RECORDED = "DENIED_RECORDED"
    EXPIRED_RECORDED = "EXPIRED_RECORDED"
    CONSUMED_RECORDED = "CONSUMED_RECORDED"


class SensitivityClassification(str, Enum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    OWNER_PRIVATE_REDACTED = "OWNER_PRIVATE_REDACTED"
    SENSITIVE_REDACTED = "SENSITIVE_REDACTED"


class PersistencePolicy(str, Enum):
    EPHEMERAL = "EPHEMERAL"
    SESSION = "SESSION"
    DURABLE_CANDIDATE = "DURABLE_CANDIDATE"
    DURABLE_AUDIT = "DURABLE_AUDIT"


class InteractionKind(str, Enum):
    USER_MESSAGE = "USER_MESSAGE"
    RESPONSE_INTENT = "RESPONSE_INTENT"
    QUESTION_INTENT = "QUESTION_INTENT"
    ACKNOWLEDGEMENT_INTENT = "ACKNOWLEDGEMENT_INTENT"
    NOTIFICATION_INTENT = "NOTIFICATION_INTENT"
    EXPRESSION_INTERRUPTED = "EXPRESSION_INTERRUPTED"


class RelevanceOutcome(str, Enum):
    IGNORE = "IGNORE"
    EPHEMERAL = "EPHEMERAL"
    RECORD_PROVISIONALLY = "RECORD_PROVISIONALLY"
    MAP = "MAP"
    INVESTIGATE = "INVESTIGATE"
    NOTIFY = "NOTIFY"
    REQUEST_INFORMATION = "REQUEST_INFORMATION"
    REQUEST_AUTHORITY = "REQUEST_AUTHORITY"
    PROPOSE_ACTION = "PROPOSE_ACTION"


class ApprovalDisposition(str, Enum):
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class VerificationResult(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    INCONCLUSIVE = "INCONCLUSIVE"
    NOT_RUN = "NOT_RUN"


class MemoryEventOperation(str, Enum):
    CANDIDATE = "CANDIDATE"
    CONSOLIDATE = "CONSOLIDATE"
    SUPERSEDE = "SUPERSEDE"
    REVOKE = "REVOKE"
    MARK_STALE = "MARK_STALE"
    MARK_EXPIRED = "MARK_EXPIRED"
    MARK_CONTRADICTED = "MARK_CONTRADICTED"


class ObjectiveOperation(str, Enum):
    RECORD = "RECORD"
    BLOCK = "BLOCK"
    COMPLETE = "COMPLETE"
    WITHDRAW = "WITHDRAW"


class LifecycleSignal(str, Enum):
    STATE_REPORTED = "STATE_REPORTED"
    REST = "REST"
    PAUSE = "PAUSE"
    RESUME = "RESUME"
    STOP = "STOP"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    RECOVERED = "RECOVERED"


class EventEndpoint(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    kind: EventSourceKind
    identifier: StrictStr = Field(min_length=1, max_length=256)

    @field_validator("identifier")
    @classmethod
    def identifier_is_safe(cls, value: str) -> str:
        _reject_secret_like(value)
        return value


class InteractionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    payload_type: Literal["interaction"] = "interaction"
    interaction_kind: InteractionKind
    thread_id: StrictStr = Field(min_length=1, max_length=128)
    text: StrictStr = Field(min_length=1, max_length=4_000)
    basis_event_ids: tuple[StrictStr, ...] = Field(default=(), max_length=32)
    initiated_by_se6: StrictBool = False
    initiation_reason: StrictStr | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def proactive_intent_has_a_basis(self) -> InteractionPayload:
        if self.initiated_by_se6 and (
            not self.initiation_reason or not self.basis_event_ids
        ):
            raise ValueError("proactive interaction requires a reason and basis event")
        if not self.initiated_by_se6 and self.initiation_reason is not None:
            raise ValueError("non-proactive interaction cannot invent an initiation reason")
        return self


class ObservationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    payload_type: Literal["observation"] = "observation"
    world_node: StrictStr = Field(min_length=1, max_length=256)
    relation: StrictStr = Field(min_length=1, max_length=128)
    value_summary: StrictStr = Field(min_length=1, max_length=2_000)
    provenance: ObservationProvenance
    observed_at_utc: datetime
    evidence_references: tuple[StrictStr, ...] = Field(default=(), max_length=32)
    current_claim: StrictBool = True
    confidence_basis_points: StrictInt = Field(ge=0, le=10_000)

    @field_validator("observed_at_utc")
    @classmethod
    def time_is_aware(cls, value: datetime) -> datetime:
        return _utc(value, "observed_at_utc")

    @model_validator(mode="after")
    def verified_provenance_requires_evidence(self) -> ObservationPayload:
        if (
            self.provenance is ObservationProvenance.INDEPENDENTLY_VERIFIED
            and not self.evidence_references
        ):
            raise ValueError("independently verified observation requires evidence")
        return self


class RelevanceDimensions(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    objective: StrictInt = Field(ge=0, le=100)
    owner: StrictInt = Field(ge=0, le=100)
    urgency: StrictInt = Field(ge=0, le=100)
    novelty: StrictInt = Field(ge=0, le=100)
    contradiction: StrictInt = Field(ge=0, le=100)
    risk: StrictInt = Field(ge=0, le=100)
    consequence: StrictInt = Field(ge=0, le=100)
    temporal_sensitivity: StrictInt = Field(ge=0, le=100)
    confidence: StrictInt = Field(ge=0, le=100)
    recurrence: StrictInt = Field(ge=0, le=100)


class AttentionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    payload_type: Literal["attention"] = "attention"
    subject_event_id: StrictStr = Field(pattern=_EVENT_ID_PATTERN)
    dimensions: RelevanceDimensions
    score: StrictInt = Field(ge=0, le=100)
    outcome: RelevanceOutcome
    rationale_codes: tuple[StrictStr, ...] = Field(default=(), max_length=16)
    authority_effect: Literal["NONE"] = "NONE"


class AwarenessPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    payload_type: Literal["awareness"] = "awareness"
    previous_awareness_state_id: StrictStr = Field(
        pattern=r"^awareness_[0-9a-f]{64}$"
    )
    proposed_awareness_state_id: StrictStr = Field(
        pattern=r"^awareness_[0-9a-f]{64}$"
    )
    observation_event_ids: tuple[StrictStr, ...] = Field(default=(), max_length=32)
    contradiction_event_ids: tuple[StrictStr, ...] = Field(default=(), max_length=32)
    authority_effect: Literal["NONE"] = "NONE"


class ObjectivePayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    payload_type: Literal["objective"] = "objective"
    operation: ObjectiveOperation
    objective_id: StrictStr = Field(min_length=1, max_length=256)
    summary: StrictStr = Field(min_length=1, max_length=1_000)
    required_capabilities: tuple[StrictStr, ...] = Field(default=(), max_length=32)
    basis_event_ids: tuple[StrictStr, ...] = Field(default=(), max_length=32)
    authority_effect: Literal["NONE"] = "NONE"


class ProposalPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    payload_type: Literal["proposal"] = "proposal"
    proposal_kind: StrictStr = Field(min_length=1, max_length=128)
    summary: StrictStr = Field(min_length=1, max_length=2_000)
    requested_capability: StrictStr | None = Field(default=None, max_length=256)
    alternatives: tuple[StrictStr, ...] = Field(default=(), max_length=16)
    expected_benefit: StrictStr = Field(min_length=1, max_length=500)
    expected_cost: StrictStr = Field(min_length=1, max_length=500)
    risk: StrictStr = Field(min_length=1, max_length=500)
    verification_plan: tuple[StrictStr, ...] = Field(default=(), max_length=16)
    boundary_required: Literal[True] = True
    boundary_decision: BoundaryDecision = BoundaryDecision.PAUSE
    authority_effect: Literal["NONE"] = "NONE"

    @model_validator(mode="after")
    def proposal_cannot_self_authorize(self) -> ProposalPayload:
        if self.boundary_decision is BoundaryDecision.ALLOW:
            raise ValueError("a shadow proposal cannot grant itself ALLOW")
        return self


class AuthorityPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    payload_type: Literal["authority"] = "authority"
    capability: StrictStr = Field(min_length=1, max_length=256)
    scope: StrictStr = Field(min_length=1, max_length=1_000)
    reason: StrictStr = Field(min_length=1, max_length=1_000)
    alternatives: tuple[StrictStr, ...] = Field(default=(), max_length=16)
    risk: StrictStr = Field(min_length=1, max_length=500)
    expected_benefit: StrictStr = Field(min_length=1, max_length=500)
    expected_cost: StrictStr = Field(min_length=1, max_length=500)
    credential_requirement: Literal["NONE", "TERMINAL_ONLY", "EXTERNAL_BROKER"]
    recommended_choice: StrictStr = Field(min_length=1, max_length=500)
    authority_effect: Literal["NONE"] = "NONE"


class ApprovalPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    payload_type: Literal["approval"] = "approval"
    request_event_id: StrictStr = Field(pattern=_EVENT_ID_PATTERN)
    disposition: ApprovalDisposition
    decision_reason: StrictStr = Field(min_length=1, max_length=1_000)
    authoritative_receipt_reference: StrictStr | None = Field(
        default=None, max_length=256
    )
    authority_effect: Literal["NONE"] = "NONE"

    @model_validator(mode="after")
    def approval_is_only_a_record(self) -> ApprovalPayload:
        if (
            self.disposition is ApprovalDisposition.APPROVED
            and not self.authoritative_receipt_reference
        ):
            raise ValueError("recorded approval requires an authoritative receipt reference")
        return self


class ConsequencePayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    payload_type: Literal["consequence"] = "consequence"
    proposal_event_id: StrictStr = Field(pattern=_EVENT_ID_PATTERN)
    execution_status: ExecutionStatus
    expected_summary: StrictStr = Field(min_length=1, max_length=1_000)
    observed_summary: StrictStr | None = Field(default=None, max_length=1_000)
    receipt_references: tuple[StrictStr, ...] = Field(default=(), max_length=32)
    network_used: StrictBool = False
    production_effect: StrictBool = False

    @model_validator(mode="after")
    def execution_claim_requires_receipt(self) -> ConsequencePayload:
        if self.execution_status is not ExecutionStatus.NOT_EXECUTED and (
            not self.observed_summary or not self.receipt_references
        ):
            raise ValueError("an execution claim requires observation and receipt")
        return self


class VerificationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    payload_type: Literal["verification"] = "verification"
    subject_event_id: StrictStr = Field(pattern=_EVENT_ID_PATTERN)
    result: VerificationResult
    independently_verified: StrictBool
    evidence_references: tuple[StrictStr, ...] = Field(default=(), max_length=32)
    failure_class: StrictStr | None = Field(default=None, max_length=256)
    summary: StrictStr = Field(min_length=1, max_length=1_000)

    @model_validator(mode="after")
    def verification_claim_requires_evidence(self) -> VerificationPayload:
        if self.independently_verified and not self.evidence_references:
            raise ValueError("independent verification requires evidence")
        if self.result is VerificationResult.FAILED and not self.failure_class:
            raise ValueError("failed verification requires a failure class")
        return self


class MemoryPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    payload_type: Literal["memory"] = "memory"
    operation: MemoryEventOperation
    subject: StrictStr = Field(min_length=1, max_length=256)
    content_summary: StrictStr = Field(min_length=1, max_length=2_000)
    source_event_ids: tuple[StrictStr, ...] = Field(default=(), max_length=32)
    evidence_references: tuple[StrictStr, ...] = Field(default=(), max_length=32)
    supersedes_memory_id: StrictStr | None = Field(default=None, max_length=256)
    revokes_memory_id: StrictStr | None = Field(default=None, max_length=256)
    authority_effect: Literal["NONE"] = "NONE"

    @model_validator(mode="after")
    def operation_has_required_reference(self) -> MemoryPayload:
        if self.operation in {
            MemoryEventOperation.SUPERSEDE,
            MemoryEventOperation.MARK_STALE,
            MemoryEventOperation.MARK_EXPIRED,
            MemoryEventOperation.MARK_CONTRADICTED,
        } and not self.supersedes_memory_id:
            raise ValueError("memory transition requires supersedes_memory_id")
        if self.operation is MemoryEventOperation.REVOKE and not self.revokes_memory_id:
            raise ValueError("revocation requires revokes_memory_id")
        return self


class DevelopmentPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    payload_type: Literal["development"] = "development"
    need_kind: StrictStr = Field(min_length=1, max_length=128)
    pattern_key: StrictStr = Field(min_length=1, max_length=256)
    verified_occurrences: StrictInt = Field(ge=1)
    required_capability: StrictStr | None = Field(default=None, max_length=256)
    blocked_objective: StrictStr | None = Field(default=None, max_length=500)
    evidence_event_ids: tuple[StrictStr, ...] = Field(default=(), max_length=64)
    proposal_only: Literal[True] = True
    authority_effect: Literal["NONE"] = "NONE"


class LifecyclePayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    payload_type: Literal["lifecycle"] = "lifecycle"
    signal: LifecycleSignal
    prior_state: StrictStr = Field(min_length=1, max_length=128)
    projected_state: StrictStr = Field(min_length=1, max_length=128)
    reason: StrictStr = Field(min_length=1, max_length=1_000)
    controller_authoritative: StrictBool
    evidence_references: tuple[StrictStr, ...] = Field(default=(), max_length=32)


class ModelTerminalPayload(BaseModel):
    """Describes a replaceable cognition terminal, never an identity change."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    payload_type: Literal["model_terminal"] = "model_terminal"
    previous_terminal_id: StrictStr = Field(min_length=1, max_length=256)
    terminal_id: StrictStr = Field(min_length=1, max_length=256)
    provider: StrictStr = Field(min_length=1, max_length=128)
    model: StrictStr = Field(min_length=1, max_length=128)
    mode: Literal["DETERMINISTIC", "MODEL_TERMINAL"]
    authority_effect: Literal["NONE"] = "NONE"


class LocalEventBudgetRenewalPayload(BaseModel):
    """One attributable local-only grant, retained in the existing event ledger."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    payload_type: Literal["local_event_budget_renewal"] = "local_event_budget_renewal"
    generation: StrictInt = Field(ge=1, le=2**31 - 1)
    previous_consumed_total: StrictInt = Field(ge=0, le=2**63 - 1)
    previous_event_budget: StrictInt = Field(ge=1, le=2**63 - 257)
    additional_events: StrictInt = Field(ge=1, le=256)
    entity_id: StrictStr = Field(min_length=1, max_length=256)
    identity_state_id: StrictStr = Field(pattern=r"^identity_[0-9a-f]{64}$")
    loop_ids: tuple[StrictStr, StrictStr, StrictStr]
    owner_reference: StrictStr = Field(min_length=1, max_length=256)
    request_id: StrictStr = Field(pattern=r"^entity_request_[0-9a-f]{64}$")
    reason: StrictStr = Field(min_length=1, max_length=500)
    policy_source: Literal["OWNER_AUTHENTICATED_STEP_UP"] = "OWNER_AUTHENTICATED_STEP_UP"
    scope: Literal["LOCAL_ENTITY_PROCESSING_EVENTS"] = "LOCAL_ENTITY_PROCESSING_EVENTS"
    external_authority_effect: Literal["NONE"] = "NONE"

    @model_validator(mode="after")
    def exact_loops_and_reason(self) -> LocalEventBudgetRenewalPayload:
        if len(set(self.loop_ids)) != 3 or any(not re.fullmatch(r"se6_loop_[0-9a-f]{64}", item) for item in self.loop_ids):
            raise ValueError("local renewal requires the exact three loop bindings")
        if not self.reason.strip():
            raise ValueError("local renewal requires a reason")
        return self


class InteractiveProofPayload(BaseModel):
    """Non-secret, exact-scope control material; never ordinary queued ingress."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    payload_type: Literal["interactive_proof"] = "interactive_proof"
    operation: Literal[
        "RESERVE",
        "STEP",
        "COMPLETE",
        "FAIL",
        "REVOKE",
        "RECOVERY_AUTHORIZE",
        "RECOVERY_FAIL",
    ]
    proof_run_id: StrictStr = Field(pattern=r"^interactive_proof_[0-9a-f]{32}$")
    entity_id: StrictStr
    identity_state_id: StrictStr
    contract_sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    owner_reference: StrictStr
    session_binding_hash: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    expected_consumed: StrictInt = Field(ge=0, le=14)
    max_events: Literal[14] = 14


EventPayload = Annotated[
    InteractionPayload | ObservationPayload | AttentionPayload | AwarenessPayload | ObjectivePayload | ProposalPayload | AuthorityPayload | ApprovalPayload | ConsequencePayload | VerificationPayload | MemoryPayload | DevelopmentPayload | LifecyclePayload | ModelTerminalPayload | LocalEventBudgetRenewalPayload | InteractiveProofPayload,
    Field(discriminator="payload_type"),
]


_EVENT_PAYLOAD_TYPES: Mapping[EventType, str] = {
    EventType.USER_MESSAGE: "interaction",
    EventType.INTERACTION: "interaction",
    EventType.NOTIFICATION: "interaction",
    EventType.INTERRUPTION: "interaction",
    EventType.OBSERVATION: "observation",
    EventType.ENVIRONMENT_CHANGE: "observation",
    EventType.ATTENTION: "attention",
    EventType.RELEVANCE: "attention",
    EventType.AWARENESS_UPDATE: "awareness",
    EventType.PERSPECTIVE_REQUEST: "awareness",
    EventType.CONTRADICTION: "observation",
    EventType.OBJECTIVE: "objective",
    EventType.PROPOSAL: "proposal",
    EventType.DEVELOPMENT_CANDIDATE: "proposal",
    EventType.GERMINATION_REQUEST: "proposal",
    EventType.EMBODIMENT_REQUEST: "proposal",
    EventType.CAPABILITY_REQUEST: "authority",
    EventType.OWNER_AUTHORITY_REQUEST: "authority",
    EventType.APPROVAL: "approval",
    EventType.EXECUTION: "consequence",
    EventType.OBSERVED_CONSEQUENCE: "consequence",
    EventType.VERIFICATION: "verification",
    EventType.ASSIMILATION: "memory",
    EventType.MEMORY_CANDIDATE: "memory",
    EventType.MEMORY_CONSOLIDATION: "memory",
    EventType.MEMORY_REVOCATION: "memory",
    EventType.MEMORY_STALE: "memory",
    EventType.MEMORY_EXPIRED: "memory",
    EventType.MEMORY_CONTRADICTED: "memory",
    EventType.DEVELOPMENT_NEED: "development",
    EventType.LIFECYCLE: "lifecycle",
    EventType.REST: "lifecycle",
    EventType.PAUSE: "lifecycle",
    EventType.RESUME: "lifecycle",
    EventType.STOP: "lifecycle",
    EventType.RECOVERY: "lifecycle",
    EventType.MODEL_TERMINAL_CHANGED: "model_terminal",
    EventType.LOCAL_EVENT_BUDGET_RENEWAL: "local_event_budget_renewal",
    EventType.INTERACTIVE_PROOF_CONTROL: "interactive_proof",
}


class EntityEventDraft(BaseModel):
    """A queued event before the coordinator assigns a sequence and ID."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    event_type: EventType
    occurred_at_utc: datetime
    originating_loop: LoopName
    source: EventEndpoint
    target: EventEndpoint
    relation: StrictStr = Field(min_length=1, max_length=128)
    provenance: ObservationProvenance
    epistemic_status: EpistemicStatus
    authority_status: AuthorityStatus
    correlation_id: StrictStr = Field(min_length=1, max_length=256)
    causal_id: StrictStr | None = Field(default=None, max_length=256)
    parent_event_id: StrictStr | None = Field(default=None, pattern=_EVENT_ID_PATTERN)
    sensitivity: SensitivityClassification = SensitivityClassification.INTERNAL
    persistence_policy: PersistencePolicy = PersistencePolicy.SESSION
    payload: EventPayload

    @field_validator("occurred_at_utc")
    @classmethod
    def occurred_at_is_aware(cls, value: datetime) -> datetime:
        return _utc(value, "occurred_at_utc")

    @model_validator(mode="after")
    def event_semantics_are_consistent(self) -> EntityEventDraft:
        _validate_payload_type(self.event_type, self.payload)
        _validate_epistemic_semantics(self.provenance, self.epistemic_status)
        _reject_secrets_in_value(self.model_dump(mode="python"))
        return self


class EntityEvent(BaseModel):
    """A sequenced, content-addressed event with no direct authority effect."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["se6-entity-event-v1"] = EVENT_SCHEMA_VERSION
    event_id: StrictStr = Field(pattern=_EVENT_ID_PATTERN)
    sequence: StrictInt = Field(ge=1)
    event_type: EventType
    occurred_at_utc: datetime
    originating_loop: LoopName
    source: EventEndpoint
    target: EventEndpoint
    relation: StrictStr = Field(min_length=1, max_length=128)
    provenance: ObservationProvenance
    epistemic_status: EpistemicStatus
    authority_status: AuthorityStatus
    correlation_id: StrictStr = Field(min_length=1, max_length=256)
    causal_id: StrictStr | None = Field(default=None, max_length=256)
    parent_event_id: StrictStr | None = Field(default=None, pattern=_EVENT_ID_PATTERN)
    sensitivity: SensitivityClassification
    persistence_policy: PersistencePolicy
    payload: EventPayload
    authority_effect: Literal["NONE"] = "NONE"

    @field_validator("occurred_at_utc")
    @classmethod
    def occurred_at_is_aware(cls, value: datetime) -> datetime:
        return _utc(value, "occurred_at_utc")

    @model_validator(mode="after")
    def event_is_canonical_and_non_authorizing(self) -> EntityEvent:
        _validate_payload_type(self.event_type, self.payload)
        _validate_epistemic_semantics(self.provenance, self.epistemic_status)
        _reject_secrets_in_value(self.material_fields())
        expected = canonical_sha256(self.material_fields())
        if self.event_id != f"entity_event_{expected}":
            raise ValueError("event_id must derive from event material")
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(
            mode="python", exclude={"event_id", "authority_effect"}
        )


def create_entity_event(*, sequence: int, draft: EntityEventDraft) -> EntityEvent:
    material = {
        "schema_version": EVENT_SCHEMA_VERSION,
        "sequence": sequence,
        **draft.model_dump(mode="python"),
    }
    digest = canonical_sha256(material)
    return EntityEvent(
        event_id=f"entity_event_{digest}",
        authority_effect="NONE",
        **material,
    )


def _utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _reject_secret_like(value: str) -> None:
    if any(pattern.search(value) for pattern in _SECRET_LIKE_PATTERNS):
        raise ValueError("secret-like material is prohibited in entity events")


def _reject_secrets_in_value(value: Any) -> None:
    if isinstance(value, str):
        _reject_secret_like(value)
        return
    if isinstance(value, Mapping):
        for item in value.values():
            _reject_secrets_in_value(item)
        return
    if isinstance(value, (tuple, list, set, frozenset)):
        for item in value:
            _reject_secrets_in_value(item)


def _validate_payload_type(event_type: EventType, payload: EventPayload) -> None:
    expected = _EVENT_PAYLOAD_TYPES[event_type]
    if payload.payload_type != expected:
        raise ValueError(
            f"{event_type.value} requires the {expected} payload contract"
        )


def _validate_epistemic_semantics(
    provenance: ObservationProvenance, status: EpistemicStatus
) -> None:
    if provenance is ObservationProvenance.USER_REPORTED and status not in {
        EpistemicStatus.USER_SUPPLIED,
        EpistemicStatus.UNKNOWN,
    }:
        raise ValueError("USER_REPORTED material cannot be promoted beyond USER_SUPPLIED")
    if provenance is ObservationProvenance.MODEL_INFERRED and status not in {
        EpistemicStatus.INFERRED,
        EpistemicStatus.MODEL_PROPOSED,
        EpistemicStatus.UNKNOWN,
    }:
        raise ValueError("MODEL_INFERRED material cannot be treated as observed or verified")
    if provenance is ObservationProvenance.MODEL_PREDICTED and status not in {
        EpistemicStatus.MODEL_PROPOSED,
        EpistemicStatus.INFERRED,
        EpistemicStatus.UNKNOWN,
    }:
        raise ValueError("MODEL_PREDICTED material cannot be treated as observed or verified")
    if status is EpistemicStatus.VERIFIED and provenance is not ObservationProvenance.INDEPENDENTLY_VERIFIED:
        raise ValueError("VERIFIED status requires independently verified provenance")


__all__ = [
    "ApprovalDisposition",
    "ApprovalPayload",
    "AttentionPayload",
    "AuthorityPayload",
    "AuthorityStatus",
    "AwarenessPayload",
    "ConsequencePayload",
    "DevelopmentPayload",
    "EntityEvent",
    "EntityEventDraft",
    "EventEndpoint",
    "EventPayload",
    "EventSourceKind",
    "EventType",
    "InteractionKind",
    "InteractionPayload",
    "LifecyclePayload",
    "LifecycleSignal",
    "LoopName",
    "MemoryEventOperation",
    "MemoryPayload",
    "ModelTerminalPayload",
    "ObjectiveOperation",
    "ObjectivePayload",
    "ObservationPayload",
    "ObservationProvenance",
    "PersistencePolicy",
    "ProposalPayload",
    "RelevanceDimensions",
    "RelevanceOutcome",
    "SensitivityClassification",
    "VerificationPayload",
    "VerificationResult",
    "create_entity_event",
]
