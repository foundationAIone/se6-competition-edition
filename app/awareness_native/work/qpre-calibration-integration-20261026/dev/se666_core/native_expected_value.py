"""Exact-value observation after actual Native Boundary, never new authority."""
from copy import deepcopy
from dataclasses import replace
from fractions import Fraction
import json

from . import grounded_qpre_expected_value_v1 as math
from .qpre_calibration_v1 import QPREProbabilityRender
from .observation_grounding import digest, require

VERSION='se6-native-exact-value-observer-v1'


def decode_policy(wire):
    require(type(wire) is dict and set(wire)=={'version','source_state_hash','frame_hash',
        'probability_render_id','model_version','calibration_state_hash','declaration_reference',
        'unit_reference','values','policy_sha256'},'NATIVE_VALUE_POLICY_FIELDS')
    require(wire['version']==math.VERSION,'NATIVE_VALUE_POLICY_VERSION')
    def scalar(row):
        require(type(row) is list and len(row)==2 and all(type(v) is int for v in row) and row[1]>0,
            'NATIVE_VALUE_EXACT_WIRE_RATIONAL')
        return Fraction(*row)
    def band(row):
        require(type(row) is dict and set(row)=={'lo','point','hi'},'NATIVE_VALUE_WIRE_INTERVAL')
        return math.ValueInterval(scalar(row['lo']),scalar(row['point']),scalar(row['hi']))
    require(type(wire['values']) is list and 0<len(wire['values'])<=64,'NATIVE_VALUE_COMPLETE_WIRE_POLICY')
    values=[]
    for row in wire['values']:
        require(type(row) is dict and set(row)=={'candidate_id','outcomes','outside_field','penalty'},'NATIVE_VALUE_CANDIDATE_FIELDS')
        require(type(row['outcomes']) is list and all(type(r) is list and len(r)==2 for r in row['outcomes']),
            'NATIVE_VALUE_WIRE_OUTCOMES')
        values.append(math.CandidateValue(row['candidate_id'],tuple((k,band(v)) for k,v in row['outcomes']),
            None if row['outside_field'] is None else band(row['outside_field']),band(row['penalty'])))
    policy=math.ValuePolicy(**{k:wire[k] for k in ('source_state_hash','frame_hash','probability_render_id',
        'model_version','calibration_state_hash','declaration_reference','unit_reference','policy_sha256')},values=tuple(values))
    policy.validate()
    return policy


def validate_config(config):
    require(type(config) is dict and set(config)=={'version','policy'} and config['version']==VERSION,
        'NATIVE_VALUE_CONFIG')
    if config['policy'] is not None:decode_policy(config['policy'])


def policy_wire(policy):
    policy.validate()
    return {**policy.material(),'policy_sha256':policy.policy_sha256}


def source_context(decision, *, state, core, binding, actions, boundary, graph):
    """Shared real Native render/Boundary input for scalar and typed observers."""
    audit=decision.get('selection',{})
    # A preexisting refusal is preserved even if it precedes a probability field.
    probability=audit.get('probability_learning',{}).get('render')
    if probability is None:
        require(decision['status']=='UNKNOWN','NATIVE_VALUE_ACTUAL_RENDER_REQUIRED')
        return None
    render=QPREProbabilityRender.model_validate_json(json.dumps(probability))
    require(render.base_render.possibility_field.source_state_hash==binding['entity_state'] and
        render.base_render.possibility_field.model_dump(mode='json')==audit['possibility_field'],
        'NATIVE_VALUE_ACTUAL_NATIVE_RENDER_BINDING')
    eligible=[];checks={}
    if decision['status']=='GOAL_PATH_PREDICTED':
        # All source-projected candidates already passed actual resource/conduct
        # checks. Run the existing evidence-grounded veto for EACH candidate;
        # no scalar value can rehabilitate a contradicted non-winning path.
        from .native_reflection_consequences import findings,apply_boundary
        nodes={n['node_id']:n for n in graph['vertices']}
        ids={s['candidate_id'] for s in audit['probability_learning']['scores']}
        for candidate in render.base_render.possibility_field.candidates:
            cid=candidate.candidate_id
            if cid not in ids:continue
            prediction=json.loads(nodes[candidate.provenance_references[0]]['description'])
            probe=dict(status='GOAL_PATH_PREDICTED',actions=prediction['continuation'],prediction=prediction,
                selection=deepcopy(audit))
            probe['selection']['selected_candidate_id']=cid
            if 'reflection_consequences' in boundary['selection_policy']:
                cfg=boundary['selection_policy']['reflection_consequences']
                probe['selection']['reflection_consequences']=findings(graph,probe['selection'],cid,cfg['evidence'],cfg)
                probe=apply_boundary(probe,state,core,binding,actions,boundary)
            allowed=probe['status']=='GOAL_PATH_PREDICTED'
            checks[cid]=dict(source_projection_eligible=True,reflection_boundary='RETAIN' if allowed else 'REFUSE')
            if allowed:eligible.append(cid)
    eligibility=dict(source_native_state=state.state_hash,binding=deepcopy(binding),
        source_projection_sha256=digest(audit['projection']),checks=checks,eligible_candidate_ids=sorted(eligible),
        preexisting_native_status=decision['status'],authority_effect='NONE')
    eligibility_sha=digest(eligibility)
    context=dict(binding=deepcopy(binding),probability_render_id=render.render_id,
        model_version=render.model_version,calibration_state_hash=render.calibration_state_hash,
        source_state_hash=render.base_render.source_state_hash,frame_hash=render.base_render.frame_hash,
        eligibility_sha256=eligibility_sha,eligible_candidate_ids=sorted(eligible))
    return render,audit,tuple(sorted(eligible)),eligibility,context


def observe(decision, *, state, core, authority, binding, actions, boundary, graph):
    policy=boundary.get('selection_policy',{})
    if 'native_typed_valuation' in policy:
        from .native_typed_valuation import observe_typed
        return observe_typed(decision,state=state,core=core,authority=authority,binding=binding,
            actions=actions,boundary=boundary,graph=graph)
    config=policy.get('native_expected_value')
    if config is None:return decision
    validate_config(config)
    actual=source_context(decision,state=state,core=core,binding=binding,actions=actions,boundary=boundary,graph=graph)
    if actual is None:
        decision['selection']['native_expected_value']=dict(version=VERSION,status='UNKNOWN',reason='PREEXISTING_BOUNDARY_NO_RENDER',
            authority_effect='NONE',world_effects=0)
        return decision
    render,audit,eligible,eligibility,context=actual
    eligibility_sha=context['eligibility_sha256']
    observation=dict(version=VERSION,status='UNKNOWN',reason='NO_INDEPENDENTLY_ADMITTED_VALUE_POLICY',
        context=context,eligibility=eligibility,authority_effect='NONE',world_effects=0,
        production_eligible=False,owner_equation_equivalence=False)
    supplied=config['policy'];verifier=getattr(authority,'authenticate_expected_value_policy',None)
    if supplied is not None and callable(verifier):
        policy=decode_policy(supplied)
        admitted=verifier(deepcopy(supplied),deepcopy(context))
        require(type(admitted) is dict and set(admitted)=={'policy_sha256','context_sha256','scope','admission_reference'} and
            admitted['policy_sha256']==policy.policy_sha256 and admitted['context_sha256']==digest(context) and
            admitted['scope'] in ('TEST_ONLY','OWNER_ADMITTED') and type(admitted['admission_reference']) is str and
            bool(admitted['admission_reference']),'NATIVE_VALUE_INDEPENDENT_POLICY_ADMISSION')
        result=math.evaluate_shadow(render=render,policy=policy,eligible_candidate_ids=tuple(sorted(eligible)),
            eligibility_provenance='native-boundary:'+eligibility_sha)
        observation.update(status=result['status'],reason=result['reason'],admission=admitted,calculation=result)
    observation['observation_sha256']=digest(observation)
    audit['native_expected_value']=observation
    if decision['status']=='UNKNOWN':return decision
    result=observation.get('calculation',{})
    if observation.get('admission',{}).get('scope')=='TEST_ONLY':
        return dict(status='UNKNOWN',actions=[],reason='EXPECTED_VALUE_TEST_POLICY_NONAUTHORIZING',selection=audit)
    if result.get('status')!='CERTIFIED_INTERVAL_LEADER':
        return dict(status='UNKNOWN',actions=[],reason='EXPECTED_VALUE_UNKNOWN_OR_ABSTAIN',selection=audit)
    if result['winner']!=audit['selected_candidate_id']:
        return dict(status='UNKNOWN',actions=[],reason='EXPECTED_VALUE_DIFFERS_FROM_EXISTING_SELECTION',selection=audit)
    # A leader only supports the already selected, independently eligible
    # action. The existing exact dispatcher remains the sole World authority.
    return decision
