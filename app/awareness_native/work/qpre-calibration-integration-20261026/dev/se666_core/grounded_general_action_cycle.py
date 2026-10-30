"""Development-only witnessed action/assimilation bridge for audited Entity states.

This connector deliberately does NOT grant production authority. It consumes a
read-only SE6 Entity selection and a separate exact test-only permission, then
performs ONE explicitly bounded disposable local-file effect, independently
reads it back and constructs the existing audited Entity Observation and
Assimilation events. Unknown/failed effects stop without a retry.

Only usable against a disposable EntityStore created by for_testing and a
scratch fixture marked explicitly for this protocol. Not full canonical/AGI.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile

from .entity_store import EntityStore
from .entity_events import (
    EntityEventDraft, EventType, LoopName, EventEndpoint,
    EventSourceKind, ObservationProvenance, AuthorityStatus,
    ObservationPayload, MemoryPayload, MemoryEventOperation,
)
from .epistemic_status import EpistemicStatus
from .three_loop_entity import SE6TriLoopCoordinator
from .grounded_general_state import (
    project_general_state, recheck_general_state,
    select_entity_readonly, verify_audited_successor,
)

VERSION = 'se6-disposable-general-action-witness-v1'
MARKER = '.SE6_DISPOSABLE_ACTION_CYCLE'
MARKER_VALUE = 'se6-test-world-only-v1'


class GeneralCycleStop(RuntimeError):
    """Stable fail-closed test-world failure (no automatic retries)."""


@dataclass(frozen=True)
class DisposableActionPermission:
    # Supplied by an independently authorized test runner. Mere possession of
    # a read-only selection never satisfies this permission by itself.
    entity_state_id: str
    selection_query: str
    world_sha256_before: str
    desired_counter: int
    attempt_id: str
    world_path: str
    authority_scope: str = 'DISPOSABLE_FILE_WRITE_EXACT'


def _canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def _sha(value: bytes) -> str:
    return sha256(value).hexdigest()


def _must(ok, reason):
    if not ok:
        raise GeneralCycleStop(reason)


def _verify_scope(store, world: Path):
    """Refuse any production path even with a forged/mistaken test grant."""
    _must(type(store) is EntityStore, 'ENTITY_STORE_TYPE')
    root = world.parent.resolve(strict=True)
    _must(root.parent == Path(tempfile.gettempdir()).resolve(strict=True) and
          root.name.startswith('SE6-BOUNDED-WITNESS-'),
          'NOT_DISPOSABLE_WORLD_ROOT')
    _must(world.name == 'world.json' and world.is_file() and not world.is_symlink(),
          'NOT_DISPOSABLE_WORLD_FILE')
    marker = root / MARKER
    _must(marker.is_file() and not marker.is_symlink() and
          marker.read_text(encoding='utf-8') == MARKER_VALUE,
          'NO_EXPLICIT_TEST_WORLD_MARKER')
    # Require for_testing store rooted in exactly the same temporary fixture.
    db = root / 'entity.sqlite3'
    _must(db.is_file() and not db.is_symlink(), 'DISPOSABLE_STORE_REQUIRED')
    # _store_locator uses the actual EntityStore file location; check through
    # its public audited read and its concrete test-path reference.
    from .entity_research_bridge import _store_locator
    _must(isinstance(_store_locator(store), str), 'STORE_LOCATOR_REQUIRED')
    store_path = getattr(store, '_path', None)
    if store_path is None:
        # Supported EntityStore versions use path, not _path; see below.
        store_path = getattr(store, 'path', None)
    _must(store_path is not None and Path(store_path).resolve(strict=True) == db,
          'TEST_STORE_WRONG_WORLD_ROOT')
    return root


def _independent_read(world: Path, *, timeout=10):
    """Read effect from a different process, not the actor's write return."""
    code = (
        'import sys,json,pathlib,hashlib;'
        'b=pathlib.Path(sys.argv[1]).read_bytes();'
        'v=json.loads(b);'
        'print(json.dumps({"value":v,"sha256":hashlib.sha256(b).hexdigest()}))'
    )
    run = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', code, str(world)],
                         capture_output=True, text=True, timeout=timeout)
    _must(run.returncode == 0, 'INDEPENDENT_READBACK_PROCESS_FAILED')
    result = json.loads(run.stdout)
    _must(type(result) is dict and set(result) == {'value','sha256'},
          'INDEPENDENT_READBACK_FIELDS')
    return result


def _commit(store, coordinator, draft, key, timestamp):
    """Reuse audited EntityStore ingress/commit; never invent a receipt."""
    ingress = store.enqueue(draft=draft, ingress_key=key, enqueued_at_utc=timestamp)
    coordinator.enqueue(draft)
    before = coordinator.state
    n = len(coordinator.bus.events)
    step = coordinator.run_step(expected_state_version=before.state_version)
    events = coordinator.bus.events[n:]
    receipt = store.commit_step(
        expected_state_id=before.entity_state_id,
        expected_state_version=before.state_version,
        ingress_id=ingress.ingress_id,
        state_after=coordinator.state,
        events=events,
        result=step,
        runtime_session_id='isolated-test-session',
        committed_at_utc=timestamp,
        queued_drafts=coordinator.pending_drafts,
    )
    return events, receipt


def execute_disposable_general_cycle(*, store: EntityStore, coordinator,
                                      requests: list[dict], permission: DisposableActionPermission,
                                      world: Path,
                                      timestamp: datetime | None = None):
    """One bounded REAL test-world cycle, with action selected from SE6 read-only result.

    Existing Entity state/receipts must be authoritative for the *test fixture*.
    The injected permission is test-only and is NOT derived from the selector.
    If the independent verification fails after the world effect, no memory or
    observation is committed; the attempt remains claimed to prevent replay.
    """
    _must(type(permission) is DisposableActionPermission, 'SEPARATE_PERMISSION_REQUIRED')
    world = Path(world)
    root = _verify_scope(store, world)
    _must(isinstance(coordinator, SE6TriLoopCoordinator), 'COORDINATOR_TYPE')
    _must(coordinator.state == store.reconstruct().state, 'COORDINATOR_STATE_STALE')
    _must(type(permission.attempt_id) is str and 4 <= len(permission.attempt_id) <= 64 and
          all(c.isalnum() or c in '-_' for c in permission.attempt_id), 'ATTEMPT_ID')
    _must(permission.authority_scope == 'DISPOSABLE_FILE_WRITE_EXACT' and
          permission.world_path == str(world.resolve(strict=True)) and
          permission.desired_counter == 1,
          'EXTERNAL_EXACT_SCOPE_REQUIRED')
    _must(type(permission.selection_query) is str and permission.selection_query != '',
          'PERMISSION_SELECTION_REQUIRED')
    # Authenticated Entity projection and mapping/QPRE/Sphere selection are
    # consumed by this effect choice. None of these grant permission.
    p0, packet0 = project_general_state(store)
    selection = select_entity_readonly(store, requests)
    _must(selection['status'] == 'READ_ONLY_PROPOSAL' and
          selection['selected_query'] == permission.selection_query and
          selection['actions'] == [] and
          selection['audit']['authority_effect'] == 'NONE' and
          selection['audit']['source_projection'] == p0.projection_hash,
          'SELECTION_NOT_SOURCE_BOUND_OR_INELIGIBLE')
    _must(permission.entity_state_id == p0.entity_state_id, 'PERMISSION_WRONG_ENTITY_HEAD')
    original = world.read_bytes()
    _must(_sha(original) == permission.world_sha256_before and
          json.loads(original) == {'counter': 0}, 'WORLD_PRECONDITION_CHANGED')
    _must(type(timestamp) is datetime and timestamp.tzinfo is not None,
          'TEST_TIMESTAMP_REQUIRED')
    recheck_general_state(store, p0, packet0)
    # A durable attempt claim goes to disk BEFORE any side effect. Never retry
    # an uncertain effect, even when verification times out or commit fails.
    claim = root / ('attempt-' + permission.attempt_id + '.json')
    try:
        with claim.open('x', encoding='utf-8') as f:
            f.write(_canonical({'schema':VERSION,'entity_state_id':p0.entity_state_id,
               'permission_attempt':permission.attempt_id,
               'world_preimage_hash':_sha(original),
               'selected_query':selection['selected_query'],
               'status':'CLAIMED_BEFORE_EFFECT'}).decode('utf-8'))
            f.flush()
            os.fsync(f.fileno())
    except FileExistsError as e:
        raise GeneralCycleStop('ATTEMPT_ALREADY_CLAIMED_NO_RETRY') from e
    # The ONLY supported adapter is this explicitly disposable 0->1 fixture.
    # Effect results are NOT considered independently verified merely because
    # the write returned without exception.
    world.write_bytes(_canonical({'counter': permission.desired_counter}))
    try:
        result = _independent_read(world)
    except subprocess.TimeoutExpired as exc:
        raise GeneralCycleStop('INDEPENDENT_WORLD_WITNESS_TIMEOUT_STOP_PRESERVE') from exc
    expected = {'counter': permission.desired_counter}
    _must(result['value'] == expected and
          result['sha256'] == _sha(_canonical(expected)),
          'INDEPENDENT_WORLD_EFFECT_NOT_VERIFIED_STOP_PRESERVE')
    _must(_sha(world.read_bytes()) == result['sha256'],
          'WORLD_CHANGED_AFTER_INDEPENDENT_WITNESS_STOP_PRESERVE')
    # Observation first, assimilation only of the exact independently verified
    # observation event. The event constructor is not a substitute for the
    # witness callback and an existing authority decision.
    witness_ref = 'sha256:' + result['sha256']
    eid = p0.identity_instance_id
    obs = EntityEventDraft(
        event_type=EventType.OBSERVATION, occurred_at_utc=timestamp,
        originating_loop=LoopName.EXTERNAL,
        source=EventEndpoint(kind=EventSourceKind.COMPONENT,
              identifier='disposable-independent-world-verifier'),
        target=EventEndpoint(kind=EventSourceKind.SE6, identifier=eid),
        relation='verified-disposable-world-effect',
        provenance=ObservationProvenance.INDEPENDENTLY_VERIFIED,
        epistemic_status=EpistemicStatus.VERIFIED,
        authority_status=AuthorityStatus.NOT_REQUIRED,
        correlation_id='test-cycle-'+permission.attempt_id,
        payload=ObservationPayload(
            world_node='disposable-world-file',relation='counter-equals',
            value_summary='counter=1 in isolated file test',
            provenance=ObservationProvenance.INDEPENDENTLY_VERIFIED,
            observed_at_utc=timestamp, evidence_references=(witness_ref,),
            confidence_basis_points=10000,
        ),
    )
    obs_events, receipt1 = _commit(store,coordinator,obs,
                                  'test-observation-'+permission.attempt_id,timestamp)
    observed = next(e for e in obs_events if e.event_type is EventType.OBSERVATION)
    successor1 = verify_audited_successor(EntityStore.for_testing(root / 'entity.sqlite3'),p0,packet0)
    _must(successor1['after_version'] == successor1['before_version'] + 1,
          'OBSERVATION_SUCCESSOR_NOT_VERIFIED')
    _must(len(coordinator.state.memory.records) == len(p0.restored_state().memory.records),
          'UNVERIFIED_MEMORY_CONSOLIDATION')
    p1, packet1 = project_general_state(store)
    assimilation = EntityEventDraft(
        event_type=EventType.ASSIMILATION, occurred_at_utc=timestamp,
        originating_loop=LoopName.BECOMING,
        source=EventEndpoint(kind=EventSourceKind.COMPONENT,
              identifier='disposable-independent-world-verifier'),
        target=EventEndpoint(kind=EventSourceKind.SE6, identifier=eid),
        relation='assimilate-verified-disposable-effect',
        provenance=ObservationProvenance.INDEPENDENTLY_VERIFIED,
        epistemic_status=EpistemicStatus.VERIFIED,
        authority_status=AuthorityStatus.NOT_REQUIRED,
        correlation_id='test-assimilation-'+permission.attempt_id,
        causal_id=observed.event_id, parent_event_id=observed.event_id,
        payload=MemoryPayload(
            operation=MemoryEventOperation.CONSOLIDATE,
            subject='disposable-world-file',
            content_summary='counter=1 in isolated file test',
            source_event_ids=(observed.event_id,),evidence_references=(witness_ref,),
        ),
    )
    memory_events, receipt2 = _commit(store,coordinator,assimilation,
                                     'test-assimilation-'+permission.attempt_id,timestamp)
    successor2 = verify_audited_successor(EntityStore.for_testing(root / 'entity.sqlite3'),p1,packet1)
    _must(successor2['after_version'] == successor2['before_version'] + 1 and
          len(coordinator.state.memory.records) == len(p1.restored_state().memory.records)+1,
          'ASSIMILATION_SUCCESSOR_NOT_VERIFIED')
    return {'status':'DISPOSABLE_GENERAL_CYCLE_VERIFIED',
            'version': VERSION, 'selected_query':selection['selected_query'],
            'before_state_id':p0.entity_state_id,
            'observation_event_id':observed.event_id,
            'observation_receipt':receipt1.receipt_id,
            'assimilation_event_id':memory_events[0].event_id,
            'assimilation_receipt':receipt2.receipt_id,
            'state_version':coordinator.state.state_version,
            'witness_sha256':result['sha256'],
            'world_effects':1,'actual_world_truth':False,
            'test_only_permission':True, 'production_authority':False,
            'full_canonical':False, 'alpha_points':0}
