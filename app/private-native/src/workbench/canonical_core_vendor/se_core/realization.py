"""Receipt-bound composition of existing bounded SE operators, not a new engine.

Premises/assertions remain owner-supplied. Verification certifies local execution
and conditional entailment, never world truth or consciousness. Trace objects are
read-only views; SE.transition alone authorizes actions and changes retained state.
"""
from dataclasses import asdict, dataclass
import json

from .kernel import (SE, SEObservation, SEState, SETransitionReceipt, _context,
                     _hash, _json, _validate_state, mirror_relation)
from .mathematics import (MathConstraint, SEMathObservation, SEMathState, _inputs,
                          _premises, mirror_equations, project_retained)


@dataclass(frozen=True)
class RealizationStage:
    name: str
    operator: str
    outcome: str
    input_json: str
    output_json: str
    state_before_hash: str
    state_after_hash: str
    evidence_refs: tuple[str, ...]
    previous_stage_id: str | None

    @property
    def stage_id(self):
        return 'se-stage:' + _hash(asdict(self))


@dataclass(frozen=True)
class RealizationTrace:
    observation_id: str
    source_origin: str
    state_before_hash: str
    state_after_hash: str
    receipt_hash: str | None
    previous_receipt_hash: str | None
    stages: tuple[RealizationStage, ...]
    error: str | None = None
    schema: str = 'se-core-realization-v1'

    @property
    def trace_hash(self):
        return 'se-realization:' + _hash(asdict(self))

    def to_record(self):
        return {**asdict(self), 'trace_hash': self.trace_hash,
                'stages': [{**asdict(stage), 'stage_id': stage.stage_id,
                            'input': json.loads(stage.input_json),
                            'output': json.loads(stage.output_json)} for stage in self.stages]}


@dataclass(frozen=True)
class RealizedTransition:
    state: SEState
    receipt: SETransitionReceipt | None
    trace: RealizationTrace


def _origin(observation):
    # Attribution labels are not owner authentication. Host authority/evidence
    # checks are still mandatory; no input is classified VERIFIED by this label.
    if observation.source in ('owner', 'owner-task'):
        return 'OWNER_SUPPLIED'
    if isinstance(observation.source, str) and observation.source.casefold().startswith('model'):
        return 'MODEL_PROPOSED'
    return 'UNKNOWN'


def _map(state, observation):
    _validate_state(state)
    if isinstance(observation, SEMathObservation):
        _inputs(state, observation)
        return {'domain': 'mathematics', 'kind': observation.kind,
                'variables': [asdict(v) for v in (observation.variables or state.variables)],
                'incoming_equations': [asdict(e) for e in observation.equations],
                'available_premises': [c.reference for c in state.current_constraints],
                'available_deductions': [d.reference for d in state.active_deductions],
                'proposed_proof': None if observation.proof is None else asdict(observation.proof)}
    if not isinstance(observation, SEObservation) or observation.kind not in ('ASSERT', 'RECALL'):
        raise ValueError('supported structured observation required')
    if not all(isinstance(s, str) and s.strip() for s in (observation.subject, observation.predicate)):
        raise ValueError('subject and predicate required')
    if observation.kind == 'ASSERT' and (not isinstance(observation.value, str) or not observation.value.strip()):
        raise ValueError('assertion value required')
    if observation.kind == 'RECALL' and (observation.value is not None or observation.correction):
        raise ValueError('recall cannot supply an answer or correction')
    key = (observation.subject.strip().casefold(), observation.predicate.strip().casefold())
    return {'domain': 'relation', 'kind': observation.kind, 'key': key,
            'proposed_value': observation.value,
            'current_relations': [asdict(r) for r in state.relations if r.key == key]}


def _mirror(state, observation):
    if isinstance(observation, SEMathObservation):
        if observation.kind == 'MATH_DERIVE':
            premises = _premises(state, observation.proof)
        else:
            sources = tuple(sorted(set((*observation.evidence_refs, observation.observation_id))))
            proposed = tuple(MathConstraint(e.label, e.equation, sources) for e in observation.equations)
            premises = (*state.current_constraints, *proposed)
        return {'comparisons': mirror_equations(premises),
                'premise_refs': tuple(p.reference for p in premises),
                'explicit_correction': observation.kind == 'MATH_CORRECT'}
    key = (observation.subject.strip().casefold(), observation.predicate.strip().casefold())
    prior = tuple(r for r in state.relations if r.key == key)
    if observation.kind == 'RECALL' and not prior:
        return {'prior_relations': [], 'status': 'UNKNOWN', 'conflict': False}
    value = observation.value if observation.kind == 'ASSERT' else prior[0].value
    comparison = mirror_relation(prior, value, correction=observation.correction)
    return {**asdict(comparison), 'comparison_hash': comparison.comparison_hash}


def _project(state, observation):
    result = {'state_hash': state.state_hash, 'identity': state.identity,
              'relations': [asdict(r) for r in state.relations], 'world_truth_verified': False}
    if isinstance(state, SEMathState):
        active = state.active_deductions
        result['mathematics'] = {
            'current_premises': [c.reference for c in state.current_constraints],
            'active_deductions': [d.reference for d in active],
            'invalidated_deductions': [d.reference for d in state.invalidated_deductions],
            'selected_projection': project_retained(state, active[-1].reference) if active else None,
            'complete_system_solved': False}
    if isinstance(observation, SEObservation):
        key = (observation.subject.strip().casefold(), observation.predicate.strip().casefold())
        relation = next((r for r in state.relations if r.key == key), None)
        result['current_relation'] = None if relation is None else asdict(relation)
        result['relation_status'] = 'OWNER_SUPPLIED' if relation is not None else 'UNKNOWN'
    return result


def _trace(receipt, mapped, mirrored):
    before, after, obs = receipt.state_before, receipt.state_after, receipt.observation
    source_refs = (*obs.evidence_refs, 'observation:' + obs.observation_id,
                   'state:' + before.state_hash)
    stages = []
    def add(name, operator, outcome, inputs, outputs, *, retained=False, refs=source_refs):
        stages.append(RealizationStage(name, operator, outcome, _json(inputs), _json(outputs),
            before.state_hash, after.state_hash if retained else before.state_hash,
            tuple(refs), stages[-1].stage_id if stages else None))
    add('MAP', 'se_core.realization._map', 'MAPPED', asdict(obs), mapped)
    add('MIRROR', 'mirror_equations' if isinstance(obs, SEMathObservation) else 'mirror_relation',
        'COMPARED', mapped, mirrored)
    if isinstance(obs, SEMathObservation) and obs.kind == 'MATH_DERIVE':
        operators = json.loads(receipt.candidate.action.payload)['operators']
        add('TRANSFORM', 'se_core.mathematics.transform_equations', 'CANDIDATE_ONLY',
            asdict(obs.proof), operators)
    add('BOUNDARY', 'se_core.kernel._bound', receipt.boundary.outcome,
        {'candidate_id': receipt.candidate.candidate_id, 'authority': json.loads(receipt.authority)},
        asdict(receipt.boundary))
    add('ACT', 'SE.transition.executor', 'EXECUTED' if receipt.action else 'NOT_AUTHORIZED',
        None if receipt.action is None else asdict(receipt.action),
        None if receipt.observed_consequence is None else asdict(receipt.observed_consequence))
    add('VERIFY', 'SE.transition.consequence_check + verify_deduction',
        'VERIFIED_LOCAL_EXECUTION' if receipt.verification.passed else 'UNVERIFIED',
        {'expected': receipt.expected_consequence}, asdict(receipt.verification),
        refs=(*source_refs, *receipt.verification.evidence_refs))
    superseded = tuple(r for r in before.relations if r not in after.relations)
    add('ASSIMILATE', 'SE.transition + assimilate_mathematics',
        'RETAINED' if receipt.assimilation else 'NO_NEW_KNOWLEDGE',
        {'verification': asdict(receipt.verification)},
        {'retained': [asdict(item) for item in receipt.assimilation],
         'superseded_relations': [asdict(r) for r in superseded],
         'correction_status': 'CORRECTED' if receipt.assimilation and (
             isinstance(obs, SEObservation) and obs.correction or obs.kind == 'MATH_CORRECT') else None,
         'prior_relation_status': 'SUPERSEDED' if superseded else None,
         'retention_verification': 'VERIFIED_LOCAL_EXECUTION' if receipt.verification.passed else 'UNVERIFIED',
         'source_origin': _origin(obs), 'world_truth_verified': False}, retained=True,
        refs=(*source_refs, 'receipt:' + receipt.receipt_hash))
    try:
        projected = _project(after, obs)
        projected_status = 'READ_ONLY_PROJECTED'
    except ValueError as error:
        projected = {'status': 'UNAVAILABLE', 'reason': str(error), 'state_hash': after.state_hash}
        projected_status = 'UNAVAILABLE'
    add('PROJECT', 'project_retained + current_relation_lookup', projected_status,
        {'retained_state_hash': after.state_hash}, projected, retained=True,
        refs=('receipt:' + receipt.receipt_hash, 'state:' + after.state_hash))
    _validate_state(after)
    add('NEXT_STATE', 'SE.transition.current_state_binding',
        'VERIFIED_LOCAL_STATE' if receipt.verification.passed else 'UNVERIFIED_OR_REFUSED',
        {'receipt_hash': receipt.receipt_hash}, {'identity': after.identity,
         'version': after.version, 'actions_used': after.actions_used,
         'state_hash': after.state_hash, 'previous_state_hash': before.state_hash}, retained=True)
    add('FEEDBACK', 'SE.transition + SE.restore', 'NEXT_INPUT_REQUIRED',
        {'state_hash': after.state_hash}, {'next_transition_must_bind': after.state_hash,
         'receipt_anchor': receipt.receipt_hash, 'automatic_execution': False}, retained=True)
    return RealizationTrace(obs.observation_id, _origin(obs), before.state_hash,
        after.state_hash, receipt.receipt_hash, receipt.previous_receipt_hash, tuple(stages))


def realize_transition(engine, state, observation, boundary_context):
    if state != engine.state:
        raise ValueError('realization must bind the current state')
    ctx = _context(boundary_context)
    try:
        mapped = _map(state, observation)
        mirrored = _mirror(state, observation)
    except ValueError as error:
        stage = RealizationStage('INPUT', 'existing typed operator validation', 'REJECTED',
            _json(asdict(observation)), _json({'reason': str(error)}), state.state_hash,
            state.state_hash, (), None)
        trace = RealizationTrace(observation.observation_id, _origin(observation),
            state.state_hash, state.state_hash, None,
            engine.receipts[-1].receipt_hash if engine.receipts else None, (stage,), str(error))
        return RealizedTransition(state, None, trace)
    # The same central transition runs fixed domain mapping, comparison,
    # boundary, verification, assimilation and post-retention projection.
    after, receipt, trace = engine.transition(state, observation, ctx, _realization=True)
    return RealizedTransition(after, receipt, trace)


def verify_realization(engine, trace):
    """Replay canonical receipts without effects, then reproduce the projection.

Self-hashing, declared verification flags and arbitrary trace input are not
accepted as evidence. Input rejections without a canonical receipt are unverified.
"""
    if not isinstance(trace, RealizationTrace) or trace.receipt_hash is None:
        return False
    try:
        restored = SE.restore(engine.dumps(), expected_head=engine.receipts[-1].receipt_hash)
        receipt = next(r for r in restored.receipts if r.receipt_hash == trace.receipt_hash)
        rebuilt = _trace(receipt, _map(receipt.state_before, receipt.observation),
                         _mirror(receipt.state_before, receipt.observation))
        return rebuilt == trace
    except (ValueError, StopIteration, TypeError, KeyError):
        return False
