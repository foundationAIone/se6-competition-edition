"""Opt-in finite model -> existing Entity QPRE port; no authority or World I/O.

Auditing authenticates persisted bytes/ancestry, NOT an external model's truth.
The reference model and its new ordered-composition law remain proposals. Only
the exact-normalizer subdomain is admitted here; no transcendental error claim.
"""
from __future__ import annotations

from datetime import datetime, timezone
from fractions import Fraction
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
import json

from . import owner_equation_math_v1 as math
from . import candidate_state_transition as typed
from .entity_events import (EventType, ObservationPayload, ObservationProvenance,
                           MemoryPayload, MemoryEventOperation)
from .entity_state import MemoryStatus
from .epistemic_status import EpistemicStatus
from .observation_grounding import digest, require

VERSION = 'se6-audited-finite-owner-math-port-v1-development-proposal'
MODEL = 'se6-finite-owner-math-model-v1'
SUBJECT = 'se6-finite-owner-math-model'


def rational(x):
    if type(x) is int:
        return math.exact(x)
    require(type(x) is list and len(x) == 2 and all(type(v) is int for v in x)
            and x[1] > 0, 'MATH_RATIONAL_REQUIRED')
    return math.exact(Fraction(*x))


def _vector(x, n):
    require(type(x) is list and len(x) == n, 'MATH_VECTOR_DOMAIN')
    return tuple(rational(v) for v in x)


def _numeric_paths(z, paths, n, *, self_model=False):
    require(type(paths) is list and len(paths) == n, 'MATH_SOURCE_PATHS')
    values = []
    for path in paths:
        require(type(path) is list and 1 <= len(path) <= 8 and
                all(type(k) is str or type(k) is int for k in path), 'MATH_SOURCE_PATH')
        if self_model:
            require(path[0] in ('state_version', 'event_sequence', 'resources',
                               'shared_metabolism'), 'MATH_SELF_PATH_NOT_OPERATIONAL')
        value = typed.at(z['X'], path)
        require(type(value) is int, 'MATH_SOURCE_NOT_BOUNDED_INTEGER')
        values.append(math.exact(value))
    return tuple(values)


def _load(store, p, memory_id):
    integrity, restart, lineage = store.inspect_read_only()
    require(integrity.valid and restart is not None and lineage is not None and
            restart.state.entity_state_id == p.entity_state_id and
            restart.latest_receipt.receipt_id == p.receipt_id, 'MATH_SOURCE_HEAD_DRIFT')
    matches = [r for r in restart.state.memory.active_at(datetime.now(timezone.utc))
               if r.memory_id == memory_id]
    require(len(matches) == 1, 'MATH_MODEL_NOT_CURRENT_RETAINED_MEMORY')
    record = matches[0]
    require(record.subject == SUBJECT and record.status in (MemoryStatus.VERIFIED, MemoryStatus.DURABLE)
            and record.epistemic_status is EpistemicStatus.VERIFIED,
            'MATH_MODEL_NOT_VERIFIED_PERSISTED_RECORD')
    def unique_object(pairs):
        require(len({k for k,_ in pairs})==len(pairs), 'MATH_DUPLICATE_JSON_FIELD')
        return dict(pairs)
    try:
        model = json.loads(record.content_summary,object_pairs_hook=unique_object)
    except (ValueError, TypeError) as e:
        raise ValueError('MATH_MODEL_JSON') from e
    require(type(model) is dict and set(model) == {
        'schema','entity','basis','operators','policy','horizon','candidates'}, 'MATH_MODEL_FIELDS')
    require(model['schema'] == MODEL and model['entity'] == p.identity_instance_id,
            'MATH_MODEL_IDENTITY')
    ref = 'sha256:' + digest(model)
    require(ref in record.evidence_references, 'MATH_MODEL_CONTENT_REFERENCE')
    events = {event.event_id:event for event in restart.historical_events}
    require(bool(record.source_event_ids), 'MATH_MODEL_OBSERVATION_REQUIRED')
    sources=[events.get(eid) for eid in record.source_event_ids]
    require(all(e is not None for e in sources), 'MATH_MODEL_SOURCE_EVENT_MISSING')
    memory_events=[e for e in sources if type(e.payload) is MemoryPayload]
    observations=[e for e in sources if type(e.payload) is ObservationPayload]
    require(len(memory_events)==1 and bool(observations) and
            len(sources)==1+len(observations), 'MATH_MODEL_MEMORY_SOURCE_STRUCTURE')
    memory_event=memory_events[0]
    require(memory_event.event_type is EventType.ASSIMILATION and
            memory_event.provenance is ObservationProvenance.INDEPENDENTLY_VERIFIED and
            memory_event.epistemic_status is EpistemicStatus.VERIFIED and
            memory_event.target.identifier==p.identity_instance_id and
            memory_event.payload.operation in (MemoryEventOperation.CONSOLIDATE,MemoryEventOperation.SUPERSEDE) and
            memory_event.payload.subject==record.subject and
            memory_event.payload.content_summary==record.content_summary and
            memory_event.payload.evidence_references==record.evidence_references and
            memory_event.payload.source_event_ids==tuple(e.event_id for e in observations) and
            memory_event.payload.supersedes_memory_id==record.supersedes_memory_id and
            memory_event.occurred_at_utc==record.recorded_at_utc,
            'MATH_MODEL_MEMORY_EVENT_ANCESTRY')
    for event in observations:
        require(event.event_type is EventType.OBSERVATION and
                event.provenance is ObservationProvenance.INDEPENDENTLY_VERIFIED and
                event.epistemic_status is EpistemicStatus.VERIFIED and
                event.target.identifier == p.identity_instance_id and
                type(event.payload) is ObservationPayload and event.payload.current_claim and
                event.payload.provenance is ObservationProvenance.INDEPENDENTLY_VERIFIED and
                event.payload.value_summary == record.content_summary and
                ref in event.payload.evidence_references,
                'MATH_MODEL_OBSERVATION_ANCESTRY')
        current=[r for r in restart.state.environment.relations
                 if r.world_node==event.payload.world_node and r.relation==event.payload.relation and r.current]
        require(len(current)==1 and current[0].superseded_by is None and
                current[0].value_summary==event.payload.value_summary and
                current[0].epistemic_status is EpistemicStatus.VERIFIED and
                ref in current[0].evidence_references,
                'MATH_MODEL_CURRENT_RELATION_CONTRADICTED_OR_UNAVAILABLE')
    return model, record


def evaluate_current(*, store, projection, z, memory_id, requests, flower_context=None):
    """Recompute all numbers; accepts no caller scores, vectors, or certificates.

Each candidate's utility model is a complete finite deterministic transition
table. Its uniform bound is derived by enumerating EVERY row. Actual input
vectors come from the current audited Entity record. Model truth is not implied.
"""
    # A public helper must not turn a genuine projection plus caller-forged X/U
    # into a source-certified evaluation. Recreate the full current typed packet.
    from .grounded_general_state import project_general_state, recheck_general_state
    actual_projection,packet=project_general_state(store)
    actual_z=recheck_general_state(store,actual_projection,packet)
    require(actual_projection == projection and typed.exact(actual_z,z), 'MATH_FULL_SOURCE_REBIND')
    model, record = _load(store, projection, memory_id)
    flower_binding=None
    if flower_context is not None:
        from . import grounded_flower_feature_correspondence as feature
        flower_binding=feature.certify_retained_model(z=z,model=model,requests=requests,**flower_context)
    basis = model['basis']
    require(type(basis) is list and 1 <= len(basis) <= 4 and
            all(type(v) is str and 0 < len(v) <= 64 for v in basis) and
            len(set(basis)) == len(basis), 'MATH_BASIS')
    n = len(basis)
    matrices = model['operators']
    require(type(matrices) is dict and set(matrices) == {
        'flower','ethical_projection','knowledge','merkabah_forward','cube_stabilizer'}, 'MATH_OPERATOR_SET')
    ops = math.OperatorSet(**{key:math.Linear(tuple(_vector(row,n) for row in value))
                             for key,value in matrices.items()})
    pol = model['policy']
    require(type(pol) is dict and set(pol) == {'eps','arbitration','eta','rho','gamma','beta','max_gain'},
            'MATH_POLICY_FIELDS')
    # No uncertified exp/sqrt rounding. The exact algebraic subdomain is explicit.
    require(type(pol['eps']) is str and type(pol['arbitration']) is str and
            type(pol['max_gain']) is str, 'MATH_POLICY_DECIMALS')
    require(Decimal(pol['arbitration']) == 0, 'MATH_TRANSCENDENTAL_ENCLOSURE_UNAVAILABLE')
    require(type(model['horizon']) is int and 0 <= model['horizon'] <= 16, 'MATH_HORIZON')
    specs = model['candidates']
    require(type(specs) is dict and 1 <= len(specs) <= 12, 'MATH_FINITE_CANDIDATES')
    require(all(r['id'] in specs for r in requests), 'MATH_REQUEST_NOT_IN_RETAINED_MODEL')
    source_binding = dict(version=VERSION, math_contract=math.CONTRACT,
        entity=projection.identity_instance_id, head=projection.entity_state_id,
        source=projection.projection_hash, receipt=projection.receipt_hash,
        frame=projection.source_frame.theta_hash, basis=basis, model=digest(model),
        memory=record.memory_id, events=list(record.source_event_ids),
        uncertainty=digest(z['U']), math_source=sha256(Path(math.__file__).read_bytes()).hexdigest(),
        bridge_source=sha256(Path(__file__).read_bytes()).hexdigest(),
        scope='AUDITED_PERSISTED_FINITE_MODEL_NOT_WORLD_TRUTH_OR_CANONICAL_ADOPTION')
    if flower_binding is not None:
        source_binding['flower_binding_sha256']=flower_binding['binding_sha256']
    rows = {}
    for r in requests:
        spec = specs[r['id']]
        require(type(spec) is dict and set(spec) == {
            'path','equals','effect','inherited','information','self','valuation','cost','risk',
            'irreversibility','utility','start'}, 'MATH_CANDIDATE_FIELDS')
        require(typed.exact(spec['path'],r['path']) and typed.exact(spec['equals'],r['equals']) and
                typed.exact(spec['effect'],r.get('effect')), 'MATH_REQUEST_MODEL_SCOPE')
        inherited = _numeric_paths(z,spec['inherited'],n)
        information = _numeric_paths(z,spec['information'],n)
        if flower_binding is not None:
            require(information==flower_binding['information'] and
                    ops.flower.rows==flower_binding['phi_rows'],'FLOWER_MATH_INPUT_BINDING')
            information=flower_binding['information']
        self_state = _numeric_paths(z,spec['self'],n,self_model=True)
        table = spec['utility']
        require(type(table) is list and 1 <= len(table) <= 16, 'MATH_FINITE_UTILITY_TABLE')
        utility = []
        for cell in table:
            require(type(cell) is dict and set(cell) == {'value','next'} and
                    type(cell['next']) is int and 0 <= cell['next'] < len(table), 'MATH_TOTAL_UTILITY_MODEL')
            utility.append(_vector(cell['value'],n))
        require(type(spec['start']) is int and 0 <= spec['start'] < len(table), 'MATH_UTILITY_INITIAL_STATE')
        cap = max(abs(v) for row in utility for v in row)
        cap_ref = 'sha256:'+math.digest(dict(table=table, bound=cap, proof='EXHAUSTIVE_TOTAL_FINITE_TABLE'))
        policy = math.Policy(Decimal(pol['eps']),Decimal(pol['arbitration']),
            rational(pol['eta']),rational(pol['rho']),rational(pol['gamma']),rational(pol['beta']),
            cap,cap_ref,Decimal(pol['max_gain']))
        denominator = Fraction(policy.denominator())
        require(denominator*denominator == 1+Fraction(policy.eps), 'MATH_EXACT_NORMALIZER_UNAVAILABLE')
        prefix=[]; at=spec['start']
        for _ in range(model['horizon']):
            prefix.append(utility[at]); at=table[at]['next']
        contribution = math.Contribution(projection.entity_state_id, inherited,
            (math.FieldPoint(r['id'],projection.entity_state_id,information,Fraction(1),'VERIFIED'),),
            self_state,projection.entity_state_id,tuple(prefix))
        evaluated = math.evaluate(ops,policy,contribution)
        if flower_binding is not None:
            feature.require_consumed(flower_binding,evaluated)
        require(evaluated.actualized is False, 'MATH_PROPOSAL_CANNOT_BE_ACTUALIZED')
        exact_vector=tuple(inherited[i]+policy.eta*evaluated.terms['field_integral_numerator'][i]/denominator+
            policy.rho*self_state[i]+policy.gamma*evaluated.terms['future_prefix'][i] for i in range(n))
        decimal_error=max(abs(exact_vector[i]-Fraction(evaluated.vector[i])) for i in range(n))
        tail=abs(policy.gamma)*cap*policy.beta**(model['horizon']+1)/(1-policy.beta)
        valuation=_vector(spec['valuation'],n)
        costs=tuple(rational(spec[k]) for k in ('cost','risk','irreversibility'))
        require(all(v>=0 for v in costs) and costs[0].denominator == 1 and costs[0] <= 1_000_000,
                'MATH_NONNEGATIVE_BOUNDED_COSTS')
        value=sum((Fraction(v)*w for v,w in zip(evaluated.vector,valuation)),Fraction())-sum(costs)
        radius=(tail+decimal_error)*sum(abs(v) for v in valuation)
        binding=dict(source=source_binding,request=r,inputs=dict(inherited=inherited,information=information,
            self=self_state),model_spec=spec,cap_certificate=cap_ref,evaluation=evaluated.proposal_hash,
            exact_normalizer=denominator,decimal_error=decimal_error,tail=tail,score=value,radius=radius)
        if flower_binding is not None:
            binding["flower_correspondence"]=flower_binding
        record_hash=math.digest(binding)
        rows[r['id']]=dict(evaluation=evaluated,score=value,radius=radius,cost=int(costs[0]),
            risk=costs[1],irreversibility=costs[2],binding=math._canonical(binding),hash=record_hash,
            public=dict(contract=VERSION,model_contract=MODEL,hash=record_hash,
                evaluation=math._canonical(dict(vector=evaluated.vector,terms=evaluated.terms,
                    stages=evaluated.stage_traces)),score=math._canonical(value),radius=math._canonical(radius)))
    return rows,dict(source_binding, request_ids=[r['id'] for r in requests],
                     binding_sha256=math.digest([rows[r['id']]['hash'] for r in requests]))


def choose_certified(rows, eligible):
    """Exact rational comparison of the computed math output and sound radius."""
    candidates=[(identifier,rows[identifier]) for identifier in eligible]
    if not candidates:
        return None,'MATH_NO_ELIGIBLE_CANDIDATES'
    candidates.sort(key=lambda pair:(-pair[1]['score'],pair[1]['irreversibility'],pair[1]['risk'],
                                     pair[1]['cost'],eligible[pair[0]],pair[0]))
    identifier,top=candidates[0]
    for _,other in candidates[1:]:
        if top['score']-top['radius'] <= other['score']+other['radius']:
            if not(top['score']==other['score'] and top['radius']==other['radius']==0):
                return None,'MATH_CERTIFIED_INTERVAL_OVERLAP'
    if top['score']-top['radius'] <= 0:
        return None,'MATH_CERTIFIED_VALUE_NOT_POSITIVE'
    return identifier,'MATH_CERTIFIED_ELIGIBLE_SELECTION'


def qpre_payload(row):
    """Actual evaluated values travel through QPRE, not only a hash sidecar."""
    values = dict(vector=row['evaluation'].vector, score=row['score'],radius=row['radius'],
                  costs=(row['cost'],row['risk'],row['irreversibility']),binding=row['hash'])
    return {'owner-math-'+key+'-v1':json.dumps(math._canonical(value),sort_keys=True,separators=(',',':'))
            for key,value in values.items()}


def from_qpre(candidate):
    """Read only a Sphere-validated QPRE payload; this is not a verifier itself."""
    fields={f.name:f.possible_value for f in candidate.realization.candidate_state[1:]}
    require(set(fields)=={'owner-math-'+key+'-v1' for key in ('vector','score','radius','costs','binding')},
            'MATH_QPRE_FIELDS')
    def fraction(x):
        if type(x) is int:
            return Fraction(x)
        require(type(x) is dict and set(x)=={'num','den'} and type(x['num']) is int and
                type(x['den']) is int and x['den']>0, 'MATH_QPRE_RATIONAL')
        return Fraction(x['num'],x['den'])
    values={k:json.loads(v) for k,v in fields.items()}
    cost,risk,irreversibility=map(fraction,values['owner-math-costs-v1'])
    return dict(score=fraction(values['owner-math-score-v1']),radius=fraction(values['owner-math-radius-v1']),
                cost=cost,risk=risk,irreversibility=irreversibility,hash=values['owner-math-binding-v1'],
                vector=values['owner-math-vector-v1'])
