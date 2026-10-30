"""Source-pinned failure mapping and candidate-field dependency inspection.

Consumes already independently admitted capture facts, never a scoring oracle.
This is a diagnostic operation over local evidence; neither geometry nor
reported model assertions acquire authority by being mapped.
"""
from copy import deepcopy
import hashlib,json,time

def encode(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def digest(v):return hashlib.sha256(encode(v)).hexdigest()

def build_map(row,diagnostic,contract_sha256):
    if row.get('official_status') not in ('PASS','FAIL','UNASSESSABLE'):
        raise ValueError('Admitted frozen result required')
    for k in ('request_sha256','provider_response_sha256'):
        if len(row[k])!=64:raise ValueError('Actual capture reference required')
    question=row['public_question'];answer=row['actual_answer_text']
    # Each node represents an observed input or a separately checked fact. The
    # labels describe dependencies, not an instruction to trust its content.
    entries=[
        ('input',{'question':question,'question_sha256':hashlib.sha256(question.encode()).hexdigest()},[]),
        ('contract',{'contract_sha256':contract_sha256,'task_type':row['task_id']},['input']),
        ('request',{'request_sha256':row['request_sha256']},['input','contract']),
        ('submission',{'captured_text':answer,'provider_response_sha256':row['provider_response_sha256']},['request']),
        ('mathematics',diagnostic['mathematical_observation'],['input']),
        ('scope',diagnostic['scope_observation'],['submission','contract']),
        ('mirror',{'semantic':diagnostic['semantic_correct'],'schema':diagnostic['schema_compliant'],'official_status_preserved':row['official_status']},['submission','mathematics','scope']),
        ('cause',{'confirmed':diagnostic['confirmed_causes'],'model_internal_cause':'UNOBSERVABLE'},['mirror','request']),
    ]
    nodes=[{'id':ident,'route':'RELATIONAL','connected':True,'input':encode(data).decode(),
        'source_spans':[[0,len(question)]],'depends_on':deps,
        'purpose':'LOCAL_CAPTURE_DIAGNOSTIC_REFERENCE_NO_WORLD_AUTHORITY'} for ident,data,deps in entries]
    return {'schema':'se6-v11-diagnostic-dependency-plan-v1','nodes':nodes,
        'original_question':question,'question_sha256':hashlib.sha256(question.encode()).hexdigest(),
        'capture_id':row['task_id']+'-'+row['phase_id']+'-'+row['condition'],
        'scope':'Typed references and local independently checked conclusions; not new task/model answers or historical regrading'}

def inspect_maps(bundle,manifest,pin,items,*,mode='field'):
    """Run in one fresh bounded offline interpreter per matched mode.

    The real V11 mapping, centered source-coupled field, QPRE/mirror rendering
    and navigation are reused. Independent numeric/path verifiers execute in
    the existing prepare function. All items share equal map/field budgets.
    """
    from .native_adapter import validate_bundle
    from .canonical_bridge import load_bridge
    from .toroidal_pipeline import prepare
    if mode not in ('field','ordinary'):raise ValueError('Matched diagnostic mode')
    if not isinstance(items,list) or not 1<=len(items)<=16:raise ValueError('Diagnostic bound')
    validate_bundle(bundle,manifest,pin)
    import socket
    def denied(*a,**k):raise ValueError('Offline diagnosis has no network authority')
    socket.socket.connect=denied;socket.create_connection=denied;socket.getaddrinfo=denied
    preflight,_,loader=load_bridge(bundle)
    records=[];wall=time.perf_counter();cpu=time.process_time()
    for item in items:
        plan=build_map(item['row'],item['diagnostic'],item['contract_sha256'])
        pre=preflight(plan['original_question'],plan,None)
        initial=prepare(pre,plan,enabled=mode=='field',budget=1)
        # Explicit diagnostic starting reference, not a fabricated previous
        # movement or assimilated physical position. Both arms start at the
        # same actual failed submission and inspect recorded dependencies.
        start=deepcopy(initial['navigation']['proposed_checkpoint'])
        vertex=next(v for v in initial['environment']['vertices'] if v['id']=='submission')
        start.update(step=0,position='submission',mapped_node_id=vertex['mapped_node_id'],
            orientation=[0.,0.,0.],last_trajectory=['submission'],previous_state_sha256=None)
        start['state_sha256']=digest({k:v for k,v in start.items() if k!='state_sha256'})
        tor=prepare(pre,plan,enabled=mode=='field',budget=1,navigation_prior=start)
        nav=tor['navigation'];env=tor['environment']
        # A field selects which evidence is inspected first. The actual
        # semantic/schema checks remain mandatory independently of its path.
        traversed=nav['trajectory'][1:]
        discovered=[n['id'] for n in plan['nodes'] if n['id'] in traversed]
        from operator_executor import load
        mapper,_,_,_,_,_=load()
        mapping=mapper.UniversalMap.model_validate_json(json.dumps(pre['plan_mapping']['model']))
        vertices={v.node_id:v for v in mapping.vertices}
        aliases={v['id']:vertices[v['mapped_node_id']] for v in env['vertices']}
        flower=mapper.create_flower_center(aliases[nav['start']],terminals=tuple(v for k,v in aliases.items() if k!=nav['start']))
        centers=[flower]
        for ident in nav['trajectory'][1:]:
            flower=mapper.recenter_flower(flower,aliases[ident],terminals=tuple(v for k,v in aliases.items() if k!=ident));centers.append(flower)
        assert all(mapper.FlowerCenter.model_validate_json(f.model_dump_json())==f for f in centers)
        records.append({'capture_id':plan['capture_id'],'plan':plan,'typed_mapping':pre['plan_mapping'],
            'field':tor['result'],'navigation':nav,'numeric_verification':tor['oracle'],
            'navigation_verification':tor['navigation_oracle'],'typed_operator_outputs':tor['typed'],
            'native_flower_centers':[f.model_dump(mode='json') for f in centers],
            'starting_reference_scope':'Explicit HOST failed-submission reference, not an inferred past trajectory',
            'inspected_reference_ids':discovered,'diagnostic':deepcopy(item['diagnostic']),
            'mandatory_checks_used_field_as_truth':False,'provider_calls':0,
            'resources':{'initialization':initial['resources'],'inspection':tor['resources'],'field_preparations':2},'scope':'Executed computational candidate-field inspection; local evidence mirror establishes fault truth separately'})
    return {'schema':'se6-v11-failure-mapping-candidate-execution-v1','mode':mode,'records':records,
        'compiled_operator_sources':loader.loaded,'resources':{'wall_seconds':time.perf_counter()-wall,
            'cpu_seconds':time.process_time()-cpu,'provider_calls':0,'local_monetary_usd':None},
        'no_new_model_answers':True,'historical_grades_changed':False}

def compare_inspections(field,ordinary):
    if len(field['records'])!=len(ordinary['records']):raise ValueError('Matched record count')
    result=[]
    for c,d in zip(field['records'],ordinary['records']):
        if c['plan']!=d['plan'] or c['diagnostic']!=d['diagnostic']:raise ValueError('Matched evidence inputs')
        if c['field']['numeric_sha256']!=d['field']['numeric_sha256']:raise ValueError('Equal field computation')
        result.append({'capture_id':c['capture_id'],'full_trajectory':c['navigation']['trajectory'],
            'neutralized_trajectory':d['navigation']['trajectory'],
            'changed_path':c['navigation']['trajectory']!=d['navigation']['trajectory'],
            'changed_selected_evidence':c['inspected_reference_ids']!=d['inspected_reference_ids'],
            'changed_fault_conclusion':False,'semantic_verification_mandatory_both':True,
            'field_causal_scope':'Candidate policy changes inspections; no improved fault truth/model cognition claimed'})
    return {'records':result,'changed_path_count':sum(x['changed_path'] for x in result),
        'improved_correctness_count':0,'scope':'Matched actual-field/neutralized inspection, same data/verification/field cost'}
