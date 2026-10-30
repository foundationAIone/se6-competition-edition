"""Focused tests for the Entity-bound durable cognition layer.

All stores and transports in this module are disposable.  No production
Entity, Level-5 evidence, credential, or external network is touched.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier

import pytest
from pydantic import ValidationError

from se666_core.embodiment_lifecycle import LifecycleState
from se666_core.entity_capability_gateway import (
    CapabilityAuthoritySource,
    CapabilityBudget,
    CapabilityGatewayError,
    CapabilityRateLimit,
    EntityCapabilityGateway,
    create_capability_grant,
    create_capability_request,
    create_capability_revocation,
)
from se666_core.entity_cognition import (
    AttentionDimensions,
    AttentionResourceEnvelope,
    CapabilityType,
    EvidenceSourceKind,
    FourPillarsAttestation,
    HardBoundaryAttestation,
    MemoryStatus,
    ObjectiveOrigin,
    ObjectiveStatus,
    PiBDecision,
    create_attention_record,
    create_evidence_reference,
    create_memory_record,
    create_objective_record,
    evaluate_candidate_admission,
)
from se666_core.entity_cognition_store import (
    CognitionStoreError,
    CognitionStorePolicy,
    EntityCognitionStore,
)
from se666_core.entity_runtime import LocalEntityRuntime
from se666_core.entity_state import (
    ControllerStatus,
    EmergencyStopState,
    LifecycleView,
    OperationalConnectionState,
    create_entity_state,
)
from se666_core.entity_store import EntityStore
from tests.test_local_entity_runtime import _state

T0 = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
ENTITY_ID = f"instance_{'1' * 64}"
IDENTITY_ID = f"identity_{'2' * 64}"
ENTITY_STATE_ID = f"entity_state_{'3' * 64}"


def _entity_store(tmp_path: Path) -> EntityStore:
    initial = _state(local_live=True)
    material = {
        name: getattr(initial, name)
        for name in initial.__class__.model_fields
        if name not in {"entity_state_id", "state_hash"}
    }
    material["identity"] = initial.identity.model_copy(
        update={
            "instance_id": ENTITY_ID,
            "identity_state_id": IDENTITY_ID,
            "identity_state_hash": "2" * 64,
            "identity_lineage": (IDENTITY_ID,),
        }
    )
    state = create_entity_state(**material)
    store = EntityStore.for_testing(tmp_path / "entity.sqlite3")
    LocalEntityRuntime(
        store=store,
        runtime_session_id="runtime_cognition_test",
        clock=lambda: T0,
    ).initialize(state=state)
    return store


def _cognition_store(
    tmp_path: Path, *, maximum_active_attention: int = 64
) -> EntityCognitionStore:
    store = EntityCognitionStore.for_testing(
        tmp_path / "cognition.sqlite3",
        entity_store=_entity_store(tmp_path),
        policy=CognitionStorePolicy(
            maximum_active_attention=maximum_active_attention
        ),
    )
    store.initialize(created_at_utc=T0)
    return store


def _verified_evidence():
    return create_evidence_reference(
        entity_id=ENTITY_ID,
        source_kind=EvidenceSourceKind.INDEPENDENT_VERIFIER,
        source_id="verification:test",
        content_hash="b" * 64,
        observed_at_utc=T0,
        independently_verified=True,
        verification_reference="receipt:verification-test",
    )


def _gateway(tmp_path: Path) -> tuple[EntityCapabilityGateway, EntityCognitionStore]:
    store = _cognition_store(tmp_path)
    gateway = EntityCapabilityGateway(
        store=store,
        authority_verifier=lambda reference, source: (
            reference == "owner-grant:test"
            and source is CapabilityAuthoritySource.OWNER_AUTHENTICATED
        ),
    )
    return gateway, store


def _grant(
    store: EntityCognitionStore,
    *,
    capability: CapabilityType = CapabilityType.CODE_READ,
    allowed_targets: tuple[str, ...] = ("repository:se666_core",),
    scopes: tuple[str, ...] = ("READ_ONLY",),
    maximum_requests: int = 4,
    rate_requests: int = 2,
    issued_at_utc: datetime = T0,
    expires_at_utc: datetime = T0 + timedelta(hours=1),
):
    binding = store.binding()
    return create_capability_grant(
        entity_id=binding.entity_id,
        identity_state_id=binding.current_identity_state_id,
        entity_state_id=binding.current_entity_state_id,
        capability=capability,
        authority_source=CapabilityAuthoritySource.OWNER_AUTHENTICATED,
        authority_reference="owner-grant:test",
        scopes=scopes,
        allowed_targets=allowed_targets,
        budget=CapabilityBudget(
            maximum_requests=maximum_requests,
            maximum_bytes=1_000_000,
            maximum_elapsed_ms=10_000,
        ),
        rate_limit=CapabilityRateLimit(
            maximum_requests=rate_requests,
            window_seconds=60,
        ),
        issued_at_utc=issued_at_utc,
        expires_at_utc=expires_at_utc,
        audit_reference="owner-audit:test",
    )


def test_memory_status_vocabulary_and_model_false_fact_prevention() -> None:
    assert tuple(status.value for status in MemoryStatus) == (
        "OBSERVATION",
        "HYPOTHESIS",
        "INFERENCE",
        "PROVISIONAL",
        "VERIFIED_FACT",
        "CONTRADICTED",
        "SUPERSEDED",
        "REVOKED",
        "EXPIRED",
    )
    model_evidence = create_evidence_reference(
        entity_id=ENTITY_ID,
        source_kind=EvidenceSourceKind.MODEL_OUTPUT,
        source_id="model-output:test",
        content_hash="a" * 64,
        observed_at_utc=T0,
        independently_verified=False,
        verification_reference=None,
    )

    with pytest.raises(
        ValidationError, match="VERIFIED_FACT requires independent verified evidence"
    ):
        create_memory_record(
            entity_id=ENTITY_ID,
            identity_state_id=IDENTITY_ID,
            entity_state_id=ENTITY_STATE_ID,
            subject="claim:test",
            content_summary="A model asserted this claim.",
            status=MemoryStatus.VERIFIED_FACT,
            confidence_basis_points=9_000,
            provenance=(model_evidence,),
            evidence=(model_evidence,),
            objective_ids=(),
            recorded_at_utc=T0,
        )


def test_memory_persists_with_entity_and_loop_binding_across_reopen(
    tmp_path: Path,
) -> None:
    store = _cognition_store(tmp_path)
    evidence = _verified_evidence()
    record = create_memory_record(
        entity_id=ENTITY_ID,
        identity_state_id=IDENTITY_ID,
        entity_state_id=store.binding().current_entity_state_id,
        subject="runtime:continuity",
        content_summary="The bounded cognition store reconstructed successfully.",
        status=MemoryStatus.VERIFIED_FACT,
        confidence_basis_points=10_000,
        provenance=(evidence,),
        evidence=(evidence,),
        objective_ids=("objective:continuity",),
        recorded_at_utc=T0,
    )
    store.append_memory(record)

    reopened = EntityCognitionStore.for_testing(
        store.path,
        entity_store=store.entity_store,
        policy=store.policy,
    )
    audit = reopened.audit_read_only()

    assert audit.valid
    assert audit.memory_record_count == 1
    assert reopened.memory_records() == (record,)
    assert reopened.binding().entity_id == ENTITY_ID
    assert (
        reopened.binding().binding.root_runtime_session_id
        == "runtime_cognition_test"
    )
    assert len(set(reopened.binding().loop_ids)) == 3
    assert audit.network_authority == "NONE"
    assert audit.external_requests == "BLOCKED"


def test_derived_objective_cannot_expand_parent_authority_or_capabilities(
    tmp_path: Path,
) -> None:
    store = _cognition_store(tmp_path)
    state_id = store.binding().current_entity_state_id
    parent = create_objective_record(
        objective_id="objective:parent",
        entity_id=ENTITY_ID,
        identity_state_id=IDENTITY_ID,
        entity_state_id=state_id,
        revision=1,
        previous_objective_record_id=None,
        parent_objective_id=None,
        description="Inspect bounded repository state.",
        origin=ObjectiveOrigin.OWNER,
        priority=90,
        status=ObjectiveStatus.ACTIVE,
        governing_authority_reference="owner-authority:test",
        authority_scope=("repository:read",),
        required_capabilities=(CapabilityType.CODE_READ,),
        constraints=("No external effects.",),
        progress_summary="Not started.",
        evidence_references=("owner-request:test",),
        completion_condition="A bounded read report exists.",
        created_at_utc=T0,
        updated_at_utc=T0,
        derived=False,
    )
    store.append_objective(parent)
    child = create_objective_record(
        objective_id="objective:child",
        entity_id=ENTITY_ID,
        identity_state_id=IDENTITY_ID,
        entity_state_id=state_id,
        revision=1,
        previous_objective_record_id=None,
        parent_objective_id=parent.objective_id,
        description="Read one bounded source file.",
        origin=ObjectiveOrigin.ENTITY_DERIVED,
        priority=80,
        status=ObjectiveStatus.ACTIVE,
        governing_authority_reference=parent.governing_authority_reference,
        authority_scope=("repository:read",),
        required_capabilities=(CapabilityType.CODE_READ,),
        constraints=parent.constraints,
        progress_summary="Not started.",
        evidence_references=(parent.objective_record_id,),
        completion_condition="One source file has been inspected.",
        created_at_utc=T0,
        updated_at_utc=T0,
        derived=True,
    )
    store.append_objective(child)
    escalated = create_objective_record(
        **{
            **child.model_dump(
                mode="python", exclude={"objective_record_id"}
            ),
            "objective_id": "objective:escalated-child",
            "required_capabilities": (
                CapabilityType.CODE_READ,
                CapabilityType.API_WRITE,
            ),
        }
    )

    with pytest.raises(CognitionStoreError) as caught:
        store.append_objective(escalated)
    assert caught.value.code == "OBJECTIVE_AUTHORITY_ESCALATION"


def test_attention_is_dimensioned_resource_bounded_and_capacity_limited(
    tmp_path: Path,
) -> None:
    store = _cognition_store(tmp_path, maximum_active_attention=1)
    common = {
        "entity_id": ENTITY_ID,
        "identity_state_id": IDENTITY_ID,
        "entity_state_id": store.binding().current_entity_state_id,
        "dimensions": AttentionDimensions(
            relevance=90,
            change=80,
            uncertainty=70,
            risk=60,
            deadline=50,
            novelty=40,
            recurrence=30,
            owner_priority=100,
        ),
        "objective_ids": ("objective:continuity",),
        "evidence_references": ("observation:test",),
        "resources": AttentionResourceEnvelope(
            maximum_work_items=2,
            maximum_events=4,
            maximum_elapsed_ms=500,
        ),
        "recorded_at_utc": T0,
        "deadline_at_utc": T0 + timedelta(hours=1),
        "expires_at_utc": T0 + timedelta(hours=2),
        "supersedes_attention_id": None,
        "current": True,
    }
    store.append_attention(
        create_attention_record(subject="subject:first", **common)
    )

    with pytest.raises(CognitionStoreError) as caught:
        store.append_attention(
            create_attention_record(subject="subject:second", **common)
        )
    assert caught.value.code == "ATTENTION_BOUND_EXCEEDED"


def test_four_pillars_cannot_override_a_hard_boundary() -> None:
    admission = evaluate_candidate_admission(
        entity_id=ENTITY_ID,
        candidate_id="candidate:test",
        candidate_hash="c" * 64,
        pi_b_decision=PiBDecision.ALLOW,
        hard_boundaries=HardBoundaryAttestation(
            safety=False,
            law=True,
            consent=True,
            authority=True,
            privacy=True,
            emergency_stop_clear=True,
        ),
        four_pillars=FourPillarsAttestation(
            authenticity=True,
            integrity=True,
            responsibility=True,
            enrichment=True,
        ),
        evaluated_at_utc=T0,
    )

    assert not admission.admitted
    assert admission.reason_codes == ("HARD_BOUNDARY_SAFETY",)


def test_capability_scope_expiry_revocation_and_rate_are_durable(
    tmp_path: Path,
) -> None:
    gateway, store = _gateway(tmp_path)
    grant = _grant(store, rate_requests=1)
    gateway.record_grant(grant)
    first = gateway.evaluate(
        create_capability_request(
            grant=grant,
            target="repository:se666_core",
            requested_scopes=("READ_ONLY",),
            requested_bytes=100,
            requested_elapsed_ms=10,
            requested_at_utc=T0 + timedelta(seconds=1),
        )
    )
    second = gateway.evaluate(
        create_capability_request(
            grant=grant,
            target="repository:se666_core",
            requested_scopes=("READ_ONLY",),
            requested_bytes=100,
            requested_elapsed_ms=10,
            requested_at_utc=T0 + timedelta(seconds=2),
        )
    )

    assert first.allowed
    assert second.reason_codes == ("CAPABILITY_RATE_LIMIT_EXCEEDED",)
    reopened = EntityCapabilityGateway(
        store=EntityCognitionStore.for_testing(
            store.path,
            entity_store=store.entity_store,
            policy=store.policy,
        ),
        authority_verifier=lambda reference, source: (
            reference == "owner-grant:test"
            and source is CapabilityAuthoritySource.OWNER_AUTHENTICATED
        ),
    )
    assert len(reopened.audit_records()) == 3

    runtime = LocalEntityRuntime(
        store=store.entity_store,
        runtime_session_id="runtime_cognition_after_grant",
        clock=lambda: T0 + timedelta(seconds=30),
    )
    runtime.submit_message(
        text="Advance the Entity before revoking its durable grant.",
        thread_id="programmerone-primary",
        ingress_key="capability-revocation-state-advance:1",
        occurred_at_utc=T0 + timedelta(seconds=30),
    )
    assert runtime.process_one() is not None
    assert store.binding().current_entity_state_id != grant.entity_state_id
    revocation = create_capability_revocation(
        grant=grant,
        entity_state_id=store.binding().current_entity_state_id,
        authority_source=CapabilityAuthoritySource.OWNER_AUTHENTICATED,
        authority_reference="owner-grant:test",
        reason="Owner revoked the bounded grant.",
        revoked_at_utc=T0 + timedelta(minutes=2),
    )
    reopened.record_revocation(revocation)
    revoked = reopened.evaluate(
        create_capability_request(
            grant=grant,
            target="repository:se666_core",
            requested_scopes=("READ_ONLY",),
            requested_bytes=1,
            requested_elapsed_ms=1,
            requested_at_utc=T0 + timedelta(minutes=3),
        )
    )
    assert "CAPABILITY_GRANT_REVOKED" in revoked.reason_codes

    expired_grant = _grant(
        store,
        issued_at_utc=T0 - timedelta(hours=2),
        expires_at_utc=T0 - timedelta(hours=1),
    )
    gateway.record_grant(expired_grant)
    expired = gateway.evaluate(
        create_capability_request(
            grant=expired_grant,
            target="repository:se666_core",
            requested_scopes=("READ_ONLY",),
            requested_bytes=1,
            requested_elapsed_ms=1,
            requested_at_utc=T0,
        )
    )
    assert "CAPABILITY_GRANT_EXPIRED" in expired.reason_codes


def test_stale_grant_requires_explicit_verified_ancestor_path(tmp_path) -> None:
    gateway, store = _gateway(tmp_path)
    grant = _grant(
        store,
        capability=CapabilityType.HTTP_READ_ALLOWLISTED,
        allowed_targets=("example.com",),
        scopes=("READ_ONLY_OBSERVATION",),
    )
    runtime = LocalEntityRuntime(
        store=store.entity_store,
        runtime_session_id="runtime_cognition_test",
        clock=lambda: T0,
    )
    runtime.submit_message(
        text="Advance ordinary cognition after exact review.",
        thread_id="programmerone-primary",
        ingress_key="stale-grant-explicit-ancestor:1",
        occurred_at_utc=T0,
    )
    assert runtime.process_one() is not None
    assert store.binding().current_entity_state_id != grant.entity_state_id

    with pytest.raises(CapabilityGatewayError) as caught:
        gateway.record_grant(grant)
    assert caught.value.code == "CAPABILITY_GRANT_ENTITY_BINDING_MISMATCH"

    recorded = gateway.record_grant(
        grant,
        accepted_ancestor_entity_state_id=grant.entity_state_id,
    )
    assert recorded == grant
    assert store.audit_read_only().valid


def test_concurrent_single_use_budget_allows_exactly_one_request(tmp_path) -> None:
    gateway, store = _gateway(tmp_path)
    grant = _grant(store, maximum_requests=1, rate_requests=10)
    gateway.record_grant(grant)
    requests = tuple(
        create_capability_request(
            grant=grant,
            target="repository:se666_core",
            requested_scopes=("READ_ONLY",),
            requested_bytes=100,
            requested_elapsed_ms=10,
            requested_at_utc=T0 + timedelta(seconds=index + 1),
        )
        for index in range(2)
    )
    barrier = Barrier(2)

    def evaluate(index: int):
        contender = EntityCapabilityGateway(
            store=EntityCognitionStore.for_testing(
                store.path,
                entity_store=store.entity_store,
                policy=store.policy,
            )
        )
        barrier.wait()
        return contender.evaluate(requests[index])

    with ThreadPoolExecutor(max_workers=2) as pool:
        decisions = tuple(pool.map(evaluate, range(2)))

    assert sum(item.allowed for item in decisions) == 1
    refused = next(item for item in decisions if not item.allowed)
    assert set(refused.reason_codes) & {
        "CAPABILITY_REQUEST_BUDGET_EXCEEDED",
        "CAPABILITY_REQUEST_TIME_NON_MONOTONIC",
    }
    assert len(gateway.audit_records()) == 3
    assert store.audit_read_only().valid


def test_cumulative_elapsed_budget_is_durable(tmp_path) -> None:
    gateway, store = _gateway(tmp_path)
    binding = store.binding()
    grant = create_capability_grant(
        entity_id=binding.entity_id,
        identity_state_id=binding.current_identity_state_id,
        entity_state_id=binding.current_entity_state_id,
        capability=CapabilityType.CODE_READ,
        authority_source=CapabilityAuthoritySource.OWNER_AUTHENTICATED,
        authority_reference="owner-grant:test",
        scopes=("READ_ONLY",),
        allowed_targets=("repository:se666_core",),
        budget=CapabilityBudget(
            maximum_requests=10,
            maximum_bytes=10_000,
            maximum_elapsed_ms=15,
        ),
        rate_limit=CapabilityRateLimit(maximum_requests=10, window_seconds=60),
        issued_at_utc=T0,
        expires_at_utc=T0 + timedelta(hours=1),
        audit_reference="owner-audit:test",
    )
    gateway.record_grant(grant)
    first = gateway.evaluate(
        create_capability_request(
            grant=grant,
            target="repository:se666_core",
            requested_scopes=("READ_ONLY",),
            requested_bytes=1,
            requested_elapsed_ms=10,
            requested_at_utc=T0 + timedelta(seconds=1),
        )
    )
    second = gateway.evaluate(
        create_capability_request(
            grant=grant,
            target="repository:se666_core",
            requested_scopes=("READ_ONLY",),
            requested_bytes=1,
            requested_elapsed_ms=10,
            requested_at_utc=T0 + timedelta(seconds=2),
        )
    )

    assert first.allowed
    assert second.reason_codes == ("CAPABILITY_REQUEST_BUDGET_EXCEEDED",)


def test_network_grant_still_refuses_disabled_and_non_allowlisted_targets(
    tmp_path: Path,
) -> None:
    gateway, store = _gateway(tmp_path)
    grant = _grant(
        store,
        capability=CapabilityType.HTTP_READ_ALLOWLISTED,
        allowed_targets=("docs.python.org",),
        scopes=("READ_ONLY_OBSERVATION",),
    )
    gateway.record_grant(grant)
    disabled = gateway.evaluate(
        create_capability_request(
            grant=grant,
            target="https://docs.python.org/3/",
            requested_scopes=("READ_ONLY_OBSERVATION",),
            requested_bytes=4096,
            requested_elapsed_ms=1000,
            requested_at_utc=T0 + timedelta(seconds=1),
        )
    )
    refused_target = gateway.evaluate(
        create_capability_request(
            grant=grant,
            target="https://example.com/",
            requested_scopes=("READ_ONLY_OBSERVATION",),
            requested_bytes=4096,
            requested_elapsed_ms=1000,
            requested_at_utc=T0 + timedelta(seconds=2),
        )
    )

    assert not disabled.allowed
    assert disabled.reason_codes == (
        "NETWORK_AUTHORITY_NONE",
        "EXTERNAL_REQUESTS_BLOCKED",
    )
    assert "CAPABILITY_TARGET_NOT_ALLOWED" in refused_target.reason_codes


def test_canonical_emergency_stop_dominates_an_existing_grant(
    tmp_path: Path,
) -> None:
    gateway, store = _gateway(tmp_path)
    grant = _grant(store)
    gateway.record_grant(grant)
    snapshot = store.entity_store.reconstruct()
    stopped_at = T0 + timedelta(minutes=1)
    references = ("runtime-receipt:stopped", "emergency-stop:verified")
    store.entity_store.commit_runtime_detach(
        expected_state_id=snapshot.state.entity_state_id,
        expected_state_version=snapshot.state.state_version,
        expected_runtime_session_id=snapshot.latest_receipt.runtime_session_id,
        lifecycle=LifecycleView(
            durable_state=LifecycleState.STOPPED,
            operational_state=OperationalConnectionState.DISCONNECTED_SAFE,
            controller_status=ControllerStatus.ABSENT,
            controller_authoritative=False,
            emergency_stop=EmergencyStopState.TRIGGERED,
            observed_at_utc=stopped_at,
            evidence_references=references,
        ),
        verified_runtime_receipt_references=references,
        occurred_at_utc=stopped_at,
        committed_at_utc=stopped_at,
    )

    decision = gateway.evaluate(
        create_capability_request(
            grant=grant,
            target="repository:se666_core",
            requested_scopes=("READ_ONLY",),
            requested_bytes=1,
            requested_elapsed_ms=1,
            requested_at_utc=stopped_at + timedelta(seconds=1),
        )
    )

    assert "EMERGENCY_STOP_ACTIVE" in decision.reason_codes
    assert "ENTITY_RUNTIME_NOT_AUTHORITATIVE" in decision.reason_codes