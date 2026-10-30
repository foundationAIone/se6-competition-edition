"""Versioned DEVELOPMENT state/return contract. No effects or authority.

This is an explicit candidate refinement, not an amendment of RealizationFrame
v1. P projects a possibility field; Pack/Decode recover a different, verified
state representation. Neither operation inverts a World effect.
"""
from copy import deepcopy
import math
from .observation_grounding import digest, require

VERSION = 'grounded-state-transition-candidate-v1'
SCHEMA = 'grounded-total-state-candidate-v1'
INPUT_VERSION = 'grounded-decision-inputs-v1'
FRAME_DIMENSIONS = ('continuation-length','prediction-status','action-cost','risk-units')


def tree(value, depth=0, budget=None):
    """Injective finite typed encoding; bool/int, list/tuple, missing/null differ."""
    budget = [32768] if budget is None else budget
    budget[0] -= 1
    require(depth <= 32 and budget[0] >= 0, 'TYPED_TREE_BOUND')
    t = type(value)
    if value is None: return ['null']
    if t is bool: return ['bool', value]
    if t is int:
        require(value.bit_length() <= 4096, 'INTEGER_BOUND')
        return ['int', str(value)]
    if t is float:
        require(math.isfinite(value), 'FINITE_FLOAT_REQUIRED')
        return ['float', value.hex()]
    if t is str:
        require(len(value) <= 65536, 'STRING_BOUND')
        return ['str', value]
    if t in (list, tuple):
        return ['list' if t is list else 'tuple', [tree(x, depth+1, budget) for x in value]]
    require(t is dict and all(type(k) is str for k in value), 'UNSUPPORTED_TYPED_VALUE')
    return ['dict', [[tree(k, depth+1, budget), tree(value[k], depth+1, budget)] for k in sorted(value)]]


def un_tree(node):
    budget=[32768]
    def decode(n,depth=0):
        budget[0]-=1
        require(depth<=32 and budget[0]>=0,'TYPED_TREE_BOUND')
        require(type(n) is list and n, 'TYPED_NODE')
        tag = n[0]
        if tag == 'null':
            require(len(n) == 1, 'NULL_ARITY'); return None
        require(len(n) == 2, 'TYPED_ARITY')
        v = n[1]
        if tag == 'bool': require(type(v) is bool, 'BOOL_TYPE'); return v
        if tag == 'str': require(type(v) is str, 'STRING_TYPE'); return v
        if tag == 'int': require(type(v) is str, 'INT_ENCODING'); return int(v)
        if tag == 'float': require(type(v) is str, 'FLOAT_ENCODING'); return float.fromhex(v)
        require(type(v) is list, 'CONTAINER_ENCODING')
        if tag in ('list', 'tuple'):
            values = [decode(x,depth+1) for x in v]
            return values if tag == 'list' else tuple(values)
        require(tag == 'dict', 'UNKNOWN_TYPE_TAG')
        result = {}
        for pair in v:
            require(type(pair) is list and len(pair) == 2, 'DICT_ENTRY')
            k = decode(pair[0],depth+1); require(type(k) is str and k not in result, 'DICT_KEY')
            result[k] = decode(pair[1],depth+1)
        return result
    result = decode(node)
    require(tree(result) == node, 'NONCANONICAL_TREE_IMAGE')
    return result


def same(a, b): return tree(a) == tree(b)
def seal(value): return digest(tree(value))


def exact(a,b):
    """Type-aware equality, traversing the already validated expected tree.

    No probabilistic hash equality or second encoding/budget is used for the
    exact representation laws. The expected operand bounds recursive work.
    """
    if type(a) is not type(b): return False
    if type(a) is dict:
        return a.keys()==b.keys() and all(exact(v,b[k]) for k,v in a.items())
    if type(a) in (list,tuple):
        return len(a)==len(b) and all(exact(x,y) for x,y in zip(a,b))
    if type(a) is float: return a.hex()==b.hex()
    return a==b


def _view(z, context):
    if context['projection'] == 'state-operational-v1':
        validate_state(z)
        return dict(X=z['X'], frame=z['Theta']['frame'], active=[g['id'] for g in z['Theta']['governing'] if g['status']=='APPLICABLE'])
    if context['projection'] == 'field-evaluation-v1':
        require(type(z) is list, 'FIELD_DOMAIN')
        return [dict(candidate_id=r['candidate_id'], source=r['source'],
                     admissible=r['mirror']['consistent'], reasons=r['mirror']['reasons']) for r in z]
    require(context['projection'] == 'structural-paths-v1', 'UNKNOWN_PROJECTION')
    return [at(z, p) for p in context['paths']]


def at(value, path):
    require(type(path) is list and len(path) <= 32, 'PATH_TYPE')
    for k in path:
        if type(value) is dict:
            require(type(k) is str and k in value, 'MISSING_PATH')
        else:
            require(type(value) in (list, tuple) and type(k) is int and 0 <= k < len(value), 'PATH_INDEX')
        value = value[k]
    return value


def pack(z, context):
    """Computed projection plus immutable FULL complement; deterministic in c."""
    require(type(context) is dict and set(context) == {'version','schema','entity','predecessor','frame','governing','source_pins','projection','paths'}, 'PACK_CONTEXT')
    require(context['version'] == VERSION, 'PACK_VERSION')
    source = tree(z)
    if context['projection'] == 'state-operational-v1':
        require(same(context, state_context(z)), 'STATE_CONTEXT_BINDING')
    return dict(context=deepcopy(context), view=tree(_view(z, context)), complement=source)


def recover(packet, expected_context):
    require(type(packet) is dict and set(packet) == {'context','view','complement'}, 'RETURN_COMPLETE_PAYLOAD')
    require(same(packet['context'], expected_context), 'RETURN_CONTEXT_BINDING')
    z = un_tree(packet['complement'])
    require(exact(pack(z, expected_context),packet), 'RETURN_NOT_IN_PACK_IMAGE')
    return z


def validate_config(config):
    require(type(config) is dict and set(config) == {'version','source_pins','governing','model_requires'}, 'STATE_CONFIG_FIELDS')
    require(config['version'] == VERSION, 'STATE_CONFIG_VERSION')
    pins = config['source_pins']
    require(type(pins) is dict and pins and all(type(k) is str and type(v) is str and len(v)==64
            and all(c in '0123456789abcdef' for c in v) for k,v in pins.items()), 'STATE_SOURCE_PINS')
    require(type(config['governing']) is list and 0 < len(config['governing']) <= 32, 'GOVERNING_BOUND')
    ids = []
    for g in config['governing']:
        require(set(g) == {'id','kind','dependencies_complete','environment_known','assumptions','domain','through_version'}, 'GOVERNING_FIELDS')
        require(type(g['id']) is str and g['id'] and g['kind'] in ('REUSABLE_RELATION','STATE_PREDICTION'), 'GOVERNING_KIND')
        require(type(g['dependencies_complete']) is bool and type(g['environment_known']) is bool, 'DEPENDENCY_DECLARATION')
        require(type(g['through_version']) is int and g['through_version'] >= 0, 'GOVERNING_FRESHNESS')
        require(type(g['assumptions']) is list and g['assumptions'] and all(type(x) is str and x for x in g['assumptions']), 'EXPLICIT_ASSUMPTIONS')
        require(type(g['domain']) is list and len(g['domain']) <= 32, 'DOMAIN_BOUND')
        for p in g['domain']:
            require(set(p) == {'path','equals'} and type(p['path']) is list and len(p['path'])<=32
                    and all(type(k) is str or (type(k) is int and k>=0) for k in p['path']), 'DOMAIN_PREDICATE')
            tree(p['equals'])
        ids.append(g['id'])
    require(len(set(ids)) == len(ids), 'UNIQUE_GOVERNING_IDS')
    needed=config['model_requires']
    require(type(needed) is list and needed and all(type(x) is str for x in needed)
            and len(set(needed))==len(needed) and set(needed)<=set(ids),'MODEL_GOVERNING_DEPENDENCIES')


def applicability(definition, observation, version, *, initial=False):
    reasons = []
    if not definition['dependencies_complete']: reasons.append('DEPENDENCIES_UNKNOWN')
    if not definition['environment_known']: reasons.append('ENVIRONMENT_UNKNOWN')
    if version > definition['through_version']: reasons.append('FRESHNESS_EXPIRED')
    if not initial and definition['kind'] == 'STATE_PREDICTION': reasons.append('OLD_STATE_PREDICTION')
    for p in definition['domain']:
        try:
            if not same(at(observation,p['path']),p['equals']): reasons.append('DOMAIN_CHANGED')
        except ValueError: reasons.append('DOMAIN_UNKNOWN')
    return list(dict.fromkeys(reasons))


def state_context(z):
    return dict(version=VERSION,schema=SCHEMA,entity=z['entity'],predecessor=z['predecessor'],
        frame=seal(z['Theta']['frame']),governing=seal(z['Theta']['governing']),source_pins=z['source_pins'],
        projection='state-operational-v1',paths=[])


def validate_state(z):
    tree(z)
    require(set(z) == {'schema','entity','predecessor','version','source_pins','X','Theta','M','E','U'}, 'TOTAL_STATE_FIELDS')
    require(z['schema'] == SCHEMA and type(z['entity']) is str and z['entity'], 'TOTAL_STATE_SCHEMA')
    require(type(z['version']) is int and z['version'] >= 0 and (z['predecessor'] is None)==(z['version']==0), 'TOTAL_STATE_LINEAGE')
    require(set(z['X']) == {'native_state','source','epoch','observation','goal','memory_ref'}, 'X_FIELDS')
    require(type(z['M']) is list and len(z['M']) == z['version']+1 and z['X']['memory_ref']==seal(z['M']), 'MEMORY_BINDING')
    x=z['X'];last=z['M'][-1]
    require(type(x['native_state']) is str and len(x['native_state'])==64 and
            all(c in '0123456789abcdef' for c in x['native_state']), 'NATIVE_STATE_REFERENCE')
    require(type(x['source']) is str and x['source'] and type(x['epoch']) is str and x['epoch']
            and (x['goal'] is None or type(x['goal']) is bool), 'OBSERVATION_STATE_TYPES')
    require(type(last['history']) is list and last['history'] and
            same(x['observation'],last['history'][-1]['raw']) and same(x['goal'],last['history'][-1]['goal']) and
            all(r['source']==x['source'] and r['epoch']==x['epoch'] for r in last['history']), 'CURRENT_OBSERVATION_MEMORY')
    if z['version']==0:
        require(last['kind']=='VERIFIED_BOUNDED_SUPPORT' and x['native_state']==last['origin']['native_state'],'GENESIS_NATIVE_REFERENCE')
    else:
        require(last['kind'] in ('VERIFIED_OBSERVATION_TRANSITION','VERIFIED_CURRENT_OBSERVATION','VERIFIED_DECISION_INPUT') and
                z['predecessor']==last['predecessor'] and x['native_state']==last['native_state'], 'SUCCESSOR_NATIVE_REFERENCE')
    require(set(z['Theta']) == {'schema','frame','x_binding','previous_theta','transition','governing'}, 'THETA_FIELDS')
    require(z['Theta']['schema'] == 'candidate-explicit-state-binding-v1' and z['Theta']['x_binding']==seal(z['X']), 'THETA_X_BINDING')
    if z['Theta']['frame'].get('version')==INPUT_VERSION:
        import json
        from .realization_frame import RealizationFrame
        f=z['Theta']['frame'];canonical=RealizationFrame.model_validate_json(json.dumps(f['canonical']))
        require(f['bound_x']==seal(z['X']) and canonical.x.state_summary=='Exact operational-X reference '+seal(z['X']),
            'CURRENT_FRAME_X_BINDING')
    require((z['Theta']['previous_theta'] is None)==(z['version']==0), 'THETA_LINEAGE')
    require(z['Theta']['transition']==seal(z['M'][-1]), 'TRANSITION_MEMORY_BINDING')
    validate_config(dict(version=VERSION,source_pins=z['source_pins'],governing=[g['definition'] for g in z['Theta']['governing']],
                         model_requires=z['M'][0]['model_requires']))
    for g in z['Theta']['governing']:
        require(set(g)=={'id','definition','support','origin','status','reasons','successor_binding'}, 'GOVERNING_STATE_FIELDS')
        reasons=applicability(g['definition'],z['X']['observation'],z['version'],initial=z['version']==0)
        if z['M'][-1].get('prediction_passed') is False: reasons.append('CONTRADICTED_MODEL')
        # A suspended relationship cannot regain use merely from later field agreement.
        prior=z['M'][-1].get('suspended_ids',[])
        if g['id'] in prior: reasons.append('PRIOR_SUSPENSION_REVALIDATION_REQUIRED')
        require(g['id']==g['definition']['id'] and g['reasons']==reasons and
                g['status']==('SUSPENDED' if reasons else 'APPLICABLE'), 'APPLICABILITY_RECOMPUTE')
        require(g['successor_binding']==dict(x=seal(z['X']),transition=z['Theta']['transition'],support=g['support']), 'GOVERNING_SUCCESSOR_BINDING')
        require(g['support']==z['M'][0]['certificate_sha256'], 'ORIGINAL_SUPPORT_BINDING')
        require(g['origin']==z['M'][0]['origin'], 'ORIGINAL_FRAME_BINDING')
    require(z['E']==[r['evidence'] for r in z['M']], 'EVIDENCE_MEMORY_BINDING')
    require(type(z['U']) is list and z['U'], 'UNCERTAINTY_REQUIRED')
    return z


def _assemble(entity, predecessor, version, pins, x, frame, previous_theta, governing, memory, uncertainty):
    x={**deepcopy(x),'memory_ref':seal(memory)}
    transition=seal(memory[-1]); items=[]
    frame=rebind_frame(frame,x,transition,memory[-1]['kind'])
    for old in governing:
        g=deepcopy(old); reasons=applicability(g['definition'],x['observation'],version,initial=version==0)
        if memory[-1].get('prediction_passed') is False: reasons.append('CONTRADICTED_MODEL')
        if g['id'] in memory[-1].get('suspended_ids',[]): reasons.append('PRIOR_SUSPENSION_REVALIDATION_REQUIRED')
        g.update(status='SUSPENDED' if reasons else 'APPLICABLE',reasons=reasons,
                 successor_binding=dict(x=seal(x),transition=transition,support=g['support']))
        items.append(g)
    z=dict(schema=SCHEMA,entity=entity,predecessor=predecessor,version=version,source_pins=deepcopy(pins),X=x,
        Theta=dict(schema='candidate-explicit-state-binding-v1',frame=deepcopy(frame),x_binding=seal(x),
                   previous_theta=previous_theta,transition=transition,governing=items),
        M=deepcopy(memory),E=[r['evidence'] for r in memory],U=deepcopy(uncertainty))
    return validate_state(z)


def initial_state(config, frame, certificate, history, binding):
    validate_config(config)
    origin=dict(native_state=binding['entity_state'],frame=seal(frame))
    support=certificate['certificate_sha256']
    memory=[dict(kind='VERIFIED_BOUNDED_SUPPORT',certificate_sha256=support,origin=origin,model_requires=deepcopy(config['model_requires']),
                 evidence=certificate['released'],history=deepcopy(history))]
    governing=[dict(id=d['id'],definition=deepcopy(d),support=support,origin=origin) for d in config['governing']]
    x=dict(native_state=binding['entity_state'],source=binding['source'],epoch=binding['epoch'],
           observation=deepcopy(history[-1]['raw']),goal=history[-1]['goal'])
    return _assemble(binding['entity_id'],None,0,config['source_pins'],x,frame,None,governing,memory,
        ['Finite observed model is conditional; unobserved environmental changes remain possible.'])


def advance(z, witness, pending, native_state, history, prediction_passed):
    """Called ONLY after existing independent witness verification. Pure proposal.

    The witnessed raw observation is a complete observation payload, NOT the
    complete physical world. All other world quantities remain unknown.
    """
    validate_state(z); b=pending['prepared']['binding']
    require(z['entity']==b['entity_id'] and z['X']['source']==b['source'] and z['X']['epoch']==b['epoch'], 'SUCCESSOR_SCOPE')
    require(same(z['M'][-1]['history'],pending['prepared']['history']), 'SUCCESSOR_PREDECESSOR_HISTORY')
    require(witness['entity_id']==z['entity'] and witness['before_head']==b['memory_head'] and
            witness['source']==b['source'] and witness['epoch']==b['epoch'] and
            witness['attempt_id']==pending['attempt_id'] and witness['action_sha256']==digest(pending['action']), 'SUCCESSOR_WITNESS_BINDING')
    require(same(history,pending['prepared']['history']+[witness['observation_row']]), 'SUCCESSOR_OBSERVATION_SCOPE')
    require(same(witness['raw'],history[-1]['raw']) and type(witness['goal']) is bool and same(witness['goal'],history[-1]['goal']), 'SUCCESSOR_READBACK')
    memory=z['M']+[dict(kind='VERIFIED_OBSERVATION_TRANSITION',predecessor=seal(z),evidence=deepcopy(witness),
        before_head=b['memory_head'],action=deepcopy(pending['action']),history=deepcopy(history),
        native_state=native_state,native_receipt_hash=pending['core_head'],prediction_passed=prediction_passed,
        suspended_ids=[g['id'] for g in z['Theta']['governing'] if g['status']=='SUSPENDED'])]
    x=dict(native_state=native_state,source=b['source'],epoch=b['epoch'],observation=deepcopy(witness['raw']),goal=witness['goal'])
    inputs=pending['prepared'].get('learned',{}).get('selection',{}).get('decision_inputs')
    frame,unknown=renewed_inputs(z,memory[-1],inputs)
    return _assemble(z['entity'],seal(z),z['version']+1,z['source_pins'],x,frame,seal(z['Theta']),
        z['Theta']['governing'],memory,unknown)


def renewed_inputs(z, record, inputs):
    """Retain the exact consumed result, not a new observation or authority."""
    if inputs is None:return z['Theta']['frame'],z['U']
    require(inputs['version']==INPUT_VERSION and inputs['predecessor']==seal(z),'INPUT_SUCCESSOR_BINDING')
    record['decision_inputs']=deepcopy(inputs)
    return inputs['frame'],list(dict.fromkeys(z['U']+inputs['uncertainty']))


def advance_decision(z, native_record, native_state):
    """No-World Update: preserve external observation; retain actual Native work."""
    import json
    validate_state(z)
    material=native_record['material'];receipt=native_record['receipt']
    require(exact(material['semantic_packet'],pack(z,state_context(z))),'LOCAL_DECISION_PREDECESSOR')
    decision=json.loads(receipt['observed_consequence']['result'])['decision']
    require(decision['status']=='UNKNOWN' and decision['selection'].get('decision_inputs'), 'LOCAL_NO_EFFECT_DECISION')
    memory=z['M']+[dict(kind='VERIFIED_DECISION_INPUT',predecessor=seal(z),
        evidence=dict(native_receipt_hash=receipt['receipt_hash']),history=deepcopy(material['history']),
        native_state=native_state,native_receipt_hash=receipt['receipt_hash'],
        before_head=material['binding']['memory_head'],
        suspended_ids=[g['id'] for g in z['Theta']['governing'] if g['status']=='SUSPENDED'])]
    frame,unknown=renewed_inputs(z,memory[-1],decision['selection']['decision_inputs'])
    x={k:deepcopy(v) for k,v in z['X'].items() if k!='memory_ref'};x['native_state']=native_state
    return _assemble(z['entity'],seal(z),z['version']+1,z['source_pins'],x,frame,seal(z['Theta']),
        z['Theta']['governing'],memory,unknown)


def eligible(z, certificate, history, binding):
    validate_state(z)
    require(z['entity']==binding['entity_id'] and z['X']['source']==binding['source'] and z['X']['epoch']==binding['epoch'], 'SELECTION_STATE_SCOPE')
    require(z['X']['native_state']==binding['entity_state'],'SELECTION_CURRENT_NATIVE_REFERENCE')
    require(same(z['M'][-1]['history'],history), 'SELECTION_RETAINED_HISTORY')
    require(all(g['support']==certificate['certificate_sha256'] for g in z['Theta']['governing']), 'SELECTION_RETAINED_SUPPORT')
    by_id={g['id']:g for g in z['Theta']['governing']}
    # This bounded learner has one certificate/model family. Every prediction
    # consumes its exact declared dependency set; an unrelated valid item can
    # never license a model whose required calibration is suspended.
    return all(by_id[i]['status']=='APPLICABLE' for i in z['M'][0]['model_requires'])


def refresh_observation(z, history, binding):
    """Pure derived current view from an authenticated fresh reset observation.

    Caller authenticates public rows first. This does not perform or authorize
    a reset. It does not manufacture an action consequence from a new reading.
    All other changed histories require the normal witnessed transition path.
    """
    validate_state(z)
    require(z['entity']==binding['entity_id'] and z['X']['source']==binding['source']
            and z['X']['epoch']==binding['epoch'],'REFRESH_SOURCE_SCOPE')
    require(len(history)==1 and history[0]['action'] is None and history[0]['index']==0
            and history[0]['goal'] is None and history[0]['source']==binding['source']
            and history[0]['epoch']==binding['epoch'],'REFRESH_ONLY_AUTHENTIC_RESET_OBSERVATION')
    record=dict(kind='VERIFIED_CURRENT_OBSERVATION',predecessor=seal(z),evidence=deepcopy(history),
                history=deepcopy(history),native_state=binding['entity_state'],before_head=binding['memory_head'],
                suspended_ids=[g['id'] for g in z['Theta']['governing'] if g['status']=='SUSPENDED'])
    x=dict(native_state=binding['entity_state'],source=binding['source'],epoch=binding['epoch'],
           observation=deepcopy(history[0]['raw']),goal=None)
    return _assemble(z['entity'],seal(z),z['version']+1,z['source_pins'],x,z['Theta']['frame'],seal(z['Theta']),
                     z['Theta']['governing'],z['M']+[record],z['U'])


def base_frame(frame):
    return frame['base'] if frame.get('version')==INPUT_VERSION else frame


def rebind_frame(frame,x,transition,kind):
    """Changed-X Update is NOT same-X EXPANSION. Preserve exact source lineage."""
    if frame.get('version')!=INPUT_VERSION or frame['bound_x']==seal(x):return frame
    return _frame_successor(frame,seal(x),transition,kind)


def _frame_successor(frame,x_hash,transition,kind):
    """Pure fixed-size binding constructor; also used by capacity reservation."""
    import json
    from . import realization_frame as frames
    from .epistemic_status import EpistemicStatus as E
    previous=frames.RealizationFrame.model_validate_json(json.dumps(frame['canonical']))
    source=frames.create_source_observation(source_reference='operational-X:'+x_hash,
        summary='Verified candidate Update binding; not a same-X frame expansion.',epistemic_status=E.DETERMINISTIC,
        evidence_references=('X:'+x_hash,'transition:'+transition))
    successor=frames.advance_realization_state(previous.x,state_summary='Exact operational-X reference '+x_hash,
        additional_observations=(source,))
    current=frames.create_realization_frame(successor,frame_name=previous.frame_name,
        dimensions=previous.dimensions,representation_rules=previous.representation_rules)
    return {**deepcopy(frame),'canonical':current.model_dump(mode='json'),'bound_x':x_hash,'prior_frame':seal(frame),
        'update_binding':dict(previous_canonical_frame=previous.theta_hash,transition=transition,kind=kind,
            world_effect_observed=kind=='VERIFIED_OBSERVATION_TRANSITION')}


def decision_inputs(z, supplied, graph, policy, binding, history):
    """Typed inputs consumed before QPRE; no producer flag becomes World truth.

    ObservationAwareness and EpistemicStatus retain their existing meanings.
    RealizationFrame EXPANSION uses one exact frozen X. A later observed-X
    rebind is a separate candidate Update, never a renamed EXPANSION.
    """
    import json
    from . import realization_frame as frames
    from .operational_awareness import ObservationAwareness,ObservationStatus
    from .epistemic_status import EpistemicStatus as E
    from . import universal_mapper as mapper
    require(type(supplied) is dict and set(supplied)=={'version','binding','observation','lifecycle',
        'observation_use','added_dimensions','require_trace_inverse'},'DECISION_INPUT_FIELDS')
    require(supplied['version']==INPUT_VERSION and exact(supplied['binding'],binding),'DECISION_INPUT_BINDING')
    status=ObservationAwareness.model_validate_json(json.dumps(supplied['observation']))
    lifecycle=E(supplied['lifecycle'])
    require(supplied['observation_use'] in ('CURRENT_REQUIRED','RETAINED_CONDITIONAL') and
        type(supplied['require_trace_inverse']) is bool,'DECISION_INPUT_USE')
    if status.status is not ObservationStatus.NOT_OBSERVED:
        require(status.summary==digest(history[-1]['raw']) and status.result_type=='AUTHENTICATED_RAW_HISTORY'
            and status.evidence_references==(digest(history),),'OBSERVATION_EXACT_HISTORY')
    else:
        require(lifecycle not in (E.VERIFIED,E.MEASURED,E.OBSERVED),'ABSENT_NOT_VERIFIED')
    # Even a correctly shaped VERIFIED object gets truth only from the caller's
    # existing authenticate_rows port, invoked before this function.
    current=(status.status is ObservationStatus.VERIFIED and lifecycle is E.VERIFIED)
    contradicted=lifecycle in (E.CONTRADICTED,E.REVOKED)
    allowed=not contradicted and (current or supplied['observation_use']=='RETAINED_CONDITIONAL')
    unknown=[]
    if not current:unknown.append('Current observation: '+status.status.value+' / '+lifecycle.value)
    if not current and allowed:unknown.append('Action prediction uses retained conditional evidence; current actuality is not asserted.')
    graph=mapper.UniversalMap.model_validate_json(json.dumps(graph))
    old=z['Theta']['frame'];dims=['continuation-length','prediction-status']
    if old.get('version')==INPUT_VERSION:dims=list(old['canonical']['dimensions'])
    added=supplied['added_dimensions']
    require(type(added) is list and len(added)==len(set(added)) and
        all(d in FRAME_DIMENSIONS for d in added),'SUPPORTED_MAPPED_DIMENSIONS')
    prices={k:v['cost'] for k,v in policy['admitted_prices'].items()}
    cells=[]
    center=graph.vertices[0]
    ids={r.node_id for e in graph.relations if e.label=='action-conditioned-prediction'
         and e.source_nodes==(center.reference,) for r in e.target_nodes}
    for n in graph.vertices:
        if n.node_id not in ids:continue
        p=json.loads(n.description);word=p['continuation']
        require(word and set(word)<=set(prices),'FRAME_PREDICTION_ACTIONS')
        cells.append(dict(node=n.node_id,values={'continuation-length':len(word),'prediction-status':p['status'],
            'action-cost':sum(prices[a] for a in word),
            'risk-units':sum(policy['actions'][a]['risk_units'] for a in word)}))
    require(cells,'FRAME_MAPPED_EVIDENCE')
    source=frames.create_source_observation(source_reference='operational-X:'+seal(z['X']),
        summary='Exact candidate operational X and authenticated history',epistemic_status=E.DETERMINISTIC,
        evidence_references=('X:'+seal(z['X']),'history:'+digest(history),'map:'+graph.map_hash))
    # Complete X stays in the adopted lossless packet; the bounded frame uses
    # its exact content reference, never tries to reconstruct X from this hash.
    x=frames.create_realization_state(state_summary='Exact operational-X reference '+seal(z['X']),
        source_observations=(source,))
    previous=(frames.RealizationFrame.model_validate_json(json.dumps(old['canonical'])) if old.get('version')==INPUT_VERSION else
        frames.create_realization_frame(x,frame_name='Mapped finite prediction evaluation',dimensions=dims))
    expanded=frames.expand_realization_frame(previous,frame_name=previous.frame_name,added_dimensions=added)
    require(expanded.x==previous.x and expanded.preserved_observation_bindings==previous.preserved_observation_bindings,
        'EXACT_X_FRAME_EXPANSION')
    frame=dict(version=INPUT_VERSION,base=deepcopy(base_frame(old)),canonical=expanded.model_dump(mode='json'),
        prior_frame=seal(old),bound_x=seal(z['X']),mapped_graph=graph.map_hash)
    return dict(version=INPUT_VERSION,predecessor=seal(z),observation=status.model_dump(mode='json'),
        lifecycle=lifecycle.value,observation_use=supplied['observation_use'],observation_allowed=allowed,
        require_trace_inverse=supplied['require_trace_inverse'],uncertainty=unknown,frame=frame,
        frame_expansion=dict(previous=previous.model_dump(mode='json'),expanded=expanded.model_dump(mode='json'),
            mapped_cells=cells,rebind_from=seal(old),world_state_changed=False))


def transport_keys(value, mapping):
    """Candidate coordinate transport: finite bijective top-level key renaming.

    Physical changes are not transport. Scalars, scaling, non-bijections and
    unknown frame maps reject. at(transport(x), renamed(p)) == at(x,p).
    """
    require(type(value) is dict and type(mapping) is dict and set(value)==set(mapping)
            and all(type(k) is str and type(v) is str for k,v in mapping.items())
            and len(set(mapping.values()))==len(mapping), 'UNSUPPORTED_FRAME_TRANSPORT')
    tree(value)
    return {mapping[k]:deepcopy(v) for k,v in value.items()}


def transport_relation(definition, value, mapping):
    """Transport declared path predicates, not physical calibration constants."""
    transported=transport_keys(value,mapping)
    result=deepcopy(definition)
    for predicate in result['domain']:
        require(predicate['path'] and predicate['path'][0] in mapping,'UNSUPPORTED_RELATION_TRANSPORT')
        predicate['path'][0]=mapping[predicate['path'][0]]
    require(applicability(definition,value,0,initial=True)==applicability(result,transported,0,initial=True),
            'TRANSPORT_EVALUATION_DOES_NOT_COMMUTE')
    return result,transported


def differentiate(terminals, inputs=None):
    """D candidate: lossless finite partition by computational horizon/status.

    No physical substrate is inferred. The partition's refs, not original list
    positions, feed traversal. Every input belongs to exactly one fiber.
    """
    import json
    fibers={}
    cells={c['node']:c['values'] for c in inputs['frame_expansion']['mapped_cells']} if inputs else {}
    dimensions=inputs['frame']['canonical']['dimensions'] if inputs else ['continuation-length','prediction-status']
    for node in terminals:
        p=json.loads(node.description)
        values=cells.get(node.node_id,{'continuation-length':len(p['continuation']),'prediction-status':p['status']})
        require(all(d in values for d in dimensions),'SUBSTRATE_DIMENSION_EVIDENCE')
        key=tuple(values[d] for d in dimensions)
        fibers.setdefault(key,[]).append(node.node_id)
    return [dict(substrate='COMPUTATIONAL_FINITE_HISTORY',horizon=k[0],status=k[1],nodes=sorted(v),
                 **(dict(dimensions=list(dimensions),coordinates=list(k)) if inputs else {}))
            for k,v in sorted(fibers.items())]


def transform_trace(prediction, proposal, history):
    """T candidate: replay conditional transition model, unfold ordered edges."""
    from .observation_grounding import predict, raw_id
    recomputed=predict(proposal,history,prediction['continuation'])
    require(same(prediction,recomputed),'TRANSFORMATION_PREDICTION_RECOMPUTE')
    if prediction['outcomes'] is None: return dict(status='UNKNOWN',edges=[])
    previous=raw_id(history[-1]['raw']); edges=[]
    for action,(observed,goal) in zip(prediction['continuation'],prediction['outcomes']):
        edges.append(dict(before=previous,action=action,after=observed,goal=goal));previous=observed
    require(len(edges)==len(prediction['continuation']),'TRANSFORMATION_COMPLETE_TRACE')
    return dict(status='CONDITIONAL_TRACE',edges=edges,history=digest(history))


def reflect(trace,prediction,declared_cost,prices,applicable,inputs=None):
    """S candidate: operational and resource views share unchanged provenance.

    These are deterministic views, NOT independent World observations. Exact
    trace/goal/action/cost agreement is the invariant; disagreement is retained.
    """
    edges=trace['edges']
    goal=bool(edges) and edges[-1]['goal'] is True
    actions=[e['action'] for e in edges]
    resource=sum(prices[a] for a in actions)
    reasons=[]
    if not applicable: reasons.append('SUSPENDED_GOVERNANCE')
    if not goal: reasons.append('GOAL_VIEW_REFUSED')
    if actions != prediction['continuation'] or [[e['after'],e['goal']] for e in edges]!=prediction['outcomes']:
        reasons.append('TRACE_VIEW_CONTRADICTION')
    if resource != declared_cost: reasons.append('RESOURCE_VIEW_CONTRADICTION')
    sphere=None
    if inputs is not None:
        sphere=sphere_inputs(trace,prices,inputs)
        if not sphere['consistent']:reasons.append('SPHERE_INTERPRETATION_CONTRADICTION')
        if inputs['require_trace_inverse'] and sphere['trace_inversion']['kind'] in ('UNKNOWN','NO_VALID_INVERSE'):
            reasons.append('REQUIRED_TRACE_INVERSE_UNAVAILABLE')
    return dict(consistent=not reasons,reasons=reasons,goal_view=goal,resource_view=resource,
                prediction_sha256=digest(prediction),independent_world_observation=False,
                **(dict(sphere=sphere) if sphere is not None else {}))


def sphere_inputs(trace, prices, inputs):
    """Existing typed Sphere constructors, with a finite explicit inverse domain.

    Reversal is an involution on finite computational edge lists; it is NOT an
    inverse World action. Cost totals have no inverse on arbitrary traces.
    Shared-source views are interpreted and compared, never counted as witnesses.
    """
    import json
    from . import realization_frame as frames,universal_mapper as mapper
    from .epistemic_status import EpistemicStatus as E
    frame=frames.RealizationFrame.model_validate_json(json.dumps(inputs['frame']['canonical']))
    source=mapper.create_reality_object(label='conditional computational trace',
        description=digest(trace),source_observations=frame.x.source_observations)
    fh=frame.theta_hash
    forward=dict(frame=fh,edges=trace['edges'],cost=sum(prices[e['action']] for e in trace['edges']))
    reverse=dict(frame=fh,edges=list(reversed(trace['edges'])),cost=forward['cost'])
    text=lambda v:json.dumps(v,sort_keys=True,separators=(',',':'))
    a=mapper.create_perspective_view(source,perspective_key='computational-forward',representation=text(forward))
    b=mapper.create_perspective_view(source,perspective_key='computational-reverse',representation=text(reverse))
    invariant=mapper.extract_common_denominator(source,(a,b))
    inverse_node=mapper.create_reality_object(label='reversed computational trace',description=text(reverse),
        source_observations=frame.x.source_observations)
    has_trace=trace['status']=='CONDITIONAL_TRACE'
    inversion=mapper.create_inversion_assessment(source,kind=mapper.InversionKind.MIRROR if has_trace else mapper.InversionKind.UNKNOWN,
        domain='finite-computational-trace-reversal-v1',reason='Exact list reversal; not a World inverse.' if has_trace else 'No defined trace.',
        epistemic_status=E.DETERMINISTIC if has_trace else E.UNKNOWN,inverse_node=inverse_node if has_trace else None)
    no_cost_inverse=mapper.create_inversion_assessment(source,kind=mapper.InversionKind.NO_VALID_INVERSE,
        domain='arbitrary-trace-cost-total-v1',reason='A scalar cost does not determine the originating trace.',epistemic_status=E.DETERMINISTIC)
    left=json.loads(a.representation);right=json.loads(b.representation)
    consistent=(exact(left,forward) and exact(right,reverse) and right['frame']==left['frame']==fh
        and exact(list(reversed(right['edges'])),left['edges']))
    if inversion.kind not in (mapper.InversionKind.UNKNOWN,mapper.InversionKind.NO_VALID_INVERSE):
        consistent=consistent and inversion.inverse_node==inverse_node.reference
    graph=mapper.create_universal_map(vertices=[source,inverse_node],perspectives=[a,b],
        invariants=[invariant],inversions=[inversion,no_cost_inverse])
    return dict(graph=graph.model_dump(mode='json'),trace_inversion=inversion.model_dump(mode='json'),
        cost_inversion=no_cost_inverse.model_dump(mode='json'),consistent=consistent,
        source_frame=fh,shared_source_only=True,independent_corroboration=False,
        uncertainty=(['Trace inverse unavailable in the declared domain.'] if inversion.kind in
            (mapper.InversionKind.UNKNOWN,mapper.InversionKind.NO_VALID_INVERSE) else []))


def verify_lineage(packets,records,renewals,*,native_state_hash):
    """Read-only retained-image membership/recomputation, no live permission."""
    first=next((r for r in records if 'semantic_packet' in r['material']),None)
    require(first is not None,'STATE_INITIAL_RECORD')
    m=first['material']; policy=first['boundary']['selection_policy']
    initial=initial_state(policy['state_semantics'],policy['frame'],m['certificate'],m['history'],m['binding'])
    require(exact(pack(initial,state_context(initial)),packets[0]),'STATE_GENESIS_REPLAY')
    current=initial
    rows=[r for r in renewals if 'semantic_successor_sha256' in r]
    relevant={r['semantic_successor_sha256']:r for r in rows}
    require(len(relevant)==len(rows),'DUPLICATE_STATE_RENEWAL')
    witnessed=set()
    used_native=set();used_attempts=set()
    for packet in packets[1:]:
        z=recover(packet,packet['context']); r=z['M'][-1]; w=r['evidence']
        if r['kind']=='VERIFIED_CURRENT_OBSERVATION':
            owners=[r for r in records if digest(r['material'].get('semantic_packet'))==digest(packet)]
            require(owners,'REFRESH_NATIVE_CONSUMPTION_RECORD')
            owner=owners[0]['material']
            require(same(r['history'],owner['history']),'REFRESH_CONSUMED_HISTORY')
            expected=refresh_observation(current,owner['history'],owner['binding'])
            require(same(z,expected),'REFRESH_REPLAY')
            current=z;continue
        require(digest(packet) in relevant,'STATE_RENEWAL_RECEIPT')
        renewal=relevant[digest(packet)];witnessed.add(digest(packet))
        matched=[n for n in records if n['receipt']['receipt_hash']==r['native_receipt_hash']]
        require(len(matched)==1 and r['native_receipt_hash'] not in used_native,'EXACT_SELECTING_NATIVE_RECORD')
        selected=matched[0];material=selected['material'];receipt=selected['receipt']
        import json
        decision=json.loads(receipt['observed_consequence']['result'])['decision']
        if r['kind']=='VERIFIED_DECISION_INPUT':
            require(renewal['status']=='VERIFIED_LOCAL_DECISION' and renewal['world_effects']==0 and
                renewal['local_decision_receipt']==receipt['receipt_hash'] and
                renewal['before_head']==material['binding']['memory_head'],'LOCAL_RENEWAL_BINDING')
            require(native_state_hash(receipt['state_after'])==r['native_state'] and
                native_state_hash(receipt['state_before'])==material['binding']['entity_state'],'LOCAL_NATIVE_BINDING')
            require(exact(z,advance_decision(current,selected,r['native_state'])),'LOCAL_DECISION_REPLAY')
            used_native.add(r['native_receipt_hash']);current=z;continue
        require(decision['status']=='GOAL_PATH_PREDICTED' and decision['actions'],'NATIVE_SELECTED_PATH')
        actions=[a for a in material['actions'] if a['id']==decision['actions'][0]]
        require(len(actions)==1 and same(actions[0],r['action']),'NATIVE_WITNESSED_ACTION')
        require(digest(material['semantic_packet'])==digest(pack(current,state_context(current))) and
                same(material['history'],current['M'][-1]['history']),'NATIVE_CONSUMED_PREDECESSOR')
        require(native_state_hash(receipt['state_after'])==r['native_state'] and
                native_state_hash(receipt['state_before'])==material['binding']['entity_state'],'NATIVE_SUCCESSOR_STATE_BINDING')
        require(w['attempt_id'] not in used_attempts and w['purpose']=='GROUNDING_WORLD_EFFECT', 'DUPLICATE_OR_WRONG_WITNESS')
        used_attempts.add(w['attempt_id']);used_native.add(r['native_receipt_hash'])
        require(renewal['witness_sha256']==digest(w) and renewal['attempt_id']==w['attempt_id'] and
                renewal['before_head']==w['before_head'] and renewal['source']==w['source'] and
                renewal['epoch']==w['epoch'] and same(renewal['history_after'],r['history']) and
                same(renewal['goal'],w['goal']) and renewal['remaining_path']==decision['actions'][1:], 'EXACT_RENEWAL_CAUSAL_RECORD')
        from .observation_grounding import predict,raw_id
        prediction=predict(m['certificate']['proposal'],current['M'][-1]['history'],[r['action']['id']])
        actual_pass=(prediction['outcomes'] is not None and prediction['outcomes'][0]==[raw_id(w['raw']),w['goal']])
        require(r['prediction_passed']==actual_pass and renewal['passed']==actual_pass,'REPLAY_PREDICTION_VERIFICATION')
        pending=dict(attempt_id=w['attempt_id'],action=actions[0],core_head=r['native_receipt_hash'],prepared=dict(
            binding=material['binding'],history=material['history'],learned=decision))
        expected=advance(current,w,pending,r['native_state'],r['history'],r['prediction_passed'])
        require(same(z,expected),'STATE_SUCCESSOR_REPLAY')
        current=z
    require(witnessed==set(relevant),'STATE_RENEWAL_COUNT')
    return current
