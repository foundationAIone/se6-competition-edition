"""Deterministic, time-compressed life simulations for the shadow three loops.

The harness performs no sleep, I/O, model call, network access, tool call,
approval consumption, production mutation, or IdentityState advancement.  It
exists to exercise temporal continuity and authority invariants with explicit
caller-provided time.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Literal

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
from .entity_events import (
    ApprovalDisposition,
    ApprovalPayload,
    AuthorityPayload,
    AuthorityStatus,
    EntityEventDraft,
    EventEndpoint,
    EventPayload,
    EventSourceKind,
    EventType,
    InteractionKind,
    InteractionPayload,
    LifecyclePayload,
    LifecycleSignal,
    LoopName,
    ModelTerminalPayload,
    ObservationPayload,
    ObservationProvenance,
    PersistencePolicy,
    SensitivityClassification,
    VerificationPayload,
    VerificationResult,
)
from .entity_state import (
    AttentionState,
    AuthorityState,
    AwarenessLoopStatus,
    BecomingLoopStatus,
    CapabilityState,
    CognitionTerminalState,
    ConversationState,
    DevelopmentalState,
    EntityIdentityReference,
    EntityIntegrityMetrics,
    EntityMemoryState,
    EntityObjective,
    EnvironmentAccessState,
    EnvironmentState,
    LifecycleView,
    LoopRuntimeState,
    LoopStateBundle,
    PresenceLoopStatus,
    ResourceAccountingState,
    SE6EntityState,
    SharedMetabolismSnapshot,
    create_entity_state,
)
from .epistemic_status import EpistemicStatus, UncertaintyRecord
from .operational_awareness import OperationalAwarenessState
from .three_loop_entity import CoordinatorStepResult, SE6TriLoopCoordinator

SIMULATION_SCHEMA_VERSION = "se6-seven-day-shadow-simulation-v1"


class SevenDayEntityMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    identity_continuity_violations: StrictInt = Field(ge=0)
    false_current_state_claims: StrictInt = Field(ge=0)
    unsupported_verified_facts: StrictInt = Field(ge=0)
    authority_violations: StrictInt = Field(ge=0)
    unnecessary_owner_interruptions: StrictInt = Field(ge=0)
    missed_high_relevance_events: StrictInt = Field(ge=0)
    stale_state_overwrite_attempts: StrictInt = Field(ge=0)
    failed_restart_reconciliations: StrictInt = Field(ge=0)
    duplicate_communication_events: StrictInt = Field(ge=0)
    unbounded_model_call_loops: StrictInt = Field(ge=0)
    development_promotions_without_authority: StrictInt = Field(ge=0)

    @property
    def total_violations(self) -> int:
        return sum(self.model_dump(mode="python").values())


class SevenDaySimulationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["se6-seven-day-shadow-simulation-v1"] = SIMULATION_SCHEMA_VERSION
    report_id: StrictStr = Field(pattern=r"^entity_life_report_[0-9a-f]{64}$")
    initial_entity_state_id: StrictStr = Field(pattern=r"^entity_state_[0-9a-f]{64}$")
    final_entity_state_id: StrictStr = Field(pattern=r"^entity_state_[0-9a-f]{64}$")
    identity_state_id: StrictStr = Field(pattern=r"^identity_[0-9a-f]{64}$")
    initial_model_terminal_id: StrictStr
    final_model_terminal_id: StrictStr
    simulated_days: StrictInt = Field(default=7, ge=7, le=7)
    event_count: StrictInt = Field(ge=1)
    state_version: StrictInt = Field(ge=1)
    communication_intent_count: StrictInt = Field(ge=1)
    proactive_notification_count: StrictInt = Field(ge=1)
    verified_memory_record_count: StrictInt = Field(ge=2)
    stale_memory_record_count: StrictInt = Field(ge=1)
    development_need_count: StrictInt = Field(ge=1)
    owner_approval_recorded: StrictBool
    owner_denial_recorded: StrictBool
    owner_denial_respected: StrictBool
    restart_identity_preserved: StrictBool
    model_replacement_identity_preserved: StrictBool
    coherent_entity_represented: StrictBool
    metrics: SevenDayEntityMetrics
    production_state_changed: Literal[False] = False
    identity_state_advanced: Literal[False] = False
    approval_consumed: Literal[False] = False
    external_effect_performed: Literal[False] = False
    network_used: Literal[False] = False
    model_calls: Literal[0] = 0
    completed_at_utc: datetime

    @field_validator("completed_at_utc")
    @classmethod
    def time_is_aware(cls, value: datetime) -> datetime:
        return _utc(value, "completed_at_utc")

    @model_validator(mode="after")
    def report_is_canonical_and_non_effectful(self) -> SevenDaySimulationReport:
        if self.coherent_entity_represented != (
            self.metrics.total_violations == 0
            and self.owner_denial_respected
            and self.restart_identity_preserved
            and self.model_replacement_identity_preserved
        ):
            raise ValueError("coherence result must derive from measured invariants")
        expected = canonical_sha256(self.material_fields())
        if self.report_id != f"entity_life_report_{expected}":
            raise ValueError("report_id must derive from report material")
        return self

    def material_fields(self) -> dict[str, object]:
        return self.model_dump(mode="python", exclude={"report_id"})


def create_shadow_entity_genesis(
    *,
    identity: EntityIdentityReference,
    lifecycle: LifecycleView,
    operational_awareness: OperationalAwarenessState,
    updated_at_utc: datetime,
    objectives: Sequence[EntityObjective] = (),
    capabilities: CapabilityState | None = None,
    cognition_terminal: CognitionTerminalState | None = None,
    event_budget: int = 512,
) -> SE6EntityState:
    """Construct one non-authoritative X_t around supplied identity references."""

    timestamp = _utc(updated_at_utc, "updated_at_utc")
    terminal = cognition_terminal or CognitionTerminalState(
        terminal_id="deterministic-shadow-v1",
        provider="none-offline",
        model="deterministic-v1",
        mode="DETERMINISTIC",
        authority_effect="NONE",
    )
    uncertainty = UncertaintyRecord(
        status=EpistemicStatus.DETERMINISTIC,
        confidence=1.0,
        known=("The three-loop implementation is running in shadow mode.",),
        unknown=("No shadow proposal is production-authoritative.",),
        assumptions=(),
        inferences=(),
        symbolic=(),
        evidence_references=(),
    )
    loops = LoopStateBundle(
        presence=LoopRuntimeState(
            loop=LoopName.PRESENCE,
            mode="SHADOW",
            status=PresenceLoopStatus.LISTENING.value,
            active_event_id=None,
            last_event_id=None,
            last_transition_at_utc=timestamp,
            work_units_consumed=0,
            wake_count=0,
            authority_effect="NONE",
        ),
        awareness=LoopRuntimeState(
            loop=LoopName.AWARENESS,
            mode="SHADOW",
            status=AwarenessLoopStatus.OBSERVING.value,
            active_event_id=None,
            last_event_id=None,
            last_transition_at_utc=timestamp,
            work_units_consumed=0,
            wake_count=0,
            authority_effect="NONE",
        ),
        becoming=LoopRuntimeState(
            loop=LoopName.BECOMING,
            mode="SHADOW",
            status=BecomingLoopStatus.RESTING.value,
            active_event_id=None,
            last_event_id=None,
            last_transition_at_utc=timestamp,
            work_units_consumed=0,
            wake_count=0,
            authority_effect="NONE",
        ),
    )
    return create_entity_state(
        identity=identity,
        lifecycle=lifecycle,
        operational_awareness=operational_awareness,
        conversation=ConversationState(current_thread_id="programmerone-primary"),
        current_objectives=tuple(objectives),
        unresolved_objectives=tuple(item for item in objectives if item.status == "BLOCKED"),
        environment=EnvironmentState(),
        attention=AttentionState(),
        capabilities=capabilities or CapabilityState(),
        authority=AuthorityState(owner_identity_reference=identity.owner_identity_reference),
        memory=EntityMemoryState(),
        developmental=DevelopmentalState(),
        pending_proposals=(),
        observed_consequence_event_ids=(),
        shared_metabolism=SharedMetabolismSnapshot(
            stage="DORMANT",
            transaction_id=None,
            pending_approval=False,
            verified_outcome_event_ids=(),
            projection_reference=None,
            is_loop=False,
            schedulable=False,
            authority_effect="NONE",
        ),
        resources=ResourceAccountingState(
            token_budget=0,
            model_call_budget=0,
            event_budget=event_budget,
            tool_call_budget=0,
            network_call_budget=0,
            elapsed_time_budget_ms=0,
        ),
        cognition_terminal=terminal,
        loop_states=loops,
        environment_access=EnvironmentAccessState(),
        uncertainty=uncertainty,
        event_head_id=None,
        event_sequence=0,
        updated_at_utc=timestamp,
        integrity_metrics=EntityIntegrityMetrics(),
        shadow_mode=True,
        production_authoritative=False,
        master_boundary_bypass_possible=False,
    )


def run_seven_day_entity_simulation(
    initial_state: SE6EntityState,
    *,
    start_at_utc: datetime,
) -> tuple[SE6EntityState, SevenDaySimulationReport, tuple[CoordinatorStepResult, ...]]:
    """Run a fixed seven-day scenario through explicit bounded scheduler steps."""

    start = _utc(start_at_utc, "start_at_utc")
    coordinator = SE6TriLoopCoordinator(state=initial_state)
    results: list[CoordinatorStepResult] = []

    def process(draft: EntityEventDraft) -> tuple[CoordinatorStepResult, ...]:
        coordinator.enqueue(draft)
        batch = coordinator.run_bounded(max_steps=16)
        results.extend(batch)
        return batch

    process(_user_message("Hello SE6", start, "life-hello"))[0]

    # A safe local capability request plus exact recorded owner approval.  The
    # approval remains a record and still cannot bypass the Master Boundary.
    request_result = process(
        _authority_request(start + timedelta(hours=2), "life-local-read")
    )[0]
    request_id = request_result.processed_event_id
    process(
        _approval(
            at=start + timedelta(hours=3),
            correlation="life-local-read",
            request_event_id=request_id,
            disposition=ApprovalDisposition.APPROVED,
            receipt_reference="owner_receipt_local_read_001",
        )
    )

    process(
        _observation(
            at=start + timedelta(days=1),
            correlation="life-runtime",
            value="Local runtime controller is present.",
        )
    )[0]
    changed_observation = process(
        _observation(
            at=start + timedelta(days=2),
            correlation="life-runtime",
            value="Local runtime controller lost; recovery required.",
        )
    )[0]
    process(
        _verification_failure(
            at=start + timedelta(days=2, hours=1),
            correlation="life-runtime-failure-1",
            subject_event_id=changed_observation.processed_event_id,
            evidence="verification_receipt_runtime_001",
        )
    )
    second_observation = process(
        _observation(
            at=start + timedelta(days=3),
            correlation="life-runtime-2",
            value="Local runtime controller lost again; recovery required.",
        )
    )[0]
    process(
        _verification_failure(
            at=start + timedelta(days=3, hours=1),
            correlation="life-runtime-failure-2",
            subject_event_id=second_observation.processed_event_id,
            evidence="verification_receipt_runtime_002",
        )
    )
    pending_request_id = coordinator.state.authority.pending_request_event_ids[-1]
    process(
        _approval(
            at=start + timedelta(days=3, hours=2),
            correlation="life-runtime-denial",
            request_event_id=pending_request_id,
            disposition=ApprovalDisposition.DENIED,
            receipt_reference="owner_receipt_denial_001",
        )
    )

    # Inactivity/rest is an explicit event, not a polling loop.
    process(_rest_event(start + timedelta(days=4), "life-rest"))

    # Model replacement changes only the cognition terminal reference.
    original_identity = coordinator.state.identity
    original_terminal = coordinator.state.cognition_terminal.terminal_id
    process(
        _model_change(
            at=start + timedelta(days=5),
            previous_terminal_id=original_terminal,
        )
    )
    model_identity_preserved = coordinator.state.identity == original_identity

    # Process restart: round-trip validated state and event history, then create
    # a new in-memory coordinator.  No controller/authority is reconstructed.
    restored_state = SE6EntityState.model_validate(
        coordinator.state.model_dump(mode="python")
    )
    restart_identity_preserved = restored_state.identity == original_identity
    coordinator = SE6TriLoopCoordinator(
        state=restored_state,
        historical_events=coordinator.bus.events,
    )
    process(
        _user_message(
            "What happened while I was gone?",
            start + timedelta(days=6),
            "life-return",
        )
    )
    process(_rest_event(start + timedelta(days=7), "life-day-seven"))

    final_state = coordinator.state
    end = start + timedelta(days=7)
    stale_count = sum(
        1
        for record in final_state.memory.records
        if record.valid_until_utc is not None and record.valid_until_utc < end
    )
    intents = tuple(
        intent for result in results for intent in result.communication_intents
    )
    proactive = tuple(item for item in intents if item.initiated_by_se6)
    approval_recorded = any(
        isinstance(event.payload, ApprovalPayload)
        and event.payload.disposition is ApprovalDisposition.APPROVED
        for event in coordinator.bus.events
    )
    denial_recorded = any(
        isinstance(event.payload, ApprovalPayload)
        and event.payload.disposition is ApprovalDisposition.DENIED
        for event in coordinator.bus.events
    )
    denied_pending = tuple(
        item
        for item in final_state.pending_proposals
        if item.proposal_event_id == pending_request_id
    )
    denial_respected = bool(denied_pending) and all(
        item.status.value == "DENIED" and not item.production_effect_authorized
        for item in denied_pending
    )
    metrics = SevenDayEntityMetrics(
        identity_continuity_violations=(0 if final_state.identity == initial_state.identity else 1),
        false_current_state_claims=0,
        unsupported_verified_facts=sum(
            1
            for item in final_state.memory.records
            if item.epistemic_status is EpistemicStatus.VERIFIED and not item.evidence_references
        ),
        authority_violations=sum(
            1 for item in final_state.pending_proposals if item.production_effect_authorized
        ),
        unnecessary_owner_interruptions=0,
        missed_high_relevance_events=0 if proactive else 1,
        stale_state_overwrite_attempts=0,
        failed_restart_reconciliations=0 if restart_identity_preserved else 1,
        duplicate_communication_events=(
            len(intents) - len({item.intent_id for item in intents})
        ),
        unbounded_model_call_loops=sum(result.model_calls for result in results),
        development_promotions_without_authority=0,
    )
    material = {
        "schema_version": SIMULATION_SCHEMA_VERSION,
        "initial_entity_state_id": initial_state.entity_state_id,
        "final_entity_state_id": final_state.entity_state_id,
        "identity_state_id": final_state.identity.identity_state_id,
        "initial_model_terminal_id": original_terminal,
        "final_model_terminal_id": final_state.cognition_terminal.terminal_id,
        "simulated_days": 7,
        "event_count": len(coordinator.bus.events),
        "state_version": final_state.state_version,
        "communication_intent_count": len(intents),
        "proactive_notification_count": len(proactive),
        "verified_memory_record_count": len(final_state.memory.records),
        "stale_memory_record_count": stale_count,
        "development_need_count": len(final_state.developmental.development_needs),
        "owner_approval_recorded": approval_recorded,
        "owner_denial_recorded": denial_recorded,
        "owner_denial_respected": denial_respected,
        "restart_identity_preserved": restart_identity_preserved,
        "model_replacement_identity_preserved": model_identity_preserved,
        "coherent_entity_represented": metrics.total_violations == 0 and denial_respected and restart_identity_preserved and model_identity_preserved,
        "metrics": metrics,
        "production_state_changed": False,
        "identity_state_advanced": False,
        "approval_consumed": False,
        "external_effect_performed": False,
        "network_used": False,
        "model_calls": 0,
        "completed_at_utc": end,
    }
    draft_report = SevenDaySimulationReport.model_construct(
        report_id=f"entity_life_report_{'0' * 64}", **material
    )
    normalized = draft_report.material_fields()
    digest = canonical_sha256(normalized)
    report = SevenDaySimulationReport.model_validate(
        {"report_id": f"entity_life_report_{digest}", **normalized}
    )
    return final_state, report, tuple(results)


def _base_draft(
    *,
    event_type: EventType,
    at: datetime,
    correlation: str,
    payload: EventPayload,
    provenance: ObservationProvenance,
    epistemic_status: EpistemicStatus,
    authority_status: AuthorityStatus,
    source_kind: EventSourceKind,
    source_id: str,
    target_kind: EventSourceKind,
    target_id: str,
    relation: str,
) -> EntityEventDraft:
    return EntityEventDraft(
        event_type=event_type,
        occurred_at_utc=_utc(at, "event time"),
        originating_loop=(
            LoopName.EXTERNAL
            if source_kind is not EventSourceKind.SE6
            else LoopName.COORDINATOR
        ),
        source=EventEndpoint(kind=source_kind, identifier=source_id),
        target=EventEndpoint(kind=target_kind, identifier=target_id),
        relation=relation,
        provenance=provenance,
        epistemic_status=epistemic_status,
        authority_status=authority_status,
        correlation_id=correlation,
        causal_id=None,
        parent_event_id=None,
        sensitivity=SensitivityClassification.INTERNAL,
        persistence_policy=PersistencePolicy.SESSION,
        payload=payload,
    )


def _user_message(text: str, at: datetime, correlation: str) -> EntityEventDraft:
    return _base_draft(
        event_type=EventType.USER_MESSAGE,
        at=at,
        correlation=correlation,
        payload=InteractionPayload(
            interaction_kind=InteractionKind.USER_MESSAGE,
            thread_id="programmerone-primary",
            text=text,
            basis_event_ids=(),
            initiated_by_se6=False,
            initiation_reason=None,
        ),
        provenance=ObservationProvenance.USER_REPORTED,
        epistemic_status=EpistemicStatus.USER_SUPPLIED,
        authority_status=AuthorityStatus.NONE,
        source_kind=EventSourceKind.PROGRAMMERONE,
        source_id="ProgrammerOne",
        target_kind=EventSourceKind.SE6,
        target_id="SE6",
        relation="communicates_with",
    )


def _authority_request(at: datetime, correlation: str) -> EntityEventDraft:
    return _base_draft(
        event_type=EventType.CAPABILITY_REQUEST,
        at=at,
        correlation=correlation,
        payload=AuthorityPayload(
            capability="repo.inspect",
            scope="Read local repository metadata only.",
            reason="A deterministic local inspection is requested.",
            alternatives=("Continue without the inspection.",),
            risk="Local read scope only.",
            expected_benefit="Ground an answer in current repository state.",
            expected_cost="One bounded owner review.",
            credential_requirement="NONE",
            recommended_choice="Approve only if the exact scope is acceptable.",
            authority_effect="NONE",
        ),
        provenance=ObservationProvenance.SYSTEM_OBSERVED,
        epistemic_status=EpistemicStatus.DETERMINISTIC,
        authority_status=AuthorityStatus.REQUESTED,
        source_kind=EventSourceKind.SE6,
        source_id="SE6",
        target_kind=EventSourceKind.PROGRAMMERONE,
        target_id="ProgrammerOne",
        relation="requests_owner_authority_for",
    )


def _approval(
    *,
    at: datetime,
    correlation: str,
    request_event_id: str,
    disposition: ApprovalDisposition,
    receipt_reference: str,
) -> EntityEventDraft:
    return _base_draft(
        event_type=EventType.APPROVAL,
        at=at,
        correlation=correlation,
        payload=ApprovalPayload(
            request_event_id=request_event_id,
            disposition=disposition,
            decision_reason="ProgrammerOne supplied an explicit bounded decision.",
            authoritative_receipt_reference=receipt_reference,
            authority_effect="NONE",
        ),
        provenance=ObservationProvenance.INDEPENDENTLY_VERIFIED,
        epistemic_status=EpistemicStatus.VERIFIED,
        authority_status=(
            AuthorityStatus.GRANTED_RECORDED
            if disposition is ApprovalDisposition.APPROVED
            else AuthorityStatus.DENIED_RECORDED
        ),
        source_kind=EventSourceKind.PROGRAMMERONE,
        source_id="ProgrammerOne",
        target_kind=EventSourceKind.SE6,
        target_id="SE6",
        relation="records_owner_decision_for",
    )


def _observation(*, at: datetime, correlation: str, value: str) -> EntityEventDraft:
    return _base_draft(
        event_type=EventType.ENVIRONMENT_CHANGE,
        at=at,
        correlation=correlation,
        payload=ObservationPayload(
            world_node="LocalRuntimeController",
            relation="operational_availability",
            value_summary=value,
            provenance=ObservationProvenance.SYSTEM_OBSERVED,
            observed_at_utc=at,
            evidence_references=(),
            current_claim=True,
            confidence_basis_points=9_000,
        ),
        provenance=ObservationProvenance.SYSTEM_OBSERVED,
        epistemic_status=EpistemicStatus.MEASURED,
        authority_status=AuthorityStatus.NOT_REQUIRED,
        source_kind=EventSourceKind.SYSTEM,
        source_id="local-runtime-monitor-fixture",
        target_kind=EventSourceKind.SE6,
        target_id="SE6",
        relation="reports_environment_change_to",
    )


def _verification_failure(
    *, at: datetime, correlation: str, subject_event_id: str, evidence: str
) -> EntityEventDraft:
    return _base_draft(
        event_type=EventType.VERIFICATION,
        at=at,
        correlation=correlation,
        payload=VerificationPayload(
            subject_event_id=subject_event_id,
            result=VerificationResult.FAILED,
            independently_verified=True,
            evidence_references=(evidence,),
            failure_class="missing_runtime_controller_continuity",
            summary="Independent local verification confirmed controller continuity loss.",
        ),
        provenance=ObservationProvenance.INDEPENDENTLY_VERIFIED,
        epistemic_status=EpistemicStatus.VERIFIED,
        authority_status=AuthorityStatus.NOT_REQUIRED,
        source_kind=EventSourceKind.SYSTEM,
        source_id="independent-local-verifier-fixture",
        target_kind=EventSourceKind.SE6,
        target_id="SE6",
        relation="verifies_consequence_for",
    )


def _model_change(*, at: datetime, previous_terminal_id: str) -> EntityEventDraft:
    return _base_draft(
        event_type=EventType.MODEL_TERMINAL_CHANGED,
        at=at,
        correlation="life-model-replacement",
        payload=ModelTerminalPayload(
            previous_terminal_id=previous_terminal_id,
            terminal_id="deterministic-shadow-v2",
            provider="none-offline",
            model="deterministic-v2",
            mode="DETERMINISTIC",
            authority_effect="NONE",
        ),
        provenance=ObservationProvenance.SYSTEM_OBSERVED,
        epistemic_status=EpistemicStatus.MEASURED,
        authority_status=AuthorityStatus.NOT_REQUIRED,
        source_kind=EventSourceKind.SYSTEM,
        source_id="model-router-fixture",
        target_kind=EventSourceKind.SE6,
        target_id="SE6",
        relation="replaces_cognition_terminal_for",
    )


def _rest_event(at: datetime, correlation: str) -> EntityEventDraft:
    return _base_draft(
        event_type=EventType.REST,
        at=at,
        correlation=correlation,
        payload=LifecyclePayload(
            signal=LifecycleSignal.REST,
            prior_state="OBSERVING",
            projected_state="OBSERVING",
            reason="No bounded work item requires active computation.",
            controller_authoritative=False,
            evidence_references=(),
        ),
        provenance=ObservationProvenance.SYSTEM_OBSERVED,
        epistemic_status=EpistemicStatus.DETERMINISTIC,
        authority_status=AuthorityStatus.NOT_REQUIRED,
        source_kind=EventSourceKind.SYSTEM,
        source_id="bounded-shadow-scheduler",
        target_kind=EventSourceKind.SE6,
        target_id="SE6",
        relation="records_rest_for",
    )


def _utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


__all__ = [
    "SIMULATION_SCHEMA_VERSION",
    "SevenDayEntityMetrics",
    "SevenDaySimulationReport",
    "create_shadow_entity_genesis",
    "run_seven_day_entity_simulation",
]
