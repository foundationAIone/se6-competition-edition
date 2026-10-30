"""Read-only situated identity, documented origin and measured environment.

Audited durable existence is not current runtime liveness, authenticated owner
origin or world truth. Local repository measurements use the existing bounded
observer directly; strings and content hashes never constitute source proof.
"""
from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, PrivateAttr, model_validator

from .canonical_contracts import canonical_sha256
from .entity_store import EntityStore
from .local_entity_observers import RepositoryObservationPolicy, scan_repository

VERSION = "se6-situated-entity-v1"


def _require(value, code):
    if not value:
        raise ValueError(code)


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class OriginView(_Frozen):
    status: Literal["DOCUMENTED_PERSISTENT_GENESIS", "VERIFIED_ACTIVATION_CHAIN"]
    genesis_state_id: str
    genesis_receipt_id: str
    genesis_receipt_hash: str
    ancestry_state_ids: tuple[str, ...]
    ancestry_receipt_ids: tuple[str, ...]
    activation_record_id: str | None
    activation_receipt_id: str | None
    declared_owner_reference: str
    originating_owner_status: Literal["UNKNOWN"] = "UNKNOWN"
    originating_seed_status: Literal["UNKNOWN"] = "UNKNOWN"
    reason: str


class PresenceView(_Frozen):
    historical_runtime_session_id: str
    current_runtime_session_id: str | None
    durable_runtime_status: str
    current_presence: Literal["UNKNOWN", "PAUSED", "STOPPED", "DISCONNECTED"]
    runtime_receipt_id: str | None
    live_process_status: Literal["UNKNOWN"] = "UNKNOWN"
    reason: str


class ResourceBalance(_Frozen):
    name: str
    unit: str
    authorized_budget: int
    consumed: int
    remaining: int
    evidence_references: tuple[str, ...]

    @model_validator(mode="after")
    def balance_is_exact(self):
        _require(0 <= self.consumed <= self.authorized_budget
                 and self.remaining == self.authorized_budget - self.consumed,
                 "SITUATED_RESOURCE_BALANCE")
        return self


class CapabilityBoundary(_Frozen):
    capability: str
    technically_available: bool
    recorded_authority_status: str
    execution_authorized: Literal[False] = False
    evidence_references: tuple[str, ...]


class BoundaryView(_Frozen):
    master_boundary_required: Literal[True] = True
    loops_may_grant_authority: Literal[False] = False
    network_authority: str
    external_requests: str
    capabilities: tuple[CapabilityBoundary, ...]
    stored_boundary_decision: str
    stored_approval_required: bool
    current_world_execution_authority: Literal["NOT_ESTABLISHED_BY_SITUATEDNESS"] = "NOT_ESTABLISHED_BY_SITUATEDNESS"
    evidence_references: tuple[str, ...]


class SituatedObservation(_Frozen):
    observation_id: str
    kind: str
    source_reference: str
    world_node: str
    relation: str
    value_json: str
    epistemic_status: str
    freshness: str
    observed_at_utc: datetime
    evidence_references: tuple[str, ...]
    verification_scope: str

    @model_validator(mode="after")
    def bounded_qualified_value(self):
        _require(_json(json.loads(self.value_json)) == self.value_json,
                 "SITUATED_OBSERVATION_CANONICAL_VALUE")
        _require(self.observed_at_utc.utcoffset() is not None,
                 "SITUATED_OBSERVATION_TIME")
        return self


class SituatedDifference(_Frozen):
    previous_snapshot_id: str | None
    entity_state_changed: bool
    added_observation_ids: tuple[str, ...]
    changed_observation_ids: tuple[str, ...]
    removed_observation_ids: tuple[str, ...]
    contradictions: tuple[str, ...]
    comparison_scope: Literal["SOURCE_BOUND_REPRESENTATIONS_NOT_NEW_WORLD_FACTS"] = "SOURCE_BOUND_REPRESENTATIONS_NOT_NEW_WORLD_FACTS"


class SituatedEntitySnapshot(_Frozen):
    version: Literal["se6-situated-entity-v1"] = VERSION
    snapshot_id: str
    snapshot_hash: str
    entity_id: str
    identity_state_id: str
    entity_state_id: str
    state_hash: str
    state_version: int
    previous_entity_state_id: str | None
    receipt_id: str
    checkpoint_id: str
    frame_hash: str
    observed_at_utc: datetime
    origin: OriginView
    presence: PresenceView
    boundary: BoundaryView
    resources: tuple[ResourceBalance, ...]
    observations: tuple[SituatedObservation, ...]
    difference: SituatedDifference
    geographical_location_status: Literal["UNKNOWN"] = "UNKNOWN"
    absent_sensor_status: Literal["UNKNOWN_NOT_OBSERVED"] = "UNKNOWN_NOT_OBSERVED"
    authority_effect: Literal["NONE"] = "NONE"
    durable_state_written: Literal[False] = False
    _source_attested_hash: str | None = PrivateAttr(default=None)

    def material_fields(self):
        return self.model_dump(mode="python", exclude={"snapshot_id", "snapshot_hash"})

    @model_validator(mode="after")
    def content_addressed(self):
        _require(self.observed_at_utc.utcoffset() is not None
            and all(o.observed_at_utc <= self.observed_at_utc for o in self.observations),
            "SITUATED_OBSERVATION_AFTER_SNAPSHOT")
        _require(self.entity_state_id == "entity_state_" + self.state_hash
                 and self.identity_state_id.startswith("identity_")
                 and self.origin.ancestry_state_ids[-1] == self.entity_state_id,
                 "SITUATED_STATE_IDENTITY_ANCESTRY")
        expected = canonical_sha256(self.material_fields())
        _require(self.snapshot_hash == expected and self.snapshot_id == "situated_entity_" + expected,
                 "SITUATED_SNAPSHOT_CONTENT")
        _require(len({o.observation_id for o in self.observations}) == len(self.observations),
                 "SITUATED_DUPLICATE_OBSERVATION_ID")
        return self


class RepositoryObservationPort:
    """Concrete existing sensor invocation, not an evidence issuer callback."""
    def __init__(self, root, *, policy=None):
        self.root = Path(root).resolve(strict=True)
        _require(self.root.is_dir(), "SITUATED_OBSERVER_ROOT")
        self.policy = policy if policy is not None else RepositoryObservationPolicy()
        _require(type(self.policy) is RepositoryObservationPolicy, "SITUATED_OBSERVER_POLICY")
        self.source_reference = "local-repository:" + canonical_sha256(str(self.root))

    def read_snapshot(self, *, observed_at_utc):
        _require(type(self.policy) is RepositoryObservationPolicy
            and self.source_reference == "local-repository:" + canonical_sha256(str(self.root.resolve(strict=True))),
            "SITUATED_OBSERVER_SOURCE_BINDING")
        return scan_repository(self.root, observed_at_utc=observed_at_utc, policy=self.policy)

    def read(self, *, observed_at_utc):
        observation = self.read_snapshot(observed_at_utc=observed_at_utc)
        value = dict(tree_hash=observation.tree_hash, entry_count=observation.entry_count,
            truncated=observation.truncated, max_files=self.policy.max_files,
            policy_hash=canonical_sha256(self.policy.model_dump(mode="python")),
            entries=[e.model_dump(mode="json") for e in observation.entries])
        stable = canonical_sha256(dict(source=self.source_reference, value=value))
        return SituatedObservation(observation_id="situated_observation_" + stable,
            kind="LOCAL_REPOSITORY_METADATA", source_reference=self.source_reference,
            world_node=self.source_reference, relation="observes_bounded_repository_metadata",
            value_json=_json(value), epistemic_status="MEASURED", freshness="CURRENT_REMEASUREMENT",
            observed_at_utc=observation.observed_at_utc,
            evidence_references=(observation.snapshot_id, observation.tree_hash),
            verification_scope="DIRECT_LOCAL_METADATA_ONLY_NOT_CONTENT_SEMANTICS_OR_WORLD_PERMISSION")


def _difference(previous, entity_id, identity_id, head, observations):
    if previous is None:
        return SituatedDifference(previous_snapshot_id=None, entity_state_changed=False,
            added_observation_ids=(), changed_observation_ids=(), removed_observation_ids=(),
            contradictions=tuple(sorted(o.observation_id for o in observations if o.epistemic_status == "CONTRADICTED")))
    _require(type(previous) is SituatedEntitySnapshot
             and previous._source_attested_hash == previous.snapshot_hash,
             "SITUATED_PREVIOUS_SOURCE_REQUIRED")
    previous = SituatedEntitySnapshot.model_validate_json(previous.model_dump_json())
    _require(previous.entity_id == entity_id and previous.identity_state_id == identity_id,
             "SITUATED_PREVIOUS_IDENTITY")
    before = {(o.kind, o.source_reference, o.world_node, o.relation): o for o in previous.observations}
    after = {(o.kind, o.source_reference, o.world_node, o.relation): o for o in observations}
    changed = tuple(sorted(after[k].observation_id for k in after.keys() & before.keys()
        if (after[k].value_json, after[k].epistemic_status, after[k].freshness) !=
           (before[k].value_json, before[k].epistemic_status, before[k].freshness)))
    return SituatedDifference(previous_snapshot_id=previous.snapshot_id,
        entity_state_changed=previous.entity_state_id != head,
        added_observation_ids=tuple(sorted(after[k].observation_id for k in after.keys() - before.keys())),
        changed_observation_ids=changed,
        removed_observation_ids=tuple(sorted(before[k].observation_id for k in before.keys() - after.keys())),
        contradictions=tuple(sorted(o.observation_id for o in observations if o.epistemic_status == "CONTRADICTED")))


def read_situated_entity(entity_store, *, expected_entity_id, expected_identity_state_id,
        expected_entity_state_id, observation_port=None, runtime_ledger=None, previous=None,
        as_of_utc=None):
    """Compose immutable current source evidence; no Entity writes or grants."""
    _require(type(entity_store) is EntityStore, "SITUATED_ACTUAL_ENTITY_STORE")
    now = datetime.now(UTC) if as_of_utc is None else as_of_utc
    _require(isinstance(now, datetime) and now.utcoffset() is not None, "SITUATED_AWARE_TIME")
    _require(as_of_utc is None or entity_store.is_test_store, "SITUATED_PRODUCTION_CLOCK_FIXED")
    audit, snapshot, lineage = entity_store.inspect_read_only()
    _require(audit.valid and snapshot is not None and lineage is not None, "SITUATED_ENTITY_AUDIT_REQUIRED")
    state = snapshot.state
    _require(state.identity.instance_id == expected_entity_id
        and state.identity.identity_state_id == expected_identity_state_id
        and state.entity_state_id == expected_entity_state_id, "SITUATED_EXACT_ENTITY_HEAD")
    _require(now >= state.updated_at_utc, "SITUATED_AS_OF_BEFORE_SOURCE")
    genesis, origin_receipt = lineage.states[0], lineage.receipts[0]
    _require(origin_receipt.commit_kind == "GENESIS" and genesis.previous_entity_state_id is None
        and genesis.identity.instance_id == state.identity.instance_id
        and state.identity.identity_state_id == "identity_" + state.identity.identity_state_hash,
        "SITUATED_GENESIS_IDENTITY_BINDING")
    head_refs = (state.entity_state_id, snapshot.latest_receipt.receipt_id, snapshot.latest_checkpoint.checkpoint_id)
    origin = OriginView(status="VERIFIED_ACTIVATION_CHAIN" if snapshot.activation_record else "DOCUMENTED_PERSISTENT_GENESIS",
        genesis_state_id=genesis.entity_state_id, genesis_receipt_id=origin_receipt.receipt_id,
        genesis_receipt_hash=origin_receipt.receipt_hash,
        ancestry_state_ids=tuple(s.entity_state_id for s in lineage.states),
        ancestry_receipt_ids=tuple(r.receipt_id for r in lineage.receipts),
        activation_record_id=snapshot.activation_record.activation_record_id if snapshot.activation_record else None,
        activation_receipt_id=snapshot.activation_receipt.receipt_id if snapshot.activation_receipt else None,
        declared_owner_reference=state.identity.owner_identity_reference,
        reason="Audited persisted genesis/activation ancestry; external seed and originating-owner authentication are not inferred.")
    runtime_basis = next(r for r in reversed(lineage.receipts) if r.commit_kind in {"GENESIS", "ACTIVATION", "RUNTIME_REBIND"})
    presence = PresenceView(historical_runtime_session_id=runtime_basis.runtime_session_id,
        current_runtime_session_id=None, durable_runtime_status="UNKNOWN", current_presence="UNKNOWN",
        runtime_receipt_id=None, reason="No independently read matching runtime ledger/liveness evidence.")
    if runtime_ledger is not None:
        from .production_runtime_service import ProductionRuntimeLedger
        _require(type(runtime_ledger) is ProductionRuntimeLedger and runtime_ledger.test_only == entity_store.is_test_store,
                 "SITUATED_ACTUAL_RUNTIME_LEDGER")
        session, runtime_receipt = runtime_ledger.latest_read_only()
        if session is not None:
            _require(session.instance_id == state.identity.instance_id
                and session.identity_state_id == state.identity.identity_state_id
                and session.owner_id == state.identity.owner_identity_reference
                and session.runtime_session_id == runtime_basis.runtime_session_id,
                "SITUATED_RUNTIME_IDENTITY_BINDING")
            _require(runtime_receipt.created_at_utc <= now, "SITUATED_RUNTIME_FUTURE")
            logical = runtime_receipt.resulting_status
            presence = PresenceView(historical_runtime_session_id=runtime_basis.runtime_session_id,
                current_runtime_session_id=session.runtime_session_id, durable_runtime_status=logical,
                current_presence=logical if logical in {"PAUSED", "STOPPED"} else "UNKNOWN",
                runtime_receipt_id=runtime_receipt.receipt_id,
                reason="Current audited logical runtime status; ACTIVE receipts do not prove process liveness.")
    capability = tuple(CapabilityBoundary(capability=c.capability, technically_available=c.available,
        recorded_authority_status=c.authority_status.value, evidence_references=c.evidence_references)
        for c in state.capabilities.capabilities)
    boundary = BoundaryView(network_authority=state.environment_access.network_authority,
        external_requests=state.environment_access.external_requests, capabilities=capability,
        stored_boundary_decision=state.operational_awareness.boundary.effective_decision.value,
        stored_approval_required=state.operational_awareness.boundary.approval_required,
        evidence_references=head_refs)
    resource_fields = (("tokens", "TOKEN_COUNT", "token_budget", "token_count"),
        ("model_calls", "MODEL_CALL_COUNT", "model_call_budget", "model_calls"),
        ("entity_events", "ENTITY_EVENT_COUNT", "event_budget", "events_processed"),
        ("tool_calls", "TOOL_CALL_COUNT", "tool_call_budget", "tool_calls"),
        ("network_calls", "NETWORK_CALL_COUNT", "network_call_budget", "network_calls"),
        ("elapsed_time", "MILLISECOND", "elapsed_time_budget_ms", "elapsed_time_ms"))
    resources = tuple(ResourceBalance(name=name, unit=unit,
        authorized_budget=getattr(state.resources, budget), consumed=getattr(state.resources, count),
        remaining=getattr(state.resources, budget) - getattr(state.resources, count), evidence_references=head_refs)
        for name, unit, budget, count in resource_fields)
    observations = []
    current_values = {}
    for relation in state.environment.relations:
        if relation.current and relation.epistemic_status.value not in {"REVOKED", "EXPIRED", "STALE"}:
            current_values.setdefault((relation.world_node, relation.relation), set()).add(relation.value_summary)
    for relation in state.environment.relations:
        status = relation.epistemic_status.value
        # Independently verified-looking strings in retained state are not a
        # new independent witness. Preserve measured/reported/inferred scopes.
        if status == "VERIFIED": status = "OBSERVED"
        if not relation.current and status not in {"CONTRADICTED", "REVOKED", "EXPIRED"}: status = "STALE"
        contradictory = relation.current and len(current_values.get((relation.world_node, relation.relation), ())) > 1
        if contradictory: status = "CONTRADICTED"
        observations.append(SituatedObservation(observation_id=relation.relation_id, kind="RETAINED_ENTITY_RELATION",
            source_reference=relation.source_event_id, world_node=relation.world_node, relation=relation.relation,
            value_json=_json(relation.value_summary), epistemic_status=status,
            freshness="HISTORICAL_NO_CURRENT_WITNESS", observed_at_utc=relation.observed_at_utc,
            evidence_references=(relation.source_event_id, *relation.evidence_references),
            verification_scope=("DERIVED_CONTRADICTION_BETWEEN_CURRENT_RETAINED_REPORTS_NOT_INDEPENDENT_FACTS"
                if contradictory else "ACTUAL_DURABLE_RELATION_STATUS_NOT_RECONSTRUCTED_EXTERNAL_VERIFICATION")))
    if observation_port is not None:
        _require(type(observation_port) is RepositoryObservationPort, "SITUATED_ACTUAL_OBSERVATION_PORT")
        observations.append(observation_port.read(observed_at_utc=now))
    observations = tuple(sorted(observations, key=lambda o: o.observation_id))
    difference = _difference(previous, expected_entity_id, expected_identity_state_id, expected_entity_state_id, observations)
    frame = canonical_sha256(dict(domain=VERSION, entity_id=expected_entity_id,
        identity_state_id=expected_identity_state_id, genesis_receipt_hash=origin_receipt.receipt_hash))
    material = dict(version=VERSION, entity_id=expected_entity_id, identity_state_id=expected_identity_state_id,
        entity_state_id=state.entity_state_id, state_hash=state.state_hash, state_version=state.state_version,
        previous_entity_state_id=state.previous_entity_state_id, receipt_id=snapshot.latest_receipt.receipt_id,
        checkpoint_id=snapshot.latest_checkpoint.checkpoint_id, frame_hash=frame, observed_at_utc=now,
        origin=origin, presence=presence, boundary=boundary, resources=resources, observations=observations,
        difference=difference, geographical_location_status="UNKNOWN", absent_sensor_status="UNKNOWN_NOT_OBSERVED",
        authority_effect="NONE", durable_state_written=False)
    after_audit, after, _ = entity_store.inspect_read_only()
    _require(after_audit.valid and after is not None and after.state == state
        and after.latest_receipt == snapshot.latest_receipt, "SITUATED_CONCURRENT_ENTITY_CHANGE")
    provisional = SituatedEntitySnapshot.model_construct(snapshot_id="", snapshot_hash="", **material)
    content_hash = canonical_sha256(provisional.material_fields())
    result = SituatedEntitySnapshot(snapshot_id="situated_entity_" + content_hash, snapshot_hash=content_hash, **material)
    result._source_attested_hash = content_hash
    return result


def verify_situated_entity(entity_store, snapshot, *, observation_port=None, runtime_ledger=None, previous=None):
    """Re-read actual sources before consumption or cold source restoration."""
    _require(type(snapshot) is SituatedEntitySnapshot, "SITUATED_TYPED_SNAPSHOT")
    validated = SituatedEntitySnapshot.model_validate_json(snapshot.model_dump_json())
    current = read_situated_entity(entity_store, expected_entity_id=validated.entity_id,
        expected_identity_state_id=validated.identity_state_id, expected_entity_state_id=validated.entity_state_id,
        observation_port=observation_port, runtime_ledger=runtime_ledger, previous=previous,
        as_of_utc=validated.observed_at_utc if entity_store.is_test_store else None)
    _require(validated.observed_at_utc <= current.observed_at_utc,
             "SITUATED_FUTURE_SNAPSHOT_TIME")
    def current_source_material(value):
        material = value.material_fields()
        # Current remeasurement legitimately has a newer timestamp and witness
        # snapshot ID. Compare its exact stable source/metadata semantics, then
        # return the NEW actually witnessed projection. No TTL is invented and
        # the old timestamp is never promoted to a fresh observation.
        material.pop('observed_at_utc')
        for observation in material['observations']:
            if observation['freshness'] == 'CURRENT_REMEASUREMENT':
                observation.pop('observed_at_utc')
                observation['evidence_references'] = observation['evidence_references'][1:]
        return material
    _require(current_source_material(current) == current_source_material(validated),
             "SITUATED_SOURCE_REPLAY_MISMATCH")
    return current
