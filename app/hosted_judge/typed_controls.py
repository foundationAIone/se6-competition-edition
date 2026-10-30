"""Public-only prospective controls over the existing V11 tools/realization.

No scoring keys, model calls or developer-agent framework. B is an explicit
bounded conventional stateful tool policy, not an autonomous LLM agent.
"""
from copy import deepcopy
import hashlib,json,time
from .benchmark_controls import valid,conventional_native,_conventional_effect
from . import realization_loop as loop
from .answer_contract import digest,encode
from .typed_native import prepare,finalize

def native_input(prepared):
    if prepared['task_type']!='graph':return prepared['native_question']
    f=prepared['public_facts'];value=encode({'edges':f['edges'],'start':f['start'],
        'target':f['target'],'question_sha256':prepared['original_question_sha256']}).decode()
    if len(value)>1000:raise ValueError('GRAPH_CONTEXT_BOUND')
    verb='Correct' if prepared['prior_state_sha256'] else 'Remember'
    return verb+': graph_inputs location is '+value+'.'

def verified_context(prepared,result,*,conventional=False):
    a=result['attestation'];out=a['raw_execution_out'];cp=a.get('primary_native_checkpoint') or result['checkpoint']
    # Source-bound owned native worker already runs mandatory checkpoint replay.
    # No caller/model assertion is accepted as a receipt or worker result here.
    proof=((result['public'].get('canonical') or {}).get('independent_checkpoint_replay') is True)
    if conventional:proof=result['public'].get('native_verification')=='PINNED_COMPETITION_CORE_AND_LOCAL_CERTIFICATES_REPLAYED' and bool(out['receipts'])
    return {'verified':proof,'checkpoint_sha256':digest(cp),'raw_out_sha256':digest(out),
        'native_question_sha256':prepared['native_question_sha256'],
        'bundle_manifest_sha256':a['bundle_manifest_sha256']}

def selected_context(result,condition,effect=None):
    """Matched one verified node, not every answer decorated with a path.

    Selection is explicitly the bounded policy under test; actual complete
    native output remains archived. Public facts and verification stay equal.
    Identical returned data means no causal model-context contrast.
    """
    out=result['attestation']['raw_execution_out']
    if condition=='B':selected=effect.get('selected_node') if effect else None;trajectory=[]
    else:
        tor=(result['public'].get('canonical') or {}).get('toroidal_realization') or {}
        nav=tor.get('navigation') or {};trajectory=nav.get('actual_trajectory',[])
        cycles=(result['public'].get('realization_loop') or {}).get('cycles',[])
        artifact_selected=cycles[0].get('selected_node') if cycles else None
        # Matched C/D policy: one context slot for the first CURRENT value
        # inspected on the actual verified path; full native output is archived.
        selected=next((i for i in trajectory if any(n['id']==i and n['status']=='COMPLETE' and n.get('knowledge_status')=='CURRENT' for n in out['nodes'])),None)
    node=next((n for n in out['nodes'] if n['id']==selected and n['status']=='COMPLETE' and n.get('knowledge_status')=='CURRENT'),None)
    public_node=next((n for n in result['public'].get('nodes',[]) if n['id']==selected),None)
    return {'selection_budget':1,'selected_id':selected,
        'task_relevant_data':{'route':node['route'],'conditional_answer':public_node['answer']} if node and public_node else None,
        'task_relevant_data_sha256':digest({'route':node['route'],'conditional_answer':public_node['answer']}) if node and public_node else None,
        'trajectory':trajectory,'artifact_selected_id':None if condition=='B' else artifact_selected,
        'selection_policy':'CONVENTIONAL_DEPENDENCY_SINK' if condition=='B' else 'FIRST_CURRENT_ACTUAL_INSPECTION',
        'world_facts_verified':False,
        'scope':'Actual selected conditional tool result; no private oracle/model answer or whole-output replacement'}

def run_condition(task,condition,private_root,bundle,manifest,pin):
    cap,renew=valid(task,condition)
    base={'schema':'se6-v11-prospective-typed-control-v1','task_id':task['id'],'condition':condition,
        'phase_records':[],'provider_calls':0,'model_status':'NOT_EXECUTED',
        'configuration':{'public_info':'Same public phases, histories and common answer schema',
            'max_native_actions_committed':cap,'native_attempt_cost_scope':'Existing kernel limits plus post-compute/pre-effect admission; failed computation costs retained where observed',
            'max_memory_bytes':4*1024*1024,'selected_tool_context_budget':1,
            'policy':'DIRECT_MODEL_NO_TOOLS' if condition=='A' else 'BOUNDED_CONVENTIONAL_STATEFUL_TOOLS' if condition=='B' else 'V11_CANONICAL_FIELD_REALIZATION' if condition=='C' else 'V11_SAME_FIELD_ORDINARY_INSPECTION',
            'not_autonomous_LLM_tool_selection':True}}
    if condition=='A':return {**base,'status':'NOT_EXECUTED','scope':'No actual direct model response generated offline'}
    from .native_adapter import validate_bundle
    from .recursive_controller import execute
    from .typed_answer_state import append
    validate_bundle(bundle,manifest,pin);root=loop.root_path(private_root)
    if root.exists():raise ValueError('DESTINATION_ALREADY_EXISTS_NO_RETRY')
    root.mkdir(parents=True);loop.exclusive(root/'task.json',encode(task))
    cp=None;field=None;state=None;typed=None;used=0;task_id=digest({'task':task['id'],'condition':condition})[:32]
    start=time.perf_counter();cpu=time.process_time()
    for index,phase in enumerate(task['phases']):
        rid=digest({'task':task_id,'phase':phase['id']})[:32];before=deepcopy(cp)
        row={'phase_id':phase['id'],'provider_calls':0,'model_status':'NOT_EXECUTED'}
        result=None;raw_saved=False
        loop.exclusive(root/'attempts'/f'{index+1:04d}.json',encode({'request_id':rid,'question_sha256':hashlib.sha256(phase['public_question'].encode()).hexdigest(),'prior_native_checkpoint_sha256':digest(cp)}))
        try:
            if not phase.get('authorized',True):raise ValueError('AUTHORITY_DENIED')
            p=prepare(phase['public_question'],typed)
            boundary=p['public_facts'].get('boundary_status')
            if boundary:
                result={'checkpoint':cp,'field_checkpoint':field,'realization_state':state,'operations':0,
                    'attestation':{},'public':{'answer':boundary,'provider_calls':0,'native_receipt_count':0}}
                effect=None;context=None
            else:
                values=(bundle,manifest,pin,native_input(p),cp,task_id,rid,field)
                if condition=='B':
                    result=conventional_native(values)
                    loop.exclusive(root/'raw-native'/f'{index+1:04d}.json',encode(result));raw_saved=True
                    if used+result['operations']>cap:raise ValueError('ACTION_ALLOWANCE_BEFORE_EFFECT')
                    effect=_conventional_effect(root,result,before,phase['id'])
                else:
                    result=execute(values,root/'recursive',prior=state,field_mode='enabled' if condition=='C' else 'neutralized',
                        automatic_renewal=renew,remaining_native=cap-used,pre_effect_gate=lambda n:n<=cap-used)
                    effect=None
                context=verified_context(p,result,conventional=condition=='B')
            if not raw_saved:
                loop.exclusive(root/'raw-native'/f'{index+1:04d}.json',encode(result));raw_saved=True
            delivery=finalize(p,result,task_id=task_id,cycle=index+1,verified_context=context)
            if used+result['operations']>cap:raise ValueError('ACTION_ALLOWANCE')
            receipt=append(root,task_id,rid,p,delivery,typed,native_checkpoint=result['checkpoint'])
            used+=result['operations'];cp=result['checkpoint'];field=result['field_checkpoint'];state=result.get('realization_state')
            if delivery['envelope']['status']=='COMPLETE':typed=delivery['next_state']
            memory=loop.seal({'typed_task_state':typed,'checkpoint':cp,'field_checkpoint':field,
                'realization_state':state,'public_history':[x['public_question'] for x in task['phases'][:index+1]]})
            if len(encode(memory))>4*1024*1024:raise ValueError('MEMORY_BOUND')
            loop.exclusive(root/'memory'/f'{index+1:04d}.json',encode(memory))
            restored=loop.checked(json.loads((root/'memory'/f'{index+1:04d}.json').read_bytes()))
            typed=restored['typed_task_state'];cp=restored['checkpoint'];field=restored['field_checkpoint'];state=restored['realization_state']
            row.update(status='COMPLETE' if delivery['envelope']['status']=='COMPLETE' else 'ABSTAINED',
                user_answer=delivery['envelope']['user_answer'],typed_answer=delivery['envelope'],
                delivery_receipt=receipt,resources=(result['public'].get('realization_loop') or {}).get('resources') or result['public'].get('native_resources') or (result['public'].get('canonical') or {}).get('resources') or {},
                selected_context=selected_context(result,condition,effect) if not boundary else None,
                native_operations=result['operations'],raw_native_relative=f'raw-native/{index+1:04d}.json',
                prior_checkpoint_sha256=digest(before),after_checkpoint_sha256=digest(cp))
            base['phase_records'].append(row)
        except Exception as error:
            row.update(status='BLOCKED',user_answer=None,error_type=type(error).__name__,
                error_code=str(error).splitlines()[0][:100],scope='Recorded once, no retry or claimed rollback; inspect owned raw work')
            if result is not None:
                row['observed_native_operations']=result['operations']
                row['raw_native_relative']=f'raw-native/{index+1:04d}.json' if raw_saved else None
                row['resources']=(result['public'].get('realization_loop') or {}).get('resources') or result['public'].get('native_resources') or (result['public'].get('canonical') or {}).get('resources') or {}
            base['phase_records'].append(row);break
    base['status']='COMPLETE' if len(base['phase_records'])==len(task['phases']) and all(r['status'] in ('COMPLETE','ABSTAINED') for r in base['phase_records']) else 'BLOCKED'
    base['resources']={'wall_seconds':time.perf_counter()-start,'parent_cpu_seconds':time.process_time()-cpu,
        'native_actions':used,'total_cpu_seconds':None,'local_monetary_usd':None,'provider_calls':0}
    loop.exclusive(root/'control-result.json',encode(base));return base
