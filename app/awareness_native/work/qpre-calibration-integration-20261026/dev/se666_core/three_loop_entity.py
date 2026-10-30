"""Deterministic reducer for SE6's three computational loops.

This module is intentionally synchronous and in-memory.  It contains no
network, provider, subprocess, filesystem, database, thread, timer, approval,
adapter, production-runtime, or LIVE LOOP controller integration.  A caller
explicitly enqueues events and explicitly invokes one bounded scheduler step.

The loops share one :class:`SE6EntityState`.  Their outputs are response
intents, awareness projections, memory candidates, and development/authority
requests.  They never grant authority or perform an external effect.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import (
    Literal,
    TypedDict,
)

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from .canonical_contracts import canonical_sha256
from .entity_events import (
    ApprovalDisposition,
    ApprovalPayload,
    AttentionPayload,
    AuthorityPayload,
    AuthorityStatus,
    AwarenessPayload,
    DevelopmentPayload,
    EntityEvent,
    EntityEventDraft,
    EventEndpoint,
    EventPayload,
    EventSourceKind,
    EventType,
    InteractionKind,
    InteractionPayload,
    LoopName,
    MemoryEventOperation,
    MemoryPayload,
    ModelTerminalPayload,
    ObjectiveOperation,
    ObjectivePayload,
    ObservationPayload,
    ObservationProvenance,
    PersistencePolicy,
    RelevanceDimensions,
    RelevanceOutcome,
    SensitivityClassification,
    VerificationPayload,
    VerificationResult,
    create_entity_event,
)
from .entity_state import (
    AttentionRecord,
    AttentionState,
    AuthorityState,
    AwarenessLoopStatus,
    BecomingLoopStatus,
    CapabilityView,
    CognitionTerminalState,
    ConversationState,
    DevelopmentalState,
    DevelopmentNeed,
    EntityContinuationState,
    EntityMemoryState,
    EntityObjective,
    EntityOperatingMode,
    EnvironmentState,
    FailurePattern,
    LoopRuntimeState,
    LoopStateBundle,
    MemoryStatus,
    PendingProposal,
    PresenceLoopStatus,
    ProposalStatus,
    ResourceAccountingState,
    SE6EntityState,
    StaleEntityStateError,
    WorldRelation,
    advance_entity_state,
    create_development_need,
    create_memory_record,
    create_world_relation,
)
from .epistemic_status import EpistemicStatus, UncertaintyRecord
from .entity_relational_learning import (
    learning_response, memory_from_observation, observation_summary, observation_value,
    owner_observation, retention_verification,
)
from .merkabah_rotation import rotate_perspectives
from .operational_awareness import (
    ObservationStatus,
    OperationalAwarenessState,
    build_operational_awareness_state,
)
from .sphere_of_mirrors import reflect_task

COORDINATOR_SCHEMA_VERSION = "se6-three-loop-coordinator-v1"
RELEVANCE_POLICY_VERSION = "se6-three-loop-relevance-v1"


class SchedulerPriority(str, Enum):
    EMERGENCY_SAFETY = "EMERGENCY_SAFETY"
    OWNER_INTERRUPT = "OWNER_INTERRUPT"
    ACTIVE_INTERACTION = "ACTIVE_INTERACTION"
    CRITICAL_OBSERVATION = "CRITICAL_OBSERVATION"
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    NORMAL_AWARENESS = "NORMAL_AWARENESS"
    DEVELOPMENT = "DEVELOPMENT"
    REST = "REST"


_PRIORITY_RANK = {
    SchedulerPriority.EMERGENCY_SAFETY: 0,
    SchedulerPriority.OWNER_INTERRUPT: 1,
    SchedulerPriority.ACTIVE_INTERACTION: 2,
    SchedulerPriority.CRITICAL_OBSERVATION: 3,
    SchedulerPriority.PENDING_VERIFICATION: 4,
    SchedulerPriority.NORMAL_AWARENESS: 5,
    SchedulerPriority.DEVELOPMENT: 6,
    SchedulerPriority.REST: 7,
}


class CoordinatorStepStatus(str, Enum):
    APPLIED_SHADOW = "APPLIED_SHADOW"
    APPLIED_LOCAL_LIVE = "APPLIED_LOCAL_LIVE"
    NO_ELIGIBLE_LOOP = "NO_ELIGIBLE_LOOP"
    LOCAL_EVENT_BUDGET_RENEWED = "LOCAL_EVENT_BUDGET_RENEWED"
    INTERACTIVE_PROOF_CONTROLLED = "INTERACTIVE_PROOF_CONTROLLED"


class CoordinatorPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: str = COORDINATOR_SCHEMA_VERSION
    queue_capacity: StrictInt = Field(default=256, ge=1, le=10_000)
    ledger_capacity: StrictInt = Field(default=4_096, ge=1, le=100_000)
    max_causal_depth: StrictInt = Field(default=8, ge=1, le=64)
    max_derived_events_per_step: StrictInt = Field(default=8, ge=0, le=32)
    repeated_failure_threshold: StrictInt = Field(default=2, ge=2, le=20)


class CommunicationIntent(BaseModel):
    """A recommendation for one SE6 voice; it is not sent by this module."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    intent_id: StrictStr = Field(pattern=r"^communication_intent_[0-9a-f]{64}$")
    interaction_kind: InteractionKind
    thread_id: StrictStr = Field(min_length=1, max_length=128)
    text: StrictStr = Field(min_length=1, max_length=4_000)
    basis_event_ids: tuple[StrictStr, ...] = Field(min_length=1, max_length=32)
    initiated_by_se6: bool
    initiation_reason: StrictStr | None = Field(default=None, max_length=500)
    authority_effect: str = Field(default="NONE", pattern=r"^NONE$")
    external_effect: str = Field(default="NONE", pattern=r"^NONE$")

    @model_validator(mode="after")
    def intent_is_grounded_and_canonical(self) -> CommunicationIntent:
        if self.initiated_by_se6 and not self.initiation_reason:
            raise ValueError("proactive communication requires a recorded reason")
        if not self.initiated_by_se6 and self.initiation_reason is not None:
            raise ValueError("responsive communication cannot claim proactive initiation")
        expected = canonical_sha256(self.material_fields())
        if self.intent_id != f"communication_intent_{expected}":
            raise ValueError("intent_id must derive from intent material")
        return self

    def material_fields(self) -> dict[str, object]:
        return self.model_dump(mode="python", exclude={"intent_id"})


class RelevanceAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    policy_version: str = RELEVANCE_POLICY_VERSION
    subject_event_id: StrictStr = Field(pattern=r"^entity_event_[0-9a-f]{64}$")
    dimensions: RelevanceDimensions
    score: StrictInt = Field(ge=0, le=100)
    outcome: RelevanceOutcome
    rationale_codes: tuple[StrictStr, ...] = Field(default=(), max_length=16)
    authority_effect: str = Field(default="NONE", pattern=r"^NONE$")

    @model_validator(mode="after")
    def score_is_recomputed(self) -> RelevanceAssessment:
        values = self.dimensions.model_dump(mode="python").values()
        expected = sum(values) // 10
        if self.score != expected:
            raise ValueError("relevance score must be the deterministic integer mean")
        if self.outcome is not _outcome_for(self.dimensions, self.score):
            raise ValueError("relevance outcome does not match the policy")
        return self


class CoordinatorStepResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: str = COORDINATOR_SCHEMA_VERSION
    result_id: StrictStr = Field(pattern=r"^coordinator_result_[0-9a-f]{64}$")
    state_before_id: StrictStr = Field(pattern=r"^entity_state_[0-9a-f]{64}$")
    state_after_id: StrictStr = Field(pattern=r"^entity_state_[0-9a-f]{64}$")
    processed_event_id: StrictStr = Field(pattern=r"^entity_event_[0-9a-f]{64}$")
    selected_loop: LoopName | None
    priority: SchedulerPriority
    status: CoordinatorStepStatus
    emitted_event_ids: tuple[StrictStr, ...] = Field(default=(), max_length=32)
    communication_intents: tuple[CommunicationIntent, ...] = Field(default=(), max_length=8)
    processed_at_utc: datetime
    production_state_changed: bool = False
    identity_state_advanced: bool = False
    approval_consumed: bool = False
    external_effect_performed: bool = False
    network_used: bool = False
    model_calls: StrictInt = 0

    @field_validator("processed_at_utc")
    @classmethod
    def time_is_aware(cls, value: datetime) -> datetime:
        return _utc(value, "processed_at_utc")

    @model_validator(mode="after")
    def result_is_effect_free_and_canonical(self) -> CoordinatorStepResult:
        if any(
            (
                self.production_state_changed,
                self.identity_state_advanced,
                self.approval_consumed,
                self.external_effect_performed,
                self.network_used,
            )
        ) or self.model_calls:
            raise ValueError("entity coordinator cannot report an effect or model call")
        if self.selected_loop in {LoopName.COORDINATOR, LoopName.EXTERNAL}:
            raise ValueError("only one of the exact three cognitive loops may be selected")
        expected = canonical_sha256(self.material_fields())
        if self.result_id != f"coordinator_result_{expected}":
            raise ValueError("result_id must derive from result material")
        return self

    def material_fields(self) -> dict[str, object]:
        return self.model_dump(mode="python", exclude={"result_id"})


class EventBusBackpressure(RuntimeError):
    pass


class DuplicateEntityEvent(RuntimeError):
    pass


class InvalidCausalEvent(RuntimeError):
    pass


class ResourceBudgetExceeded(RuntimeError):
    pass


class InMemoryEntityEventBus:
    """Bounded deterministic queue and ledger; no callbacks or background work."""

    def __init__(
        self,
        *,
        policy: CoordinatorPolicy,
        historical_events: Sequence[EntityEvent] = (),
    ) -> None:
        self._policy = policy
        self._events: list[EntityEvent] = []
        self._queued: list[EntityEventDraft] = []
        self._queued_hashes: set[str] = set()
        prior_ids: set[str] = set()
        for expected_sequence, event in enumerate(historical_events, start=1):
            if event.sequence != expected_sequence:
                raise InvalidCausalEvent("historical event sequence is not contiguous")
            if event.parent_event_id is not None and event.parent_event_id not in prior_ids:
                raise InvalidCausalEvent("historical parent event is unavailable")
            self._events.append(event)
            prior_ids.add(event.event_id)
        if len(self._events) > policy.ledger_capacity:
            raise EventBusBackpressure("historical ledger exceeds configured capacity")

    @property
    def events(self) -> tuple[EntityEvent, ...]:
        return tuple(self._events)

    @property
    def queued_count(self) -> int:
        return len(self._queued)

    @property
    def pending_drafts(self) -> tuple[EntityEventDraft, ...]:
        """Return an immutable view of work produced by the pure reducer.

        The durable runtime uses this only after a successful step so derived
        work can be committed atomically with that step.  Exposing the tuple
        does not add callbacks, I/O, execution, or authority to the bus.
        """

        return tuple(self._queued)

    @property
    def next_sequence(self) -> int:
        return len(self._events) + 1

    def enqueue(self, draft: EntityEventDraft) -> None:
        if len(self._queued) >= self._policy.queue_capacity:
            raise EventBusBackpressure("entity event queue is full; nothing was evicted")
        digest = canonical_sha256(draft)
        if digest in self._queued_hashes:
            raise DuplicateEntityEvent("duplicate queued event rejected")
        self._validate_parent(draft.parent_event_id)
        self._queued.append(draft)
        self._queued_hashes.add(digest)

    def pop_next(self) -> EntityEventDraft:
        if not self._queued:
            raise IndexError("entity event queue is empty")
        self._queued.sort(key=_draft_order_key)
        draft = self._queued.pop(0)
        self._queued_hashes.remove(canonical_sha256(draft))
        return draft

    def publish(self, draft: EntityEventDraft) -> EntityEvent:
        if len(self._events) >= self._policy.ledger_capacity:
            raise EventBusBackpressure("entity event ledger is full; nothing was evicted")
        self._validate_parent(draft.parent_event_id)
        event = create_entity_event(sequence=self.next_sequence, draft=draft)
        if any(existing.event_id == event.event_id for existing in self._events):
            raise DuplicateEntityEvent("duplicate published event rejected")
        if self._causal_depth(event) > self._policy.max_causal_depth:
            raise InvalidCausalEvent("maximum causal event depth exceeded")
        self._events.append(event)
        return event

    def _validate_parent(self, parent_event_id: str | None) -> None:
        if parent_event_id is not None and not any(
            event.event_id == parent_event_id for event in self._events
        ):
            raise InvalidCausalEvent("parent event is not present in the bounded ledger")

    def _causal_depth(self, event: EntityEvent) -> int:
        by_id = {item.event_id: item for item in self._events}
        depth = 0
        parent_id = event.parent_event_id
        seen = {event.event_id}
        while parent_id is not None:
            if parent_id in seen:
                raise InvalidCausalEvent("causal event cycle detected")
            seen.add(parent_id)
            depth += 1
            parent = by_id.get(parent_id)
            if parent is None:
                raise InvalidCausalEvent("causal parent disappeared")
            parent_id = parent.parent_event_id
        return depth

    def _checkpoint(
        self,
    ) -> tuple[list[EntityEvent], list[EntityEventDraft], set[str]]:
        return (list(self._events), list(self._queued), set(self._queued_hashes))

    def _restore(
        self,
        checkpoint: tuple[list[EntityEvent], list[EntityEventDraft], set[str]],
    ) -> None:
        events, queued, queued_hashes = checkpoint
        self._events = list(events)
        self._queued = list(queued)
        self._queued_hashes = set(queued_hashes)


@dataclass(frozen=True)
class _PresenceEvaluation:
    intent: CommunicationIntent


@dataclass(frozen=True)
class _AwarenessEvaluation:
    awareness: OperationalAwarenessState
    environment: EnvironmentState
    attention: AttentionState
    relevance: RelevanceAssessment
    contradiction: bool
    prior_relation: WorldRelation | None
    current_relation: WorldRelation | None
    notify: bool


@dataclass(frozen=True)
class _BecomingEvaluation:
    memory: EntityMemoryState
    developmental: DevelopmentalState
    need_created: DevelopmentNeed | None
    capability_request: AuthorityPayload | None


class _EntityStateUpdates(TypedDict, total=False):
    operational_awareness: OperationalAwarenessState
    conversation: ConversationState
    current_objectives: tuple[EntityObjective, ...]
    unresolved_objectives: tuple[EntityObjective, ...]
    environment: EnvironmentState
    attention: AttentionState
    authority: AuthorityState
    memory: EntityMemoryState
    developmental: DevelopmentalState
    pending_proposals: tuple[PendingProposal, ...]
    resources: ResourceAccountingState
    cognition_terminal: CognitionTerminalState
    loop_states: LoopStateBundle
    continuation: EntityContinuationState


class InteractivePresenceLoop:
    """Forms a grounded communication intent; it never sends or authenticates."""

    identity = LoopName.PRESENCE

    def evaluate(self, event: EntityEvent, state: SE6EntityState) -> _PresenceEvaluation:
        payload = event.payload
        if isinstance(payload, InteractionPayload):
            return _PresenceEvaluation(
                intent=_presence_intent_from_interaction(event, payload, state)
            )
        if isinstance(payload, ApprovalPayload):
            decision = payload.disposition.value.lower()
            text = (
                f"The owner authority decision was recorded as {decision}. "
                "No capability was exercised by this shadow loop."
            )
            return _PresenceEvaluation(
                intent=create_communication_intent(
                    interaction_kind=InteractionKind.ACKNOWLEDGEMENT_INTENT,
                    thread_id=state.conversation.current_thread_id,
                    text=text,
                    basis_event_ids=(event.event_id,),
                    initiated_by_se6=False,
                    initiation_reason=None,
                )
            )
        if isinstance(payload, AuthorityPayload):
            text = (
                f"Owner authority is requested for capability {payload.capability}. "
                f"Reason: {payload.reason}"
            )
            return _PresenceEvaluation(
                intent=create_communication_intent(
                    interaction_kind=InteractionKind.NOTIFICATION_INTENT,
                    thread_id=state.conversation.current_thread_id,
                    text=text,
                    basis_event_ids=(event.event_id,),
                    initiated_by_se6=True,
                    initiation_reason="A typed owner-authority request requires attention.",
                )
            )
        if isinstance(payload, ObjectivePayload):
            verb = {
                ObjectiveOperation.RECORD: "recorded as active",
                ObjectiveOperation.BLOCK: "recorded as blocked",
                ObjectiveOperation.COMPLETE: "recorded as completed",
                ObjectiveOperation.WITHDRAW: "recorded as withdrawn",
            }[payload.operation]
            return _PresenceEvaluation(
                intent=create_communication_intent(
                    interaction_kind=InteractionKind.ACKNOWLEDGEMENT_INTENT,
                    thread_id=state.conversation.current_thread_id,
                    text=f"Objective {payload.objective_id} was {verb}. No external action was taken.",
                    basis_event_ids=(event.event_id,),
                    initiated_by_se6=False,
                    initiation_reason=None,
                )
            )
        raise TypeError("Presence received an unsupported event payload")


class OperationalAwarenessLoop:
    """Maps one observation into a non-authoritative awareness projection."""

    identity = LoopName.AWARENESS

    def evaluate(self, event: EntityEvent, state: SE6EntityState) -> _AwarenessEvaluation:
        if not isinstance(event.payload, ObservationPayload):
            # A non-observation routed here is retained as an unresolved signal.
            assessment = _minimal_relevance(event)
            return _AwarenessEvaluation(
                awareness=state.operational_awareness,
                environment=state.environment,
                attention=_append_attention(state.attention, assessment),
                relevance=assessment,
                contradiction=False,
                prior_relation=None,
                current_relation=None,
                notify=False,
            )
        payload = event.payload
        prior = _current_relation(state.environment, payload.world_node, payload.relation)
        contradiction = prior is not None and observation_value(prior) != observation_value(payload)
        assessment = assess_relevance(event, state, contradiction=contradiction)
        epistemic = _epistemic_for_observation(payload)
        relation = create_world_relation(
            self_node="SE6",
            world_node=payload.world_node,
            relation=payload.relation,
            value_summary=payload.value_summary,
            epistemic_status=epistemic,
            source_event_id=event.event_id,
            evidence_references=payload.evidence_references,
            observed_at_utc=payload.observed_at_utc,
            current=payload.current_claim,
            superseded_by=None,
        )
        relations = list(state.environment.relations)
        if prior is None:
            relations.append(relation)
        elif observation_value(prior) == observation_value(payload):
            # Repeated evidence stays in the event ledger; do not duplicate the map node.
            relation = prior
        else:
            prior_index = relations.index(prior)
            relations[prior_index] = create_world_relation(
                self_node=prior.self_node,
                world_node=prior.world_node,
                relation=prior.relation,
                value_summary=prior.value_summary,
                epistemic_status=prior.epistemic_status,
                source_event_id=prior.source_event_id,
                evidence_references=prior.evidence_references,
                observed_at_utc=prior.observed_at_utc,
                current=False,
                superseded_by=relation.relation_id,
            )
            relations.append(relation)
        observation_ids = _bounded_append(
            state.environment.observation_event_ids, event.event_id, 1_024
        )
        environment = EnvironmentState(
            relations=_bounded_environment_relations(relations),
            observation_event_ids=observation_ids,
            contradiction_event_ids=state.environment.contradiction_event_ids,
        )
        awareness = _project_awareness(event, state, assessment)
        return _AwarenessEvaluation(
            awareness=awareness,
            environment=environment,
            attention=_append_attention(state.attention, assessment),
            relevance=assessment,
            contradiction=contradiction,
            prior_relation=prior,
            current_relation=relation,
            notify=assessment.outcome in {
                RelevanceOutcome.NOTIFY,
                RelevanceOutcome.REQUEST_INFORMATION,
                RelevanceOutcome.REQUEST_AUTHORITY,
                RelevanceOutcome.PROPOSE_ACTION,
            },
        )


class DevelopmentalAssimilationLoop:
    """Builds verified-history memory and development proposals; never applies them."""

    identity = LoopName.BECOMING

    def __init__(self, *, repeated_failure_threshold: int = 2) -> None:
        self._threshold = repeated_failure_threshold

    def evaluate(self, event: EntityEvent, state: SE6EntityState) -> _BecomingEvaluation:
        if isinstance(event.payload, MemoryPayload):
            return _evaluate_memory_transition(event, state)
        if not isinstance(event.payload, VerificationPayload):
            return _BecomingEvaluation(
                memory=state.memory,
                developmental=state.developmental,
                need_created=None,
                capability_request=None,
            )
        payload = event.payload
        if not payload.independently_verified or not payload.evidence_references:
            return _BecomingEvaluation(
                memory=state.memory,
                developmental=state.developmental,
                need_created=None,
                capability_request=None,
            )
        memory = create_memory_record(
            subject=f"verification:{payload.subject_event_id}",
            content_summary=payload.summary,
            status=MemoryStatus.VERIFIED,
            epistemic_status=EpistemicStatus.VERIFIED,
            source_event_ids=(event.event_id,),
            evidence_references=payload.evidence_references,
            recorded_at_utc=event.occurred_at_utc,
            valid_until_utc=event.occurred_at_utc + timedelta(days=1),
            current=True,
            supersedes_memory_id=None,
            revoked_by_event_id=None,
        )
        memory_state = EntityMemoryState(
            records=(*state.memory.records, memory)
        )
        if payload.result is not VerificationResult.FAILED:
            return _BecomingEvaluation(
                memory=memory_state,
                developmental=state.developmental,
                need_created=None,
                capability_request=None,
            )
        pattern_key = payload.failure_class or "verified_failure"
        patterns = list(state.developmental.failure_patterns)
        existing = next(
            (item for item in patterns if item.pattern_key == pattern_key), None
        )
        if existing is None:
            updated_pattern = FailurePattern(
                pattern_key=pattern_key,
                verified_event_ids=(event.event_id,),
                occurrence_count=1,
            )
            patterns.append(updated_pattern)
        else:
            ids = _bounded_append(existing.verified_event_ids, event.event_id, 128)
            updated_pattern = FailurePattern(
                pattern_key=existing.pattern_key,
                verified_event_ids=ids,
                occurrence_count=len(ids),
            )
            patterns[patterns.index(existing)] = updated_pattern
        needs = list(state.developmental.development_needs)
        need = None
        request = None
        if updated_pattern.occurrence_count >= self._threshold and not any(
            item.pattern_key == pattern_key for item in needs
        ):
            capability = _capability_for_failure(pattern_key)
            need = create_development_need(
                need_kind="RECURRING_VERIFIED_FAILURE",
                summary=(
                    f"Repeated verified failure pattern {pattern_key} requires "
                    "a bounded development proposal."
                ),
                pattern_key=pattern_key,
                verified_evidence_event_ids=updated_pattern.verified_event_ids,
                required_capability=capability,
                alternatives=(
                    "Continue with the current bounded capability set.",
                    "Ask ProgrammerOne for additional evidence.",
                ),
                expected_benefit="Reduce recurrence of the verified failure class.",
                expected_cost="Owner review and isolated candidate verification.",
                risk="A proposed capability must not become authority.",
                authority_status=AuthorityStatus.REQUIRED,
                proposal_only=True,
            )
            needs.append(need)
            if not _capability_available(state.capabilities.capabilities, capability):
                request = AuthorityPayload(
                    capability=capability,
                    scope=f"Investigate a bounded response to {pattern_key}.",
                    reason=need.summary,
                    alternatives=need.alternatives,
                    risk=need.risk,
                    expected_benefit=need.expected_benefit,
                    expected_cost=need.expected_cost,
                    credential_requirement="NONE",
                    recommended_choice="Review the proposal; denial leaves current capability unchanged.",
                    authority_effect="NONE",
                )
        development = DevelopmentalState(
            failure_patterns=tuple(patterns),
            development_needs=tuple(needs),
            candidate_event_ids=state.developmental.candidate_event_ids,
            denied_request_event_ids=state.developmental.denied_request_event_ids,
        )
        return _BecomingEvaluation(
            memory=memory_state,
            developmental=development,
            need_created=need,
            capability_request=request,
        )


def _evaluate_memory_transition(
    event: EntityEvent, state: SE6EntityState
) -> _BecomingEvaluation:
    """Apply an explicit memory lifecycle event to the append-only view.

    A transition appends a new record.  The prior record remains auditable and
    is removed only from the deterministic active projection through an exact
    supersession reference.  Similarity or a model assertion is never enough
    to create VERIFIED memory.
    """

    payload = event.payload
    assert isinstance(payload, MemoryPayload)
    operation = payload.operation
    records = list(state.memory.records)
    source_ids = tuple(dict.fromkeys((event.event_id, *payload.source_event_ids)))
    if operation is MemoryEventOperation.CANDIDATE:
        epistemic = (
            EpistemicStatus.REPORTED
            if event.epistemic_status is EpistemicStatus.VERIFIED
            else event.epistemic_status
        )
        records.append(
            create_memory_record(
                subject=payload.subject,
                content_summary=payload.content_summary,
                status=MemoryStatus.PROVISIONAL,
                epistemic_status=epistemic,
                source_event_ids=source_ids,
                evidence_references=payload.evidence_references,
                recorded_at_utc=event.occurred_at_utc,
                valid_until_utc=None,
                current=True,
                supersedes_memory_id=None,
                revoked_by_event_id=None,
            )
        )
    elif operation is MemoryEventOperation.CONSOLIDATE:
        if (
            event.provenance is not ObservationProvenance.INDEPENDENTLY_VERIFIED
            or event.epistemic_status is not EpistemicStatus.VERIFIED
            or not payload.evidence_references
        ):
            return _BecomingEvaluation(
                memory=state.memory,
                developmental=state.developmental,
                need_created=None,
                capability_request=None,
            )
        records.append(
            create_memory_record(
                subject=payload.subject,
                content_summary=payload.content_summary,
                status=MemoryStatus.VERIFIED,
                epistemic_status=EpistemicStatus.VERIFIED,
                source_event_ids=source_ids,
                evidence_references=payload.evidence_references,
                recorded_at_utc=event.occurred_at_utc,
                valid_until_utc=event.occurred_at_utc + timedelta(days=1),
                current=True,
                supersedes_memory_id=payload.supersedes_memory_id,
                revoked_by_event_id=None,
            )
        )
    else:
        target_id = (
            payload.revokes_memory_id
            if operation is MemoryEventOperation.REVOKE
            else payload.supersedes_memory_id
        )
        target = next(
            (item for item in records if item.memory_id == target_id), None
        )
        if target is None:
            raise InvalidCausalEvent("memory transition target is unavailable")
        if operation is MemoryEventOperation.SUPERSEDE:
            verified = (
                event.provenance is ObservationProvenance.INDEPENDENTLY_VERIFIED
                and event.epistemic_status is EpistemicStatus.VERIFIED
                and bool(payload.evidence_references)
            )
            status = MemoryStatus.VERIFIED if verified else MemoryStatus.PROVISIONAL
            epistemic = (
                EpistemicStatus.VERIFIED if verified else event.epistemic_status
            )
            current = True
            revoked_by = None
        else:
            status = {
                MemoryEventOperation.MARK_STALE: MemoryStatus.STALE,
                MemoryEventOperation.MARK_EXPIRED: MemoryStatus.EXPIRED,
                MemoryEventOperation.MARK_CONTRADICTED: MemoryStatus.CONTRADICTED,
                MemoryEventOperation.REVOKE: MemoryStatus.REVOKED,
            }[operation]
            epistemic = {
                MemoryStatus.STALE: EpistemicStatus.STALE,
                MemoryStatus.EXPIRED: EpistemicStatus.EXPIRED,
                MemoryStatus.CONTRADICTED: EpistemicStatus.CONTRADICTED,
                MemoryStatus.REVOKED: EpistemicStatus.REVOKED,
            }[status]
            current = False
            revoked_by = event.event_id if status is MemoryStatus.REVOKED else None
        records.append(
            create_memory_record(
                subject=payload.subject,
                content_summary=payload.content_summary,
                status=status,
                epistemic_status=epistemic,
                source_event_ids=source_ids,
                evidence_references=payload.evidence_references,
                recorded_at_utc=event.occurred_at_utc,
                valid_until_utc=(event.occurred_at_utc if not current else None),
                current=current,
                supersedes_memory_id=target.memory_id,
                revoked_by_event_id=revoked_by,
            )
        )
    return _BecomingEvaluation(
        memory=EntityMemoryState(records=tuple(records)),
        developmental=state.developmental,
        need_created=None,
        capability_request=None,
    )


class SE6TriLoopCoordinator:
    """Owns one entity state, one bounded queue, and deterministic arbitration."""

    def __init__(
        self,
        *,
        state: SE6EntityState,
        policy: CoordinatorPolicy | None = None,
        historical_events: Sequence[EntityEvent] = (),
    ) -> None:
        self.policy = policy or CoordinatorPolicy()
        self.state = state
        self.bus = InMemoryEntityEventBus(
            policy=self.policy, historical_events=historical_events
        )
        if historical_events:
            if state.event_sequence != len(historical_events):
                raise InvalidCausalEvent("entity state and event ledger sequence disagree")
            if state.event_head_id != historical_events[-1].event_id:
                raise InvalidCausalEvent("entity state and event ledger head disagree")
        elif state.event_sequence:
            raise InvalidCausalEvent("advanced entity state requires its bounded event history")
        self._presence = InteractivePresenceLoop()
        self._awareness = OperationalAwarenessLoop()
        self._becoming = DevelopmentalAssimilationLoop(
            repeated_failure_threshold=self.policy.repeated_failure_threshold
        )

    def enqueue(self, draft: EntityEventDraft) -> None:
        self.bus.enqueue(draft)

    @property
    def pending_drafts(self) -> tuple[EntityEventDraft, ...]:
        """Derived work awaiting a later bounded coordinator step."""

        return self.bus.pending_drafts

    def run_step(
        self, *, expected_state_version: int | None = None,
        evaluation_at_utc: datetime | None = None,
    ) -> CoordinatorStepResult:
        """Apply one in-memory step atomically or restore the exact checkpoint."""

        checkpoint = self.bus._checkpoint()
        state_before = self.state
        try:
            return self._run_step_unchecked(
                expected_state_version=expected_state_version,
                evaluation_at_utc=evaluation_at_utc,
            )
        except Exception:
            self.bus._restore(checkpoint)
            self.state = state_before
            raise

    def _run_step_unchecked(
        self, *, expected_state_version: int | None = None, _proof_scoped: bool = False,
        evaluation_at_utc: datetime | None = None,
    ) -> CoordinatorStepResult:
        """Process at most one explicitly queued event."""

        expected = self.state.state_version if expected_state_version is None else expected_state_version
        if expected != self.state.state_version:
            raise StaleEntityStateError(
                f"stale entity state: expected {expected}, current {self.state.state_version}"
            )
        if not _proof_scoped and self.state.resources.events_processed >= self.state.resources.event_budget:
            raise ResourceBudgetExceeded("entity event budget is exhausted")
        draft = self.bus.pop_next()
        priority = priority_for(draft)
        event = self.bus.publish(draft)
        state_before = self.state
        selected = eligible_loop_for(event, state_before)
        emitted: list[EntityEvent] = []
        intents: tuple[CommunicationIntent, ...] = ()
        updates: _EntityStateUpdates = {}
        if selected is LoopName.PRESENCE:
            evaluation = self._presence.evaluate(event, state_before)
            intent_event = self._publish_intent(event, evaluation.intent)
            emitted.append(intent_event)
            intents = (evaluation.intent,)
            updates.update(
                self._presence_updates(state_before, event, intent_event)
            )
            observation = owner_observation(event, state_before)
            if observation is not None:
                self.bus.enqueue(observation)
        elif selected is LoopName.AWARENESS:
            evaluation = self._awareness.evaluate(event, state_before)
            awareness_events, queued = self._record_awareness(event, evaluation)
            if _proof_scoped and not queued:
                proof_reassertion = memory_from_observation(
                    event,
                    state_before,
                    self.bus.events,
                    allow_reassertion=True,
                )
                if proof_reassertion is not None:
                    queued = (*queued, proof_reassertion)
            emitted.extend(awareness_events)
            for queued_draft in queued:
                self.bus.enqueue(queued_draft)
            updates.update(
                {
                    "operational_awareness": evaluation.awareness,
                    "environment": _environment_with_contradictions(
                        evaluation.environment, awareness_events
                    ),
                    "attention": evaluation.attention,
                }
            )
            if isinstance(event.payload, ModelTerminalPayload):
                if event.payload.previous_terminal_id != state_before.cognition_terminal.terminal_id:
                    raise StaleEntityStateError("model terminal predecessor does not match current state")
                updates["cognition_terminal"] = CognitionTerminalState(
                    terminal_id=event.payload.terminal_id,
                    provider=event.payload.provider,
                    model=event.payload.model,
                    mode=event.payload.mode,
                    authority_effect="NONE",
                )
        elif selected is LoopName.BECOMING:
            evaluation = self._becoming.evaluate(event, state_before)
            verification = retention_verification(
                event,
                state_before,
                evaluation.memory,
                self.bus.events,
                allow_reassertion=_proof_scoped,
                verified_at_utc=evaluation_at_utc,
            )
            if verification is not None:
                self.bus.enqueue(verification)
            becoming_events = self._record_becoming(event, evaluation)
            emitted.extend(becoming_events)
            for request_event in becoming_events:
                if (
                    request_event.event_type is EventType.OWNER_AUTHORITY_REQUEST
                    and isinstance(request_event.payload, AuthorityPayload)
                ):
                    self.bus.enqueue(
                        EntityEventDraft(
                            event_type=EventType.NOTIFICATION,
                            occurred_at_utc=request_event.occurred_at_utc,
                            originating_loop=LoopName.BECOMING,
                            source=EventEndpoint(kind=EventSourceKind.SE6, identifier="SE6"),
                            target=request_event.target,
                            relation="notifies_owner_of_authority_request",
                            provenance=ObservationProvenance.SYSTEM_OBSERVED,
                            epistemic_status=EpistemicStatus.DETERMINISTIC,
                            authority_status=AuthorityStatus.REQUESTED,
                            correlation_id=request_event.correlation_id,
                            causal_id=request_event.event_id,
                            parent_event_id=request_event.event_id,
                            sensitivity=SensitivityClassification.INTERNAL,
                            persistence_policy=PersistencePolicy.SESSION,
                            payload=InteractionPayload(
                                interaction_kind=InteractionKind.NOTIFICATION_INTENT,
                                thread_id=state_before.conversation.current_thread_id,
                                text=(
                                    f"Owner authority is requested for capability "
                                    f"{request_event.payload.capability}."
                                ),
                                basis_event_ids=(request_event.event_id,),
                                initiated_by_se6=True,
                                initiation_reason=(
                                    "A recurring verified failure produced a typed capability gap."
                                ),
                            ),
                        )
                    )
            updates.update(
                self._becoming_updates(state_before, evaluation, becoming_events)
            )
        status = (
            (
                CoordinatorStepStatus.APPLIED_LOCAL_LIVE
                if state_before.operating_mode is EntityOperatingMode.LOCAL_LIVE
                else CoordinatorStepStatus.APPLIED_SHADOW
            )
            if selected is not None
            else CoordinatorStepStatus.NO_ELIGIBLE_LOOP
        )
        if len(emitted) > self.policy.max_derived_events_per_step:
            raise EventBusBackpressure("derived event bound exceeded")
        head = emitted[-1] if emitted else event
        # Only the audited proof-control transaction may persist this alternate
        # accounting path. Ordinary store commits still require a global charge.
        updates["resources"] = (state_before.resources if _proof_scoped
                                else _consume_event_budget(state_before.resources))
        updates["loop_states"] = _advanced_loop_states(
            state_before.loop_states,
            selected=selected,
            event_id=head.event_id,
            at=head.occurred_at_utc,
            awaiting_authority=bool(
                selected is LoopName.BECOMING
                and any(item.event_type is EventType.OWNER_AUTHORITY_REQUEST for item in emitted)
            ),
        )
        updates["continuation"] = _continuation_after_step(
            state_before.continuation,
            processed=event,
            emitted=tuple(emitted),
            queued=self.bus.pending_drafts,
            selected=selected,
            at=head.occurred_at_utc,
        )
        self.state = advance_entity_state(
            state_before,
            expected_state_version=expected,
            event_head_id=head.event_id,
            event_sequence=head.sequence,
            updated_at_utc=head.occurred_at_utc,
            **updates,
        )
        material = {
            "schema_version": COORDINATOR_SCHEMA_VERSION,
            "state_before_id": state_before.entity_state_id,
            "state_after_id": self.state.entity_state_id,
            "processed_event_id": event.event_id,
            "selected_loop": selected,
            "priority": priority,
            "status": status,
            "emitted_event_ids": tuple(item.event_id for item in emitted),
            "communication_intents": intents,
            "processed_at_utc": head.occurred_at_utc,
            "production_state_changed": False,
            "identity_state_advanced": False,
            "approval_consumed": False,
            "external_effect_performed": False,
            "network_used": False,
            "model_calls": 0,
        }
        draft_result = CoordinatorStepResult.model_construct(
            result_id=f"coordinator_result_{'0' * 64}", **material
        )
        normalized = draft_result.material_fields()
        digest = canonical_sha256(normalized)
        return CoordinatorStepResult.model_validate(
            {"result_id": f"coordinator_result_{digest}", **normalized}
        )

    def run_bounded(self, *, max_steps: int) -> tuple[CoordinatorStepResult, ...]:
        """Drain at most ``max_steps``; this is a bounded for-loop, not polling."""

        if max_steps < 0:
            raise ValueError("max_steps must be nonnegative")
        results: list[CoordinatorStepResult] = []
        for _ in range(max_steps):
            if not self.bus.queued_count:
                break
            results.append(self.run_step())
        return tuple(results)

    def _publish_intent(
        self, cause: EntityEvent, intent: CommunicationIntent
    ) -> EntityEvent:
        draft = EntityEventDraft(
            event_type=EventType.INTERACTION,
            occurred_at_utc=cause.occurred_at_utc,
            originating_loop=LoopName.PRESENCE,
            source=EventEndpoint(kind=EventSourceKind.SE6, identifier="SE6"),
            target=cause.source,
            relation="communicates_with",
            provenance=ObservationProvenance.SYSTEM_OBSERVED,
            epistemic_status=EpistemicStatus.DETERMINISTIC,
            authority_status=AuthorityStatus.NOT_REQUIRED,
            correlation_id=cause.correlation_id,
            causal_id=cause.event_id,
            parent_event_id=cause.event_id,
            sensitivity=SensitivityClassification.INTERNAL,
            persistence_policy=PersistencePolicy.SESSION,
            payload=InteractionPayload(
                interaction_kind=intent.interaction_kind,
                thread_id=intent.thread_id,
                text=intent.text,
                basis_event_ids=intent.basis_event_ids,
                initiated_by_se6=intent.initiated_by_se6,
                initiation_reason=intent.initiation_reason,
            ),
        )
        return self.bus.publish(draft)

    def _presence_updates(
        self,
        state: SE6EntityState,
        event: EntityEvent,
        intent_event: EntityEvent,
    ) -> _EntityStateUpdates:
        recent = state.conversation.recent_event_ids
        for item in (event.event_id, intent_event.event_id):
            recent = _bounded_append(recent, item, 64)
        decisions = state.conversation.owner_decision_event_ids
        authority = state.authority
        development = state.developmental
        pending = state.pending_proposals
        if isinstance(event.payload, AuthorityPayload):
            authority = AuthorityState(
                owner_identity_reference=authority.owner_identity_reference,
                pending_request_event_ids=_bounded_append(
                    authority.pending_request_event_ids, event.event_id, 64
                ),
                decision_event_ids=authority.decision_event_ids,
                master_boundary_required=True,
                loops_may_grant_authority=False,
            )
            if not any(item.proposal_event_id == event.event_id for item in pending):
                pending = (*pending, PendingProposal(
                    proposal_event_id=event.event_id,
                    status=ProposalStatus.AWAITING_OWNER,
                    requested_capability=event.payload.capability,
                    requires_master_boundary=True,
                    production_effect_authorized=False,
                ))
        if isinstance(event.payload, ApprovalPayload):
            decisions = _bounded_append(decisions, event.event_id, 64)
            authority = AuthorityState(
                owner_identity_reference=authority.owner_identity_reference,
                pending_request_event_ids=tuple(
                    item
                    for item in authority.pending_request_event_ids
                    if item != event.payload.request_event_id
                ),
                decision_event_ids=_bounded_append(
                    authority.decision_event_ids, event.event_id, 128
                ),
                master_boundary_required=True,
                loops_may_grant_authority=False,
            )
            denied = event.payload.disposition is ApprovalDisposition.DENIED
            pending = tuple(
                item.model_copy(
                    update={
                        "status": (
                            ProposalStatus.DENIED
                            if denied
                            else ProposalStatus.AWAITING_BOUNDARY
                        )
                    }
                )
                if item.proposal_event_id == event.payload.request_event_id
                else item
                for item in pending
            )
            if denied:
                development = DevelopmentalState(
                    failure_patterns=development.failure_patterns,
                    development_needs=development.development_needs,
                    candidate_event_ids=development.candidate_event_ids,
                    denied_request_event_ids=_bounded_append(
                        development.denied_request_event_ids, event.event_id, 256
                    ),
                )
        objectives = state.current_objectives
        unresolved = state.unresolved_objectives
        if isinstance(event.payload, ObjectivePayload):
            status_by_operation: Mapping[
                ObjectiveOperation,
                Literal["ACTIVE", "BLOCKED", "COMPLETED", "WITHDRAWN"],
            ] = {
                ObjectiveOperation.RECORD: "ACTIVE",
                ObjectiveOperation.BLOCK: "BLOCKED",
                ObjectiveOperation.COMPLETE: "COMPLETED",
                ObjectiveOperation.WITHDRAW: "WITHDRAWN",
            }
            status = status_by_operation[event.payload.operation]
            objective = EntityObjective(
                objective_id=event.payload.objective_id,
                summary=event.payload.summary,
                status=status,
                source_event_id=event.event_id,
                required_capabilities=event.payload.required_capabilities,
            )
            objectives = tuple(
                item for item in objectives if item.objective_id != objective.objective_id
            )
            unresolved = tuple(
                item for item in unresolved if item.objective_id != objective.objective_id
            )
            if status in {"ACTIVE", "BLOCKED"}:
                objectives = (*objectives, objective)
            if status == "BLOCKED":
                unresolved = (*unresolved, objective)
        conversation = ConversationState(
            current_thread_id=state.conversation.current_thread_id,
            last_interaction_event_id=intent_event.event_id,
            unresolved_questions=state.conversation.unresolved_questions,
            commitments=state.conversation.commitments,
            owner_decision_event_ids=decisions,
            pending_follow_up=state.conversation.pending_follow_up,
            durable_summary=state.conversation.durable_summary,
            recent_event_ids=recent,
        )
        return {
            "conversation": conversation,
            "current_objectives": objectives,
            "unresolved_objectives": unresolved,
            "authority": authority,
            "developmental": development,
            "pending_proposals": pending,
        }

    def _record_awareness(
        self, cause: EntityEvent, evaluation: _AwarenessEvaluation
    ) -> tuple[tuple[EntityEvent, ...], tuple[EntityEventDraft, ...]]:
        emitted: list[EntityEvent] = []
        attention_event = self.bus.publish(
            _derived_draft(
                cause,
                event_type=EventType.RELEVANCE,
                loop=LoopName.AWARENESS,
                relation="assesses_relevance_of",
                payload=AttentionPayload(
                    subject_event_id=cause.event_id,
                    dimensions=evaluation.relevance.dimensions,
                    score=evaluation.relevance.score,
                    outcome=evaluation.relevance.outcome,
                    rationale_codes=evaluation.relevance.rationale_codes,
                    authority_effect="NONE",
                ),
            )
        )
        emitted.append(attention_event)
        if evaluation.awareness is not self.state.operational_awareness:
            awareness_event = self.bus.publish(
                _derived_draft(
                    cause,
                    event_type=EventType.AWARENESS_UPDATE,
                    loop=LoopName.AWARENESS,
                    relation="proposes_awareness_projection",
                    payload=AwarenessPayload(
                        previous_awareness_state_id=self.state.operational_awareness.awareness_state_id,
                        proposed_awareness_state_id=evaluation.awareness.awareness_state_id,
                        observation_event_ids=(cause.event_id,),
                        contradiction_event_ids=(),
                        authority_effect="NONE",
                    ),
                )
            )
            emitted.append(awareness_event)
        if evaluation.contradiction and isinstance(cause.payload, ObservationPayload):
            contradiction_event = self.bus.publish(
                EntityEventDraft(
                    event_type=EventType.CONTRADICTION,
                    occurred_at_utc=cause.occurred_at_utc,
                    originating_loop=LoopName.AWARENESS,
                    source=EventEndpoint(kind=EventSourceKind.SE6, identifier="SE6"),
                    target=EventEndpoint(
                        kind=EventSourceKind.COMPONENT,
                        identifier=cause.payload.world_node,
                    ),
                    relation="contradicts_prior_relation",
                    provenance=ObservationProvenance.CONTRADICTED,
                    epistemic_status=EpistemicStatus.DETERMINISTIC,
                    authority_status=AuthorityStatus.NOT_REQUIRED,
                    correlation_id=cause.correlation_id,
                    causal_id=cause.event_id,
                    parent_event_id=cause.event_id,
                    sensitivity=SensitivityClassification.INTERNAL,
                    persistence_policy=PersistencePolicy.DURABLE_CANDIDATE,
                    payload=ObservationPayload(
                        world_node=cause.payload.world_node,
                        relation=cause.payload.relation,
                        value_summary=(
                            "A newer reported value differs from the prior mapped value; "
                            "neither difference alone grants VERIFIED status."
                        ),
                        provenance=ObservationProvenance.CONTRADICTED,
                        observed_at_utc=cause.occurred_at_utc,
                        evidence_references=(),
                        current_claim=True,
                        confidence_basis_points=10_000,
                    ),
                )
            )
            emitted.append(contradiction_event)
        queued: list[EntityEventDraft] = []
        learning = memory_from_observation(cause, self.state, self.bus.events)
        if learning is not None:
            queued.append(learning)
        if evaluation.notify and learning is None:
            queued.append(
                EntityEventDraft(
                    event_type=EventType.NOTIFICATION,
                    occurred_at_utc=cause.occurred_at_utc,
                    originating_loop=LoopName.AWARENESS,
                    source=EventEndpoint(kind=EventSourceKind.SE6, identifier="SE6"),
                    target=EventEndpoint(
                        kind=EventSourceKind.PROGRAMMERONE,
                        identifier=self.state.identity.owner_identity_reference,
                    ),
                    relation="requests_grounded_notification",
                    provenance=ObservationProvenance.SYSTEM_OBSERVED,
                    epistemic_status=EpistemicStatus.DETERMINISTIC,
                    authority_status=AuthorityStatus.NOT_REQUIRED,
                    correlation_id=cause.correlation_id,
                    causal_id=cause.event_id,
                    parent_event_id=cause.event_id,
                    sensitivity=SensitivityClassification.INTERNAL,
                    persistence_policy=PersistencePolicy.SESSION,
                    payload=InteractionPayload(
                        interaction_kind=InteractionKind.NOTIFICATION_INTENT,
                        thread_id=self.state.conversation.current_thread_id,
                        text=(
                            f"A relevant change was observed at {cause.payload.world_node}: "
                            f"{cause.payload.value_summary}"
                        ) if isinstance(cause.payload, ObservationPayload) else (
                            "A relevant internal state change requires attention."
                        ),
                        basis_event_ids=(cause.event_id,),
                        initiated_by_se6=True,
                        initiation_reason="The bounded relevance policy selected NOTIFY.",
                    ),
                )
            )
        return tuple(emitted), tuple(queued)

    def _record_becoming(
        self, cause: EntityEvent, evaluation: _BecomingEvaluation
    ) -> tuple[EntityEvent, ...]:
        emitted: list[EntityEvent] = []
        if (
            isinstance(cause.payload, VerificationPayload)
            and evaluation.memory is not self.state.memory
            and evaluation.memory.records
        ):
            newest = evaluation.memory.records[-1]
            emitted.append(
                self.bus.publish(
                    _derived_draft(
                        cause,
                        event_type=EventType.MEMORY_CONSOLIDATION,
                        loop=LoopName.BECOMING,
                        relation="proposes_verified_memory",
                        payload=MemoryPayload(
                            operation=MemoryEventOperation.CONSOLIDATE,
                            subject=newest.subject,
                            content_summary=newest.content_summary,
                            source_event_ids=newest.source_event_ids,
                            evidence_references=newest.evidence_references,
                            supersedes_memory_id=None,
                            revokes_memory_id=None,
                            authority_effect="NONE",
                        ),
                        provenance=ObservationProvenance.INDEPENDENTLY_VERIFIED,
                        epistemic_status=EpistemicStatus.VERIFIED,
                        persistence=PersistencePolicy.DURABLE_CANDIDATE,
                    )
                )
            )
        if evaluation.need_created is not None:
            need = evaluation.need_created
            emitted.append(
                self.bus.publish(
                    _derived_draft(
                        cause,
                        event_type=EventType.DEVELOPMENT_NEED,
                        loop=LoopName.BECOMING,
                        relation="detects_development_need",
                        payload=DevelopmentPayload(
                            need_kind=need.need_kind,
                            pattern_key=need.pattern_key,
                            verified_occurrences=len(need.verified_evidence_event_ids),
                            required_capability=need.required_capability,
                            blocked_objective=None,
                            evidence_event_ids=need.verified_evidence_event_ids,
                            proposal_only=True,
                            authority_effect="NONE",
                        ),
                        persistence=PersistencePolicy.DURABLE_CANDIDATE,
                    )
                )
            )
        if evaluation.capability_request is not None:
            emitted.append(
                self.bus.publish(
                    EntityEventDraft(
                        event_type=EventType.OWNER_AUTHORITY_REQUEST,
                        occurred_at_utc=cause.occurred_at_utc,
                        originating_loop=LoopName.BECOMING,
                        source=EventEndpoint(kind=EventSourceKind.SE6, identifier="SE6"),
                        target=EventEndpoint(
                            kind=EventSourceKind.PROGRAMMERONE,
                            identifier=self.state.identity.owner_identity_reference,
                        ),
                        relation="requests_owner_authority_for",
                        provenance=ObservationProvenance.SYSTEM_OBSERVED,
                        epistemic_status=EpistemicStatus.DETERMINISTIC,
                        authority_status=AuthorityStatus.REQUESTED,
                        correlation_id=cause.correlation_id,
                        causal_id=cause.event_id,
                        parent_event_id=cause.event_id,
                        sensitivity=SensitivityClassification.INTERNAL,
                        persistence_policy=PersistencePolicy.DURABLE_CANDIDATE,
                        payload=evaluation.capability_request,
                    )
                )
            )
        return tuple(emitted)

    def _becoming_updates(
        self,
        state: SE6EntityState,
        evaluation: _BecomingEvaluation,
        events: Sequence[EntityEvent],
    ) -> _EntityStateUpdates:
        authority = state.authority
        pending = state.pending_proposals
        request = next(
            (item for item in events if item.event_type is EventType.OWNER_AUTHORITY_REQUEST),
            None,
        )
        development = evaluation.developmental
        if request is not None and isinstance(request.payload, AuthorityPayload):
            authority = AuthorityState(
                owner_identity_reference=authority.owner_identity_reference,
                pending_request_event_ids=_bounded_append(
                    authority.pending_request_event_ids, request.event_id, 64
                ),
                decision_event_ids=authority.decision_event_ids,
                master_boundary_required=True,
                loops_may_grant_authority=False,
            )
            pending = (*pending, PendingProposal(
                proposal_event_id=request.event_id,
                status=ProposalStatus.AWAITING_OWNER,
                requested_capability=request.payload.capability,
                requires_master_boundary=True,
                production_effect_authorized=False,
            ))
            development_event = next(
                (item for item in events if item.event_type is EventType.DEVELOPMENT_NEED),
                None,
            )
            if development_event is not None:
                development = DevelopmentalState(
                    failure_patterns=development.failure_patterns,
                    development_needs=development.development_needs,
                    candidate_event_ids=_bounded_append(
                        development.candidate_event_ids, development_event.event_id, 256
                    ),
                    denied_request_event_ids=development.denied_request_event_ids,
                )
        return {
            "memory": evaluation.memory,
            "developmental": development,
            "authority": authority,
            "pending_proposals": pending,
        }


def _continuation_after_step(
    current: EntityContinuationState,
    *,
    processed: EntityEvent,
    emitted: tuple[EntityEvent, ...],
    queued: tuple[EntityEventDraft, ...],
    selected: LoopName | None,
    at: datetime,
) -> EntityContinuationState:
    """Project one bounded, interruptible next posture from durable work.

    This is scheduling metadata only.  It does not execute the posture, start a
    model loop, grant authority, or create an observation.
    """

    event_types = {item.event_type for item in emitted}
    queued_types = {item.event_type for item in queued}
    if processed.event_type is EventType.STOP:
        posture = "STOP"
    elif processed.event_type in {EventType.PAUSE, EventType.INTERRUPTION}:
        posture = "PAUSE"
    elif EventType.OWNER_AUTHORITY_REQUEST in event_types | queued_types:
        posture = "REQUEST_AUTHORITY"
    elif EventType.NOTIFICATION in queued_types:
        posture = "NOTIFY"
    elif selected is LoopName.AWARENESS:
        posture = "OBSERVE"
    elif selected is LoopName.BECOMING:
        posture = "BECOME"
    else:
        posture = "REST"
    if posture in {"REST", "OBSERVE"}:
        backoff = min(3_600, max(1, current.backoff_seconds * 2))
        next_wake = at + timedelta(seconds=backoff)
    else:
        backoff = 30
        next_wake = None
    return EntityContinuationState(
        state=posture,
        last_basis_event_id=(emitted[-1].event_id if emitted else processed.event_id),
        next_wake_at_utc=next_wake,
        backoff_seconds=backoff,
        wake_count=current.wake_count + 1,
        bounded=True,
        interruptible=True,
        model_loop_allowed=False,
        authority_effect="NONE",
    )


def create_communication_intent(**fields: object) -> CommunicationIntent:
    material = dict(fields)
    material.setdefault("authority_effect", "NONE")
    material.setdefault("external_effect", "NONE")
    digest = canonical_sha256(material)
    return CommunicationIntent.model_validate(
        {"intent_id": f"communication_intent_{digest}", **material}
    )


def priority_for(draft: EntityEventDraft) -> SchedulerPriority:
    if draft.event_type in {EventType.STOP, EventType.PAUSE}:
        return SchedulerPriority.EMERGENCY_SAFETY
    if draft.event_type is EventType.INTERRUPTION:
        return SchedulerPriority.OWNER_INTERRUPT
    if draft.event_type in {
        EventType.USER_MESSAGE,
        EventType.INTERACTION,
        EventType.NOTIFICATION,
        EventType.APPROVAL,
        EventType.OWNER_AUTHORITY_REQUEST,
        EventType.OBJECTIVE,
    }:
        return SchedulerPriority.ACTIVE_INTERACTION
    if draft.event_type in {
        EventType.OBSERVATION,
        EventType.ENVIRONMENT_CHANGE,
        EventType.MODEL_TERMINAL_CHANGED,
    }:
        payload = draft.payload
        if isinstance(payload, ObservationPayload) and _critical_observation(payload):
            return SchedulerPriority.CRITICAL_OBSERVATION
        return SchedulerPriority.NORMAL_AWARENESS
    if draft.event_type in {EventType.VERIFICATION, EventType.OBSERVED_CONSEQUENCE}:
        return SchedulerPriority.PENDING_VERIFICATION
    if draft.event_type in {
        EventType.MEMORY_CANDIDATE,
        EventType.MEMORY_CONSOLIDATION,
        EventType.MEMORY_REVOCATION,
        EventType.MEMORY_STALE,
        EventType.MEMORY_EXPIRED,
        EventType.MEMORY_CONTRADICTED,
        EventType.DEVELOPMENT_NEED,
        EventType.DEVELOPMENT_CANDIDATE,
        EventType.GERMINATION_REQUEST,
        EventType.EMBODIMENT_REQUEST,
    }:
        return SchedulerPriority.DEVELOPMENT
    return SchedulerPriority.REST


def eligible_loop_for(event: EntityEvent, state: SE6EntityState) -> LoopName | None:
    if event.event_type in {
        EventType.USER_MESSAGE,
        EventType.INTERACTION,
        EventType.NOTIFICATION,
        EventType.INTERRUPTION,
        EventType.APPROVAL,
        EventType.OWNER_AUTHORITY_REQUEST,
        EventType.CAPABILITY_REQUEST,
        EventType.OBJECTIVE,
    }:
        return LoopName.PRESENCE
    if event.event_type in {
        EventType.OBSERVATION,
        EventType.ENVIRONMENT_CHANGE,
        EventType.ATTENTION,
        EventType.RELEVANCE,
        EventType.AWARENESS_UPDATE,
        EventType.PERSPECTIVE_REQUEST,
        EventType.CONTRADICTION,
        EventType.LIFECYCLE,
        EventType.RECOVERY,
        EventType.REST,
        EventType.PAUSE,
        EventType.RESUME,
        EventType.STOP,
        EventType.MODEL_TERMINAL_CHANGED,
    }:
        return LoopName.AWARENESS
    if event.event_type is EventType.VERIFICATION:
        payload = event.payload
        if (
            isinstance(payload, VerificationPayload)
            and payload.independently_verified
            and payload.evidence_references
            and state.lifecycle.emergency_stop.value == "ARMED"
        ):
            return LoopName.BECOMING
        return LoopName.AWARENESS
    if event.event_type in {
        EventType.ASSIMILATION,
        EventType.MEMORY_CANDIDATE,
        EventType.MEMORY_CONSOLIDATION,
        EventType.MEMORY_REVOCATION,
        EventType.MEMORY_STALE,
        EventType.MEMORY_EXPIRED,
        EventType.MEMORY_CONTRADICTED,
        EventType.DEVELOPMENT_NEED,
        EventType.DEVELOPMENT_CANDIDATE,
        EventType.GERMINATION_REQUEST,
        EventType.EMBODIMENT_REQUEST,
    }:
        return LoopName.BECOMING
    return None


def assess_relevance(
    event: EntityEvent,
    state: SE6EntityState,
    *,
    contradiction: bool,
) -> RelevanceAssessment:
    if not isinstance(event.payload, ObservationPayload):
        return _minimal_relevance(event)
    payload = event.payload
    objective_text = " ".join(
        item.summary.lower()
        for item in (*state.current_objectives, *state.unresolved_objectives)
    )
    observation_text = f"{payload.world_node} {payload.relation} {payload.value_summary}".lower()
    objective = 70 if any(
        token in observation_text
        for token in _tokens(objective_text)
        if len(token) >= 4
    ) else 20
    owner = 100 if payload.world_node.lower() in {
        "programmerone",
        state.identity.owner_identity_reference.lower(),
    } else 20
    critical = _critical_observation(payload)
    recurrence = min(
        100,
        20 * sum(
            1
            for item in state.environment.relations
            if item.world_node == payload.world_node and item.relation == payload.relation
        ),
    )
    dimensions = RelevanceDimensions(
        objective=objective,
        owner=owner,
        urgency=100 if critical else (60 if payload.current_claim else 10),
        novelty=100 if _current_relation(state.environment, payload.world_node, payload.relation) is None else 20,
        contradiction=100 if contradiction else 0,
        risk=100 if critical else 20,
        consequence=90 if critical else 40,
        temporal_sensitivity=80 if payload.current_claim else 20,
        confidence=payload.confidence_basis_points // 100,
        recurrence=recurrence,
    )
    score = sum(dimensions.model_dump(mode="python").values()) // 10
    rationale: list[str] = []
    if critical:
        rationale.append("CRITICAL_SAFETY_OR_RUNTIME_SIGNAL")
    if contradiction:
        rationale.append("CONTRADICTION_DETECTED")
    if dimensions.novelty == 100:
        rationale.append("NOVEL_RELATION")
    if owner == 100:
        rationale.append("OWNER_RELEVANT")
    return RelevanceAssessment(
        subject_event_id=event.event_id,
        dimensions=dimensions,
        score=score,
        outcome=_outcome_for(dimensions, score),
        rationale_codes=tuple(rationale),
        authority_effect="NONE",
    )


def _minimal_relevance(event: EntityEvent) -> RelevanceAssessment:
    dimensions = RelevanceDimensions(
        objective=0,
        owner=0,
        urgency=0,
        novelty=0,
        contradiction=0,
        risk=0,
        consequence=0,
        temporal_sensitivity=0,
        confidence=0,
        recurrence=0,
    )
    return RelevanceAssessment(
        subject_event_id=event.event_id,
        dimensions=dimensions,
        score=0,
        outcome=RelevanceOutcome.IGNORE,
        rationale_codes=("NO_OBSERVATION_PAYLOAD",),
        authority_effect="NONE",
    )


def _outcome_for(dimensions: RelevanceDimensions, score: int) -> RelevanceOutcome:
    if dimensions.risk >= 90 or dimensions.contradiction >= 90:
        return RelevanceOutcome.NOTIFY
    if score >= 70:
        return RelevanceOutcome.NOTIFY
    if score >= 50:
        return RelevanceOutcome.MAP
    if score >= 30:
        return RelevanceOutcome.RECORD_PROVISIONALLY
    if score >= 10:
        return RelevanceOutcome.EPHEMERAL
    return RelevanceOutcome.IGNORE


def _presence_intent_from_interaction(
    event: EntityEvent,
    payload: InteractionPayload,
    state: SE6EntityState,
) -> CommunicationIntent:
    learned = learning_response(event, state)
    if learned is not None:
        text, references = learned
        return create_communication_intent(
            interaction_kind=InteractionKind.RESPONSE_INTENT,
            thread_id=payload.thread_id, text=text,
            basis_event_ids=tuple(dict.fromkeys((event.event_id, *references))),
            initiated_by_se6=False, initiation_reason=None,
        )
    if event.event_type is EventType.INTERRUPTION or payload.interaction_kind is InteractionKind.EXPRESSION_INTERRUPTED:
        text = "Expression stopped. The underlying SE6 state and reasoning record were not revoked."
        kind = InteractionKind.ACKNOWLEDGEMENT_INTENT
    elif event.event_type is EventType.NOTIFICATION:
        text = payload.text
        kind = InteractionKind.NOTIFICATION_INTENT
    else:
        lowered = payload.text.casefold()
        if "who are you" in lowered:
            text = (
                "I am SE6, represented here by the persistent IdentityState "
                f"{state.identity.identity_state_id}. My cognition terminal is "
                f"{state.cognition_terminal.terminal_id}; it is not my identity."
            )
        elif "where are you" in lowered:
            text = (
                f"I am situated in local instance {state.identity.instance_id}. "
                f"My operational relation is {state.lifecycle.operational_state.value}; "
                "online observation is unavailable."
            )
        elif "what state are you in" in lowered:
            text = (
                f"Entity mode: {state.operating_mode.value}. Runtime lifecycle: "
                f"{state.lifecycle.durable_state.value}. Controller: "
                f"{state.lifecycle.controller_status.value}. Presence: "
                f"{state.loop_states.presence.status}. Awareness: "
                f"{state.loop_states.awareness.status}. Becoming: "
                f"{state.loop_states.becoming.status}."
            )
        elif "what are you doing" in lowered:
            objectives = tuple(
                item.summary for item in state.current_objectives if item.status == "ACTIVE"
            )
            objective = objectives[0] if objectives else "No active objective is recorded."
            text = (
                f"Operational state: {state.lifecycle.operational_state.value}. "
                f"Durable lifecycle: {state.lifecycle.durable_state.value}. "
                f"Current objective: {objective}"
            )
        elif "what happened while i was gone" in lowered:
            text = (
                f"The retained event history contains {state.event_sequence} events, "
                f"{len(state.environment.observation_event_ids)} observations, "
                f"{len(state.environment.contradiction_event_ids)} contradictions, and "
                f"{len(state.developmental.development_needs)} development proposals. "
                "Only verified records are treated as verified facts."
            )
        elif "what are you waiting for" in lowered:
            text = (
                f"Continuation state: {state.continuation.state}. "
                f"Pending owner requests: {len(state.authority.pending_request_event_ids)}. "
                f"Pending follow-ups: {len(state.conversation.pending_follow_up)}. "
                f"Unresolved objectives: {len(state.unresolved_objectives)}."
            )
        elif "what objectives are unresolved" in lowered:
            summaries = tuple(item.summary for item in state.unresolved_objectives)
            text = (
                "Unresolved objectives: " + " | ".join(summaries)
                if summaries
                else "No unresolved objective is recorded."
            )
        elif "what are you uncertain about" in lowered:
            unknown = tuple(state.uncertainty.unknown)
            text = (
                "Recorded uncertainty: " + " | ".join(unknown)
                if unknown
                else "No explicit uncertainty item is recorded."
            )
        elif "what permissions do you currently have" in lowered:
            available = tuple(
                item.capability
                for item in state.capabilities.capabilities
                if item.available
                and item.authority_status in {
                    AuthorityStatus.NOT_REQUIRED,
                    AuthorityStatus.GRANTED_RECORDED,
                }
            )
            text = (
                "Current bounded capabilities with recorded authority status: "
                + (", ".join(available) if available else "none")
                + ". Network authority is "
                + state.environment_access.network_authority
                + "."
            )
        elif "what do you know happened" in lowered:
            verified = tuple(
                item.content_summary
                for item in state.memory.active_records
                if item.epistemic_status is EpistemicStatus.VERIFIED
            )
            text = (
                "Verified current history: " + " | ".join(verified)
                if verified
                else "No current independently verified memory is recorded."
            )
        elif "what do you only predict" in lowered:
            predicted = tuple(
                item.content_summary
                for item in state.memory.active_records
                if item.epistemic_status in {
                    EpistemicStatus.MODEL_PROPOSED,
                    EpistemicStatus.INFERRED,
                    EpistemicStatus.PREDICTED,
                }
            )
            text = (
                "Predicted or inferred material: " + " | ".join(predicted)
                if predicted
                else "No current predicted material is recorded."
            )
        elif "what has changed" in lowered:
            text = (
                f"The durable entity lineage is at state version {state.state_version} "
                f"and event sequence {state.event_sequence}. It records "
                f"{len(state.environment.observation_event_ids)} observations, "
                f"{len(state.environment.contradiction_event_ids)} contradictions, and "
                f"{len(state.memory.records)} memory records."
            )
        elif "what do you need from me" in lowered:
            pending = state.authority.pending_request_event_ids
            text = (
                f"There are {len(pending)} unresolved typed owner-authority requests."
                if pending
                else "No owner-authority request is currently recorded."
            )
        elif any(word in lowered for word in ("hello", "hi ", "hi,")) or lowered.strip() == "hi":
            text = (
                "Hello, ProgrammerOne. I am responding from the current bounded SE6 state; "
                "this response intent grants no authority."
            )
        else:
            text = (
                "I received the message. "
                f"My recorded operational state is {state.lifecycle.operational_state.value}; "
                "no external action was taken."
            )
        kind = InteractionKind.RESPONSE_INTENT
    return create_communication_intent(
        interaction_kind=kind,
        thread_id=payload.thread_id,
        text=text,
        basis_event_ids=(event.event_id,),
        initiated_by_se6=event.event_type is EventType.NOTIFICATION,
        initiation_reason=(
            payload.initiation_reason
            if event.event_type is EventType.NOTIFICATION
            else None
        ),
    )


def _project_awareness(
    event: EntityEvent,
    state: SE6EntityState,
    relevance: RelevanceAssessment,
):
    payload = event.payload
    if not isinstance(payload, ObservationPayload):
        return state.operational_awareness
    prior = state.operational_awareness
    verified = (
        payload.provenance is ObservationProvenance.INDEPENDENTLY_VERIFIED
        and event.epistemic_status is EpistemicStatus.VERIFIED
        and bool(payload.evidence_references)
    )
    observation_status = ObservationStatus.VERIFIED if verified else ObservationStatus.REPORTED
    confidence = payload.confidence_basis_points / 10_000.0
    uncertainty = UncertaintyRecord(
        status=EpistemicStatus.DETERMINISTIC,
        confidence=confidence,
        known=(
            "The observation event and its provenance were supplied to the shadow loop.",
        ),
        unknown=(
            ()
            if verified
            else ("The reported observation has not been independently verified.",)
        ),
        assumptions=(),
        inferences=(f"Relevance outcome: {relevance.outcome.value}.",),
        symbolic=("Mirror and perspective transformations remain advisory.",),
        evidence_references=payload.evidence_references if verified else (),
    )
    stated = prior.stated_intention.value or ""
    return build_operational_awareness_state(
        stated_intention=stated,
        interpreted_objective=(
            f"Map the relationship between SE6 and {payload.world_node} without action."
        ),
        objective_status=EpistemicStatus.DETERMINISTIC,
        objective_confidence=1.0,
        cognition_mode="offline_fallback",
        current_state_present=True,
        classification="operational_observation",
        classification_status=EpistemicStatus.DETERMINISTIC,
        classification_confidence=confidence,
        uncertainty=uncertainty,
        mirrors=reflect_task(payload.value_summary),
        perspectives=rotate_perspectives(payload.value_summary),
        runtime_decision=prior.boundary.runtime_decision,
        effective_decision=prior.boundary.effective_decision,
        authority_level=prior.boundary.authority_level,
        boundary_reasons=prior.boundary.reasons,
        approval_required=prior.boundary.approval_required,
        lifecycle=prior.self_location.lifecycle,
        available_tools=prior.self_location.available_tools,
        established_permissions=prior.self_location.established_permissions,
        unresolved_requests=prior.self_location.unresolved_requests,
        observation_status=observation_status,
        observation_summary=observation_summary(payload),
        observation_result_type=payload.provenance.value,
        observation_evidence_references=(
            payload.evidence_references if verified else ()
        ),
        previous_awareness_state_id=prior.awareness_state_id,
        observed_at_utc=event.occurred_at_utc,
    )


def _derived_draft(
    cause: EntityEvent,
    *,
    event_type: EventType,
    loop: LoopName,
    relation: str,
    payload: EventPayload,
    provenance: ObservationProvenance = ObservationProvenance.SYSTEM_OBSERVED,
    epistemic_status: EpistemicStatus = EpistemicStatus.DETERMINISTIC,
    persistence: PersistencePolicy = PersistencePolicy.SESSION,
) -> EntityEventDraft:
    return EntityEventDraft(
        event_type=event_type,
        occurred_at_utc=cause.occurred_at_utc,
        originating_loop=loop,
        source=EventEndpoint(kind=EventSourceKind.SE6, identifier="SE6"),
        target=EventEndpoint(kind=EventSourceKind.COMPONENT, identifier="SE6EntityState"),
        relation=relation,
        provenance=provenance,
        epistemic_status=epistemic_status,
        authority_status=AuthorityStatus.NOT_REQUIRED,
        correlation_id=cause.correlation_id,
        causal_id=cause.event_id,
        parent_event_id=cause.event_id,
        sensitivity=SensitivityClassification.INTERNAL,
        persistence_policy=persistence,
        payload=payload,
    )


def _bounded_environment_relations(relations):
    """Bound the active projection without evicting a current relationship.

    Superseded versions remain in immutable source events and predecessor
    states. Keep at least five versions per key so the existing recurrence
    score (min(100, 20*count)) is exactly preserved. If no such lossless-for-
    consumers compaction exists, fail atomically instead of raising the cap.
    """
    rows = list(relations)
    while len(rows) > 512:
        counts = {}
        for row in rows:
            key = (row.world_node, row.relation)
            counts[key] = counts.get(key, 0) + 1
        index = next((i for i, row in enumerate(rows)
                      if not row.current and row.superseded_by is not None
                      and counts[(row.world_node, row.relation)] > 5), None)
        if index is None:
            raise ValueError("ENVIRONMENT_RELATION_CAPACITY_EXHAUSTED")
        rows.pop(index)
    return tuple(rows)


def _environment_with_contradictions(
    environment: EnvironmentState, events: Sequence[EntityEvent]
) -> EnvironmentState:
    contradiction_ids = environment.contradiction_event_ids
    for event in events:
        if event.event_type is EventType.CONTRADICTION:
            contradiction_ids = _bounded_append(contradiction_ids, event.event_id, 256)
    return EnvironmentState(
        relations=environment.relations,
        observation_event_ids=environment.observation_event_ids,
        contradiction_event_ids=contradiction_ids,
    )


def _append_attention(
    attention: AttentionState, assessment: RelevanceAssessment
) -> AttentionState:
    records = (*attention.records, AttentionRecord(
        subject_event_id=assessment.subject_event_id,
        score=assessment.score,
        outcome=assessment.outcome,
        rationale_codes=assessment.rationale_codes,
    ))
    records = records[-256:]
    focused = tuple(
        item.subject_event_id
        for item in records
        if item.outcome not in {RelevanceOutcome.IGNORE, RelevanceOutcome.EPHEMERAL}
    )[-16:]
    return AttentionState(records=records, current_focus_event_ids=focused)


def _advanced_loop_states(
    loops: LoopStateBundle,
    *,
    selected: LoopName | None,
    event_id: str,
    at: datetime,
    awaiting_authority: bool,
) -> LoopStateBundle:
    def advance(item: LoopRuntimeState, status: str) -> LoopRuntimeState:
        if item.loop is not selected:
            return item
        return LoopRuntimeState(
            loop=item.loop,
            mode=item.mode,
            status=status,
            active_event_id=None,
            last_event_id=event_id,
            last_transition_at_utc=at,
            work_units_consumed=item.work_units_consumed + 1,
            wake_count=item.wake_count + 1,
            authority_effect="NONE",
        )

    return LoopStateBundle(
        presence=advance(loops.presence, PresenceLoopStatus.LISTENING.value),
        awareness=advance(loops.awareness, AwarenessLoopStatus.OBSERVING.value),
        becoming=advance(
            loops.becoming,
            (
                BecomingLoopStatus.AWAITING_AUTHORITY.value
                if awaiting_authority
                else BecomingLoopStatus.RESTING.value
            ),
        ),
    )


def _consume_event_budget(resources: ResourceAccountingState) -> ResourceAccountingState:
    return resources.model_copy(
        update={"events_processed": resources.events_processed + 1}
    )


def _draft_order_key(draft: EntityEventDraft) -> tuple[int, datetime, str]:
    priority = priority_for(draft)
    return (
        _PRIORITY_RANK[priority],
        draft.occurred_at_utc,
        canonical_sha256(draft),
    )


def _critical_observation(payload: ObservationPayload) -> bool:
    text = f"{payload.world_node} {payload.relation} {payload.value_summary}".casefold()
    return any(
        token in text
        for token in (
            "emergency",
            "integrity failure",
            "unsafe",
            "controller lost",
            "recovery required",
            "budget breach",
        )
    )


def _current_relation(
    environment: EnvironmentState, world_node: str, relation: str
) -> WorldRelation | None:
    return next(
        (
            item
            for item in reversed(environment.relations)
            if item.current and item.world_node == world_node and item.relation == relation
        ),
        None,
    )


def _epistemic_for_observation(payload: ObservationPayload) -> EpistemicStatus:
    return {
        ObservationProvenance.SYSTEM_OBSERVED: EpistemicStatus.MEASURED,
        ObservationProvenance.USER_REPORTED: EpistemicStatus.USER_SUPPLIED,
        ObservationProvenance.MODEL_INFERRED: EpistemicStatus.INFERRED,
        ObservationProvenance.MODEL_PREDICTED: EpistemicStatus.MODEL_PROPOSED,
        ObservationProvenance.EXTERNAL_RETRIEVED: EpistemicStatus.MEASURED,
        ObservationProvenance.INDEPENDENTLY_VERIFIED: EpistemicStatus.VERIFIED,
        ObservationProvenance.CONTRADICTED: EpistemicStatus.UNKNOWN,
        ObservationProvenance.UNKNOWN: EpistemicStatus.UNKNOWN,
    }[payload.provenance]


def _capability_for_failure(pattern_key: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", ".", pattern_key.casefold()).strip(".")
    return f"capability.{slug or 'unknown_failure'}"


def _capability_available(
    capabilities: Sequence[CapabilityView], capability: str
) -> bool:
    return any(item.capability == capability and item.available for item in capabilities)


def _bounded_append(values: tuple[str, ...], value: str, limit: int) -> tuple[str, ...]:
    if value in values:
        return values
    return (*values, value)[-limit:]


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[a-z0-9]+", value.casefold()))


def _utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


__all__ = [
    "RELEVANCE_POLICY_VERSION",
    "CommunicationIntent",
    "CoordinatorPolicy",
    "CoordinatorStepResult",
    "CoordinatorStepStatus",
    "DevelopmentalAssimilationLoop",
    "DuplicateEntityEvent",
    "EventBusBackpressure",
    "InMemoryEntityEventBus",
    "InteractivePresenceLoop",
    "InvalidCausalEvent",
    "OperationalAwarenessLoop",
    "RelevanceAssessment",
    "ResourceBudgetExceeded",
    "SE6TriLoopCoordinator",
    "SchedulerPriority",
    "assess_relevance",
    "create_communication_intent",
    "eligible_loop_for",
    "priority_for",
]
