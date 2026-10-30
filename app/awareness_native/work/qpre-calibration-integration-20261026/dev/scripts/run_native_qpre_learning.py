"""Disposable Native/QPRE proof with independent file readback and cold replay.

All observations are explicitly SIMULATED_DEV_OBSERVER fixture evidence.
The two selected effects touch only world.json below an OS temporary root.
No continuous Sphere implementation, production ingestion or authority is added.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

CORE = Path(__file__).resolve().parents[1]
MISSION = CORE.parents[2]
sys.path.insert(0, str(CORE))
sys.dont_write_bytecode = True

from se666_core.observation_grounding import digest, require

PREFIX = 'SE6-NATIVE-QPRE-'
MARKER = '.SE6_NATIVE_QPRE_DISPOSABLE'
MARKER_VALUE = 'explicit-simulated-development-only-v1'
SOURCE = 'simulated-native-file-observer'
EPOCH = 'native-calibration-fixture-v1'
RAW = [7, 11]
COMPOSER_PIN = '3f219886ee35c863ef81ec485c9ace22287951cb95690112dff70eb242fcb409'
ATTEMPTS_PIN = '9ef6b4d5ccca8725d901c3ae13385fadcdF41343e27ddee894de3bae57e77d04'.lower()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def read(path):
    require(path.is_file() and not path.is_symlink(), 'FIXTURE_REGULAR_FILE_REQUIRED')
    return json.loads(path.read_bytes())


def write_once(path, value):
    with path.open('xb') as output:
        output.write(canonical(value))
        output.flush()
        os.fsync(output.fileno())


def check_root(root):
    root = Path(root).resolve(strict=True)
    require(root.parent == Path(tempfile.gettempdir()).resolve(strict=True)
            and root.name.startswith(PREFIX), 'NATIVE_FIXTURE_DISPOSABLE_ROOT_REQUIRED')
    require(not any(p.is_symlink() for p in (root, *root.parents)), 'NATIVE_FIXTURE_SYMLINK')
    marker = root / MARKER
    require(marker.is_file() and not marker.is_symlink()
            and marker.read_text() == MARKER_VALUE, 'NATIVE_FIXTURE_MARKER_REQUIRED')
    return root


def new_root():
    root = Path(tempfile.mkdtemp(prefix=PREFIX))
    (root / MARKER).write_text(MARKER_VALUE, encoding='utf-8')
    return root


def _module(name, path, pin):
    require(hashlib.sha256(path.read_bytes()).hexdigest() == pin, 'FIXTURE_DEPENDENCY_PIN')
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def dependencies():
    composer = _module('_native_qpre_typed_composer', MISSION /
        'work/codex-vscode-research/operational-realization/engine/typed_composer.py', COMPOSER_PIN)
    attempts = _module('_native_qpre_durable_attempts', MISSION /
        'work/codex-vscode-research/alpha-continuation/engine/durable_attempts.py', ATTEMPTS_PIN)
    from se666_core.reference_continuity import DevelopmentReference
    package = MISSION / 'work/se6-reference-continuity-v010-448349319aa1/SE6_Reference_Continuity_v0.1.0'
    manifest = hashlib.sha256((package / 'PACKAGE_MANIFEST.json').read_bytes()).hexdigest()
    reference = DevelopmentReference(package_root=package, package_manifest_sha256=manifest,
                                     canonical_root=CORE)
    return reference, composer.TypedComposer, attempts.DurableAttempts


def child(root, mode, *args):
    root = check_root(root)
    result = subprocess.run([sys.executable, '-B', str(Path(__file__).resolve()),
        '--child', mode, '--root', str(root), *map(str, args)], cwd=str(CORE),
        capture_output=True, text=True, timeout=90,
        env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
    require(result.returncode == 0, 'NATIVE_FIXTURE_CHILD_FAILED:' + result.stderr[-6000:])
    return json.loads(result.stdout)


def row(episode, index, action=None):
    return dict(id=f'{episode}:{index}', source=SOURCE, epoch=EPOCH, episode=episode,
                index=index, action=action, raw=RAW, goal=None if action is None else True)


def publish_rows(root, rows):
    """Separate observer process rereads the frozen public fixture bytes."""
    name = 'input-' + digest(rows) + '.json'
    path = root / name
    if not path.exists():
        write_once(path, rows)
    return child(root, 'publish', '--input', name)


class DiskRows:
    def __init__(self, root, keys):
        self.root = check_root(root)
        self.keys = keys

    def authenticate_rows(self, rows, epoch, key):
        expected = self.keys.get(key, key)
        record = read(self.root / ('rows-' + expected + '.json'))
        require(record['origin'] == 'SIMULATED_DEV_OBSERVER' and record['rows'] == rows
                and record['rows_sha256'] == digest(rows) == expected
                and record['source'] == SOURCE and record['epoch'] == epoch == EPOCH,
                'DISK_OBSERVER_ROWS_BINDING')
        require(all(r['source'] == SOURCE and r['epoch'] == EPOCH for r in rows),
                'DISK_OBSERVER_ROW_SOURCE')
        return True


def authority(root, config):
    from se666_core.grounded_native_input import GroundingTranscriptAuthority
    chronology = read(root / 'chronology.json')
    require(digest(chronology) == config['chronology_sha256'], 'DISK_CHRONOLOGY_PIN')
    return GroundingTranscriptAuthority(DiskRows(root, config['row_keys']),
        {'cycle': chronology}, {'cycle': config['chronology_sha256']})


def decision_input(history, binding):
    from se666_core.candidate_state_transition import INPUT_VERSION
    return dict(version=INPUT_VERSION, binding=deepcopy(binding),
        observation=dict(status='VERIFIED', summary=digest(history[-1]['raw']),
            result_type='AUTHENTICATED_RAW_HISTORY', evidence_references=[digest(history)]),
        lifecycle='verified', observation_use='CURRENT_REQUIRED',
        added_dimensions=['action-cost', 'risk-units'], require_trace_inverse=True)


def boundary(identity):
    from se666_core import grounded_canonical_selection as selection
    from se666_core import grounded_canonical_context as context
    from se666_core import candidate_state_transition as state
    from se666_core.qpre_native_learning import VERSION
    policy = dict(version=selection.VERSION, goal_value_units=120, uncertainty_units=0,
        frame={'domain': 'finite-action-history', 'basis': 'opaque-observation-history', 'version': 1},
        actions={a: dict(risk_units=0, reversibility='REVERSIBLE',
            conduct={p: True for p in selection.PILLARS}) for a in ('a', 'b')},
        state_semantics=dict(version=state.VERSION,
            source_pins={'fixture-model-contract': digest({'raw': RAW, 'source': SOURCE, 'epoch': EPOCH})},
            governing=[dict(id='fixture-self-loop', kind='REUSABLE_RELATION',
                dependencies_complete=True, environment_known=True,
                assumptions=['Explicit simulated one-state source epoch remains unchanged.'],
                domain=[], through_version=16)], model_requires=['fixture-self-loop']),
        decision_inputs_version=state.INPUT_VERSION,
        operator_order_contract=selection.POST_QPRE_ORDER,
        retention_limits=dict(version=context.LIMIT_VERSION, witness_nodes=256,
            witness_depth=8, witness_bytes=4096), probability_learning=VERSION)
    return dict(identity=identity, authorized=True, permissions=['a', 'b'],
        native_permissions=['GROUNDING_EVALUATE'], max_native_actions=20,
        remaining_actions=2, remaining_effects=2, remaining_cost=10,
        retention_permissions=['READ_CURRENT', 'ARCHIVE_RETAIN'], selection_policy=policy)


def actions(phase):
    return [dict(id=a, payload={'fixed_opcode': a}, cost=cost)
            for a, cost in (('a', 1 if phase == 1 else 3), ('b', 2 if phase == 1 else 1))]


def derive_goal(before, after, pending):
    """Observer's frozen task predicate; never consume the dispatcher goal flag."""
    prior = before['history']
    history = after['history']
    return bool(prior and len(history) == len(prior) + 1 and history[:-1] == prior
        and after['effects'] == before['effects'] + 1
        and history[-1]['action'] == pending['action']['id'] in ('a', 'b')
        and history[-1]['source'] == prior[-1]['source'] == SOURCE
        and history[-1]['epoch'] == prior[-1]['epoch'] == EPOCH
        and history[-1]['episode'] == prior[-1]['episode']
        and history[-1]['index'] == prior[-1]['index'] + 1
        and history[-1]['raw'] == after['raw'] == before['raw'])


def verify_goal_flags(before, after, pending):
    goal = derive_goal(before, after, pending)
    require(type(after['goal']) is bool and type(after['history'][-1]['goal']) is bool
            and after['goal'] is goal and after['history'][-1]['goal'] is goal,
            'INDEPENDENT_GOAL_FLAG_MISMATCH')
    return goal


def probability_summary(state):
    from se666_core import qpre_native_learning as learning
    from se666_core.qpre_calibration_v1 import posterior_distribution
    saved = learning.snapshot(state)
    result = {}
    for name, key in learning.keys(state['scope']).items():
        distribution = posterior_distribution(saved, action_key=key, candidate_id='report-' + name)
        action = next(a for a in saved.actions if a.action_key == key)
        result[name] = dict(goal_fraction=[saved.alpha + action.counts[0],
            len(action.counts) * saved.alpha + sum(action.counts)],
            distribution=distribution.model_dump(mode='json'))
    return result


class NativeFixture:
    """Host ports for this exact disposable fixture, never production authority."""
    def __init__(self, root):
        self.root = check_root(root)
        self.config = read(self.root / 'config.json')
        self.reference, self.composer, self.attempts_type = dependencies()
        self.authority = authority(self.root, self.config)

    @classmethod
    def create(cls, root=None):
        from tests.test_entity_cognition_layer import _cognition_store
        from se666_core import observation_grounding as grounding
        from se666_core.grounded_native_input import certificate
        root = check_root(root or new_root())
        cognition = _cognition_store(root)
        identity = cognition.entity_store.reconstruct().state.identity.instance_id
        reference, _, _ = dependencies()
        engine = reference.canonical.core.SE(reference.canonical.core.SEState(identity=identity))
        binding = dict(entity_id=identity, entity_state=engine.state.state_hash,
            memory_head='disposable-native-genesis', source=SOURCE, epoch=EPOCH)
        training = [row(1, 0), row(1, 1, 'a'), row(2, 0), row(2, 1, 'b')]
        proposal = grounding.fit(training, ['a', 'b'], limits={'max_states': 1, 'max_plan_depth': 1})
        hold = [row(10, 0), row(10, 1, 'a')]
        released = [row(10, 2, 'a')]
        committed = grounding.commit(proposal, hold, [['a']], binding)
        chronology = dict(origin='SIMULATED_DEV_OBSERVER', source=SOURCE, epoch=EPOCH,
            events=[dict(sequence=0, kind='COMMIT', sha256=digest(committed)),
                    dict(sequence=1, kind='READBACK', sha256=digest(released))])
        write_once(root / 'chronology.json', chronology)
        for rows in (training, released, hold, [row(20, 0)]):
            publish_rows(root, rows)
        cert = certificate(proposal, training, committed, released,
            training_key='training', release_key='holdback', chronology_key='cycle')
        source_names = ['se666_core/grounded_native_input.py', 'se666_core/grounded_canonical_selection.py',
            'se666_core/grounded_post_qpre_sphere.py', 'se666_core/entity_cognition_scheduler.py',
            'se666_core/qpre_native_learning.py', 'se666_core/qpre_calibration_v1.py',
            'se666_core/qpre_development_learning.py', 'se666_core/candidate_state_transition.py',
            'se666_core/observation_grounding.py', 'scripts/run_native_qpre_learning.py',
            'tests/test_qpre_native_learning.py']
        plan = dict(version='disposable-native-qpre-frozen-plan-v1', origin='SIMULATED_DEV_OBSERVER',
            source_pins={name: hashlib.sha256((CORE / name).read_bytes()).hexdigest() for name in source_names},
            existing_dependency_pins=dict(typed_composer=COMPOSER_PIN, durable_attempts=ATTEMPTS_PIN,
                reference_package_manifest=reference.manifest_sha),
            phases=[dict(phase=p, actions=actions(p)) for p in (1, 2)],
            public_training=training, finite_model=dict(max_states=1, max_plan_depth=1),
            maximum_selected_world_effects=2, independent_observer='separate-process-disk-read',
            observed_task='Append exactly one admitted action; preserve the exact prior history and raw value; increment the effect count exactly once.',
            goal_derivation='Observer compares immutable world-before bytes with actual post-effect world bytes; dispatcher flags must match that derivation.',
            cold_restore_between_phases=True, matched_native_prior_ablation='NO_DISPATCH_NO_RETENTION',
            production_access=False, network=False, model_calls=False,
            completion='two independently witnessed effects, durable renewal and fresh-process replay')
        write_once(root / 'FROZEN_PLAN.json', plan)
        write_once(root / 'config.json', dict(identity=identity, binding=binding, certificate=cert,
            chronology_sha256=digest(chronology), row_keys={'training': digest(training), 'holdback': digest(released)},
            native=dict(core_journal=engine.dumps(), core_head=None), origin='SIMULATED_DEV_OBSERVER',
            frozen_plan_sha256=digest(plan)))
        write_once(root / 'world.json', dict(history=[row(20, 0)], effects=0, raw=RAW, goal=None))
        return cls(root)

    def consumer(self):
        from se666_core.grounded_native_input import GroundedNativeConsumer
        return GroundedNativeConsumer(self.reference, self.config['native'], self.authority, self.composer)

    def restore(self, phase):
        from se666_core.grounded_native_input import GroundedNativeConsumer
        state = read(self.root / f'retained-{phase}.json')
        receipt = read(self.root / f'renewal-{phase}.json')
        require(receipt['state_sha256'] == digest(state), 'RESTORE_EXTERNAL_STATE_PIN')
        return GroundedNativeConsumer.restore(self.reference, state, self.authority, self.composer,
            expected_sha256=receipt['state_sha256'], independent_learning_verifier=self.verify_learning)

    def verify_learning(self, event):
        """Reread independently produced effect and renewal records on every use."""
        attempt = event['pending']['attempt_id']
        require(attempt in ('native-cycle-1', 'native-cycle-2'), 'RESTORE_ATTEMPT_SCOPE')
        phase = int(attempt[-1])
        observed = read(self.root / f'effect-{phase}.json')
        before = read(self.root / f'world-before-{phase}.json')
        retained = read(self.root / f'retained-{phase}.json')
        renewal = read(self.root / f'renewal-{phase}.json')
        require(renewal['origin'] == observed['origin'] == 'SIMULATED_DEV_OBSERVER'
                and renewal['state_sha256'] == digest(retained)
                and renewal['previous_head'] == event['pending']['prepared']['binding']['memory_head']
                and renewal['event_sha256'] == event['record_sha256']
                and any(digest(item) == digest(event) for item in retained['probability_events']),
                'RESTORE_INDEPENDENT_RENEWAL')
        require(observed['witness'] == event['witness']
                and observed['witness_sha256'] == digest(event['witness'])
                and observed['pending_sha256'] == digest(event['pending'])
                and observed['world_sha256'] == digest(observed['world_snapshot'])
                and observed['before_world_sha256'] == digest(before)
                and event['witness']['goal'] is verify_goal_flags(before, observed['world_snapshot'], event['pending']),
                'RESTORE_INDEPENDENT_EFFECT')
        return True

    def scheduler(self, history, *, commit_observation=True):
        from tests.test_entity_cognition_layer import T0
        from se666_core.entity_store import EntityStore
        from se666_core.entity_cognition_store import EntityCognitionStore
        from se666_core.entity_runtime import LocalEntityRuntime
        from se666_core.entity_cognition_scheduler import PersistentCognitionScheduler
        from se666_core.three_loop_entity import SE6TriLoopCoordinator
        from se666_core import grounded_general_action_cycle as commits
        from se666_core.entity_events import (EntityEventDraft, EventType, LoopName, EventEndpoint,
            EventSourceKind, ObservationProvenance, AuthorityStatus, ObservationPayload)
        from se666_core.epistemic_status import EpistemicStatus
        store = EntityStore.for_testing(self.root / 'entity.sqlite3')
        cognition = EntityCognitionStore.for_testing(self.root / 'cognition.sqlite3', entity_store=store)
        at = T0 + timedelta(seconds=10 + len(history))
        if commit_observation:
            DiskRows(self.root, self.config['row_keys']).authenticate_rows(history, EPOCH, digest(history))
            draft = EntityEventDraft(event_type=EventType.OBSERVATION, occurred_at_utc=at,
                originating_loop=LoopName.EXTERNAL,
                source=EventEndpoint(kind=EventSourceKind.COMPONENT, identifier=SOURCE),
                target=EventEndpoint(kind=EventSourceKind.SE6, identifier=self.config['identity']),
                relation='disposable-native-current-observation', provenance=ObservationProvenance.INDEPENDENTLY_VERIFIED,
                epistemic_status=EpistemicStatus.VERIFIED, authority_status=AuthorityStatus.NOT_REQUIRED,
                correlation_id='native-history-' + digest(history),
                payload=ObservationPayload(world_node=SOURCE, relation='current-raw', value_summary=digest(history[-1]['raw']),
                    provenance=ObservationProvenance.INDEPENDENTLY_VERIFIED, observed_at_utc=at,
                    evidence_references=('history:' + digest(history), 'observer:' + digest(read(self.root / ('rows-' + digest(history) + '.json')))),
                    confidence_basis_points=10000))
            snapshot = store.reconstruct()
            coordinator = SE6TriLoopCoordinator(state=snapshot.state, historical_events=snapshot.historical_events)
            commits._commit(store, coordinator, draft,
                            'native-observation-' + digest(history), at)
        events = store.reconstruct().historical_events
        observation = next(e for e in reversed(events) if e.event_type is EventType.OBSERVATION)
        runtime = LocalEntityRuntime(store=store, runtime_session_id='native-qpre-fixture-runtime', clock=lambda: at)
        return PersistentCognitionScheduler(runtime=runtime, store=cognition, clock=lambda: at), observation.event_id

    def select(self, consumer, phase, *, use_scheduler=True):
        world = read(self.root / 'world.json')
        history = world['history']
        memory_head = ('disposable-native-genesis' if phase == 1 else
                       read(self.root / f'renewal-{phase-1}.json')['state_sha256'])
        binding = dict(self.config['binding'], entity_state=consumer.engine.state.state_hash, memory_head=memory_head)
        args = (consumer, self.config['certificate'], history, binding, actions(phase),
                boundary(self.config['identity']), f'native-cycle-{phase}')
        if use_scheduler:
            scheduler, observation = self.scheduler(history)
            selected = scheduler.evaluate_native_shadow(*args, observation_event_id=observation,
                decision_input=decision_input(history, binding))
        else:
            selected = consumer.select(*args[1:], decision_input=decision_input(history, binding))
        return selected

    def dispatch(self, consumer, phase):
        plan = read(self.root / 'FROZEN_PLAN.json')
        require(digest(plan) == self.config['frozen_plan_sha256'], 'FIXTURE_FROZEN_PLAN_PIN')
        require(all(hashlib.sha256((CORE / name).read_bytes()).hexdigest() == pin
                    for name, pin in plan['source_pins'].items()), 'FIXTURE_FROZEN_SOURCE_CHANGED')
        pending = deepcopy(consumer.pending)
        world_before = read(self.root / 'world.json')

        def permission(value):
            require(value == consumer.pending and value['action'] in actions(phase)
                    and value['prepared']['binding']['entity_id'] == self.config['identity']
                    and world_before['effects'] == phase - 1, 'FIXTURE_EXACT_CURRENT_PERMISSION')

        def execute(value):
            world = read(self.root / 'world.json')
            require(world == world_before, 'FIXTURE_WORLD_CAS')
            write_once(self.root / f'world-before-{phase}.json', world)
            observed = row(20, len(world['history']), value['action']['id'])
            successor = dict(history=world['history'] + [observed], effects=phase, raw=RAW, goal=True)
            next_path = self.root / f'world-next-{phase}.json'
            write_once(next_path, successor)
            os.replace(next_path, self.root / 'world.json')
            write_once(self.root / f'pending-{phase}.json', value)
            return child(self.root, 'effect', '--phase', phase)

        prior = None if phase == 1 else read(self.root / f'effect-{phase-1}.json')['pending_core_head']
        consumer.dispatch(current_head=pending['prepared']['binding']['memory_head'],
            current_permission_verifier=permission, existing_dispatcher=execute,
            durable_attempts=self.attempts_type(self.root / 'attempts', self.config['identity']),
            durable_prior_head=prior)
        return read(self.root / f'effect-{phase}.json')['witness']

    def verify_effect(self, witness, pending):
        phase = int(pending['attempt_id'][-1])
        observed = read(self.root / f'effect-{phase}.json')
        world = read(self.root / 'world.json')
        before = read(self.root / f'world-before-{phase}.json')
        require(observed['origin'] == 'SIMULATED_DEV_OBSERVER'
                and observed['witness_sha256'] == digest(witness)
                and observed['witness'] == witness
                and observed['pending_sha256'] == digest(pending)
                and observed['world_sha256'] == digest(world)
                and observed['before_world_sha256'] == digest(before)
                and witness['goal'] is verify_goal_flags(before, world, pending),
                'INDEPENDENT_DISK_EFFECT_REQUIRED')
        return True

    def renew(self, phase):
        def writer(state, previous):
            expected = ('disposable-native-genesis' if phase == 1 else
                        read(self.root / f'renewal-{phase-1}.json')['state_sha256'])
            require(previous == expected, 'FIXTURE_RENEWAL_CAS')
            write_once(self.root / f'retained-{phase}.json', state)
            return dict(purpose='GROUNDING_DURABLE_RENEWAL', state_sha256=digest(state), previous_head=previous,
                        path=f'retained-{phase}.json')
        return writer

    def verify_renewal(self, phase):
        def verifier(receipt, state, previous):
            independent = child(self.root, 'renewal', '--phase', phase, '--previous', previous)
            require(independent['state_sha256'] == receipt['state_sha256'] == digest(state)
                    and independent['previous_head'] == previous
                    and canonical(read(self.root / receipt['path'])) == canonical(state),
                    'INDEPENDENT_RENEWAL_DISK_READ')
            return True
        return verifier

    def complete(self, consumer, phase):
        witness = self.dispatch(consumer, phase)
        result = consumer.verify_cycle(witness, independent_effect_verifier=self.verify_effect,
            durable_renewal_writer=self.renew(phase), independent_renewal_verifier=self.verify_renewal(phase))
        return result


def run_demo(root=None):
    fixture = NativeFixture.create(root)
    consumer = fixture.consumer()
    first = fixture.select(consumer, 1)
    initial_probabilities = probability_summary(consumer.probability_state)
    verified = fixture.complete(consumer, 1)
    cold = child(fixture.root, 'cold')
    result = dict(scope='DISPOSABLE_SIMULATED_NATIVE_ONLY', root=str(fixture.root),
        identity=fixture.config['identity'], first_action=first['pending']['action']['id'],
        first_verified=verified['passed'], first_scheduler=first['scheduler_shadow'],
        requesting_process_id=os.getpid(),
        initial_probabilities=initial_probabilities, frozen_plan_sha256=fixture.config['frozen_plan_sha256'],
        **cold, production_ingestion=False, production_authority=False,
        continuous_package_sphere='UNAVAILABLE_NOT_RECONSTRUCTED')
    write_once(fixture.root / 'report.json', result)
    return result


def child_mode(args):
    root = check_root(args.root)
    if args.child == 'publish':
        require(Path(args.input).name == args.input, 'FIXTURE_INPUT_FILENAME')
        rows = read(root / args.input)
        record = dict(origin='SIMULATED_DEV_OBSERVER', source=SOURCE, epoch=EPOCH,
                      rows=rows, rows_sha256=digest(rows))
        target = root / ('rows-' + digest(rows) + '.json')
        if target.exists():
            require(read(target) == record, 'OBSERVER_IMMUTABLE_ROWS')
        else:
            write_once(target, record)
        return dict(rows_sha256=digest(rows))
    if args.child == 'effect':
        phase = args.phase
        require(phase in (1, 2), 'FIXTURE_PHASE')
        world = read(root / 'world.json')
        before = read(root / f'world-before-{phase}.json')
        pending = read(root / f'pending-{phase}.json')
        binding = pending['prepared']['binding']
        observed = world['history'][-1]
        require(world['effects'] == phase and observed['action'] == pending['action']['id'], 'OBSERVER_EXACT_EFFECT')
        plan = read(root / 'FROZEN_PLAN.json')
        require(pending['action'] in plan['phases'][phase-1]['actions'], 'OBSERVER_FROZEN_ACTION')
        goal = verify_goal_flags(before, world, pending)
        witness = dict(purpose='GROUNDING_WORLD_EFFECT', issuer='independent-child-simulated-observer',
            entity_id=binding['entity_id'], attempt_id=pending['attempt_id'], source=SOURCE, epoch=EPOCH,
            action_sha256=digest(pending['action']), before_head=binding['memory_head'],
            raw=observed['raw'], goal=goal, observation_row=observed,
            independent_receipt_sha256=digest(dict(world=world, pending=pending)))
        record = dict(origin='SIMULATED_DEV_OBSERVER', witness=witness, witness_sha256=digest(witness),
            world_sha256=digest(world), world_snapshot=world, before_world_sha256=digest(before),
            pending_sha256=digest(pending), pending_core_head=pending['core_head'],
            process_id=os.getpid())
        write_once(root / f'effect-{phase}.json', record)
        rows = world['history']
        write_once(root / ('rows-' + digest(rows) + '.json'), dict(origin='SIMULATED_DEV_OBSERVER',
            source=SOURCE, epoch=EPOCH, rows=rows, rows_sha256=digest(rows)))
        return record
    if args.child == 'renewal':
        state = read(root / f'retained-{args.phase}.json')
        event = state['probability_events'][-1]
        effect = read(root / f'effect-{args.phase}.json')
        require(event['witness'] == effect['witness'] and event['pending']['attempt_id'] == f'native-cycle-{args.phase}'
                and event['pending']['prepared']['binding']['memory_head'] == args.previous,
                'OBSERVER_RENEWAL_EFFECT_ANCESTRY')
        record = dict(origin='SIMULATED_DEV_OBSERVER', purpose='GROUNDING_DURABLE_RENEWAL',
            state_sha256=digest(state), previous_head=args.previous, event_sha256=event['record_sha256'],
            process_id=os.getpid())
        write_once(root / f'renewal-{args.phase}.json', record)
        return record
    if args.child == 'cold':
        fixture = NativeFixture(root)
        consumer = fixture.restore(1)
        prior = deepcopy(consumer.probability_state)
        # Isolated in-memory ablation: same actual Native state/history/semantics,
        # symmetric prior, one actual selector call, no dispatch or persistence.
        from se666_core.qpre_native_learning import initial
        control = fixture.consumer()
        control.engine = deepcopy(consumer.engine)
        control.semantic_states = deepcopy(consumer.semantic_states)
        control.current_certificate = deepcopy(consumer.current_certificate)
        control.probability_state = initial(prior['scope'])
        control_choice = fixture.select(control, 2, use_scheduler=False)
        baseline_action = control_choice['pending']['action']['id']
        control_audit = control_choice['pending']['prepared']['learned']['selection']
        control.pending = None  # Explicitly discard the nondispatching ablation.
        chosen = fixture.select(consumer, 2)
        learning = chosen['pending']['prepared']['learned']['selection']['probability_learning']
        audit = chosen['pending']['prepared']['learned']['selection']
        require(audit['possibility_field'] == control_audit['possibility_field'], 'MATCHED_NATIVE_ABLATION_FIELD')
        probability_render = learning['render']
        for sphere in audit['sphere']:
            evidence = sphere['mirror']['probability_binding']
            distribution = next(d for d in probability_render['distributions']
                                if d['candidate_id'] == sphere['candidate_id'])
            require(evidence['render_id'] == probability_render['render_id']
                    and evidence['calibration_state_hash'] == probability_render['calibration_state_hash']
                    and evidence['distribution_sha256'] == digest(distribution)
                    and evidence['independent_probability_truth'] is False,
                    'POST_QPRE_SPHERE_CONSUMED_EXACT_PROBABILITY')
        verified = fixture.complete(consumer, 2)
        final = fixture.restore(2)
        return dict(cold_process_id=os.getpid(), parent_process_id=os.getppid(),
            second_action=chosen['pending']['action']['id'], symmetric_prior_action=baseline_action,
            second_verified=verified['passed'], second_scheduler=chosen['scheduler_shadow'],
            probability_before_second=prior['snapshot'], probability_after_second=final.probability_state['snapshot'],
            probabilities_before_second=probability_summary(prior),
            probabilities_after_second=probability_summary(final.probability_state),
            second_scores=[dict(action=learning['candidate_actions'][score['candidate_id']], **score)
                           for score in learning['scores']],
            matched_native_ablation=True, ablation_world_effects=0,
            same_goal_cost_comparison=dict(learned_action_cost=chosen['pending']['action']['cost'],
                symmetric_prior_cost=control_choice['pending']['action']['cost'],
                both_goals_observed_in_public_training=True, actual_optimality_established=False),
            world_effects=read(root / 'world.json')['effects'],
            restored_identity=final.engine.state.identity, verified_learning_events=len(final.probability_events),
            base_qpre_and_post_qpre_sphere_consumed=bool(chosen['pending']['prepared']['learned']['selection']['sphere']))
    raise ValueError('FIXTURE_CHILD_MODE')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root')
    parser.add_argument('--child', choices=['publish', 'effect', 'renewal', 'cold'])
    parser.add_argument('--input')
    parser.add_argument('--phase', type=int)
    parser.add_argument('--previous')
    args = parser.parse_args()
    def deny_network(event, _args):
        if event.startswith('socket.'):
            raise PermissionError('NATIVE_FIXTURE_NETWORK_DISABLED')
    sys.addaudithook(deny_network)
    result = child_mode(args) if args.child else run_demo(args.root)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
