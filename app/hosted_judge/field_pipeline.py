"""Candidate field -> actual typed QPRE/views/classification, without authority.

These finite contracts implement an evaluated interface, not the unspecified
full-form T/P or a physical Merkabah. Mandatory native verification stays intact.
"""
from copy import deepcopy
import json
import math
import time


def prepare(preflight, result, *, budget=1, extra_candidate_fields=None):
    from operator_executor import load, digest
    from computational_interference_field import digest as field_digest
    from native_bridge import sha as plan_digest
    start=time.perf_counter_ns();cpu=time.process_time_ns()
    if type(budget) is not int or not 0<=budget<=12:raise ValueError('FIELD_AUDIT_BUDGET')
    if field_digest({k:v for k,v in result.items() if k!='result_sha256'})!=result['result_sha256']:raise ValueError('FIELD_RESULT_SEAL')
    if plan_digest(result['inputs']['plan'])!=preflight['plan_sha256']:raise ValueError('FIELD_PLAN_SUBSTITUTION')
    if result['inputs']['actual_mapping']!=preflight['plan_mapping']:raise ValueError('FIELD_MAPPING_SUBSTITUTION')
    m,q,k,f,E,pins=load()
    mapping=m.UniversalMap.model_validate_json(json.dumps(preflight['plan_mapping']['model']))
    nodes={n.node_id:n for n in mapping.vertices}
    source=next(n for n in mapping.vertices if n.kind is m.NodeKind.REALITY_OBJECT)
    numeric=result['numeric'];projection=result['projection'];ref='field:'+result['numeric_sha256']
    rows=projection['candidates'];sample={s['id']:s for s in numeric['samples']}
    extra_candidate_fields=extra_candidate_fields or {}
    if not isinstance(extra_candidate_fields,dict) or any(k not in sample for k in extra_candidate_fields):raise ValueError('FIELD_EXTRA_CANDIDATE_ID')
    for values in extra_candidate_fields.values():
        if not isinstance(values,list) or len(values)>4 or any(not isinstance(v,tuple) or len(v)!=2 or any(not isinstance(t,str) or not 1<=len(t)<=512 for t in v) for v in values):raise ValueError('FIELD_EXTRA_CANDIDATE_BOUND')
    possibilities=[];classes=[]
    for row in rows:
        s=sample[row['id']]
        energy=s['energy'];cross=s['interference']
        label='ZERO' if energy<=1e-24 else 'REINFORCING' if cross>1e-12 else 'CANCELLING' if cross< -1e-12 else 'ORTHOGONAL_OR_SINGLE'
        classes.append({'id':row['id'],'class':label,'energy':energy,'interference':cross})
        # Field-derived priorities are possibilities, never truth/confidence.
        if not row['eligible']:continue
        uncertainty=q.StructuredUncertainty(unknown=('Audit outcome not yet observed',),assumptions=('Dimensionless field candidate; priority is not probability or answer truth',))
        realization=q.build_candidate_realization(source_state_hash=preflight['checkpoint_sha256'],frame_hash=preflight['question_sha256'],
            candidate_state=tuple(q.CandidateStateField(name=name,possible_value=str(value)) for name,value in
                [('node_id',row['id']),('field_priority',row['field_priority']),('field_class',label),('audit_budget',budget)]+extra_candidate_fields.get(row['id'],[])),
            transformations=(q.TransformationStep(operation='candidate-field-to-optional-audit-priority',input_reference=ref,possible_output='Audit node '+row['id']),),
            predicted_consequences=(q.build_predicted_consequence(summary='Optional node-binding audit for '+row['id']+'; outcome unknown',provenance_references=(ref,)),),
            reversibility=q.Reversibility.REVERSIBLE,cost_units=1,risk_score=0,provenance_references=(ref,))
        possibilities.append(q.build_qpre_candidate(source_state_hash=preflight['checkpoint_sha256'],frame_hash=preflight['question_sha256'],
            assumptions=uncertainty.assumptions,uncertainty=uncertainty,realization=realization,provenance_references=(ref,)))
    render=None
    if possibilities:
        render=q.render_qpre(q.build_possibility_field(source_state_hash=preflight['checkpoint_sha256'],frame_hash=preflight['question_sha256'],candidates=possibilities))
    # Both views contain actually calculated source components, not prompts.
    component_rank=sorted(sample,key=lambda ident:(-sum(v*v for term in sample[ident]['components'] for v in term),ident))
    representations=[('resultant-field',json.dumps({'ranking':projection['ranking'],'energies':{i:s['energy'] for i,s in sample.items()}},sort_keys=True)),
                     ('source-components',json.dumps({'ranking':component_rank,'interference':{i:s['interference'] for i,s in sample.items()}},sort_keys=True))]
    views=tuple(m.create_perspective_view(source,perspective_key=key,representation=value,epistemic_status=E.SYMBOLIC) for key,value in representations)
    invariant=m.extract_common_denominator(source,views)
    terminals=tuple(m.create_periodic_terminal(nodes[row['mapped_node_id']],label=row['id']+':'+c['class'],grounding=m.PeriodicGrounding.SYMBOLIC,epistemic_status=E.SYMBOLIC)
                    for row,c in zip(rows,classes))
    dimension=m.create_periodic_dimension(name='candidate-field-interference',property_name='Numerical squared-norm/interference thresholds; no physical grounding',terminals=terminals)
    expanded=m.create_universal_map(vertices=mapping.vertices,relations=mapping.relations,hyperedges=mapping.hyperedges,
        dimensions=(*mapping.dimensions,dimension),scales=mapping.scales,perspectives=(*mapping.perspectives,*views),
        flower_lineage=mapping.flower_lineage,invariants=(*mapping.invariants,invariant),inversions=mapping.inversions)
    selected=projection['ranking'][:budget]
    if any(i not in preflight['admitted_ids'] for i in selected):raise ValueError('FIELD_SELECTION_NOT_ADMITTED')
    roundtrip=m.UniversalMap.model_validate_json(expanded.model_dump_json())==expanded
    if render is not None:roundtrip=roundtrip and q.QPRERender.model_validate_json(render.model_dump_json())==render
    if not roundtrip:raise ValueError('FIELD_TYPED_ROUNDTRIP')
    stages=[{'operator':name,'status':status,'scope':scope} for name,status,scope in [
        ('F_FoL / scoped substrate mapping','ACTUAL_EXECUTION','Existing typed terminals/dependencies/Flower lineage bound exactly; full substrate semantics unspecified'),
        ('Relational embedding candidate','ACTUAL_EXECUTION','Explicit graph-feature coordinates and sources; not canonical Flower geometry'),
        ('K_Merkabah candidate','ACTUAL_EXECUTION','Bounded stationary and moving sources, numerical vector field and source interaction'),
        ('T candidate','ACTUAL_EXECUTION','Field squared norm transforms optional audit priorities'),
        ('Q_QPRE','ACTUAL_EXECUTION' if render is not None else 'JUSTIFIED_IDENTITY','Existing finite possibility render; no eligible node means no candidate'),
        ('S','ACTUAL_EXECUTION','Two numerical-data perspectives and exact common provenance invariant'),
        ('Classification candidate','ACTUAL_EXECUTION','Documented interference thresholds in existing SYMBOLIC periodic dimension'),
        ('Pi_B host admission','ACTUAL_EXECUTION','HOST preflight admission, dependencies and optional audit budget; full Master Boundary not realized'),
        ('Full-form T / P / physical coupling','UNAVAILABLE','Canonical numerical semantics unspecified; FULL_SE6 is not executed')]]
    material={'schema':'se6-v9-field-pipeline-v1','field_result_sha256':result['result_sha256'],'selected_ids':selected,
        'ranking':projection['ranking'],'classification':classes,'stages':stages,'typed_roundtrip_verified':roundtrip,
        'qpre':render.model_dump(mode='json') if render is not None else None,'mapping':expanded.model_dump(mode='json'),
        'mirror_comparison':{'resultant_ranking':projection['ranking'],'component_ranking':component_rank,
            'same_source_and_provenance':True,'semantically_equivalent':False},
        'budget':budget,'authority_effect':'NONE','source_pins':pins,
        'resources':{'wall_ns':time.perf_counter_ns()-start,'cpu_ns':time.process_time_ns()-cpu,'provider_calls':0,'local_monetary_usd':None}}
    return {**material,'pipeline_sha256':digest(material)}


def finish(pipeline, result, out, replay_passed, admitted_ids):
    from operator_executor import digest
    from relational_field_realization import finish_field
    if digest({k:v for k,v in pipeline.items() if k!='pipeline_sha256'})!=pipeline['pipeline_sha256']:raise ValueError('PIPELINE_SEAL')
    if pipeline['field_result_sha256']!=result['result_sha256']:raise ValueError('PIPELINE_FIELD_SUBSTITUTION')
    if type(replay_passed) is not bool:raise ValueError('REPLAY_BOOLEAN')
    actual={n['id']:n for n in out['nodes']};receipts={r['receipt_hash'] for r in out['receipts']};audits=[]
    for ident in pipeline['selected_ids']:
        n=actual[ident];hashes=(n.get('result') or {}).get('receipt_hashes',[])
        passed=replay_passed and ident in admitted_ids and n['status']=='COMPLETE' and all(h in receipts for h in hashes)
        audits.append({'id':ident,'passed':passed})
    cp=finish_field(result,audits)
    eligible={r['id']:r['eligible'] for r in result['projection']['candidates']}
    executed=[n['id'] for n in out['nodes'] if n['status']=='COMPLETE']
    # Only verified actual native evidence enters native memory; the candidate
    # feedback is a separate record of host observations, never a new fact.
    return {'audits':audits,'checkpoint':cp,'native_replay_passed':replay_passed,
        'actual_completed_ids':executed,'selected_candidate_eligible':all(eligible[i] for i in pipeline['selected_ids']),
        'mandatory_verification_skipped':False,'native_truth_modified':False,'authority_effect':'NONE',
        'stages':[{'operator':'VerifyAssimilate','status':'ACTUAL_EXECUTION' if replay_passed else 'BLOCKED','scope':'Existing independent native journal/certificate replay; supplied premises remain conditional'},
            {'operator':'Next candidate field state','status':'ACTUAL_EXECUTION','scope':'Bounded separate field checkpoint and host-audit feedback; persisted by existing session journal'}]}


def public(result,pipeline,feedback):
    numeric=deepcopy(result['numeric'])
    for key in ('input_sha256','prior_state_sha256'):numeric.pop(key,None)
    if numeric.get('state_rebase'):numeric['state_rebase'].pop('old_input_sha256',None)
    for row in numeric['G0']:row.pop('mapped_node_id',None)
    projection=deepcopy(result['projection'])
    for row in projection['candidates']:row.pop('mapped_node_id',None)
    return {'schema':result['schema'],'status':result['status'],'units':result['units'],
        'numeric':numeric,'projection':projection,
        'classification':pipeline['classification'],'selected_extra_audits':feedback['audits'],
        'next_forces':feedback['checkpoint']['forces'],'next_step':feedback['checkpoint']['step'],
        'typed_roundtrip_verified':pipeline['typed_roundtrip_verified'],
        'qpre':{'rendered':pipeline['qpre'] is not None,'candidate_count':sum(r['eligible'] for r in result['projection']['candidates']),
            'actual':False,'authority':False},'mirror_comparison':pipeline['mirror_comparison'],
        'stages':pipeline['stages']+feedback['stages'],'resources':pipeline['resources'],
        'full_se6_executed':False,'native_truth_modified':False,'mandatory_verification_skipped':False,
        'scope':result['scope']+'; QPRE/views/classification are actual finite native contracts; full-form transforms remain unspecified.'}
