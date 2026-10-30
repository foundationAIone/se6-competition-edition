"""Bounded local runtime adapter for the durable SE6 three-loop entity.

The reducer remains pure in :mod:`three_loop_entity`; this module supplies the
small I/O boundary needed to durably enqueue one event and atomically commit
one reducer step.  It has no network, subprocess, shell, provider, model, LIVE
LOOP, or production-control capability.  Construction grants no authority.

``LocalEntitySupervisor`` is event driven.  Each wake processes a fixed number
of already-durable ingresses and then rests.  Its wait loop never calls a
model, never invents an observation, and is interruptible through one event.
"""

from __future__ import annotations

import logging
import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from enum import Enum
from threading import Event, RLock, Thread
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
from .dashboard_read_timing import read_count, read_span
from .entity_cognition import EvidenceSourceKind, MemoryStatus
from .entity_cognition_store import CognitionStoreError, EntityCognitionStore
from .entity_activation import (
    EntityActivationEvidenceBundle,
    EntityActivationRecord,
)
from .entity_events import (
    ApprovalDisposition,
    ApprovalPayload,
    AuthorityStatus,
    EntityEvent,
    EntityEventDraft,
    EventEndpoint,
    EventSourceKind,
    EventType,
    InteractionKind,
    InteractionPayload,
    LocalEventBudgetRenewalPayload,
    LoopName,
    MemoryEventOperation,
    MemoryPayload,
    ModelTerminalPayload,
    ObjectiveOperation,
    ObjectivePayload,
    ObservationPayload,
    ObservationProvenance,
    PersistencePolicy,
    SensitivityClassification,
    VerificationPayload,
    VerificationResult,
)
from .entity_state import (
    ControllerStatus,
    EmergencyStopState,
    EntityOperatingMode,
    LifecycleView,
    OperationalConnectionState,
    SE6EntityState,
    SharedMetabolismSnapshot,
)
from .entity_store import (
    EntityCommitReceipt,
    EntityIngressRecord,
    EntityOutboxDeliveryRecord,
    EntityOutboxRecord,
    EntityRestartSnapshot,
    EntityStore,
    EntityStoreError,
    EntityStoreIntegrityResult,
)
from .epistemic_status import EpistemicStatus
from .three_loop_entity import (
    CoordinatorPolicy,
    CoordinatorStepResult,
    SE6TriLoopCoordinator,
    ResourceBudgetExceeded,
)

ENTITY_RUNTIME_SCHEMA_VERSION = "se6-local-entity-runtime-v1"
ENTITY_PROJECTION_SCHEMA_VERSION = "se6-local-entity-projection-v1"


class EntityRuntimeError(RuntimeError):
    """Stable, non-secret failure at the durable reducer boundary."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class EntityPresenceStatus(str, Enum):
    ABSENT = "ABSENT"
    SHADOW_READY = "SHADOW_READY"
    PRESENT = "PRESENT"
    DEGRADED = "DEGRADED"
    STOPPED = "STOPPED"


class LocalEntityRuntimePolicy(BaseModel):
    """Fixed bounds for one local entity adapter."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["se6-local-entity-runtime-policy-v1"] = (
        "se6-local-entity-runtime-policy-v1"
    )
    max_steps_per_wake: StrictInt = Field(default=8, ge=1, le=64)
    idle_wait_seconds: StrictInt = Field(default=30, ge=1, le=3_600)
    maximum_pending_ingress: StrictInt = Field(default=256, ge=1, le=10_000)
    network_calls_allowed: Literal[False] = False
    model_calls_allowed: Literal[False] = False
    subprocess_allowed: Literal[False] = False
    shell_allowed: Literal[False] = False
    production_effects_allowed: Literal[False] = False


class EntityStepCommit(BaseModel):
    """One fully committed reducer step and its local projections."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["se6-local-entity-step-commit-v1"] = (
        "se6-local-entity-step-commit-v1"
    )
    ingress: EntityIngressRecord
    result: CoordinatorStepResult
    receipt: EntityCommitReceipt
    state: SE6EntityState
    events: tuple[EntityEvent, ...] = Field(min_length=1, max_length=33)
    new_outbox: tuple[EntityOutboxRecord, ...] = Field(default=(), max_length=8)

    @model_validator(mode="after")
    def bindings_match(self) -> EntityStepCommit:
        if self.receipt.processed_ingress_id != self.ingress.ingress_id:
            raise ValueError("step receipt does not bind the processed ingress")
        if self.receipt.coordinator_result_id != self.result.result_id:
            raise ValueError("step receipt does not bind the coordinator result")
        if self.receipt.state_after_id != self.state.entity_state_id:
            raise ValueError("step receipt does not bind the current state")
        if tuple(item.event_id for item in self.events) != (
            (self.result.processed_event_id,) + self.result.emitted_event_ids
        ):
            raise ValueError("step events do not match the reducer result")
        if tuple(item.outbox_id for item in self.new_outbox) != self.receipt.outbox_ids:
            raise ValueError("step outbox does not match the commit receipt")
        return self


class LocalEntityProjection(BaseModel):
    """Truthful backend projection; PRESENT is an exact multi-gate status."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["se6-local-entity-projection-v1"] = (
        ENTITY_PROJECTION_SCHEMA_VERSION
    )
    projection_id: StrictStr = Field(pattern=r"^entity_projection_[0-9a-f]{64}$")
    status: EntityPresenceStatus
    entity_present: StrictBool
    entity_state_id: StrictStr | None = Field(
        default=None, pattern=r"^entity_state_[0-9a-f]{64}$"
    )
    entity_state_hash: StrictStr | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    state_version: StrictInt | None = Field(default=None, ge=0)
    runtime_session_id: StrictStr = Field(min_length=1, max_length=512)
    operating_mode: EntityOperatingMode | None = None
    identity_state_id: StrictStr | None = Field(
        default=None, pattern=r"^identity_[0-9a-f]{64}$"
    )
    presence_status: StrictStr = Field(min_length=1, max_length=64)
    awareness_status: StrictStr = Field(min_length=1, max_length=64)
    becoming_status: StrictStr = Field(min_length=1, max_length=64)
    continuation_state: StrictStr = Field(min_length=1, max_length=64)
    pending_ingress_count: StrictInt = Field(ge=0)
    undelivered_notification_count: StrictInt = Field(ge=0)
    current_objective_count: StrictInt = Field(ge=0)
    unresolved_objective_count: StrictInt = Field(ge=0)
    attention_record_count: StrictInt = Field(ge=0)
    event_sequence: StrictInt = Field(ge=0)
    store_integrity: Literal["VALID", "INVALID", "ABSENT"]
    event_processor_available: StrictBool
    presence_path_available: StrictBool
    awareness_path_available: StrictBool
    continuation_available: StrictBool
    supervisor_active: StrictBool
    network_authority: Literal["NONE"] = "NONE"
    online_observation_enabled: Literal[False] = False
    external_requests: Literal["BLOCKED"] = "BLOCKED"
    integrity_violation_count: StrictInt = Field(ge=0)
    projected_at_utc: datetime
    reason_codes: tuple[StrictStr, ...] = Field(default=(), max_length=32)
    authority_effect: Literal["NONE"] = "NONE"

    @field_validator("projected_at_utc")
    @classmethod
    def time_is_aware(cls, value: datetime) -> datetime:
        return _utc(value, "projected_at_utc")

    @model_validator(mode="after")
    def present_is_not_cosmetic(self) -> LocalEntityProjection:
        exact = (
            self.status is EntityPresenceStatus.PRESENT
            and self.entity_state_id is not None
            and self.entity_state_hash is not None
            and self.operating_mode is EntityOperatingMode.LOCAL_LIVE
            and self.store_integrity == "VALID"
            and self.event_processor_available
            and self.presence_path_available
            and self.awareness_path_available
            and self.continuation_available
            and self.supervisor_active
            and self.integrity_violation_count == 0
            and not self.reason_codes
        )
        if self.entity_present != exact:
            raise ValueError("ENTITY PRESENT projection does not match exact gates")
        expected = canonical_sha256(self.material_fields())
        if self.projection_id != f"entity_projection_{expected}":
            raise ValueError("projection_id must derive from projection material")
        return self

    def material_fields(self) -> dict[str, object]:
        return self.model_dump(mode="python", exclude={"projection_id"})


class LocalEntityRuntime:
    """Serializes durable ingress and pure reducer commits under one lock."""

    def __init__(
        self,
        *,
        store: EntityStore,
        runtime_session_id: str,
        policy: LocalEntityRuntimePolicy | None = None,
        coordinator_policy: CoordinatorPolicy | None = None,
        clock: Callable[[], datetime] | None = None,
        authority_guard: Callable[[str], bool] | None = None,
        cognition_store: EntityCognitionStore | None = None,
    ) -> None:
        if not runtime_session_id or len(runtime_session_id) > 512:
            raise ValueError("runtime_session_id is invalid")
        self.store = store
        self.runtime_session_id = runtime_session_id
        self.policy = policy or LocalEntityRuntimePolicy()
        self.coordinator_policy = coordinator_policy or CoordinatorPolicy()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._authority_guard = authority_guard
        self.cognition_store = cognition_store
        self._lock = RLock()
        # A read already owns an immutable, audited snapshot. It must not wait
        # for a reducer/SQLite commit merely to observe these process flags.
        # Writers acquire _lock then _projection_lock; projection never acquires
        # the writer lock or performs store I/O while holding _projection_lock.
        self._projection_lock = RLock()
        self._wake_callback: Callable[[], None] | None = None
        self._supervisor_active = False
        self._stopped = False

    def initialize(self, *, state: SE6EntityState) -> EntityCommitReceipt:
        """Create a store and its one genesis; never infer activation evidence."""

        with self._lock:
            if self._stopped:
                raise EntityRuntimeError("ENTITY_RUNTIME_STOPPED")
            self.require_authority()
            self.store.initialize_schema()
            return self.store.commit_genesis(
                state=state,
                runtime_session_id=self.runtime_session_id,
                committed_at_utc=self._now(),
            )

    def activate(
        self,
        *,
        activation_record: EntityActivationRecord,
        activation_evidence: EntityActivationEvidenceBundle,
        lifecycle: LifecycleView,
        shared_metabolism: SharedMetabolismSnapshot,
        occurred_at_utc: datetime | None = None,
    ) -> EntityCommitReceipt:
        """Commit one verified SHADOW→LOCAL_LIVE CAS; grant no authority."""

        at = _utc(occurred_at_utc or self._now(), "occurred_at_utc")
        with self._lock:
            self._ensure_running()
            self.require_authority()
            snapshot = self.store.reconstruct()
            self.require_authority()
            return self.store.commit_activation(
                expected_state_id=snapshot.state.entity_state_id,
                expected_state_version=snapshot.state.state_version,
                runtime_session_id=self.runtime_session_id,
                activation_record=activation_record,
                activation_evidence=activation_evidence,
                lifecycle=lifecycle,
                shared_metabolism=shared_metabolism,
                occurred_at_utc=at,
                committed_at_utc=self._now(),
            )

    def rebind_successor_runtime(
        self,
        *,
        expected_previous_runtime_session_id: str,
        lifecycle: LifecycleView,
        verified_runtime_receipt_references: Sequence[str],
        occurred_at_utc: datetime | None = None,
    ) -> EntityCommitReceipt:
        """Bind an existing LOCAL_LIVE head to a verified successor runtime."""

        at = _utc(occurred_at_utc or self._now(), "occurred_at_utc")
        with self._lock:
            self._ensure_running()
            self.require_authority()
            snapshot = self.store.reconstruct()
            self.require_authority()
            return self.store.commit_runtime_rebind(
                expected_state_id=snapshot.state.entity_state_id,
                expected_state_version=snapshot.state.state_version,
                expected_previous_runtime_session_id=(
                    expected_previous_runtime_session_id
                ),
                runtime_session_id=self.runtime_session_id,
                lifecycle=lifecycle,
                verified_runtime_receipt_references=tuple(
                    verified_runtime_receipt_references
                ),
                occurred_at_utc=at,
                committed_at_utc=self._now(),
            )

    def bind_wake_callback(self, callback: Callable[[], None] | None) -> None:
        with self._lock:
            self._wake_callback = callback

    def set_supervisor_active(self, active: bool) -> None:
        with self._lock:
            with self._projection_lock:
                self._supervisor_active = bool(active)

    def stop(self) -> None:
        """Stop only this adapter; it does not mutate production lifecycle."""

        with self._lock:
            with self._projection_lock:
                self._stopped = True
                self._supervisor_active = False
            self._wake_callback = None

    def restart_snapshot(self) -> EntityRestartSnapshot:
        with self._lock:
            return self.store.reconstruct()

    def enqueue(
        self,
        *,
        draft: EntityEventDraft,
        ingress_key: str,
        final_admission: Callable[..., datetime] | None = None,
    ) -> EntityIngressRecord:
        with self._lock:
            self._ensure_running()
            self.require_authority()
            audit = self.store.audit_read_only()
            if not audit.valid:
                raise EntityRuntimeError("ENTITY_STORE_NOT_VALID")
            if audit.pending_ingress_count >= self.policy.maximum_pending_ingress:
                raise EntityRuntimeError("ENTITY_INGRESS_BACKPRESSURE")
            def final_check(**audited):
                self._ensure_running()
                self.require_authority()
                if audited['pending_count'] >= self.policy.maximum_pending_ingress:
                    raise EntityRuntimeError("ENTITY_INGRESS_BACKPRESSURE")
                return (final_admission(**audited) if final_admission is not None
                        else self._now())

            record = self.store.enqueue(
                draft=draft,
                ingress_key=ingress_key,
                enqueued_at_utc=self._now(),
                final_admission=final_check,
            )
            callback = self._wake_callback
        if callback is not None:
            callback()
        return record

    def renew_local_event_budget(
        self, *, entity_id: str, expected_generation: int, additional_events: int,
        loop_ids: tuple[str, str, str], owner_reference: str, request_id: str,
        reason: str, final_owner_check: Callable[[], None],
    ) -> dict:
        """One owner-authorized control step; ordinary queued work stays in order."""
        from .entity_event_budget import RENEWAL_RELATION, budget_projection, renewal_events
        with self._lock:
            self._ensure_running()
            self.require_authority()
            snapshot = self.store.reconstruct()
            state = snapshot.state
            if entity_id != state.identity.instance_id:
                raise EntityRuntimeError("LOCAL_EVENT_BUDGET_BINDING_MISMATCH")
            if expected_generation != len(renewal_events(snapshot.historical_events)):
                raise EntityRuntimeError("LOCAL_EVENT_BUDGET_GENERATION_MISMATCH")
            at = self._now()
            grant = LocalEventBudgetRenewalPayload(generation=expected_generation + 1,
                previous_consumed_total=state.resources.events_processed,
                previous_event_budget=state.resources.event_budget, additional_events=additional_events,
                entity_id=entity_id, identity_state_id=state.identity.identity_state_id,
                loop_ids=loop_ids, owner_reference=owner_reference, request_id=request_id, reason=reason)
            draft = EntityEventDraft(event_type=EventType.LOCAL_EVENT_BUDGET_RENEWAL,
                occurred_at_utc=at, originating_loop=LoopName.COORDINATOR,
                source=EventEndpoint(kind=EventSourceKind.SYSTEM, identifier="LOCAL_EVENT_BUDGET_CONTROLLER"),
                target=EventEndpoint(kind=EventSourceKind.SE6, identifier="SE6"), relation=RENEWAL_RELATION,
                provenance=ObservationProvenance.INDEPENDENTLY_VERIFIED, epistemic_status=EpistemicStatus.VERIFIED,
                authority_status=AuthorityStatus.GRANTED_RECORDED, correlation_id=request_id,
                causal_id=state.event_head_id, parent_event_id=state.event_head_id,
                sensitivity=SensitivityClassification.INTERNAL, persistence_policy=PersistencePolicy.DURABLE_AUDIT,
                payload=grant)

            def final_check():
                self.require_authority()
                final_owner_check()

            receipt = self.store.commit_local_event_budget_renewal(
                expected_state_id=state.entity_state_id, expected_state_version=state.state_version,
                runtime_session_id=self.runtime_session_id, draft=draft,
                committed_at_utc=self._now(), final_authority_check=final_check)
            after = self.store.reconstruct()
            result = budget_projection(after.state, after.historical_events)
            result.update(receipt_id=receipt.receipt_id, request_id=request_id, loop_ids=loop_ids,
                          grant=grant.model_dump(mode="json"))
            callback = self._wake_callback
        if callback is not None:
            callback()
        return result

    def interactive_proof(self, *, payload, final_owner_check: Callable[[], None]) -> dict:
        """One explicit owner action, no wake/drain of the global queue."""
        from .interactive_entity_proof import ProofExecutionError, control_draft, projection
        from .entity_events import InteractiveProofPayload
        with self._lock:
            self._ensure_running()
            self.require_authority()
            final_owner_check()
            snapshot = self.store.reconstruct()
            before = projection(snapshot.historical_events, self._now())

            def final_check():
                self.require_authority()
                final_owner_check()
                # Audit/reduction latency cannot turn an expired reservation into
                # an executable one. Session restoration never extends its TTL.
                current = projection(snapshot.historical_events, self._now())
                permitted = {
                    "RESERVE": {"NOT_RESERVED", "EXPIRED"},
                    "RECOVERY_AUTHORIZE": {"FAILED"},
                    "STEP": {"ACTIVE", "RECOVERY_AUTHORIZED", "RECOVERY_RUNNING"},
                    "FAIL": {"ACTIVE"},
                    "RECOVERY_FAIL": {"RECOVERY_AUTHORIZED", "RECOVERY_RUNNING"},
                    "COMPLETE": {"ACTIVE", "RECOVERY_AUTHORIZED", "RECOVERY_RUNNING"},
                    "REVOKE": {"ACTIVE", "RECOVERY_AUTHORIZED", "RECOVERY_RUNNING"},
                }.get(payload.operation, set())
                if current["status"] not in permitted:
                    raise EntityRuntimeError("INTERACTIVE_PROOF_EXPIRED_OR_CLOSED")

            def commit(control):
                return self.store.commit_step(expected_state_id=snapshot.state.entity_state_id,
                    expected_state_version=snapshot.state.state_version, ingress_id=None,
                    state_after=None, events=(), result=None, runtime_session_id=self.runtime_session_id,
                    committed_at_utc=self._now(), _proof_draft=control_draft(snapshot.state, control, self._now()),
                    _proof_authority_check=final_check)

            try:
                receipt = commit(payload)
            except ProofExecutionError:
                # Failed reduction has already rolled back. Close, never retry or
                # turn leftover proof allowance into globally executable work.
                failure_operation = (
                    "RECOVERY_FAIL"
                    if before["status"] in {"RECOVERY_AUTHORIZED", "RECOVERY_RUNNING"}
                    else "FAIL"
                )
                failed = InteractiveProofPayload.model_validate(
                    payload.model_dump(mode="python")
                    | {"operation": failure_operation}
                )
                receipt = commit(failed)
            after = self.store.reconstruct()
            return projection(after.historical_events, self._now()) | {"receipt_id": receipt.receipt_id}

    def process_one(self, *, ingress_id: str | None = None) -> EntityStepCommit | None:
        """Process and atomically commit at most one already-durable ingress."""

        with self._lock:
            self._ensure_running()
            self.require_authority()
            snapshot = self.store.reconstruct()
            if not snapshot.pending_ingress:
                if ingress_id is not None:
                    raise EntityRuntimeError("ENTITY_INGRESS_NOT_PENDING")
                return None
            fifo_head = min(
                snapshot.pending_ingress, key=lambda item: item.queue_sequence
            )
            ingress = fifo_head if ingress_id is None else next(
                (item for item in snapshot.pending_ingress if item.ingress_id == ingress_id), None
            )
            if ingress is None:
                raise EntityRuntimeError("ENTITY_INGRESS_NOT_PENDING")
            if ingress.ingress_id != fifo_head.ingress_id:
                raise EntityRuntimeError("EARLIER_INGRESS_PENDING")
            if ingress.draft.event_type is EventType.LOCAL_EVENT_BUDGET_RENEWAL:
                raise EntityRuntimeError("LOCAL_EVENT_BUDGET_AUTHORITY_REQUIRED")
            coordinator = SE6TriLoopCoordinator(
                state=snapshot.state,
                policy=self.coordinator_policy,
                historical_events=snapshot.historical_events,
            )
            coordinator.enqueue(ingress.draft)
            before_count = len(coordinator.bus.events)
            result = coordinator.run_step(
                expected_state_version=snapshot.state.state_version,
                evaluation_at_utc=self._now(),
            )
            events = coordinator.bus.events[before_count:]
            queued_drafts = coordinator.pending_drafts
            # The pure reducer can take time.  Recheck immediately before the
            # first durable write so a controller loss cannot commit work that
            # was only eligible when the step began.
            self.require_authority()
            receipt = self.store.commit_step(
                expected_state_id=snapshot.state.entity_state_id,
                expected_state_version=snapshot.state.state_version,
                ingress_id=ingress.ingress_id,
                state_after=coordinator.state,
                events=events,
                result=result,
                runtime_session_id=self.runtime_session_id,
                committed_at_utc=self._now(),
                queued_drafts=queued_drafts,
            )
            committed = self.store.reconstruct()
            outbox_by_id = {
                item.outbox_id: item for item in committed.undelivered_outbox
            }
            new_outbox = tuple(outbox_by_id[item] for item in receipt.outbox_ids)
            return EntityStepCommit(
                ingress=ingress,
                result=result,
                receipt=receipt,
                state=committed.state,
                events=events,
                new_outbox=new_outbox,
            )

    def process_bounded(
        self, *, max_steps: int | None = None
    ) -> tuple[EntityStepCommit, ...]:
        bound = self.policy.max_steps_per_wake if max_steps is None else max_steps
        if bound < 0 or bound > self.policy.max_steps_per_wake:
            raise ValueError("max_steps exceeds the bounded wake policy")
        commits = []
        for _ in range(bound):
            commit = self.process_one()
            if commit is None:
                break
            commits.append(commit)
        return tuple(commits)

    def enqueue_due_memory_expirations(
        self, *, at_utc: datetime | None = None, limit: int = 32
    ) -> tuple[EntityIngressRecord, ...]:
        """Turn elapsed validity deadlines into explicit durable work.

        Time passage alone does not rewrite memory.  This method observes the
        caller clock, queues bounded MARK_EXPIRED events, and lets the normal
        CAS reducer path append the lifecycle records.
        """

        if limit < 1 or limit > 256:
            raise ValueError("expiration limit must be between 1 and 256")
        instant = _utc(at_utc or self._now(), "at_utc")
        with self._lock:
            self._ensure_running()
            self.require_authority()
            state = self.store.reconstruct().state
            due = tuple(
                record
                for record in state.memory.active_records
                if record.valid_until_utc is not None
                and record.valid_until_utc < instant
            )[:limit]
        queued = []
        for record in due:
            deadline = record.valid_until_utc
            assert deadline is not None
            try:
                queued.append(
                    self.submit_memory_transition(
                        operation=MemoryEventOperation.MARK_EXPIRED,
                        subject=record.subject,
                        content_summary=(
                            "The prior memory validity interval elapsed; the "
                            "record is retained but no longer current."
                        ),
                        source_event_ids=record.source_event_ids,
                        evidence_references=(
                            f"retention-deadline:{deadline.isoformat()}",
                        ),
                        supersedes_memory_id=record.memory_id,
                        ingress_key=f"memory-expiry:{record.memory_id}",
                        occurred_at_utc=deadline,
                    )
                )
            except EntityStoreError as exc:
                if exc.code != "INGRESS_REPLAY_REJECTED":
                    raise
        return tuple(queued)

    def submit_message(
        self,
        *,
        text: str,
        thread_id: str,
        ingress_key: str,
        occurred_at_utc: datetime | None = None,
    ) -> EntityIngressRecord:
        at = _utc(occurred_at_utc or self._now(), "occurred_at_utc")
        draft = EntityEventDraft(
            event_type=EventType.USER_MESSAGE,
            occurred_at_utc=at,
            originating_loop=LoopName.EXTERNAL,
            source=EventEndpoint(
                kind=EventSourceKind.PROGRAMMERONE, identifier="ProgrammerOne"
            ),
            target=EventEndpoint(kind=EventSourceKind.SE6, identifier="SE6"),
            relation="communicates_with",
            provenance=ObservationProvenance.USER_REPORTED,
            epistemic_status=EpistemicStatus.USER_SUPPLIED,
            authority_status=AuthorityStatus.NOT_REQUIRED,
            correlation_id=thread_id,
            causal_id=None,
            parent_event_id=None,
            sensitivity=SensitivityClassification.OWNER_PRIVATE_REDACTED,
            persistence_policy=PersistencePolicy.SESSION,
            payload=InteractionPayload(
                interaction_kind=InteractionKind.USER_MESSAGE,
                thread_id=thread_id,
                text=text,
                basis_event_ids=(),
                initiated_by_se6=False,
                initiation_reason=None,
            ),
        )
        return self.enqueue(draft=draft, ingress_key=ingress_key)

    def submit_objective(
        self,
        *,
        operation: ObjectiveOperation,
        objective_id: str,
        summary: str,
        required_capabilities: Sequence[str] = (),
        ingress_key: str,
        occurred_at_utc: datetime | None = None,
    ) -> EntityIngressRecord:
        at = _utc(occurred_at_utc or self._now(), "occurred_at_utc")
        draft = EntityEventDraft(
            event_type=EventType.OBJECTIVE,
            occurred_at_utc=at,
            originating_loop=LoopName.EXTERNAL,
            source=EventEndpoint(
                kind=EventSourceKind.PROGRAMMERONE, identifier="ProgrammerOne"
            ),
            target=EventEndpoint(kind=EventSourceKind.SE6, identifier="SE6"),
            relation="states_bounded_objective",
            provenance=ObservationProvenance.USER_REPORTED,
            epistemic_status=EpistemicStatus.USER_SUPPLIED,
            authority_status=AuthorityStatus.NOT_REQUIRED,
            correlation_id=objective_id,
            sensitivity=SensitivityClassification.INTERNAL,
            persistence_policy=PersistencePolicy.DURABLE_AUDIT,
            payload=ObjectivePayload(
                operation=operation,
                objective_id=objective_id,
                summary=summary,
                required_capabilities=tuple(required_capabilities),
                basis_event_ids=(),
                authority_effect="NONE",
            ),
        )
        return self.enqueue(draft=draft, ingress_key=ingress_key)

    def submit_observation(
        self,
        *,
        payload: ObservationPayload,
        ingress_key: str,
        event_type: EventType = EventType.OBSERVATION,
        occurred_at_utc: datetime | None = None,
        source_identifier: str = "local-observer",
    ) -> EntityIngressRecord:
        if event_type not in {EventType.OBSERVATION, EventType.ENVIRONMENT_CHANGE}:
            raise ValueError("local observation event type is invalid")
        at = _utc(occurred_at_utc or payload.observed_at_utc, "occurred_at_utc")
        epistemic = {
            ObservationProvenance.INDEPENDENTLY_VERIFIED: EpistemicStatus.VERIFIED,
            ObservationProvenance.SYSTEM_OBSERVED: EpistemicStatus.OBSERVED,
            ObservationProvenance.USER_REPORTED: EpistemicStatus.USER_SUPPLIED,
            ObservationProvenance.MODEL_INFERRED: EpistemicStatus.MODEL_PROPOSED,
            ObservationProvenance.MODEL_PREDICTED: EpistemicStatus.MODEL_PROPOSED,
            ObservationProvenance.EXTERNAL_RETRIEVED: EpistemicStatus.DERIVED,
            ObservationProvenance.CONTRADICTED: EpistemicStatus.CONTRADICTED,
            ObservationProvenance.UNKNOWN: EpistemicStatus.UNKNOWN,
        }.get(payload.provenance, EpistemicStatus.REPORTED)
        draft = EntityEventDraft(
            event_type=event_type,
            occurred_at_utc=at,
            originating_loop=LoopName.EXTERNAL,
            source=EventEndpoint(
                kind=EventSourceKind.COMPONENT, identifier=source_identifier
            ),
            target=EventEndpoint(kind=EventSourceKind.SE6, identifier="SE6"),
            relation="reports_local_observation",
            provenance=payload.provenance,
            epistemic_status=epistemic,
            authority_status=AuthorityStatus.NOT_REQUIRED,
            correlation_id=f"observation:{canonical_sha256(payload)}",
            sensitivity=SensitivityClassification.INTERNAL,
            persistence_policy=PersistencePolicy.DURABLE_CANDIDATE,
            payload=payload,
        )
        return self.enqueue(draft=draft, ingress_key=ingress_key)

    def submit_model_terminal_change(
        self,
        *,
        terminal_id: str,
        provider: str,
        model: str,
        mode: Literal["DETERMINISTIC", "MODEL_TERMINAL"],
        previous_terminal_id: str,
        ingress_key: str,
        occurred_at_utc: datetime | None = None,
    ) -> EntityIngressRecord:
        at = _utc(occurred_at_utc or self._now(), "occurred_at_utc")
        payload = ModelTerminalPayload(
            terminal_id=terminal_id,
            provider=provider,
            model=model,
            mode=mode,
            previous_terminal_id=previous_terminal_id,
            authority_effect="NONE",
        )
        return self.enqueue(
            ingress_key=ingress_key,
            draft=EntityEventDraft(
                event_type=EventType.MODEL_TERMINAL_CHANGED,
                occurred_at_utc=at,
                originating_loop=LoopName.COORDINATOR,
                source=EventEndpoint(
                    kind=EventSourceKind.SYSTEM, identifier="entity-runtime"
                ),
                target=EventEndpoint(kind=EventSourceKind.SE6, identifier="SE6"),
                relation="replaces_cognition_terminal",
                provenance=ObservationProvenance.SYSTEM_OBSERVED,
                epistemic_status=EpistemicStatus.DETERMINISTIC,
                authority_status=AuthorityStatus.NOT_REQUIRED,
                correlation_id=f"model-terminal:{terminal_id}",
                sensitivity=SensitivityClassification.INTERNAL,
                persistence_policy=PersistencePolicy.DURABLE_AUDIT,
                payload=payload,
            ),
        )

    def submit_memory_transition(
        self,
        *,
        operation: MemoryEventOperation,
        subject: str,
        content_summary: str,
        ingress_key: str,
        source_event_ids: Sequence[str] = (),
        evidence_references: Sequence[str] = (),
        supersedes_memory_id: str | None = None,
        revokes_memory_id: str | None = None,
        independently_verified: bool = False,
        occurred_at_utc: datetime | None = None,
    ) -> EntityIngressRecord:
        at = _utc(occurred_at_utc or self._now(), "occurred_at_utc")
        provenance = (
            ObservationProvenance.INDEPENDENTLY_VERIFIED
            if independently_verified
            else ObservationProvenance.SYSTEM_OBSERVED
        )
        epistemic = (
            EpistemicStatus.VERIFIED
            if independently_verified
            else EpistemicStatus.MEASURED
        )
        return self.enqueue(
            ingress_key=ingress_key,
            draft=EntityEventDraft(
                event_type={
                    MemoryEventOperation.CANDIDATE: EventType.MEMORY_CANDIDATE,
                    MemoryEventOperation.CONSOLIDATE: EventType.MEMORY_CONSOLIDATION,
                    MemoryEventOperation.REVOKE: EventType.MEMORY_REVOCATION,
                    MemoryEventOperation.MARK_STALE: EventType.MEMORY_STALE,
                    MemoryEventOperation.MARK_EXPIRED: EventType.MEMORY_EXPIRED,
                    MemoryEventOperation.MARK_CONTRADICTED: EventType.MEMORY_CONTRADICTED,
                }.get(operation, EventType.MEMORY_CONSOLIDATION),
                occurred_at_utc=at,
                originating_loop=LoopName.COORDINATOR,
                source=EventEndpoint(
                    kind=EventSourceKind.SYSTEM, identifier="entity-memory-policy"
                ),
                target=EventEndpoint(kind=EventSourceKind.SE6, identifier="SE6"),
                relation="records_memory_lifecycle_transition",
                provenance=provenance,
                epistemic_status=epistemic,
                authority_status=AuthorityStatus.NOT_REQUIRED,
                correlation_id=f"memory:{canonical_sha256((operation, subject, ingress_key))}",
                sensitivity=SensitivityClassification.INTERNAL,
                persistence_policy=PersistencePolicy.DURABLE_AUDIT,
                payload=MemoryPayload(
                    operation=operation,
                    subject=subject,
                    content_summary=content_summary,
                    source_event_ids=tuple(source_event_ids),
                    evidence_references=tuple(evidence_references),
                    supersedes_memory_id=supersedes_memory_id,
                    revokes_memory_id=revokes_memory_id,
                    authority_effect="NONE",
                ),
            ),
        )

    def submit_verification(
        self,
        *,
        subject_event_id: str,
        result: VerificationResult | str,
        summary: str,
        evidence_references: Sequence[str],
        ingress_key: str,
        failure_class: str | None = None,
        independently_verified: bool = True,
        occurred_at_utc: datetime | None = None,
    ) -> EntityIngressRecord:
        try:
            normalized_result = (
                result if isinstance(result, VerificationResult) else VerificationResult(result)
            )
        except ValueError as exc:
            raise EntityRuntimeError("VERIFICATION_RESULT_INVALID") from exc

        at = _utc(occurred_at_utc or self._now(), "occurred_at_utc")
        if independently_verified:
            with self._lock:
                self._ensure_running()
                snapshot = self.store.reconstruct()
                history = snapshot.historical_events
                if not any(item.event_id == subject_event_id for item in history):
                    raise EntityRuntimeError(
                        "VERIFICATION_SUBJECT_NOT_IN_ENTITY_HISTORY"
                    )
                if not evidence_references:
                    raise EntityRuntimeError("VERIFICATION_EVIDENCE_REQUIRED")

                subject = next(item for item in history if item.event_id == subject_event_id)
                lineage_references = {
                    ref for ref in evidence_references
                    if ref.startswith("cognition_memory_")
                }
                lineage_records = {}
                if lineage_references:
                    if self.cognition_store is None:
                        raise EntityRuntimeError("VERIFICATION_EVIDENCE_NOT_CANONICAL")
                    try:
                        binding = self.cognition_store.binding(audited_state=snapshot.state)
                        records = self.cognition_store.memory_records()
                    except CognitionStoreError as exc:
                        raise EntityRuntimeError("VERIFICATION_EVIDENCE_NOT_CANONICAL") from exc
                    records_by_id = {record.memory_id: record for record in records}
                    candidate = records_by_id.get(subject.correlation_id)
                    approval_id = (
                        candidate.subject.removeprefix("relational:track-b:")
                        if candidate is not None
                        else ""
                    )
                    try:
                        subject_summary = (
                            json.loads(subject.payload.value_summary)
                            if isinstance(subject.payload, ObservationPayload)
                            else {}
                        )
                    except (TypeError, ValueError):
                        subject_summary = {}
                    if (
                        candidate is None
                        or subject.relation != "retained_provider_hypothesis"
                        or not isinstance(subject.payload, ObservationPayload)
                        or subject.payload.world_node != "provider-candidate:" + candidate.memory_id
                        or not approval_id
                        or subject_summary.get("scope") != "track-b-synthetic"
                        or candidate.status is not MemoryStatus.HYPOTHESIS
                        or not any(item.source_kind is EvidenceSourceKind.MODEL_OUTPUT
                                   and item.source_id == approval_id
                                   for item in candidate.provenance)
                        or candidate.entity_id != binding.entity_id
                        or candidate.identity_state_id != binding.current_identity_state_id
                        or binding.entity_id != snapshot.state.identity.instance_id
                        or binding.current_identity_state_id != snapshot.state.identity.identity_state_id
                    ):
                        raise EntityRuntimeError("VERIFICATION_EVIDENCE_SUBJECT_MISMATCH")
                    approval_id = candidate.subject.removeprefix("relational:track-b:")
                    for ref in lineage_references:
                        record = records_by_id.get(ref)
                        if (
                            record is None
                            or ref not in subject.payload.evidence_references
                            or record.entity_id != binding.entity_id
                            or record.identity_state_id != binding.current_identity_state_id
                        ):
                            raise EntityRuntimeError("VERIFICATION_EVIDENCE_NOT_CANONICAL")
                        if ref == candidate.memory_id:
                            if record is not candidate:
                                raise EntityRuntimeError("VERIFICATION_EVIDENCE_NOT_CANONICAL")
                        elif (
                            record.subject != "provider-receipt:" + approval_id
                            or not any(item.source_kind is EvidenceSourceKind.EXECUTION_RECEIPT
                                       and item.source_id == approval_id
                                       for item in record.provenance)
                            or record.status is not MemoryStatus.OBSERVATION
                        ):
                            raise EntityRuntimeError("VERIFICATION_EVIDENCE_SUBJECT_MISMATCH")
                        lineage_records[ref] = record

                by_reference: dict[str, list[EntityEvent]] = {}
                for item in history:
                    refs: tuple[str, ...] = ()
                    if isinstance(item.payload, (ObservationPayload, VerificationPayload, MemoryPayload)):
                        refs = item.payload.evidence_references
                    for ref in refs:
                        by_reference.setdefault(ref, []).append(item)

                independent_evidence_found = False
                for ref in tuple(evidence_references):
                    if ref in lineage_records:
                        continue
                    if ref == subject_event_id:
                        raise EntityRuntimeError("VERIFICATION_EVIDENCE_SUBJECT_MISMATCH")
                    if ref not in by_reference:
                        raise EntityRuntimeError("VERIFICATION_EVIDENCE_NOT_CANONICAL")
                    filtered = [
                        event for event in by_reference[ref]
                        if getattr(event, "event_id", None) != subject_event_id
                    ]
                    if any(
                        event.event_type is EventType.USER_MESSAGE
                        for event in filtered
                    ):
                        raise EntityRuntimeError("VERIFICATION_EVIDENCE_SUBJECT_MISMATCH")
                    if not filtered:
                        raise EntityRuntimeError("VERIFICATION_EVIDENCE_NOT_CANONICAL")
                    model_only = bool(filtered) and all(
                        event.provenance in {
                            ObservationProvenance.MODEL_INFERRED,
                            ObservationProvenance.MODEL_PREDICTED,
                        }
                        for event in filtered
                    )
                    if model_only:
                        raise EntityRuntimeError("VERIFICATION_EVIDENCE_MODEL_OUTPUT_REJECTED")
                    independent_evidence_found = True
                if not independent_evidence_found:
                    raise EntityRuntimeError("VERIFICATION_INDEPENDENT_SUPPORT_MISSING")

        provenance = (
            ObservationProvenance.INDEPENDENTLY_VERIFIED
            if independently_verified
            else ObservationProvenance.SYSTEM_OBSERVED
        )
        epistemic = (
            EpistemicStatus.VERIFIED
            if independently_verified
            else EpistemicStatus.REPORTED
        )
        return self.enqueue(
            ingress_key=ingress_key,
            draft=EntityEventDraft(
                event_type=EventType.VERIFICATION,
                occurred_at_utc=at,
                originating_loop=LoopName.EXTERNAL,
                source=EventEndpoint(
                    kind=EventSourceKind.COMPONENT, identifier="local-verifier"
                ),
                target=EventEndpoint(kind=EventSourceKind.SE6, identifier="SE6"),
                relation="reports_bounded_verification",
                provenance=provenance,
                epistemic_status=epistemic,
                authority_status=AuthorityStatus.NOT_REQUIRED,
                correlation_id=f"verification:{subject_event_id}",
                causal_id=subject_event_id,
                sensitivity=SensitivityClassification.INTERNAL,
                persistence_policy=PersistencePolicy.DURABLE_AUDIT,
                payload=VerificationPayload(
                    subject_event_id=subject_event_id,
                    result=normalized_result,
                    independently_verified=independently_verified,
                    evidence_references=tuple(evidence_references),
                    failure_class=failure_class,
                    summary=summary,
                ),
            ),
        )

    def submit_owner_decision(
        self,
        *,
        request_event_id: str,
        disposition: ApprovalDisposition,
        decision_reason: str,
        ingress_key: str,
        authoritative_receipt_reference: str | None = None,
        occurred_at_utc: datetime | None = None,
    ) -> EntityIngressRecord:
        """Record a caller-authenticated owner decision; never infer one."""

        at = _utc(occurred_at_utc or self._now(), "occurred_at_utc")
        with self._lock:
            self._ensure_running()
            snapshot = self.store.reconstruct()
            if request_event_id not in snapshot.state.authority.pending_request_event_ids:
                raise EntityRuntimeError("OWNER_REQUEST_NOT_PENDING")
        return self.enqueue(
            ingress_key=ingress_key,
            draft=EntityEventDraft(
                event_type=EventType.APPROVAL,
                occurred_at_utc=at,
                originating_loop=LoopName.EXTERNAL,
                source=EventEndpoint(
                    kind=EventSourceKind.PROGRAMMERONE,
                    identifier="ProgrammerOne",
                ),
                target=EventEndpoint(kind=EventSourceKind.SE6, identifier="SE6"),
                relation="records_owner_decision",
                provenance=ObservationProvenance.USER_REPORTED,
                epistemic_status=EpistemicStatus.USER_SUPPLIED,
                authority_status={
                    ApprovalDisposition.APPROVED: AuthorityStatus.GRANTED_RECORDED,
                    ApprovalDisposition.DENIED: AuthorityStatus.DENIED_RECORDED,
                    ApprovalDisposition.EXPIRED: AuthorityStatus.EXPIRED_RECORDED,
                    ApprovalDisposition.REVOKED: AuthorityStatus.DENIED_RECORDED,
                }[disposition],
                correlation_id=f"owner-decision:{request_event_id}",
                causal_id=request_event_id,
                sensitivity=SensitivityClassification.INTERNAL,
                persistence_policy=PersistencePolicy.DURABLE_AUDIT,
                payload=ApprovalPayload(
                    request_event_id=request_event_id,
                    disposition=disposition,
                    decision_reason=decision_reason,
                    authoritative_receipt_reference=authoritative_receipt_reference,
                    authority_effect="NONE",
                ),
            ),
        )

    def acknowledge_local_delivery(
        self,
        *,
        outbox_id: str,
        delivery_reference: str,
        delivered_at_utc: datetime | None = None,
    ) -> EntityOutboxDeliveryRecord:
        """Record a caller-confirmed dashboard delivery; this sends nothing."""

        with self._lock:
            self._ensure_running()
            self.require_authority()
            return self.store.acknowledge_outbox(
                outbox_id=outbox_id,
                delivery_reference=delivery_reference,
                delivered_at_utc=delivered_at_utc or self._now(),
            )

    def projection(self) -> LocalEntityProjection:
        with self._lock:
            audit = self.store.audit_read_only()
            if not audit.valid:
                return _make_projection(
                    runtime_session_id=self.runtime_session_id,
                    state=None,
                    audit=audit,
                    supervisor_active=self._supervisor_active,
                    stopped=self._stopped,
                    at=self._now(),
                )
            snapshot = self.store.reconstruct()
            return _make_projection(
                runtime_session_id=self.runtime_session_id,
                state=snapshot.state,
                audit=audit,
                supervisor_active=self._supervisor_active,
                stopped=self._stopped,
                at=self._now(),
            )

    def projection_from_audited_snapshot(
        self,
        snapshot: EntityRestartSnapshot | None,
        audit: EntityStoreIntegrityResult,
    ) -> LocalEntityProjection:
        """Project one caller-supplied snapshot produced by the same full audit."""

        with read_span("three_loop_lock_wait"):
            self._projection_lock.acquire()
        try:
            with read_span("three_loop_snapshot_validation"):
                state = snapshot.state if snapshot is not None else None
                if audit.valid and (
                    state is None
                    or audit.head_state_id != state.entity_state_id
                    or audit.head_state_version != state.state_version
                ):
                    raise EntityRuntimeError("ENTITY_AUDITED_SNAPSHOT_MISMATCH")
                if audit.valid:
                    read_count("three_loop_snapshot_reuses")
            with read_span("three_loop_shared_projection"):
                read_count("three_loop_shared_builds")
                return _make_projection(
                    runtime_session_id=self.runtime_session_id,
                    state=state,
                    audit=audit,
                    supervisor_active=self._supervisor_active,
                    stopped=self._stopped,
                    at=self._now(),
                )
        finally:
            self._projection_lock.release()

    def _ensure_running(self) -> None:
        if self._stopped:
            raise EntityRuntimeError("ENTITY_RUNTIME_STOPPED")

    def require_authority(self) -> None:
        """Fail closed when the host's process-local authority is unavailable.

        A generic/shadow runtime has no host guard and therefore gains no new
        authority from this method.  Production supplies a read-only predicate
        bound to its exact runtime session, live controller, lifecycle and
        emergency posture.  Exceptions and non-boolean answers are refusals.
        """

        guard = self._authority_guard
        if guard is None:
            return
        try:
            allowed = guard(self.runtime_session_id)
        except Exception:
            logging.getLogger(__name__).debug(
                "Runtime authority guard failed closed", exc_info=True
            )
            allowed = False
        if allowed is not True:
            raise EntityRuntimeError("ENTITY_RUNTIME_AUTHORITY_UNAVAILABLE")

    def _now(self) -> datetime:
        return _utc(self._clock(), "clock")


class LocalEntitySupervisor:
    """Interruptible event/timer wake mechanism with fixed work per wake."""

    def __init__(
        self,
        runtime: LocalEntityRuntime,
        *,
        observation_cycle: Callable[[], None] | None = None,
        cognition_cycle: Callable[[], tuple[EntityStepCommit, ...]] | None = None,
    ) -> None:
        self.runtime = runtime
        self._observation_cycle = observation_cycle
        self._cognition_cycle = cognition_cycle
        self._wake = Event()
        self._stop = Event()
        self._thread: Thread | None = None
        self._lock = RLock()
        self._last_error_code: str | None = None

    @property
    def active(self) -> bool:
        thread = self._thread
        return bool(thread is not None and thread.is_alive() and not self._stop.is_set())

    @property
    def last_error_code(self) -> str | None:
        return self._last_error_code

    def start(self) -> None:
        with self._lock:
            if self.active:
                return
            self.runtime.require_authority()
            self._stop.clear()
            self._wake.clear()
            self.runtime.bind_wake_callback(self.wake)
            self.runtime.set_supervisor_active(True)
            self._thread = Thread(
                target=self._run,
                name="se6-local-entity-supervisor",
                daemon=True,
            )
            self._thread.start()

    def wake(self) -> None:
        self._wake.set()

    def stop(self, *, timeout_seconds: float = 5.0) -> None:
        with self._lock:
            self._stop.set()
            self._wake.set()
            thread = self._thread
        if thread is not None:
            thread.join(timeout=max(0.0, timeout_seconds))
            if thread.is_alive():
                raise EntityRuntimeError("ENTITY_SUPERVISOR_STOP_TIMEOUT")
        with self._lock:
            self.runtime.bind_wake_callback(None)
            self.runtime.set_supervisor_active(False)
            self._thread = None

    def run_wake_for_testing(self) -> tuple[EntityStepCommit, ...]:
        """Synchronous one-wake hook; it obeys the production step bound."""

        self.runtime.require_authority()
        return self._run_cycle()

    def _run_cycle(self) -> tuple[EntityStepCommit, ...]:
        # A bounded, content-verified head is sufficient only for refusal.
        # It never authorizes work; admitted work still runs all existing audits.
        state, _ = self.runtime.store.authority_head_read_only()
        if state.resources.events_processed >= state.resources.event_budget:
            raise ResourceBudgetExceeded("entity event budget is exhausted")
        if self._observation_cycle is not None:
            self._observation_cycle()
        try:
            self.runtime.enqueue_due_memory_expirations()
        except EntityRuntimeError as exc:
            if exc.code != "ENTITY_INGRESS_BACKPRESSURE":
                raise
            # The durable ingress queue is already full. Expiration work
            # remains represented by the still-active due memory records and
            # will be retried after existing durable ingress has drained.
            # Do not let this optional enqueue prevent cognition from
            # processing the work that is already durable.
        if self._cognition_cycle is not None:
            return self._cognition_cycle()
        return self.runtime.process_bounded()

    def _run(self) -> None:
        try:
            while not self._stop.is_set():
                self._wake.wait(self.runtime.policy.idle_wait_seconds)
                self._wake.clear()
                if self._stop.is_set():
                    break
                try:
                    self.runtime.require_authority()
                    self._run_cycle()
                    self._last_error_code = None
                except ResourceBudgetExceeded:
                    self._last_error_code = "LOCAL_EVENT_BUDGET_EXHAUSTED"
                    # Keep the existing supervisor waiting. Only an explicit,
                    # authenticated renewal can add capacity and wake it again.
                except (EntityRuntimeError, EntityStoreError, OSError, ValueError) as exc:
                    self._last_error_code = getattr(
                        exc, "code", "ENTITY_OBSERVATION_OR_RUNTIME_FAILED"
                    )
                    if self._last_error_code == "ENTITY_RUNTIME_AUTHORITY_UNAVAILABLE":
                        self._stop.set()
                        break
                    # Fail closed and wait for an explicit new wake or stop.
        finally:
            self.runtime.bind_wake_callback(None)
            self.runtime.set_supervisor_active(False)


def _make_projection(
    *,
    runtime_session_id: str,
    state: SE6EntityState | None,
    audit: EntityStoreIntegrityResult,
    supervisor_active: bool,
    stopped: bool,
    at: datetime,
) -> LocalEntityProjection:
    reasons = []
    if not audit.valid:
        reasons.extend(audit.reason_codes or ("ENTITY_STORE_INVALID",))
    if stopped:
        reasons.append("ENTITY_RUNTIME_STOPPED")
    if not supervisor_active:
        reasons.append("ENTITY_SUPERVISOR_INACTIVE")
    if state is not None:
        if state.operating_mode is not EntityOperatingMode.LOCAL_LIVE:
            reasons.append("ENTITY_NOT_ACTIVATED")
        if (
            not state.lifecycle.controller_authoritative
            or state.lifecycle.controller_status is not ControllerStatus.ACTIVE
            or state.lifecycle.operational_state is not OperationalConnectionState.CONNECTED
            or state.lifecycle.emergency_stop is not EmergencyStopState.ARMED
        ):
            reasons.append("AUTHORITATIVE_RUNTIME_UNAVAILABLE")
        if state.integrity_metrics.total_violations:
            reasons.append("ENTITY_INTEGRITY_VIOLATION")
        if (
            state.environment_access.online_observation_enabled
            or state.environment_access.network_authority != "NONE"
            or state.environment_access.external_requests != "BLOCKED"
        ):
            reasons.append("LOCAL_OFFLINE_POLICY_INVALID")
    unique_reasons = tuple(dict.fromkeys(reasons))
    if stopped:
        status = EntityPresenceStatus.STOPPED
    elif state is None:
        status = EntityPresenceStatus.ABSENT
    elif unique_reasons:
        status = (
            EntityPresenceStatus.SHADOW_READY
            if unique_reasons == (
                "ENTITY_SUPERVISOR_INACTIVE",
                "ENTITY_NOT_ACTIVATED",
            )
            or unique_reasons == ("ENTITY_NOT_ACTIVATED",)
            else EntityPresenceStatus.DEGRADED
        )
    else:
        status = EntityPresenceStatus.PRESENT
    # Read all three loop statuses from the same caller-audited immutable state.
    # These are projection timings, not reducer execution or loop work receipts.
    with read_span("presence_projection"):
        presence_status = state.loop_states.presence.status if state else "UNAVAILABLE"
    with read_span("awareness_projection"):
        awareness_status = state.loop_states.awareness.status if state else "UNAVAILABLE"
    with read_span("becoming_projection"):
        becoming_status = state.loop_states.becoming.status if state else "UNAVAILABLE"
    material = {
        "schema_version": ENTITY_PROJECTION_SCHEMA_VERSION,
        "status": status,
        "entity_present": status is EntityPresenceStatus.PRESENT,
        "entity_state_id": state.entity_state_id if state else None,
        "entity_state_hash": state.state_hash if state else None,
        "state_version": state.state_version if state else None,
        "runtime_session_id": runtime_session_id,
        "operating_mode": state.operating_mode if state else None,
        "identity_state_id": state.identity.identity_state_id if state else None,
        "presence_status": presence_status,
        "awareness_status": awareness_status,
        "becoming_status": becoming_status,
        "continuation_state": state.continuation.state if state else "STOP",
        "pending_ingress_count": audit.pending_ingress_count,
        "undelivered_notification_count": audit.undelivered_outbox_count,
        "current_objective_count": len(state.current_objectives) if state else 0,
        "unresolved_objective_count": len(state.unresolved_objectives) if state else 0,
        "attention_record_count": len(state.attention.records) if state else 0,
        "event_sequence": state.event_sequence if state else 0,
        "store_integrity": audit.status,
        "event_processor_available": state is not None and not stopped,
        "presence_path_available": state is not None and not stopped,
        "awareness_path_available": state is not None and not stopped,
        "continuation_available": bool(
            state is not None
            and state.continuation.bounded
            and state.continuation.interruptible
            and not state.continuation.model_loop_allowed
        ),
        "supervisor_active": supervisor_active and not stopped,
        "network_authority": "NONE",
        "online_observation_enabled": False,
        "external_requests": "BLOCKED",
        "integrity_violation_count": (
            state.integrity_metrics.total_violations if state else 0
        ),
        "projected_at_utc": at,
        "reason_codes": unique_reasons,
        "authority_effect": "NONE",
    }
    digest = canonical_sha256(material)
    return LocalEntityProjection(
        projection_id=f"entity_projection_{digest}", **material
    )


def _utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


__all__ = [
    "ENTITY_PROJECTION_SCHEMA_VERSION",
    "ENTITY_RUNTIME_SCHEMA_VERSION",
    "EntityPresenceStatus",
    "EntityRuntimeError",
    "EntityStepCommit",
    "LocalEntityProjection",
    "LocalEntityRuntime",
    "LocalEntityRuntimePolicy",
    "LocalEntitySupervisor",
]
