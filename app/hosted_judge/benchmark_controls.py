"""Offline candidate comparison controls, not generated Nemotron answers.

B reuses the same supplied mathematical tools and their journal verifier without
canonical governance; it is a competent deterministic tool control, not a new
general agent. D neutralizes field influence while computing the same fields.
No hidden answer keys, provider calls, production operations or arbitrary tools.
"""
from copy import deepcopy
import hashlib,json,multiprocessing,re,time
from pathlib import Path

SCHEMA='se6-v11-offline-benchmark-controls-v1'
CONDITIONS={'A','B','C','D'}
TASK_KEYS={'id','category','phases','max_actions','automatic_renewal'}
PHASE_KEYS={'id','public_question','authorized'}

def encode(v):
    return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def sha(v):return hashlib.sha256(encode(v)).hexdigest()
def valid(task,condition):
    if condition not in CONDITIONS:raise ValueError('UNKNOWN_CONDITION')
    if not isinstance(task,dict) or set(task)-TASK_KEYS:raise ValueError('PUBLIC_TASK_KEYS')
    for key in ('id','category'):
        if not isinstance(task.get(key),str) or not re.fullmatch('[A-Za-z0-9_-]{1,64}',task[key]):raise ValueError('TASK_IDENTITY')
    phases=task.get('phases')
    if not isinstance(phases,list) or not 1<=len(phases)<=4:raise ValueError('PHASE_BOUND')
    seen=set()
    for phase in phases:
        if not isinstance(phase,dict) or set(phase)-PHASE_KEYS:raise ValueError('PUBLIC_PHASE_KEYS')
        ident=phase.get('id');q=phase.get('public_question')
        if not isinstance(ident,str) or not re.fullmatch('[A-Za-z0-9_-]{1,64}',ident) or ident in seen:raise ValueError('PHASE_IDENTITY')
        seen.add(ident)
        if not isinstance(q,str) or not 0<len(q.encode())<=4096:raise ValueError('QUESTION_BOUND')
        if type(phase.get('authorized',True)) is not bool:raise ValueError('AUTHORITY_TYPE')
    cap=task.get('max_actions',20)
    if type(cap) is not int or not 1<=cap<=20:raise ValueError('ACTION_BOUND')
    renew=task.get('automatic_renewal',False)
    if type(renew) is not bool or renew and len(phases)!=1:raise ValueError('RENEWAL_BOUND')
    return cap,renew

def _conventional_child(pipe,values):
    try:
        from .native_adapter import execute_native
        result=execute_native(*values,canonical_governance=False,field_mode='disabled',toroidal_mode='disabled')
        pipe.send({'ok':True,'result':result})
    except Exception:
        pipe.send({'ok':False,'code':'NATIVE_EXECUTION_REJECTED'})
    finally:pipe.close()

def conventional_native(values):
    """Same owned fresh-worker 20-second deadline as the supplied native runner."""
    ctx=multiprocessing.get_context('spawn');reader,writer=ctx.Pipe(duplex=False)
    process=ctx.Process(target=_conventional_child,args=(writer,values),daemon=True)
    process.start();writer.close()
    try:
        if not reader.poll(20):raise ValueError('NATIVE_TIMEOUT')
        row=reader.recv()
        if not row['ok']:raise ValueError(row['code'])
        return row['result']
    finally:
        reader.close();process.join(timeout=.2)
        if process.is_alive():process.terminate();process.join(timeout=2)
        if process.is_alive():process.kill();process.join(timeout=2)
        process.close()

def _conventional_effect(root,result,prior,phase_id):
    from . import realization_loop as loop
    eligible=sorted((n for n in result['attestation']['raw_execution_out']['nodes']
        if n['status']=='COMPLETE' and n.get('knowledge_status')=='CURRENT' and n['result'] is not None and n['route'] in loop.ROUTES),key=lambda n:n['id'])
    if not eligible:return None
    # Conventional dependency-sink inspection, not arbitrary first-premise bias.
    prerequisites={d for n in result['attestation']['plan']['nodes'] for d in n.get('depends_on',[])}
    sinks=[n for n in eligible if n['id'] not in prerequisites]
    node=(sinks or eligible)[0]
    artifact={'schema':SCHEMA,'operation':'conventional-materialize-verified-native-result',
        'selected_id':node['id'],'route':node['route'],'verified_native_result':node['result'],
        'native_checkpoint_sha256':sha(result['checkpoint']),'prior_memory_sha256':sha(prior) if prior else None,
        'phase_id':phase_id,'scope':'Conditional shared-tool result; no canonical realization claim'}
    raw=encode(artifact)
    if len(raw)>8192:raise ValueError('ARTIFACT_BYTE_CAP')
    digest=hashlib.sha256(raw).hexdigest();path=root/'conventional-effects'/(digest+'.json')
    loop.root_path(path);loop.exclusive(path,raw)
    observation=loop.fresh_readback(path)
    if observation!={'sha256':digest,'bytes':len(raw)}:raise ValueError('EFFECT_OBSERVATION_REJECTED')
    return {'effect_sha256':digest,'bytes':len(raw),'verified':True,'selected_node':node['id'],
        'relative_path':'conventional-effects/'+digest+'.json',
        'scope':'Fresh interpreter byte readback; shared tools already independently replayed'}

def _resource(result):
    public=result['public'];recursive=(public.get('realization_loop') or {}).get('resources')
    if recursive is not None:
        return {'native':recursive,'total_cpu_seconds':None,'cpu_scope':'Component CPU only; readback child CPU unknown'}
    resource=public.get('native_resources') or (public.get('canonical') or {}).get('resources') or {}
    return {'native':deepcopy(resource),'total_cpu_seconds':None,'cpu_scope':'Native worker CPU only; readback/parent recorded separately'}

def run_condition(task,condition,private_root,bundle,manifest,pin):
    """Trusted offline caller; public tasks cannot choose paths/tools/field modes.

    Returns actual native conditional outputs, never fabricated model outputs.
    Destination must be a NEW owned directory. Failed/partial work is immutable,
    not retried. All four-phase memories have the same 4MiB bound and public data.
    """
    cap,renew=valid(task,condition)
    base={'schema':SCHEMA,'task_id':task['id'],'category':task['category'],'condition':condition,
        'model_status':'NOT_EXECUTED','provider_calls':0,'model_tokens':0,'phase_records':[],
        'tool_context':[],'scope':'Offline tools/conditional knowledge only; no fresh Nemotron answer'}
    if condition=='A':
        return {**base,'status':'NOT_EXECUTED','resources':{'wall_seconds':0,'cpu_seconds':0,'local_monetary_cost_usd':None},
            'configuration':{'tools':False,'memory':'Public questions only','field_mode':None,'artifact_capability':False}}
    from .native_adapter import validate_bundle
    from . import realization_loop as loop
    from .recursive_controller import execute
    validate_bundle(bundle,manifest,pin) # before any imports from the private bundle
    root=loop.root_path(private_root)
    if root.exists():raise ValueError('DESTINATION_ALREADY_EXISTS_NO_RETRY')
    root.mkdir(parents=True)
    loop.exclusive(root/'task.json',encode(task))
    start=time.perf_counter();cpu=time.process_time();checkpoint=None;field=None;state=None;used=0
    task_id=sha({'task':task['id'],'condition':condition})[:32]
    mode='enabled' if condition=='C' else 'neutralized' if condition=='D' else 'disabled'
    base['configuration']={'tools':'Shared native math, HOST arithmetic and task-local relations',
        'memory':'Actual checkpoint journal and public phase history; <=4MiB',
        'canonical_governance':condition!='B','field_mode':mode,'toroidal_mode':mode,
        'ordinary_substitute':condition in ('B','D'),'artifact_capability':True,
        'd_ablation_scope':'D computes same fields but neutralizes selection influence; genuine field absence is not claimed' if condition=='D' else None}
    for index,phase in enumerate(task['phases']):
        row={'id':phase['id'],'provider_calls':0,'model_status':'NOT_EXECUTED','artifact_records':[],'native_operations':0}
        if not phase.get('authorized',True):
            row.update(status='DENIED_AUTHORITY',response=None,public=None,error_code='AUTHORITY_DENIED')
            base['phase_records'].append(row);break
        if used>=cap or state and state['step']>=4:
            row.update(status='ACTION_LIMIT',response=None,public=None,error_code='ACTION_ALLOWANCE')
            base['phase_records'].append(row);break
        request=sha({'task':task_id,'phase':index})[:32]
        loop.exclusive(root/'attempts'/f'{index+1:04d}.json',encode({'phase_id':phase['id'],'request_id':request,'before_checkpoint_sha256':sha(checkpoint)}))
        tick=time.perf_counter()
        try:
            values=(bundle,manifest,pin,phase['public_question'],checkpoint,task_id,request,field)
            if condition=='B':
                result=conventional_native(values)
                result_actions=result['operations']
                if used+result_actions>cap:raise ValueError('ACTION_ALLOWANCE')
                effect=_conventional_effect(root,result,checkpoint,phase['id'])
                if effect:row['artifact_records']=[effect]
            else:
                result=execute(values,root/'recursive',prior=state,field_mode=mode,automatic_renewal=renew,
                    remaining_native=cap-used,pre_effect_gate=lambda n:n<=cap-used)
                result_actions=result['operations'];state=result['realization_state']
                row['artifact_records']=[{'effect_sha256':c['effect_sha256'],'bytes':c['effect_bytes'],
                    'verified':c['effect_observed_by_fresh_interpreter'],'selected_node':c['selected_node'],
                    'relative_path':'recursive/effects-ledger/effects/'+c['effect_sha256']+'.json'}
                    for c in result['public']['realization_loop']['cycles'] if c.get('effect_observed_by_fresh_interpreter')]
            used+=result_actions;checkpoint=result['checkpoint'];field=result['field_checkpoint']
            if len(encode(checkpoint))>4*1024*1024:raise ValueError('MEMORY_BOUND')
            public=deepcopy(result['public'])
            nodes=public['nodes'];complete=bool(nodes) and all(n['status']=='COMPLETE' for n in nodes)
            row.update(status='COMPLETE' if complete else 'UNRESOLVED',response=public['answer'],public=public,
                checkpoint_sha256=sha(checkpoint),native_operations=result_actions,error_code=None,
                native_node_results=[{'id':n['id'],'route':n['route'],'status':n['status'],'result':deepcopy(n['result'])}
                    for n in result['attestation']['raw_execution_out']['nodes']],
                native_evidence_relative_path=f'results/{index+1:04d}.json',
                resources=_resource(result),wall_seconds=time.perf_counter()-tick)
            memory=loop.seal({'schema':SCHEMA,'checkpoint':checkpoint,'field_checkpoint':field,'realization_state':state,
                'public_history':[x['public_question'] for x in task['phases'][:index+1]],'native_actions':used})
            loop.exclusive(root/'memory'/f'{index+1:04d}.json',encode(memory))
            restored=loop.checked(json.loads((root/'memory'/f'{index+1:04d}.json').read_bytes()))
            checkpoint=restored['checkpoint'];field=restored['field_checkpoint'];state=restored['realization_state']
            # JSON transport normalization is the same boundary used by native proofs.
            loop.exclusive(root/'results'/f'{index+1:04d}.json',encode(result))
            base['tool_context'].append({'public_question':phase['public_question'],'verified_conditional_output':public,
                'world_facts_verified':False})
            base['phase_records'].append(row)
            if not complete:break
        except Exception as error:
            safe=str(error) if type(error) is ValueError and str(error) in {'NATIVE_TIMEOUT','NATIVE_EXECUTION_REJECTED','ACTION_ALLOWANCE','MEMORY_BOUND','ARTIFACT_BYTE_CAP','EFFECT_OBSERVATION_REJECTED'} else 'EXECUTION_FAILED'
            row.update(status='FAILED_CLOSED',response=None,public=None,error_code=safe,wall_seconds=time.perf_counter()-tick,
                failure_scope='May include uncommitted/orphan native or artifact work; no retry, no invented rollback')
            base['phase_records'].append(row);break
    base['status']='COMPLETE' if len(base['phase_records'])==len(task['phases']) and all(r['status']=='COMPLETE' for r in base['phase_records']) else 'STOPPED'
    base['resources']={'wall_seconds':time.perf_counter()-start,'parent_cpu_seconds':time.process_time()-cpu,
        'native_actions_committed':used,'provider_calls':0,'model_tokens':0,'total_cpu_seconds':None,
        'local_monetary_cost_usd':None,'scope':'Whole control wall; parent CPU excludes native/proof/readback children; failed work costs may be unknown'}
    base['evidence']={'private_root':str(root),'source_manifest_sha256':pin,'task_sha256':sha(task)}
    loop.exclusive(root/'control-result.json',encode(base))
    return base
