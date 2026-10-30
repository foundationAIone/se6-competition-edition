"""Explicit candidate 3D field -> existing finite native contracts, no truth power."""
from copy import deepcopy
import time
from . import field_pipeline
from .canonical_bridge import digest


def prepare(pre, plan, prior=None, *, enabled=True, budget=1, navigation_prior=None, parameters=None):
    from toroidal_field_realization import sources_from_plan, realize_toroidal
    from relational_field_realization import graph
    from computational_interference_field import digest as legacy_digest
    from .toroidal_field_oracle import verify_result
    from field_navigation import environment,navigate
    wall=time.perf_counter_ns();cpu=time.process_time_ns()
    # Reuse the actual typed plan validator, including dependency/source spans.
    rows, lineage=graph(plan,pre['plan_mapping'])
    bound=sources_from_plan(plan,pre['plan_mapping'])
    env=environment(pre['plan_mapping'],plan,pre['admitted_ids'])
    bound['sample_points']=deepcopy(env['sample_points'])
    result=realize_toroidal(bound['sources'],prior_state=prior,
        sample_points=bound['sample_points'],enabled=enabled,parameters=parameters)
    oracle=verify_result(result)
    if oracle.get('verified') is not True:raise ValueError('TOROIDAL_NUMERICAL_REPLAY')
    samples={s['id']:s for s in result['numeric']['samples']}
    priorities={s['id']:s['field_priority'] for s in result['projection']['candidates']}
    if set(samples)!={r['id'] for r in rows} or set(priorities)!=set(samples):
        raise ValueError('TOROIDAL_NODE_BINDING')
    navigation=navigate(env,navigation_prior,result,
        {'goal_ids':pre['admitted_ids'],'budget':4,'audit_budget':budget},
        mode='field' if enabled else 'ordinary')
    from .navigation_oracle import verify_navigation
    navigation_oracle=verify_navigation(env,navigation,navigation_prior,result,plan,pre['plan_mapping'])
    # Typed adapter of actual 3D components; no reconstructed answer or labels.
    # Existing QPRE/Mapper rendering stays authoritative for its finite schema.
    nav_weights={r['target']:r['effective_score'] for c in navigation['choices'] for r in c['reachable_choices']}
    candidate_rows=[{'id':r['id'],'mapped_node_id':r['mapped_node_id'],
        'eligible':r['eligible'],'field_priority':nav_weights.get(r['id'],0.)} for r in rows]
    ranking=navigation['selected_ids']
    numeric_samples=[{'id':s['id'],'energy':s['energy'],
        'components':[s['toroidal'],s['poloidal']],
        'interference':2*sum(a*b for a,b in zip(s['toroidal'],s['poloidal']))}
        for s in result['numeric']['samples']]
    adapted={'numeric':{'samples':numeric_samples},'numeric_sha256':digest(result['numeric']),
        'inputs':{'plan':plan,'actual_mapping':pre['plan_mapping']},
        'projection':{'candidates':candidate_rows,'ranking':ranking}}
    adapted['result_sha256']=legacy_digest(adapted)
    extras={r['id']:[('navigation_path',' -> '.join(navigation['trajectory'])),('navigation_reason',navigation['reason'])] for r in candidate_rows if r['id'] in ranking}
    typed=field_pipeline.prepare(pre,adapted,budget=budget,extra_candidate_fields=extras)
    for stage in typed['stages']:
        if stage['operator']=='K_Merkabah candidate':
            stage['scope']='Actual centered tetrahedra, signed moving sources and candidate solenoidal 3D toroidal/poloidal field; no physical or canonical coupling equivalence'
        elif stage['operator']=='Relational embedding candidate':
            stage['scope']='Actual typed Flower relationships plus separate candidate19-circle hex geometry; exact terminal bindings and admitted paths'
        elif stage['operator']=='T candidate':
            stage['scope']='Measured3D field alignment and bounded energy potential choose a mapped relationship trajectory and its eligible optional audit'
    # Editing scope changes this separate pipeline receipt; retain its seal.
    typed['pipeline_sha256']=digest({k:v for k,v in typed.items() if k!='pipeline_sha256'})
    material={'schema':'se6-v10-toroidal-pipeline-v1','result':result,'typed':typed,
        'plan_sha256':pre['plan_sha256'],'question_sha256':pre['question_sha256'],
        'bound_mapping':bound,'bound_mapping_model':deepcopy(pre['plan_mapping']['model']),'flower_lineage':lineage,'oracle':oracle,
        'environment':env,'navigation':navigation,'navigation_oracle':navigation_oracle,'navigation_prior':deepcopy(navigation_prior),'plan':deepcopy(plan),'actual_plan_mapping':deepcopy(pre['plan_mapping']),
        'mode':'enabled' if enabled else 'neutralized','authority_effect':'NONE',
        'resources':{'wall_ns':time.perf_counter_ns()-wall,'cpu_ns':time.process_time_ns()-cpu,
            'provider_calls':0,'local_monetary_usd':None}}
    return {**material,'prepared_sha256':digest(material)}


def finish(prepared,out,replay_passed,admitted_ids):
    from toroidal_field_realization import finish_toroidal
    from .toroidal_field_oracle import verify_result
    if digest({k:v for k,v in prepared.items() if k!='prepared_sha256'})!=prepared['prepared_sha256']:
        raise ValueError('TOROIDAL_PIPELINE_SEAL')
    if type(replay_passed) is not bool:raise ValueError('TOROIDAL_NATIVE_REPLAY_BOOLEAN')
    verify_result(prepared['result'])
    from .navigation_oracle import verify_navigation
    verify_navigation(prepared['environment'],prepared['navigation'],prepared['navigation_prior'],prepared['result'],prepared['plan'],prepared['actual_plan_mapping'])
    rows={r['id']:r for r in out['nodes']};receipt_hashes={r['receipt_hash'] for r in out['receipts']}
    audits=[]
    for ident in prepared['typed']['selected_ids']:
        node=rows[ident];values=(node.get('result') or {}).get('receipt_hashes',[])
        passed=replay_passed and ident in admitted_ids and node['status']=='COMPLETE' and all(h in receipt_hashes for h in values)
        audits.append({'id':ident,'passed':passed})
    cp=finish_toroidal(prepared['result'],audits)
    from field_navigation import finish_navigation
    nav=prepared['navigation'];env=prepared['environment']
    verified_ids=[r['id'] for r in out['nodes'] if r['status']=='COMPLETE' and r['id'] in admitted_ids] if replay_passed else []
    path_nodes=[i for i in nav['trajectory'] if i!='source']
    if all(i in verified_ids for i in path_nodes):
        navigation_feedback=finish_navigation(env,nav,verified_ids)
        # Execute existing native recursive Flower contracts along actual edges.
        from operator_executor import load
        mapper,_,_,_,_,_=load()
        mapping=mapper.UniversalMap.model_validate_json(__import__('json').dumps(prepared['bound_mapping_model']))
        aliases={r['id']:next(v for v in mapping.vertices if v.node_id==r['mapped_node_id']) for r in env['vertices']}
        flower=mapper.create_flower_center(aliases[nav['start']],terminals=tuple(v for k,v in aliases.items() if k!=nav['start']))
        centers=[flower]
        for ident in nav['trajectory'][1:]:
            flower=mapper.recenter_flower(flower,aliases[ident],terminals=tuple(v for k,v in aliases.items() if k!=ident));centers.append(flower)
        roundtrip=all(mapper.FlowerCenter.model_validate_json(f.model_dump_json())==f for f in centers)
        if not roundtrip:raise ValueError('NAVIGATION_TYPED_RECENTER')
        navigation_feedback['native_flower_centers']=[f.model_dump(mode='json') for f in centers]
        navigation_feedback['typed_recenter_roundtrip_verified']=roundtrip
        navigation_feedback['verified_ids']=verified_ids
    else:
        navigation_feedback={'status':'BLOCKED_UNVERIFIED_PATH','checkpoint':prepared['navigation_prior'],
            'relationships':[],'verified_ids':[],'native_flower_centers':[],'typed_recenter_roundtrip_verified':False,
            'scope':'Candidate path remains unassimilated because native proof/completed-node binding did not justify every traversed terminal'}
    return {'checkpoint':cp,'audits':audits,'native_replay_passed':replay_passed,
        'navigation':navigation_feedback,
        'mandatory_verification_skipped':False,'native_truth_modified':False,
        'scope':'Independent numeric replay and mandatory native proof verification precede bounded candidate-state feedback. No physical field or cognitive improvement claim.'}


def public(prepared,feedback):
    result=prepared['result'];numeric=deepcopy(result['numeric'])
    # Public plot uses a stated decimation of privately retained numeric lines.
    for line in numeric.get('lines',{}).values():
        if isinstance(line,dict) and isinstance(line.get('points'),list):
            pts=line['points'];line['recorded_points']=len(pts)
            stride=max(1,(len(pts)+24)//25)
            line['points']=pts[::stride]
            if pts and line['points'][-1]!=pts[-1]:line['points'].append(pts[-1])
            line['display']='Downsampled recorded trajectory; full private numerical receipt retained'
    typed=prepared['typed']
    env=prepared['environment'];nav=prepared['navigation'];nf=feedback['navigation']
    navigation={'status':nf['status'],'start':nav['start'],'candidate_trajectory':nav['trajectory'],
        'actual_trajectory':nav['trajectory'] if nf['status']!='BLOCKED_UNVERIFIED_PATH' else [],
        'actual_relationships':[{k:r[k] for k in ('from','to','kind','direction')} for r in nf['relationships']],
        'vertices':[{**{k:r[k] for k in ('id','position','admitted','circle_index')},'verification':'HOST_SOURCE_REFERENCE' if r['id']=='source' else 'COMPLETED_CONDITIONAL_PROOF' if r['id'] in nf['verified_ids'] else 'NOT_COMPLETED_OR_NOT_VERIFIED'} for r in env['vertices']],
        'circles':env['circles'],'choices':[{ 'from':c['from'],'reachable_choices':[{k:r[k] for k in ('target','alignment','energy_potential','field_score','effective_score')} for r in c['reachable_choices']]} for c in nav['choices']],
        'independent_replay':prepared['navigation_oracle'],'mode':nav['mode'],'reason':nav['reason'],'rotations':nav['rotations'],
        'native_flower_recenter_count':max(0,len(nf['native_flower_centers'])-1),
        'typed_recenter_roundtrip_verified':nf['typed_recenter_roundtrip_verified'],
        'state_rebase':{k:v for k,v in (nav['state_rebase'] or {}).items() if k!='prior_environment_sha256'},
        'next_step':(nf['checkpoint'] or {}).get('step'),'next_position':(nf['checkpoint'] or {}).get('position'),
        'scope':env['scope']+'; reverse arcs inspect a recorded relation without reversing dependency causality; no new fact is created by geometric movement'}
    return {'schema':result['schema'],'status':result['status'],'numeric':numeric,
        'navigation':navigation,
        'scope':'Candidate computational constitutive toroidal law; vertex polarities/coupling are engineering conventions awaiting source/owner confirmation. Moving point-source diagnostics do not establish a physical torus field.',
        'mode':prepared['mode'],'projection':result['projection'],'ranking':typed['ranking'],
        'selected_extra_audits':feedback['audits'],'next_step':feedback['checkpoint']['step'],
        'next_amplitudes':feedback['checkpoint'].get('amplitudes'),
        'typed_roundtrip_verified':typed['typed_roundtrip_verified'],
        'qpre':{'rendered':typed['qpre'] is not None,'actual':False,'authority':False},
        'mirror_comparison':typed['mirror_comparison'],'stages':typed['stages']+[{'operator':'Field-guided mapped relationship navigation','status':nf['status'],'scope':'Measured field selects actual admitted relationship inspections; native typed Flower recenter and independently replayed native consequences justify retained state'}],
        'independent_numeric_replay':prepared['oracle'],'resources':prepared['resources'],
        'mandatory_verification_skipped':False,'native_truth_modified':False,
        'full_se6_executed':False,'physical_EM_established':False}
