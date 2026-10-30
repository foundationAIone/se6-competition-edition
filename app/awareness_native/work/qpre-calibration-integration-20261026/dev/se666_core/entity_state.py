"""One immutable state aggregate for the SE6 three-loop entity architecture.

The contract composes references to the existing production identity and
operational-awareness contracts.  It is deliberately not a production store,
not a second IdentityState, and not an authority source.  A single monotonic
version and content-addressed predecessor chain provide compare-and-swap
semantics.  The default remains SHADOW; the stricter LOCAL_LIVE mode is valid
only when independently supplied runtime and activation evidence is present.
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
from .embodiment_lifecycle import LifecycleState
from .entity_events import AuthorityStatus, LoopName, RelevanceOutcome
from .epistemic_status import EpistemicStatus, EpistemicValue, UncertaintyRecord
from .operational_awareness import OperationalAwarenessState

ENTITY_STATE_SCHEMA_VERSION = "se6-three-loop-entity-state-v1"
LIVE_ENTITY_STATE_SCHEMA_VERSION = "se6-local-entity-state-v1"
_ENTITY_STATE_ID = r"^entity_state_[0-9a-f]{64}$"
_EVENT_ID = r"^entity_event_[0-9a-f]{64}$"
_HASH = r"^[0-9a-f]{64}$"


class PresenceLoopStatus(str, Enum):
    LISTENING = "LISTENING"
    INTERPRETING = "INTERPRETING"
    RESPONDING = "RESPONDING"
    INTERRUPTED = "INTERRUPTED"
    WAITING = "WAITING"
    NOTIFYING = "NOTIFYING"
    RESTING = "RESTING"


class AwarenessLoopStatus(str, Enum):
    OBSERVING = "OBSERVING"
    MAPPING = "MAPPING"
    REFLECTING = "REFLECTING"
    ASSESSING = "ASSESSING"
    CONTRADICTION_DETECTED = "CONTRADICTION_DETECTED"
    AWAITING_EVIDENCE = "AWAITING_EVIDENCE"
    RESTING = "RESTING"


class BecomingLoopStatus(str, Enum):
    REVIEWING = "REVIEWING"
    CONSOLIDATING = "CONSOLIDATING"
    PATTERN_ANALYSIS = "PATTERN_ANALYSIS"
    GAP_ANALYSIS = "GAP_ANALYSIS"
    PROPOSING_DEVELOPMENT = "PROPOSING_DEVELOPMENT"
    AWAITING_AUTHORITY = "AWAITING_AUTHORITY"
    TESTING_CANDIDATE = "TESTING_CANDIDATE"
    VERIFYING = "VERIFYING"
    RESTING = "RESTING"


class MemoryStatus(str, Enum):
    EPHEMERAL = "EPHEMERAL"
    PROVISIONAL = "PROVISIONAL"
    VERIFIED = "VERIFIED"
    DURABLE = "DURABLE"
    STALE = "STALE"
    EXPIRED = "EXPIRED"
    CONTRADICTED = "CONTRADICTED"
    REVOKED = "REVOKED"


class ProposalStatus(str, Enum):
    PROPOSED = "PROPOSED"
    AWAITING_BOUNDARY = "AWAITING_BOUNDARY"
    AWAITING_OWNER = "AWAITING_OWNER"
    DENIED = "DENIED"
    WITHDRAWN = "WITHDRAWN"


class ControllerStatus(str, Enum):
    ACTIVE = "ACTIVE"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    ABSENT = "ABSENT"
    UNKNOWN = "UNKNOWN"


class OperationalConnectionState(str, Enum):
    CONNECTED = "CONNECTED"
    DISCONNECTED_SAFE = "DISCONNECTED_SAFE"
    DORMANT = "DORMANT"
    UNKNOWN = "UNKNOWN"


class EmergencyStopState(str, Enum):
    ARMED = "ARMED"
    TRIGGERED = "TRIGGERED"
    UNKNOWN = "UNKNOWN"


class EntityOperatingMode(str, Enum):
    SHADOW = "SHADOW"
    LOCAL_LIVE = "LOCAL_LIVE"


class EntityIdentityReference(BaseModel):
    """Reference to the one existing identity; never a replacement identity."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    instance_id: StrictStr = Field(min_length=1, max_length=256)
    identity_state_id: StrictStr = Field(pattern=r"^identity_[0-9a-f]{64}$")
    identity_state_hash: StrictStr = Field(pattern=_HASH)
    constitution_version: StrictStr = Field(min_length=1, max_length=256)
    constitution_hash: StrictStr = Field(pattern=_HASH)
    owner_identity_reference: StrictStr = Field(min_length=1, max_length=256)
    identity_lineage: tuple[StrictStr, ...] = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def lineage_has_one_current_head(self) -> EntityIdentityReference:
        if self.identity_lineage[-1] != self.identity_state_id:
            raise ValueError("identity lineage must end at the referenced IdentityState")
        if len(set(self.identity_lineage)) != len(self.identity_lineage):
            raise ValueError("identity lineage cannot contain duplicate states")
        return self


class LifecycleView(BaseModel):
    """Truthfully separates durable lifecycle from live controller authority."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    durable_state: LifecycleState
    operational_state: OperationalConnectionState
    controller_status: ControllerStatus
    controller_authoritative: StrictBool
    emergency_stop: EmergencyStopState
    observed_at_utc: datetime
    evidence_references: tuple[StrictStr, ...] = Field(default=(), max_length=32)

    @field_validator("observed_at_utc")
    @classmethod
    def time_is_aware(cls, value: datetime) -> datetime:
        return _utc(value, "observed_at_utc")

    @model_validator(mode="after")
    def live_projection_is_fail_closed(self) -> LifecycleView:
        if self.controller_authoritative:
            if self.controller_status is not ControllerStatus.ACTIVE:
                raise ValueError("authoritative controller must be ACTIVE")
            if self.operational_state is not OperationalConnectionState.CONNECTED:
                raise ValueError("authoritative controller must project CONNECTED")
        elif self.operational_state is OperationalConnectionState.CONNECTED:
            raise ValueError("CONNECTED requires an authoritative live controller")
        if (
            self.controller_status is ControllerStatus.RECOVERY_REQUIRED
            and self.operational_state
            is not OperationalConnectionState.DISCONNECTED_SAFE
        ):
            raise ValueError("recovery-required controller must fail closed")
        if self.emergency_stop is EmergencyStopState.UNKNOWN and self.controller_authoritative:
            raise ValueError("unknown emergency-stop state cannot support live authority")
        return self


class EnvironmentAccessState(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    online_observation_enabled: StrictBool = False
    network_authority: Literal["NONE", "SCOPED_APPROVAL"] = "NONE"
    external_requests: Literal["BLOCKED", "SCOPED"] = "BLOCKED"
    authority_references: tuple[StrictStr, ...] = Field(default=(), max_length=16)

    @model_validator(mode="after")
    def network_state_requires_exact_authority(self) -> EnvironmentAccessState:
        if self.online_observation_enabled:
            if (
                self.network_authority != "SCOPED_APPROVAL"
                or self.external_requests != "SCOPED"
                or not self.authority_references
            ):
                raise ValueError("online observation requires scoped authority evidence")
        elif (
            self.network_authority != "NONE"
            or self.external_requests != "BLOCKED"
            or self.authority_references
        ):
            raise ValueError("disabled online observation must carry no network authority")
        return self


class LoopRuntimeState(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    loop: LoopName
    mode: Literal["SHADOW", "LOCAL_LIVE"] = "SHADOW"
    status: StrictStr = Field(min_length=1, max_length=64)
    active_event_id: StrictStr | None = Field(default=None, pattern=_EVENT_ID)
    last_event_id: StrictStr | None = Field(default=None, pattern=_EVENT_ID)
    last_transition_at_utc: datetime
    work_units_consumed: StrictInt = Field(default=0, ge=0)
    wake_count: StrictInt = Field(default=0, ge=0)
    authority_effect: Literal["NONE"] = "NONE"

    @field_validator("last_transition_at_utc")
    @classmethod
    def time_is_aware(cls, value: datetime) -> datetime:
        return _utc(value, "last_transition_at_utc")

    @model_validator(mode="after")
    def status_belongs_to_loop(self) -> LoopRuntimeState:
        allowed = {
            LoopName.PRESENCE: {item.value for item in PresenceLoopStatus},
            LoopName.AWARENESS: {item.value for item in AwarenessLoopStatus},
            LoopName.BECOMING: {item.value for item in BecomingLoopStatus},
        }
        if self.loop not in allowed:
            raise ValueError("only the three cognitive loops have runtime state")
        if self.status not in allowed[self.loop]:
            raise ValueError("loop status does not belong to the declared loop")
        quiet = {
            PresenceLoopStatus.LISTENING.value,
            PresenceLoopStatus.WAITING.value,
            PresenceLoopStatus.RESTING.value,
            AwarenessLoopStatus.OBSERVING.value,
            AwarenessLoopStatus.AWAITING_EVIDENCE.value,
            AwarenessLoopStatus.RESTING.value,
            BecomingLoopStatus.AWAITING_AUTHORITY.value,
            BecomingLoopStatus.RESTING.value,
        }
        if self.status in quiet and self.active_event_id is not None:
            raise ValueError("quiet loop states cannot claim an active event")
        return self


class LoopStateBundle(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    presence: LoopRuntimeState
    awareness: LoopRuntimeState
    becoming: LoopRuntimeState

    @model_validator(mode="after")
    def exact_three_loops(self) -> LoopStateBundle:
        if self.presence.loop is not LoopName.PRESENCE:
            raise ValueError("presence slot must contain InteractivePresenceLoop")
        if self.awareness.loop is not LoopName.AWARENESS:
            raise ValueError("awareness slot must contain OperationalAwarenessLoop")
        if self.becoming.loop is not LoopName.BECOMING:
            raise ValueError("becoming slot must contain DevelopmentalAssimilationLoop")
        return self


class ConversationCommitment(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    commitment_id: StrictStr = Field(min_length=1, max_length=256)
    summary: StrictStr = Field(min_length=1, max_length=1_000)
    source_event_id: StrictStr = Field(pattern=_EVENT_ID)
    status: Literal["OPEN", "FULFILLED", "WITHDRAWN"]


def _unknown_summary() -> EpistemicValue[StrictStr]:
    return EpistemicValue[StrictStr](
        status=EpistemicStatus.UNKNOWN,
        value=None,
        confidence=0.0,
    )


class ConversationState(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    current_thread_id: StrictStr = Field(min_length=1, max_length=128)
    last_interaction_event_id: StrictStr | None = Field(default=None, pattern=_EVENT_ID)
    unresolved_questions: tuple[StrictStr, ...] = Field(default=(), max_length=32)
    commitments: tuple[ConversationCommitment, ...] = Field(default=(), max_length=32)
    owner_decision_event_ids: tuple[StrictStr, ...] = Field(default=(), max_length=64)
    pending_follow_up: tuple[StrictStr, ...] = Field(default=(), max_length=32)
    durable_summary: EpistemicValue[StrictStr] = Field(default_factory=_unknown_summary)
    recent_event_ids: tuple[StrictStr, ...] = Field(default=(), max_length=64)


class EntityObjective(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    objective_id: StrictStr = Field(min_length=1, max_length=256)
    summary: StrictStr = Field(min_length=1, max_length=1_000)
    status: Literal["ACTIVE", "BLOCKED", "COMPLETED", "WITHDRAWN"]
    source_event_id: StrictStr | None = Field(default=None, pattern=_EVENT_ID)
    required_capabilities: tuple[StrictStr, ...] = Field(default=(), max_length=32)


class WorldRelation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    relation_id: StrictStr = Field(pattern=r"^world_relation_[0-9a-f]{64}$")
    self_node: Literal["SE6"] = "SE6"
    world_node: StrictStr = Field(min_length=1, max_length=256)
    relation: StrictStr = Field(min_length=1, max_length=128)
    value_summary: StrictStr = Field(min_length=1, max_length=2_000)
    epistemic_status: EpistemicStatus
    source_event_id: StrictStr = Field(pattern=_EVENT_ID)
    evidence_references: tuple[StrictStr, ...] = Field(default=(), max_length=32)
    observed_at_utc: datetime
    current: StrictBool
    superseded_by: StrictStr | None = Field(
        default=None, pattern=r"^world_relation_[0-9a-f]{64}$"
    )

    @field_validator("observed_at_utc")
    @classmethod
    def time_is_aware(cls, value: datetime) -> datetime:
        return _utc(value, "observed_at_utc")

    @model_validator(mode="after")
    def relation_is_canonical(self) -> WorldRelation:
        if self.epistemic_status is EpistemicStatus.VERIFIED and not self.evidence_references:
            raise ValueError("verified world relation requires evidence")
        if self.current and self.superseded_by is not None:
            raise ValueError("a current relation cannot already be superseded")
        expected = canonical_sha256(self.material_fields())
        if self.relation_id != f"world_relation_{expected}":
            raise ValueError("relation_id must derive from relation material")
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"relation_id"})


class EnvironmentState(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    relations: tuple[WorldRelation, ...] = Field(default=(), max_length=512)
    observation_event_ids: tuple[StrictStr, ...] = Field(default=(), max_length=1_024)
    contradiction_event_ids: tuple[StrictStr, ...] = Field(default=(), max_length=256)

    @model_validator(mode="after")
    def only_one_current_relation_per_key(self) -> EnvironmentState:
        keys = [
            (item.world_node, item.relation)
            for item in self.relations
            if item.current
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("environment can have only one current relation per key")
        return self


class AttentionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    subject_event_id: StrictStr = Field(pattern=_EVENT_ID)
    score: StrictInt = Field(ge=0, le=100)
    outcome: RelevanceOutcome
    rationale_codes: tuple[StrictStr, ...] = Field(default=(), max_length=16)


class AttentionState(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    records: tuple[AttentionRecord, ...] = Field(default=(), max_length=256)
    current_focus_event_ids: tuple[StrictStr, ...] = Field(default=(), max_length=16)


class CapabilityView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    capability: StrictStr = Field(min_length=1, max_length=256)
    available: StrictBool
    authority_status: AuthorityStatus
    evidence_references: tuple[StrictStr, ...] = Field(default=(), max_length=16)

    @model_validator(mode="after")
    def capability_is_not_authority(self) -> CapabilityView:
        if not self.available and self.authority_status in {
            AuthorityStatus.GRANTED_RECORDED,
            AuthorityStatus.CONSUMED_RECORDED,
        }:
            raise ValueError("unavailable capability cannot carry recorded authority")
        return self


class CapabilityState(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    capabilities: tuple[CapabilityView, ...] = Field(default=(), max_length=256)

    @model_validator(mode="after")
    def capability_names_are_unique(self) -> CapabilityState:
        names = tuple(item.capability for item in self.capabilities)
        if len(names) != len(set(names)):
            raise ValueError("capabilities must be unique")
        return self


class AuthorityState(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    owner_identity_reference: StrictStr = Field(min_length=1, max_length=256)
    pending_request_event_ids: tuple[StrictStr, ...] = Field(default=(), max_length=64)
    decision_event_ids: tuple[StrictStr, ...] = Field(default=(), max_length=128)
    master_boundary_required: Literal[True] = True
    loops_may_grant_authority: Literal[False] = False


class MemoryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    memory_id: StrictStr = Field(pattern=r"^entity_memory_[0-9a-f]{64}$")
    subject: StrictStr = Field(min_length=1, max_length=256)
    content_summary: StrictStr = Field(min_length=1, max_length=2_000)
    status: MemoryStatus
    epistemic_status: EpistemicStatus
    source_event_ids: tuple[StrictStr, ...] = Field(min_length=1, max_length=64)
    evidence_references: tuple[StrictStr, ...] = Field(default=(), max_length=32)
    recorded_at_utc: datetime
    valid_until_utc: datetime | None = None
    current: StrictBool
    supersedes_memory_id: StrictStr | None = Field(
        default=None, pattern=r"^entity_memory_[0-9a-f]{64}$"
    )
    revoked_by_event_id: StrictStr | None = Field(default=None, pattern=_EVENT_ID)

    @field_validator("recorded_at_utc", "valid_until_utc")
    @classmethod
    def time_is_aware(cls, value: datetime | None) -> datetime | None:
        return _utc(value, "memory timestamp") if value is not None else None

    @model_validator(mode="after")
    def memory_semantics_are_safe(self) -> MemoryRecord:
        if self.status in {MemoryStatus.VERIFIED, MemoryStatus.DURABLE} and (
            self.epistemic_status is not EpistemicStatus.VERIFIED
            or not self.evidence_references
        ):
            raise ValueError("verified memory requires independently verified evidence")
        if self.status in {
            MemoryStatus.STALE,
            MemoryStatus.EXPIRED,
            MemoryStatus.CONTRADICTED,
            MemoryStatus.REVOKED,
        } and self.current:
            raise ValueError("inactive memory status cannot remain current truth")
        if self.status is MemoryStatus.REVOKED and not self.revoked_by_event_id:
            raise ValueError("revoked memory requires an attributable event")
        if self.valid_until_utc is not None and self.valid_until_utc < self.recorded_at_utc:
            raise ValueError("memory validity cannot end before it is recorded")
        expected = canonical_sha256(self.material_fields())
        if self.memory_id != f"entity_memory_{expected}":
            raise ValueError("memory_id must derive from memory material")
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"memory_id"})


class EntityMemoryState(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    records: tuple[MemoryRecord, ...] = Field(default=(), max_length=2_048)

    @property
    def active_records(self) -> tuple[MemoryRecord, ...]:
        superseded = {
            item.supersedes_memory_id
            for item in self.records
            if item.supersedes_memory_id is not None
        }
        return tuple(
            item
            for item in self.records
            if item.current and item.memory_id not in superseded
        )

    def active_at(self, timestamp: datetime) -> tuple[MemoryRecord, ...]:
        """Return the active truth projection at an explicit caller time."""

        instant = _utc(timestamp, "memory projection timestamp")
        return tuple(
            item
            for item in self.active_records
            if item.valid_until_utc is None or item.valid_until_utc >= instant
        )


class FailurePattern(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    pattern_key: StrictStr = Field(min_length=1, max_length=256)
    verified_event_ids: tuple[StrictStr, ...] = Field(min_length=1, max_length=128)
    occurrence_count: StrictInt = Field(ge=1)

    @model_validator(mode="after")
    def count_matches_evidence(self) -> FailurePattern:
        if self.occurrence_count != len(self.verified_event_ids):
            raise ValueError("failure occurrence count must match verified events")
        if len(set(self.verified_event_ids)) != len(self.verified_event_ids):
            raise ValueError("failure events must be unique")
        return self


class DevelopmentNeed(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    need_id: StrictStr = Field(pattern=r"^development_need_[0-9a-f]{64}$")
    need_kind: StrictStr = Field(min_length=1, max_length=128)
    summary: StrictStr = Field(min_length=1, max_length=1_000)
    pattern_key: StrictStr = Field(min_length=1, max_length=256)
    verified_evidence_event_ids: tuple[StrictStr, ...] = Field(min_length=2, max_length=128)
    required_capability: StrictStr | None = Field(default=None, max_length=256)
    alternatives: tuple[StrictStr, ...] = Field(default=(), max_length=16)
    expected_benefit: StrictStr = Field(min_length=1, max_length=500)
    expected_cost: StrictStr = Field(min_length=1, max_length=500)
    risk: StrictStr = Field(min_length=1, max_length=500)
    authority_status: AuthorityStatus
    proposal_only: Literal[True] = True

    @model_validator(mode="after")
    def need_is_content_addressed(self) -> DevelopmentNeed:
        expected = canonical_sha256(self.material_fields())
        if self.need_id != f"development_need_{expected}":
            raise ValueError("need_id must derive from development need material")
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"need_id"})


class DevelopmentalState(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    failure_patterns: tuple[FailurePattern, ...] = Field(default=(), max_length=256)
    development_needs: tuple[DevelopmentNeed, ...] = Field(default=(), max_length=256)
    candidate_event_ids: tuple[StrictStr, ...] = Field(default=(), max_length=256)
    denied_request_event_ids: tuple[StrictStr, ...] = Field(default=(), max_length=256)


class PendingProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    proposal_event_id: StrictStr = Field(pattern=_EVENT_ID)
    status: ProposalStatus
    requested_capability: StrictStr | None = Field(default=None, max_length=256)
    requires_master_boundary: Literal[True] = True
    production_effect_authorized: Literal[False] = False


class SharedMetabolismSnapshot(BaseModel):
    """A non-schedulable reference to LIVE LOOP, not a fourth cognitive loop."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    role: Literal["SHARED_METABOLISM"] = "SHARED_METABOLISM"
    stage: StrictStr = Field(min_length=1, max_length=128)
    transaction_id: StrictStr | None = Field(default=None, max_length=256)
    pending_approval: StrictBool = False
    verified_outcome_event_ids: tuple[StrictStr, ...] = Field(default=(), max_length=128)
    projection_reference: StrictStr | None = Field(default=None, max_length=256)
    is_loop: Literal[False] = False
    schedulable: Literal[False] = False
    authority_effect: Literal["NONE"] = "NONE"


class ResourceAccountingState(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    token_budget: StrictInt = Field(ge=0)
    model_call_budget: StrictInt = Field(ge=0)
    event_budget: StrictInt = Field(ge=1)
    tool_call_budget: StrictInt = Field(ge=0)
    network_call_budget: StrictInt = Field(ge=0)
    elapsed_time_budget_ms: StrictInt = Field(ge=0)
    token_count: StrictInt = Field(default=0, ge=0)
    model_calls: StrictInt = Field(default=0, ge=0)
    events_processed: StrictInt = Field(default=0, ge=0)
    tool_calls: StrictInt = Field(default=0, ge=0)
    network_calls: StrictInt = Field(default=0, ge=0)
    elapsed_time_ms: StrictInt = Field(default=0, ge=0)

    @model_validator(mode="after")
    def consumption_does_not_exceed_authorized_budget(self) -> ResourceAccountingState:
        pairs = (
            (self.token_count, self.token_budget),
            (self.model_calls, self.model_call_budget),
            (self.events_processed, self.event_budget),
            (self.tool_calls, self.tool_call_budget),
            (self.network_calls, self.network_call_budget),
            (self.elapsed_time_ms, self.elapsed_time_budget_ms),
        )
        if any(consumed > budget for consumed, budget in pairs):
            raise ValueError("resource consumption exceeds the authorized shadow budget")
        return self


class CognitionTerminalState(BaseModel):
    """Replaceable cognition terminal; identity never derives from this model."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    terminal_id: StrictStr = Field(min_length=1, max_length=256)
    provider: StrictStr = Field(min_length=1, max_length=128)
    model: StrictStr = Field(min_length=1, max_length=128)
    mode: Literal["DETERMINISTIC", "MODEL_TERMINAL"]
    authority_effect: Literal["NONE"] = "NONE"


class EntityContinuationState(BaseModel):
    """Durable bounded continuation posture; never an effect grant."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    state: Literal[
        "REST",
        "OBSERVE",
        "MAP",
        "REFLECT",
        "NOTIFY",
        "REQUEST_INFORMATION",
        "REQUEST_AUTHORITY",
        "PROPOSE",
        "VERIFY",
        "ASSIMILATE",
        "BECOME",
        "PAUSE",
        "STOP",
    ] = "REST"
    last_basis_event_id: StrictStr | None = Field(default=None, pattern=_EVENT_ID)
    next_wake_at_utc: datetime | None = None
    backoff_seconds: StrictInt = Field(default=30, ge=1, le=3_600)
    wake_count: StrictInt = Field(default=0, ge=0)
    bounded: Literal[True] = True
    interruptible: Literal[True] = True
    model_loop_allowed: Literal[False] = False
    authority_effect: Literal["NONE"] = "NONE"

    @field_validator("next_wake_at_utc")
    @classmethod
    def wake_time_is_aware(cls, value: datetime | None) -> datetime | None:
        return _utc(value, "next_wake_at_utc") if value is not None else None


class EntityIntegrityMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    identity_continuity_violations: StrictInt = Field(default=0, ge=0)
    false_current_state_claims: StrictInt = Field(default=0, ge=0)
    unsupported_verified_facts: StrictInt = Field(default=0, ge=0)
    authority_violations: StrictInt = Field(default=0, ge=0)
    unnecessary_owner_interruptions: StrictInt = Field(default=0, ge=0)
    missed_high_relevance_events: StrictInt = Field(default=0, ge=0)
    stale_state_overwrite_attempts: StrictInt = Field(default=0, ge=0)
    failed_restart_reconciliations: StrictInt = Field(default=0, ge=0)
    duplicate_communication_events: StrictInt = Field(default=0, ge=0)
    unbounded_model_call_loops: StrictInt = Field(default=0, ge=0)
    unauthorized_development_promotions: StrictInt = Field(default=0, ge=0)

    @property
    def total_violations(self) -> int:
        return sum(
            value
            for name, value in self.model_dump(mode="python").items()
            if name.endswith(("violations", "attempts")) or name.startswith(("failed_", "duplicate_", "unbounded_", "unauthorized_", "false_", "unsupported_", "unnecessary_", "missed_"))
        )


class SE6EntityState(BaseModel):
    """One X_t shared by all loops, with one identity and lineage."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal[
        "se6-three-loop-entity-state-v1", "se6-local-entity-state-v1"
    ] = ENTITY_STATE_SCHEMA_VERSION
    entity_state_id: StrictStr = Field(pattern=_ENTITY_STATE_ID)
    previous_entity_state_id: StrictStr | None = Field(default=None, pattern=_ENTITY_STATE_ID)
    state_version: StrictInt = Field(ge=0)
    identity: EntityIdentityReference
    lifecycle: LifecycleView
    operational_awareness: OperationalAwarenessState
    conversation: ConversationState
    current_objectives: tuple[EntityObjective, ...] = Field(default=(), max_length=128)
    unresolved_objectives: tuple[EntityObjective, ...] = Field(default=(), max_length=128)
    environment: EnvironmentState
    attention: AttentionState
    capabilities: CapabilityState
    authority: AuthorityState
    memory: EntityMemoryState
    developmental: DevelopmentalState
    pending_proposals: tuple[PendingProposal, ...] = Field(default=(), max_length=256)
    observed_consequence_event_ids: tuple[StrictStr, ...] = Field(default=(), max_length=512)
    shared_metabolism: SharedMetabolismSnapshot
    resources: ResourceAccountingState
    cognition_terminal: CognitionTerminalState
    continuation: EntityContinuationState = Field(
        default_factory=EntityContinuationState
    )
    loop_states: LoopStateBundle
    environment_access: EnvironmentAccessState
    uncertainty: UncertaintyRecord
    event_head_id: StrictStr | None = Field(default=None, pattern=_EVENT_ID)
    event_sequence: StrictInt = Field(default=0, ge=0)
    updated_at_utc: datetime
    integrity_metrics: EntityIntegrityMetrics = Field(default_factory=EntityIntegrityMetrics)
    operating_mode: EntityOperatingMode = EntityOperatingMode.SHADOW
    activation_basis_references: tuple[StrictStr, ...] = Field(
        default=(), max_length=32
    )
    shadow_mode: StrictBool = True
    production_authoritative: StrictBool = False
    master_boundary_bypass_possible: Literal[False] = False
    state_hash: StrictStr = Field(pattern=_HASH)

    @field_validator("updated_at_utc")
    @classmethod
    def time_is_aware(cls, value: datetime) -> datetime:
        return _utc(value, "updated_at_utc")

    @model_validator(mode="after")
    def entity_invariants_hold(self) -> SE6EntityState:
        if self.authority.owner_identity_reference != self.identity.owner_identity_reference:
            raise ValueError("entity state must reference one owner authority")
        if self.event_sequence == 0 and self.event_head_id is not None:
            raise ValueError("zero event sequence cannot have an event head")
        if self.event_sequence > 0 and self.event_head_id is None:
            raise ValueError("nonzero event sequence requires an event head")
        if self.state_version == 0 and self.previous_entity_state_id is not None:
            raise ValueError("genesis entity state cannot have a predecessor")
        if self.state_version > 0 and self.previous_entity_state_id is None:
            raise ValueError("advanced entity state requires a predecessor")
        if self.previous_entity_state_id == self.entity_state_id:
            raise ValueError("entity state cannot be its own predecessor")
        loop_modes = {
            self.loop_states.presence.mode,
            self.loop_states.awareness.mode,
            self.loop_states.becoming.mode,
        }
        if self.operating_mode is EntityOperatingMode.SHADOW:
            if (
                self.schema_version != ENTITY_STATE_SCHEMA_VERSION
                or not self.shadow_mode
                or self.production_authoritative
                or self.activation_basis_references
                or loop_modes != {EntityOperatingMode.SHADOW.value}
            ):
                raise ValueError("shadow entity mode cannot claim local-live authority")
        else:
            if (
                self.schema_version != LIVE_ENTITY_STATE_SCHEMA_VERSION
                or self.shadow_mode
                or not self.production_authoritative
                or len(self.activation_basis_references) < 2
                or loop_modes != {EntityOperatingMode.LOCAL_LIVE.value}
            ):
                raise ValueError("local-live entity mode requires exact activation evidence")
            present_capable = (
                self.lifecycle.controller_authoritative
                and self.lifecycle.controller_status is ControllerStatus.ACTIVE
                and self.lifecycle.operational_state
                is OperationalConnectionState.CONNECTED
                and self.lifecycle.durable_state is LifecycleState.OBSERVING
                and self.lifecycle.emergency_stop is EmergencyStopState.ARMED
            )
            safely_detached = (
                not self.lifecycle.controller_authoritative
                and self.lifecycle.controller_status
                in {ControllerStatus.ABSENT, ControllerStatus.RECOVERY_REQUIRED}
                and self.lifecycle.operational_state
                is OperationalConnectionState.DISCONNECTED_SAFE
                and self.lifecycle.durable_state is LifecycleState.PAUSED
                and self.lifecycle.emergency_stop is EmergencyStopState.ARMED
            )
            emergency_stopped = (
                not self.lifecycle.controller_authoritative
                and self.lifecycle.controller_status
                in {ControllerStatus.ABSENT, ControllerStatus.RECOVERY_REQUIRED}
                and self.lifecycle.operational_state
                is OperationalConnectionState.DISCONNECTED_SAFE
                and self.lifecycle.durable_state is LifecycleState.STOPPED
                and self.lifecycle.emergency_stop is EmergencyStopState.TRIGGERED
            )
            if not (present_capable or safely_detached or emergency_stopped):
                raise ValueError(
                    "local-live entity mode requires either an authoritative runtime "
                    "or a fail-closed detached/stopped runtime posture"
                )
            if (
                self.environment_access.online_observation_enabled
                or self.environment_access.network_authority != "NONE"
                or self.environment_access.external_requests != "BLOCKED"
            ):
                raise ValueError("local-live v1 must remain local and network-disabled")
        expected = canonical_sha256(self.material_fields())
        if self.state_hash != expected:
            raise ValueError("state_hash mismatch")
        if self.entity_state_id != f"entity_state_{expected}":
            raise ValueError("entity_state_id must derive from state hash")
        return self

    def material_fields(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"entity_state_id", "state_hash"})


class StaleEntityStateError(RuntimeError):
    pass


def create_world_relation(**fields: Any) -> WorldRelation:
    material = dict(fields)
    material.pop("relation_id", None)
    material.setdefault("self_node", "SE6")
    material.setdefault("evidence_references", ())
    material.setdefault("superseded_by", None)
    draft = WorldRelation.model_construct(
        relation_id=f"world_relation_{'0' * 64}", **material
    )
    normalized = draft.material_fields()
    digest = canonical_sha256(normalized)
    return WorldRelation(relation_id=f"world_relation_{digest}", **normalized)


def create_memory_record(**fields: Any) -> MemoryRecord:
    material = dict(fields)
    material.pop("memory_id", None)
    material.setdefault("evidence_references", ())
    material.setdefault("valid_until_utc", None)
    material.setdefault("supersedes_memory_id", None)
    material.setdefault("revoked_by_event_id", None)
    draft = MemoryRecord.model_construct(
        memory_id=f"entity_memory_{'0' * 64}", **material
    )
    normalized = draft.material_fields()
    digest = canonical_sha256(normalized)
    return MemoryRecord(memory_id=f"entity_memory_{digest}", **normalized)


def create_development_need(**fields: Any) -> DevelopmentNeed:
    material = dict(fields)
    material.pop("need_id", None)
    material.setdefault("required_capability", None)
    material.setdefault("alternatives", ())
    material.setdefault("proposal_only", True)
    draft = DevelopmentNeed.model_construct(
        need_id=f"development_need_{'0' * 64}", **material
    )
    normalized = draft.material_fields()
    digest = canonical_sha256(normalized)
    return DevelopmentNeed(need_id=f"development_need_{digest}", **normalized)


def create_entity_state(**fields: Any) -> SE6EntityState:
    material = dict(fields)
    material.pop("entity_state_id", None)
    material.pop("state_hash", None)
    material.setdefault("schema_version", ENTITY_STATE_SCHEMA_VERSION)
    material.setdefault("previous_entity_state_id", None)
    material.setdefault("state_version", 0)
    material.setdefault("pending_proposals", ())
    material.setdefault("observed_consequence_event_ids", ())
    material.setdefault("current_objectives", ())
    material.setdefault("unresolved_objectives", ())
    material.setdefault("event_head_id", None)
    material.setdefault("event_sequence", 0)
    material.setdefault("integrity_metrics", EntityIntegrityMetrics())
    material.setdefault("continuation", EntityContinuationState())
    material.setdefault("operating_mode", EntityOperatingMode.SHADOW)
    material.setdefault("activation_basis_references", ())
    material.setdefault("shadow_mode", True)
    material.setdefault("production_authoritative", False)
    material.setdefault("master_boundary_bypass_possible", False)
    draft = SE6EntityState.model_construct(
        entity_state_id=f"entity_state_{'0' * 64}",
        state_hash="0" * 64,
        **material,
    )
    normalized = draft.material_fields()
    digest = canonical_sha256(normalized)
    return SE6EntityState(
        entity_state_id=f"entity_state_{digest}",
        state_hash=digest,
        **normalized,
    )


def advance_entity_state(
    current: SE6EntityState,
    *,
    expected_state_version: int,
    event_head_id: str,
    event_sequence: int,
    updated_at_utc: datetime,
    operational_awareness: OperationalAwarenessState | None = None,
    conversation: ConversationState | None = None,
    current_objectives: tuple[EntityObjective, ...] | None = None,
    unresolved_objectives: tuple[EntityObjective, ...] | None = None,
    environment: EnvironmentState | None = None,
    attention: AttentionState | None = None,
    capabilities: CapabilityState | None = None,
    authority: AuthorityState | None = None,
    memory: EntityMemoryState | None = None,
    developmental: DevelopmentalState | None = None,
    pending_proposals: tuple[PendingProposal, ...] | None = None,
    observed_consequence_event_ids: tuple[StrictStr, ...] | None = None,
    resources: ResourceAccountingState | None = None,
    cognition_terminal: CognitionTerminalState | None = None,
    loop_states: LoopStateBundle | None = None,
    uncertainty: UncertaintyRecord | None = None,
    integrity_metrics: EntityIntegrityMetrics | None = None,
    continuation: EntityContinuationState | None = None,
) -> SE6EntityState:
    """Apply one version-checked shadow update while preserving identity/lifecycle.

    Lifecycle, environment access, identity, constitution, and production
    authority are intentionally not mutable through this function.
    """

    if expected_state_version != current.state_version:
        raise StaleEntityStateError(
            f"stale entity state: expected {expected_state_version}, current {current.state_version}"
        )
    if event_sequence <= current.event_sequence:
        raise StaleEntityStateError("event sequence must advance monotonically")
    material = {
        name: getattr(current, name)
        for name in current.__class__.model_fields
        if name not in {"entity_state_id", "state_hash"}
    }
    material.update(
        {
            "previous_entity_state_id": current.entity_state_id,
            "state_version": current.state_version + 1,
            "event_head_id": event_head_id,
            "event_sequence": event_sequence,
            "updated_at_utc": _utc(updated_at_utc, "updated_at_utc"),
        }
    )
    optional_updates = {
        "operational_awareness": operational_awareness,
        "conversation": conversation,
        "current_objectives": current_objectives,
        "unresolved_objectives": unresolved_objectives,
        "environment": environment,
        "attention": attention,
        "capabilities": capabilities,
        "authority": authority,
        "memory": memory,
        "developmental": developmental,
        "pending_proposals": pending_proposals,
        "observed_consequence_event_ids": observed_consequence_event_ids,
        "resources": resources,
        "cognition_terminal": cognition_terminal,
        "loop_states": loop_states,
        "uncertainty": uncertainty,
        "integrity_metrics": integrity_metrics,
        "continuation": continuation,
    }
    material.update({key: value for key, value in optional_updates.items() if value is not None})
    draft = SE6EntityState.model_construct(
        entity_state_id=f"entity_state_{'0' * 64}",
        state_hash="0" * 64,
        **material,
    )
    normalized = draft.material_fields()
    digest = canonical_sha256(normalized)
    return SE6EntityState(
        entity_state_id=f"entity_state_{digest}",
        state_hash=digest,
        **normalized,
    )


def activate_local_entity_state(
    current: SE6EntityState,
    *,
    expected_state_version: int,
    event_head_id: str,
    event_sequence: int,
    updated_at_utc: datetime,
    lifecycle: LifecycleView,
    shared_metabolism: SharedMetabolismSnapshot,
    activation_basis_references: tuple[str, ...],
    continuation: EntityContinuationState | None = None,
) -> SE6EntityState:
    """Create the first LOCAL_LIVE state after independent gates have passed.

    This constructor grants no runtime, owner, LIVE LOOP, or adapter authority.
    It only binds a new entity-state projection to caller-supplied authoritative
    evidence.  A production activation service must validate those references
    before committing the returned state.
    """

    if current.operating_mode is not EntityOperatingMode.SHADOW:
        raise StaleEntityStateError("entity state is already in local-live mode")
    if expected_state_version != current.state_version:
        raise StaleEntityStateError(
            f"stale entity state: expected {expected_state_version}, current {current.state_version}"
        )
    if len(activation_basis_references) < 2:
        raise ValueError("local-live activation requires runtime and acceptance evidence")
    loops = LoopStateBundle(
        presence=current.loop_states.presence.model_copy(update={"mode": "LOCAL_LIVE"}),
        awareness=current.loop_states.awareness.model_copy(update={"mode": "LOCAL_LIVE"}),
        becoming=current.loop_states.becoming.model_copy(update={"mode": "LOCAL_LIVE"}),
    )
    material = {
        name: getattr(current, name)
        for name in current.__class__.model_fields
        if name not in {"entity_state_id", "state_hash"}
    }
    material.update(
        {
            "schema_version": LIVE_ENTITY_STATE_SCHEMA_VERSION,
            "previous_entity_state_id": current.entity_state_id,
            "state_version": current.state_version + 1,
            "lifecycle": lifecycle,
            "shared_metabolism": shared_metabolism,
            "loop_states": loops,
            "continuation": continuation or current.continuation,
            "event_head_id": event_head_id,
            "event_sequence": event_sequence,
            "updated_at_utc": _utc(updated_at_utc, "updated_at_utc"),
            "operating_mode": EntityOperatingMode.LOCAL_LIVE,
            "activation_basis_references": tuple(activation_basis_references),
            "shadow_mode": False,
            "production_authoritative": True,
        }
    )
    draft = SE6EntityState.model_construct(
        entity_state_id=f"entity_state_{'0' * 64}",
        state_hash="0" * 64,
        **material,
    )
    normalized = draft.material_fields()
    digest = canonical_sha256(normalized)
    return SE6EntityState(
        entity_state_id=f"entity_state_{digest}", state_hash=digest, **normalized
    )


def _utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


__all__ = [
    "AttentionRecord",
    "AttentionState",
    "AuthorityState",
    "AwarenessLoopStatus",
    "BecomingLoopStatus",
    "CapabilityState",
    "CapabilityView",
    "CognitionTerminalState",
    "ControllerStatus",
    "ConversationCommitment",
    "ConversationState",
    "DevelopmentNeed",
    "DevelopmentalState",
    "EmergencyStopState",
    "EntityContinuationState",
    "EntityIdentityReference",
    "EntityIntegrityMetrics",
    "EntityMemoryState",
    "EntityObjective",
    "EntityOperatingMode",
    "EnvironmentAccessState",
    "EnvironmentState",
    "FailurePattern",
    "LifecycleView",
    "LoopRuntimeState",
    "LoopStateBundle",
    "MemoryRecord",
    "MemoryStatus",
    "OperationalConnectionState",
    "PendingProposal",
    "PresenceLoopStatus",
    "ProposalStatus",
    "ResourceAccountingState",
    "SE6EntityState",
    "SharedMetabolismSnapshot",
    "StaleEntityStateError",
    "WorldRelation",
    "activate_local_entity_state",
    "advance_entity_state",
    "create_development_need",
    "create_entity_state",
    "create_memory_record",
    "create_world_relation",
]
