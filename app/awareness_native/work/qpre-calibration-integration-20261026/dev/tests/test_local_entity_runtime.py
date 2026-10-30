"""Durable, bounded local runtime tests using only temporary stores."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TypedDict

import pytest

from se666_core.canonical_contracts import BoundaryDecision
from se666_core.dashboard_read_timing import dashboard_read_timing
from se666_core.embodiment_lifecycle import LifecycleState
from se666_core.entity_events import (
    MemoryEventOperation,
    ObjectiveOperation,
    ObservationPayload,
    ObservationProvenance,
)
from se666_core.entity_runtime import (
    EntityPresenceStatus,
    EntityRuntimeError,
    LocalEntityRuntime,
    LocalEntitySupervisor,
)
from se666_core.entity_simulation import create_shadow_entity_genesis
from se666_core.entity_state import (
    ControllerStatus,
    EmergencyStopState,
    EntityIdentityReference,
    EntityOperatingMode,
    LifecycleView,
    LoopStateBundle,
    OperationalConnectionState,
    create_entity_state,
)
from se666_core.entity_store import EntityStore, EntityStoreError
from se666_core.epistemic_status import EpistemicStatus, UncertaintyRecord
from se666_core.merkabah_rotation import rotate_perspectives
from se666_core.operational_awareness import (
    RuntimeDecision,
    build_operational_awareness_state,
)
from se666_core.sphere_of_mirrors import reflect_task

T0 = datetime(2026, 8, 21, 16, 0, tzinfo=UTC)


class _SubmitMessageKwargs(TypedDict):
    text: str
    thread_id: str
    ingress_key: str
    occurred_at_utc: datetime
IDENTITY_ID = f"identity_{'a' * 64}"


def _state(*, local_live: bool = False):
    intention = "Maintain bounded local entity continuity."
    uncertainty = UncertaintyRecord(
        status=EpistemicStatus.DETERMINISTIC,
        confidence=1.0,
        known=("This fixture is local and offline.",),
        unknown=("Future observations are not yet known.",),
        assumptions=(),
        inferences=(),
        symbolic=(),
        evidence_references=(),
    )
    awareness = build_operational_awareness_state(
        stated_intention=intention,
        interpreted_objective=intention,
        objective_status=EpistemicStatus.DETERMINISTIC,
        objective_confidence=1.0,
        cognition_mode="offline_fallback",
        current_state_present=True,
        classification="local_entity_runtime_fixture",
        classification_status=EpistemicStatus.DETERMINISTIC,
        classification_confidence=1.0,
        uncertainty=uncertainty,
        mirrors=reflect_task(intention),
        perspectives=rotate_perspectives(intention),
        runtime_decision=RuntimeDecision.ALLOW,
        effective_decision=BoundaryDecision.ALLOW,
        approval_required=False,
        observed_at_utc=T0,
    )
    identity = EntityIdentityReference(
        instance_id="instance_local_entity_test",
        identity_state_id=IDENTITY_ID,
        identity_state_hash="a" * 64,
        constitution_version="test-constitution-v1",
        constitution_hash="b" * 64,
        owner_identity_reference="ProgrammerOne",
        identity_lineage=(IDENTITY_ID,),
    )
    lifecycle = LifecycleView(
        durable_state=LifecycleState.OBSERVING,
        operational_state=OperationalConnectionState.CONNECTED,
        controller_status=ControllerStatus.ACTIVE,
        controller_authoritative=True,
        emergency_stop=EmergencyStopState.ARMED,
        observed_at_utc=T0,
        evidence_references=("runtime_receipt_test",),
    )
    shadow = create_shadow_entity_genesis(
        identity=identity,
        lifecycle=lifecycle,
        operational_awareness=awareness,
        updated_at_utc=T0,
    )
    if not local_live:
        return shadow
    material = {
        name: getattr(shadow, name)
        for name in shadow.__class__.model_fields
        if name not in {"entity_state_id", "state_hash"}
    }
    material.update(
        {
            "schema_version": "se6-local-entity-state-v1",
            "operating_mode": EntityOperatingMode.LOCAL_LIVE,
            "activation_basis_references": (
                "runtime_receipt_test",
                "acceptance_receipt_test",
            ),
            "shadow_mode": False,
            "production_authoritative": True,
            "loop_states": LoopStateBundle(
                presence=shadow.loop_states.presence.model_copy(
                    update={"mode": "LOCAL_LIVE"}
                ),
                awareness=shadow.loop_states.awareness.model_copy(
                    update={"mode": "LOCAL_LIVE"}
                ),
                becoming=shadow.loop_states.becoming.model_copy(
                    update={"mode": "LOCAL_LIVE"}
                ),
            ),
        }
    )
    return create_entity_state(**material)


def _runtime(tmp_path: Path, *, local_live: bool = False) -> LocalEntityRuntime:
    store = EntityStore.for_testing(tmp_path / "entity.sqlite3")
    runtime = LocalEntityRuntime(
        store=store,
        runtime_session_id="runtime_entity_successor_test",
        clock=lambda: T0,
    )
    runtime.initialize(state=_state(local_live=local_live))
    return runtime


def test_audited_projection_does_not_wait_for_inflight_step_commit(tmp_path, monkeypatch, capsys):
    import json
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event, Timer, current_thread

    runtime = _runtime(tmp_path, local_live=True)
    runtime.set_supervisor_active(True)
    runtime.submit_message(text="Disposable contended step", thread_id="owner",
                           ingress_key="projection-contention", occurred_at_utc=T0)
    audit, snapshot, _ = runtime.store.inspect_read_only()
    entered, release = Event(), Event()
    original_commit = runtime.store.commit_step
    original_connect = runtime.store._connect
    projection_thread = current_thread()
    projection_store_reads = 0

    def delayed_commit(**fields):
        entered.set()
        assert release.wait(5)
        return original_commit(**fields)

    def counted_connect(**options):
        nonlocal projection_store_reads
        if current_thread() is projection_thread:
            projection_store_reads += 1
        return original_connect(**options)

    monkeypatch.setattr(runtime.store, "commit_step", delayed_commit)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(runtime.process_one)
        assert entered.wait(3)
        monkeypatch.setattr(runtime.store, "_connect", counted_connect)
        timer = Timer(1.0, release.set)  # Bounded simulated commit stall, not live evidence.
        timer.start()
        try:
            with dashboard_read_timing() as timing:
                projected = runtime.projection_from_audited_snapshot(snapshot, audit)
        finally:
            timer.cancel()
            release.set()
        committed = pending.result(timeout=5)
    with capsys.disabled():
        print("SE6_THREE_LOOP_CONTENTION_SIMULATION " + json.dumps({
            "timing": timing.report(), "projection_store_reads": projection_store_reads,
        }))
    assert projected.entity_present
    assert snapshot is not None
    assert projected.entity_state_id == snapshot.state.entity_state_id
    assert committed is not None
    assert projected.state_version is not None
    assert committed.state.state_version > projected.state_version
    assert projection_store_reads == 0
    assert timing.elapsed_ms is not None
    assert timing.elapsed_ms < 500, "projection blocked behind the step/store commit lock"


def test_audited_projection_retains_binding_stop_and_supervisor_guards(tmp_path):
    runtime = _runtime(tmp_path, local_live=True)
    audit, snapshot, _ = runtime.store.inspect_read_only()
    assert not runtime.projection_from_audited_snapshot(snapshot, audit).entity_present
    runtime.set_supervisor_active(True)
    assert runtime.projection_from_audited_snapshot(snapshot, audit).entity_present
    assert audit.head_state_version is not None
    wrong = audit.model_copy(update={"head_state_version": audit.head_state_version + 1})
    with pytest.raises(EntityRuntimeError, match="ENTITY_AUDITED_SNAPSHOT_MISMATCH"):
        runtime.projection_from_audited_snapshot(snapshot, wrong)
    runtime.set_supervisor_active(False)
    assert not runtime.projection_from_audited_snapshot(snapshot, audit).entity_present
    runtime.set_supervisor_active(True)
    runtime.stop()
    stopped = runtime.projection_from_audited_snapshot(snapshot, audit)
    assert stopped.status is EntityPresenceStatus.STOPPED
    assert not stopped.entity_present and not stopped.supervisor_active


def test_host_authority_guard_blocks_enqueue_and_precommit_transition(
    tmp_path: Path,
) -> None:
    authority = {"allowed": True, "fail_on_second_check": False, "checks": 0}

    def guard(runtime_session_id: str) -> bool:
        assert runtime_session_id == "runtime-guarded"
        authority["checks"] += 1
        if authority["fail_on_second_check"]:
            return authority["checks"] == 1
        return authority["allowed"]

    store = EntityStore.for_testing(tmp_path / "guarded-entity.sqlite3")
    runtime = LocalEntityRuntime(
        store=store,
        runtime_session_id="runtime-guarded",
        clock=lambda: T0,
        authority_guard=guard,
    )
    runtime.initialize(state=_state(local_live=True))
    runtime.submit_message(
        text="This step must be rechecked immediately before commit.",
        thread_id="programmerone-primary",
        ingress_key="guarded-message:1",
        occurred_at_utc=T0 + timedelta(seconds=1),
    )
    before = store.audit_read_only()
    pending_before = store.pending_ingress()

    authority.update({"fail_on_second_check": True, "checks": 0})
    with pytest.raises(EntityRuntimeError) as precommit:
        runtime.process_one()
    assert precommit.value.code == "ENTITY_RUNTIME_AUTHORITY_UNAVAILABLE"
    assert store.audit_read_only() == before
    assert store.pending_ingress() == pending_before

    authority.update({"fail_on_second_check": False, "allowed": False, "checks": 0})
    with pytest.raises(EntityRuntimeError) as enqueue:
        runtime.submit_message(
            text="This ingress must not be durably recorded.",
            thread_id="programmerone-primary",
            ingress_key="guarded-message:2",
            occurred_at_utc=T0 + timedelta(seconds=2),
        )
    assert enqueue.value.code == "ENTITY_RUNTIME_AUTHORITY_UNAVAILABLE"
    assert store.audit_read_only() == before
    assert store.pending_ingress() == pending_before


def test_supervisor_quiesces_without_consuming_pending_work_on_authority_loss(
    tmp_path: Path,
) -> None:
    authority = {"allowed": True}
    store = EntityStore.for_testing(tmp_path / "supervised-entity.sqlite3")
    runtime = LocalEntityRuntime(
        store=store,
        runtime_session_id="runtime-supervised",
        clock=lambda: T0,
        authority_guard=lambda _runtime_session_id: authority["allowed"],
    )
    runtime.initialize(state=_state(local_live=True))
    runtime.submit_message(
        text="Retain this work until authority is genuinely restored.",
        thread_id="programmerone-primary",
        ingress_key="supervised-message:1",
        occurred_at_utc=T0 + timedelta(seconds=1),
    )
    before = store.audit_read_only()
    pending_before = store.pending_ingress()
    authority["allowed"] = False
    supervisor = LocalEntitySupervisor(runtime)

    with pytest.raises(EntityRuntimeError) as caught:
        supervisor.run_wake_for_testing()
    assert caught.value.code == "ENTITY_RUNTIME_AUTHORITY_UNAVAILABLE"
    assert store.audit_read_only() == before
    assert store.pending_ingress() == pending_before


def test_message_is_durable_grounded_and_restartable(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    runtime.submit_message(
        text="Who are you?",
        thread_id="programmerone-primary",
        ingress_key="message:1",
        occurred_at_utc=T0 + timedelta(seconds=1),
    )

    commit = runtime.process_one()

    assert commit is not None
    assert commit.result.model_calls == 0
    assert not commit.result.network_used
    assert not commit.result.external_effect_performed
    assert len(commit.new_outbox) == 1
    response = commit.new_outbox[0].intent.text
    assert IDENTITY_ID in response
    assert "not my identity" in response
    restarted = LocalEntityRuntime(
        store=runtime.store,
        runtime_session_id="runtime_entity_after_restart",
        clock=lambda: T0 + timedelta(minutes=1),
    )
    snapshot = restarted.restart_snapshot()
    assert snapshot.state.identity.identity_state_id == IDENTITY_ID
    assert snapshot.state.event_sequence == 2
    assert snapshot.state.continuation.state == "REST"
    assert snapshot.state.continuation.bounded
    assert snapshot.state.continuation.interruptible
    assert not snapshot.state.continuation.model_loop_allowed
    assert len(snapshot.undelivered_outbox) == 1
    assert snapshot.undelivered_outbox[0].intent.text == response
    delivery = restarted.acknowledge_local_delivery(
        outbox_id=snapshot.undelivered_outbox[0].outbox_id,
        delivery_reference="dashboard-render:message-1",
        delivered_at_utc=T0 + timedelta(minutes=1),
    )
    assert delivery.authority_effect == "NONE"
    assert restarted.restart_snapshot().undelivered_outbox == ()


def test_objective_observation_and_bounded_processing_persist(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    runtime.submit_objective(
        operation=ObjectiveOperation.RECORD,
        objective_id="objective-local-continuity",
        summary="Track repository continuity locally.",
        ingress_key="objective:1",
        occurred_at_utc=T0 + timedelta(seconds=1),
    )
    runtime.submit_observation(
        payload=ObservationPayload(
            world_node="repository",
            relation="metadata_changed",
            value_summary="Repository metadata changed outside the last verified action.",
            provenance=ObservationProvenance.SYSTEM_OBSERVED,
            observed_at_utc=T0 + timedelta(seconds=2),
            evidence_references=("repo_snapshot_after",),
            current_claim=True,
            confidence_basis_points=10_000,
        ),
        ingress_key="observation:1",
    )

    commits = runtime.process_bounded(max_steps=2)

    assert len(commits) == 2
    snapshot = runtime.restart_snapshot()
    assert any(
        objective.objective_id == "objective-local-continuity"
        for objective in snapshot.state.current_objectives
    )
    assert snapshot.state.environment.observation_event_ids
    assert snapshot.state.attention.records
    assert snapshot.state.continuation.state in {"OBSERVE", "NOTIFY"}
    assert snapshot.state.resources.model_calls == 0
    assert snapshot.state.resources.network_calls == 0


def test_ingress_replay_is_rejected_and_never_executes_twice(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    kwargs: _SubmitMessageKwargs = {
        "text": "What state are you in?",
        "thread_id": "programmerone-primary",
        "ingress_key": "message:dedupe",
        "occurred_at_utc": T0 + timedelta(seconds=1),
    }
    runtime.submit_message(**kwargs)
    with pytest.raises(EntityStoreError) as replay:
        runtime.submit_message(**kwargs)
    assert replay.value.code == "INGRESS_REPLAY_REJECTED"
    assert len(runtime.process_bounded(max_steps=8)) == 1
    assert runtime.process_one() is None
    assert runtime.store.audit_read_only().event_count == 2


def test_model_terminal_replacement_never_changes_identity_or_authority(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    before = runtime.restart_snapshot().state
    runtime.submit_model_terminal_change(
        terminal_id="model-terminal-b",
        provider="local-test-provider",
        model="model-b",
        mode="MODEL_TERMINAL",
        previous_terminal_id=before.cognition_terminal.terminal_id,
        ingress_key="terminal:b",
        occurred_at_utc=T0 + timedelta(seconds=1),
    )
    commit = runtime.process_one()
    assert commit is not None
    after = commit.state
    assert after.cognition_terminal.terminal_id == "model-terminal-b"
    assert after.identity == before.identity
    assert after.authority == before.authority
    assert after.environment_access == before.environment_access
    assert not commit.result.external_effect_performed


def test_present_requires_local_live_store_paths_and_active_supervisor(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path, local_live=True)
    before = runtime.projection()
    assert before.status is EntityPresenceStatus.DEGRADED
    assert not before.entity_present
    assert "ENTITY_SUPERVISOR_INACTIVE" in before.reason_codes

    supervisor = LocalEntitySupervisor(runtime)
    supervisor.start()
    try:
        projection = runtime.projection()
        assert projection.status is EntityPresenceStatus.PRESENT
        assert projection.entity_present
        assert projection.network_authority == "NONE"
        assert not projection.online_observation_enabled
        assert projection.external_requests == "BLOCKED"
    finally:
        supervisor.stop()

    stopped = runtime.projection()
    assert not stopped.entity_present
    assert stopped.status is EntityPresenceStatus.DEGRADED


def test_supervisor_one_wake_is_bounded_and_has_no_model_or_network(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    for index in range(12):
        runtime.submit_message(
            text=f"What are you doing? request {index}",
            thread_id="programmerone-primary",
            ingress_key=f"message:{index}",
            occurred_at_utc=T0 + timedelta(seconds=index + 1),
        )
    supervisor = LocalEntitySupervisor(runtime)

    commits = supervisor.run_wake_for_testing()

    assert len(commits) == runtime.policy.max_steps_per_wake
    assert all(commit.result.model_calls == 0 for commit in commits)
    assert all(not commit.result.network_used for commit in commits)
    assert runtime.store.audit_read_only().pending_ingress_count == 4


def test_memory_lifecycle_preserves_provisional_verified_and_stale_history(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    runtime.submit_memory_transition(
        operation=MemoryEventOperation.CANDIDATE,
        subject="repository:state",
        content_summary="A local repository change was reported.",
        evidence_references=("repo_snapshot_reported",),
        ingress_key="memory:candidate",
        occurred_at_utc=T0 + timedelta(seconds=1),
    )
    candidate_commit = runtime.process_one()
    assert candidate_commit is not None
    provisional = candidate_commit.state.memory.records[-1]
    assert provisional.status.value == "PROVISIONAL"
    assert provisional.epistemic_status is not EpistemicStatus.VERIFIED

    runtime.submit_memory_transition(
        operation=MemoryEventOperation.CONSOLIDATE,
        subject="repository:state",
        content_summary="The bounded repository snapshot was independently verified.",
        evidence_references=("verification_receipt_repo",),
        ingress_key="memory:verified",
        independently_verified=True,
        occurred_at_utc=T0 + timedelta(seconds=2),
    )
    verified_commit = runtime.process_one()
    assert verified_commit is not None
    verified = verified_commit.state.memory.records[-1]
    assert verified.status.value == "VERIFIED"
    assert verified.epistemic_status is EpistemicStatus.VERIFIED

    runtime.submit_memory_transition(
        operation=MemoryEventOperation.MARK_STALE,
        subject="repository:state",
        content_summary="The prior verified repository snapshot is no longer current.",
        supersedes_memory_id=verified.memory_id,
        evidence_references=("timer_policy_v1",),
        ingress_key="memory:stale",
        occurred_at_utc=T0 + timedelta(days=2),
    )
    stale_commit = runtime.process_one()
    assert stale_commit is not None
    stale = stale_commit.state.memory.records[-1]
    assert stale.status.value == "STALE"
    assert not stale.current
    assert verified.memory_id not in {
        record.memory_id for record in stale_commit.state.memory.active_records
    }
    assert len(stale_commit.state.memory.records) == 3


def test_timer_wake_records_expiration_without_model_activity(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    runtime.submit_memory_transition(
        operation=MemoryEventOperation.CONSOLIDATE,
        subject="runtime:observation",
        content_summary="A bounded runtime observation was independently verified.",
        evidence_references=("verification_receipt_runtime",),
        ingress_key="memory:timer-source",
        independently_verified=True,
        occurred_at_utc=T0,
    )
    assert runtime.process_one() is not None
    due = runtime.enqueue_due_memory_expirations(
        at_utc=T0 + timedelta(days=2)
    )
    assert len(due) == 1

    commit = runtime.process_one()

    assert commit is not None
    assert commit.events[0].event_type.value == "MemoryExpiredEvent"
    assert commit.state.memory.records[-1].status.value == "EXPIRED"
    assert not commit.state.memory.records[-1].current
    assert commit.result.model_calls == 0
    assert not commit.result.network_used


def test_supervisor_runs_one_explicit_local_observation_cycle_per_wake(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    calls = []

    def observe_once() -> None:
        calls.append("observed")
        runtime.submit_observation(
            payload=ObservationPayload(
                world_node="local-runtime",
                relation="controller_status",
                value_summary="Controller status was measured as ACTIVE.",
                provenance=ObservationProvenance.SYSTEM_OBSERVED,
                observed_at_utc=T0 + timedelta(seconds=1),
                evidence_references=("runtime_projection_local",),
                current_claim=True,
                confidence_basis_points=10_000,
            ),
            ingress_key="observer-cycle:1",
        )

    supervisor = LocalEntitySupervisor(
        runtime, observation_cycle=observe_once
    )
    commits = supervisor.run_wake_for_testing()

    assert calls == ["observed"]
    assert commits
    assert all(not item.result.network_used for item in commits)
    assert all(item.result.model_calls == 0 for item in commits)


def test_runtime_rejects_client_forced_independent_verification_without_canonical_evidence(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    _ingress = runtime.submit_message(
        text="Pump P17 is the active pump.",
        thread_id="bench-claim",
        ingress_key="bench:claim:1",
        occurred_at_utc=T0 + timedelta(seconds=1),
    )
    commit = runtime.process_one()
    assert commit is not None
    subject_event_id = commit.events[0].event_id

    with pytest.raises(EntityRuntimeError, match="VERIFICATION_EVIDENCE|MODEL_OUTPUT|NOT_CANONICAL"):
        runtime.submit_verification(
            subject_event_id=subject_event_id,
            result="PASSED",
            summary="This claim was self-verified by a client-supplied flag.",
            evidence_references=("model-output:synthetic-claim-1",),
            ingress_key="bench:verify:forced",
            independently_verified=True,
            occurred_at_utc=T0 + timedelta(seconds=2),
        )


def test_runtime_rejects_fabricated_cognition_memory_lineage(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    runtime.submit_message(
        text="Pump P17 is the active pump.",
        thread_id="fabricated-lineage",
        ingress_key="bench:claim:fabricated-lineage",
        occurred_at_utc=T0 + timedelta(seconds=1),
    )
    commit = runtime.process_one()
    assert commit is not None
    subject_event_id = commit.events[0].event_id

    with pytest.raises(EntityRuntimeError, match="VERIFICATION_EVIDENCE_NOT_CANONICAL"):
        runtime.submit_verification(
            subject_event_id=subject_event_id,
            result="PASSED",
            summary="A fabricated cognition memory ID is not canonical lineage.",
            evidence_references=("cognition_memory_" + "f" * 64,),
            ingress_key="bench:verify:fabricated-lineage",
            independently_verified=True,
            occurred_at_utc=T0 + timedelta(seconds=2),
        )


def test_runtime_rejects_fabricated_cognition_memory_with_model_output(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    runtime.submit_message(
        text="Pump P17 is the active pump.",
        thread_id="fabricated-model-lineage",
        ingress_key="bench:claim:fabricated-model-lineage",
        occurred_at_utc=T0 + timedelta(seconds=1),
    )
    commit = runtime.process_one()
    assert commit is not None
    subject_event_id = commit.events[0].event_id
    runtime.submit_observation(
        payload=ObservationPayload(
            world_node="synthetic:glossary",
            relation="model_asserted",
            value_summary="Pump P17 denotes the active pump in the synthetic glossary.",
            provenance=ObservationProvenance.MODEL_INFERRED,
            observed_at_utc=T0 + timedelta(seconds=2),
            evidence_references=("model-output:fabricated-lineage",),
            current_claim=True,
            confidence_basis_points=1000,
        ),
        ingress_key="bench:obs:fabricated-lineage",
    )
    runtime.process_one()

    with pytest.raises(EntityRuntimeError, match="VERIFICATION_EVIDENCE|MODEL_OUTPUT"):
        runtime.submit_verification(
            subject_event_id=subject_event_id,
            result="PASSED",
            summary="Neither fabricated lineage nor model output is independent support.",
            evidence_references=(
                "cognition_memory_" + "e" * 64,
                "model-output:fabricated-lineage",
            ),
            ingress_key="bench:verify:fabricated-model-lineage",
            independently_verified=True,
            occurred_at_utc=T0 + timedelta(seconds=3),
        )


def test_runtime_rejects_model_output_as_independent_verification_evidence(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    _ingress = runtime.submit_message(
        text="Pump P17 is the active pump.",
        thread_id="bench-claim-2",
        ingress_key="bench:claim:2",
        occurred_at_utc=T0 + timedelta(seconds=1),
    )
    commit = runtime.process_one()
    assert commit is not None
    subject_event_id = commit.events[0].event_id

    runtime.submit_observation(
        payload=ObservationPayload(
            world_node="synthetic:glossary",
            relation="model_asserted",
            value_summary="Pump P17 denotes the active pump in this synthetic glossary.",
            provenance=ObservationProvenance.MODEL_INFERRED,
            observed_at_utc=T0 + timedelta(seconds=2),
            evidence_references=("model-output:synthetic-claim-1",),
            current_claim=True,
            confidence_basis_points=1000,
        ),
        ingress_key="bench:obs:model",
    )
    runtime.process_one()

    with pytest.raises(EntityRuntimeError, match="MODEL_OUTPUT|VERIFICATION_EVIDENCE"):
        runtime.submit_verification(
            subject_event_id=subject_event_id,
            result="PASSED",
            summary="The model independently verified its own claim.",
            evidence_references=("model-output:synthetic-claim-1",),
            ingress_key="bench:verify:model",
            independently_verified=True,
            occurred_at_utc=T0 + timedelta(seconds=3),
        )
