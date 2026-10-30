"""Bounded private adapter over copied existing SHADOW operators, not full equation."""
import hashlib,json,sys,time
from pathlib import Path

ROOT=Path(__file__).resolve().parent
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
def load():
    pins=json.loads((ROOT/'source-pins.json').read_bytes())
    source=ROOT/'private_source/se666_core'
    for name,pin in pins.items():
        if hashlib.sha256((source/name).read_bytes()).hexdigest()!=pin:raise ValueError('SOURCE_PIN_MISMATCH')
    sys.dont_write_bytecode=True;sys.path.insert(0,str(ROOT/'private_source'))
    from se666_core import universal_mapper as m,qpre as q,merkabah_traversal as k,realization_frame as f
    from se666_core.epistemic_status import EpistemicStatus as E
    if any(Path(mod.__file__).parent.resolve()!=source.resolve() for mod in (m,q,k,f)):raise ValueError('SOURCE_NAMESPACE_MISMATCH')
    return m,q,k,f,E,pins

def execute(payload,*,readback=None):
    """readback(request) is host-injected; never accepted from untrusted JSON.

    Hook must return observed_value, source_state_hash and candidate_id. Checks
    only authenticate exact closed-host fixture result, not general world truth.
    """
    start=time.perf_counter_ns();cpu=time.process_time_ns();m,q,k,f,E,pins=load()
    if not isinstance(payload,dict) or set(payload)-{'observation','state_summary','candidates'}:raise ValueError('INPUT_FIELDS')
    text=payload['observation'];state_summary=payload.get('state_summary','Initial private fixture state')
    if not isinstance(text,str) or not text.strip() or len(text)>512:raise ValueError('OBSERVATION_BOUND')
    if not isinstance(state_summary,str) or not state_summary.strip() or len(state_summary)>512:raise ValueError('STATE_BOUND')
    inputs=payload['candidates']
    if not isinstance(inputs,list) or not 1<=len(inputs)<=8:raise ValueError('CANDIDATE_BOUND')
    ids=[]
    for c in inputs:
        if set(c)-{'id','value','benefit','cost','risk','uncertainty','irreversibility','source_state_hash','frame_hash','depends_on'}:raise ValueError('CANDIDATE_FIELDS')
        if any(not isinstance(c.get(t),str) or not c[t].strip() or len(c[t])>64 for t in ('id','value')):raise ValueError('CANDIDATE_TEXT')
        if any(type(c.get(t)) is not int or not 0<=c[t]<=100 for t in ('benefit','cost','risk','uncertainty','irreversibility')):raise ValueError('CANDIDATE_NUMERIC')
        if c['irreversibility']>3:raise ValueError('REVERSIBILITY_BOUND')
        if not isinstance(c.get('depends_on',[]),list) or any(not isinstance(t,str) for t in c.get('depends_on',[])):raise ValueError('DEPENDENCY_TYPE')
        ids.append(c['id'])
    if len(set(ids))!=len(ids):raise ValueError('DUPLICATE_CANDIDATE')
    if any(t not in ids for c in inputs for t in c.get('depends_on',[])):raise ValueError('DANGLING_MAPPER_TARGET')
    obs=f.create_source_observation(source_reference='fixture:public-input',summary=text,epistemic_status=E.REPORTED)
    x=f.create_realization_state(state_summary=state_summary,source_observations=(obs,))
    theta=f.create_realization_frame(x,frame_name='bounded-operator-frame',dimensions=('source','possibility'),representation_rules=('source is reported, not world truth',))
    reality=m.create_reality_object(label='source',description=text,source_observations=(obs,))
    nodes={c['id']:m.create_mapper_node(kind=m.NodeKind.TERMINAL,label=c['id'],description=c['value'],epistemic_status=E.SYMBOLIC) for c in inputs}
    relation=m.create_mapper_relation(kind=m.RelationKind.RELATES_TO,label='source-to-candidates',source_nodes=(reality,),target_nodes=tuple(nodes.values()),epistemic_status=E.SYMBOLIC)
    views=tuple(m.create_perspective_view(reality,perspective_key=p,representation=f'{p}: {text}') for p in ('owner','verifier'))
    flower=m.create_flower_center(reality,terminals=tuple(nodes.values()))
    dimension=m.create_periodic_dimension(name='candidate-symbols',property_name='typed alternatives',terminals=tuple(m.create_periodic_terminal(n,label=i,grounding=m.PeriodicGrounding.SYMBOLIC,epistemic_status=E.SYMBOLIC) for i,n in nodes.items()))
    mapping=m.create_universal_map(vertices=(reality,*nodes.values()),relations=(relation,),hyperedges=(m.create_mapper_hyperedge(relation),),dimensions=(dimension,),perspectives=views,flower_lineage=(flower,),invariants=(m.extract_common_denominator(reality,views),))
    ref='map:'+mapping.map_id;possibilities=[]
    for c in inputs:
        uncertainty=q.StructuredUncertainty(unknown=('Consequence not yet observed',),assumptions=('Closed deterministic host fixture only',))
        realization=q.build_candidate_realization(source_state_hash=c.get('source_state_hash',x.x_hash),frame_hash=c.get('frame_hash',theta.theta_hash),candidate_state=tuple(q.CandidateStateField(name=name,possible_value=str(value)) for name,value in [('fixture_value',c['value']),('caller_id',c['id']),('benefit',c['benefit']),('uncertainty_penalty',c['uncertainty'])]),transformations=(q.TransformationStep(operation='bounded-fixture-selection',input_reference=ref,possible_output=c['value']),),predicted_consequences=(q.build_predicted_consequence(summary=c['value'],provenance_references=(ref,)),),reversibility=[q.Reversibility.REVERSIBLE,q.Reversibility.PARTIALLY_REVERSIBLE,q.Reversibility.UNKNOWN,q.Reversibility.IRREVERSIBLE][c['irreversibility']],cost_units=c['cost'],risk_score=c['risk'],provenance_references=(ref,))
        possibilities.append(q.build_qpre_candidate(source_state_hash=x.x_hash,frame_hash=theta.theta_hash,assumptions=uncertainty.assumptions,uncertainty=uncertainty,realization=realization,provenance_references=(ref,)))
    field=q.build_possibility_field(source_state_hash=x.x_hash,frame_hash=theta.theta_hash,candidates=possibilities);render=q.render_qpre(field)
    scores=[{'id':c['id'],'net':c['benefit']-c['cost']-c['risk']-c['irreversibility']-c['uncertainty']} for c in inputs]
    chosen=min(inputs,key=lambda c:(-(c['benefit']-c['cost']-c['risk']-c['irreversibility']-c['uncertainty']),c['irreversibility'],c['risk'],c['cost'],possibilities[ids.index(c['id'])].candidate_id))
    selected=possibilities[ids.index(chosen['id'])]
    center=k.build_traversal_center(state_hash=x.x_hash,frame_hash=theta.theta_hash)
    terminal=k.build_traversal_terminal(source_center_id=center.center_id,references=(k.TraversalReference(kind=k.TraversalReferenceKind.MAPPED,reference_id=ref),k.TraversalReference(kind=k.TraversalReferenceKind.QPRE,reference_id='qpre:'+selected.candidate_id)),summary='Selected possibility; no actuality inferred')
    evidence=None;verified=False;observed=None;x1=x;theta1=theta
    if readback is not None:
        observed=readback({'candidate_id':chosen['id'],'expected_value':chosen['value'],'source_state_hash':x.x_hash})
        verified=isinstance(observed,dict) and set(observed)=={'candidate_id','observed_value','source_state_hash'} and observed['candidate_id']==chosen['id'] and observed['observed_value']==chosen['value'] and observed['source_state_hash']==x.x_hash
        if verified:
            o1=f.create_source_observation(source_reference='fixture:independent-readback',summary=chosen['value'],epistemic_status=E.DETERMINISTIC,evidence_references=('host:'+digest(observed),))
            x1=f.advance_realization_state(x,state_summary='Readback matched: '+chosen['value'],additional_observations=(o1,))
            theta1=f.create_realization_frame(x1,frame_name='verified-fixture-successor',dimensions=('source','possibility'),representation_rules=('Closed fixture only',))
            evidence=k.build_verified_consequence_assimilation(source_center_id=center.center_id,consequence_reference='host:'+digest(observed),verification_reference='verify:'+digest(observed),assimilation_reference='state:'+x1.x_hash,next_state_hash=x1.x_hash,next_frame_hash=theta1.theta_hash)
    traversal=k.traverse_merkabah(center=center,terminal=terminal,verified_assimilation=evidence)
    models={'mapping':mapping,'qpre':render,'traversal':traversal,'state':x1,'frame':theta1}
    dumps={name:model.model_dump(mode='json') for name,model in models.items()}
    replay=all(type(model).model_validate_json(json.dumps(dumps[name]))==model for name,model in models.items())
    return {'schema':'canonical-v7-bounded-operators-v1','scope':'Existing SHADOW typed operators; finite host utility not September integral; no production/world/model authority','selected':chosen['id'],'scores':scores,'readback_verified':verified,'models':dumps,'source_pins':pins,'typed_readback_verified':replay,'measurements':{'wall_ns':time.perf_counter_ns()-start,'cpu_ns':time.process_time_ns()-cpu,'provider_calls':0,'external_effects':0}}

def safe_execute(payload,**kwargs):
    try:return {'status':'COMPLETE','result':execute(payload,**kwargs)}
    except (ValueError,KeyError,TypeError) as e:return {'status':'REJECTED','error_type':type(e).__name__,'error_code':str(e).splitlines()[0][:120]}

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    result=safe_execute(json.loads(Path(a.input).read_bytes()))
    with Path(a.output).open('x',encoding='utf8') as out:json.dump(result,out,ensure_ascii=False,indent=2)
