"""Bounded recursive closure using existing native workers and private effects.

One public question remains the model input. A second native cycle uses a goal
discovered from the first cycle's independently restored conditional knowledge.
This is a candidate local realization contract, not full mathematical SE6.
"""
from copy import deepcopy
import hashlib,json,multiprocessing,os,re,time
from pathlib import Path
from . import realization_loop as loop

MAX_COMPANION=4*1024*1024
PROOF_DEADLINE=12

def _proof_child(pipe,values):
    try:
        from .native_adapter import verify_realization
        pipe.send({'ok':True,'value':verify_realization(*values)})
    except Exception:
        pipe.send({'ok':False,'code':'RECURSIVE_PROOF_REJECTED'})
    finally:pipe.close()

def proof_worker(values):
    context=multiprocessing.get_context('spawn');reader,writer=context.Pipe(duplex=False)
    process=context.Process(target=_proof_child,args=(writer,values),daemon=True)
    process.start();writer.close()
    try:
        if not reader.poll(PROOF_DEADLINE):raise ValueError('RECURSIVE_PROOF_DEADLINE')
        row=reader.recv()
        if not row['ok']:raise ValueError(row['code'])
        return row['value']
    finally:
        reader.close();process.join(timeout=.2)
        if process.is_alive():process.terminate();process.join(timeout=2)
        if process.is_alive():process.kill();process.join(timeout=2)
        process.close()

def _write(path,value):
    raw=loop.encode(loop.seal(value))
    if len(raw)>MAX_COMPANION:raise ValueError('RECURSIVE_COMPANION_BOUND')
    loop.root_path(path)
    loop.exclusive(path,raw)

def restore(root,bundle,manifest,pin,task_id):
    """Restore the actual effect ledger AND replay its retained native companion."""
    root=loop.root_path(root);state=loop.load_restore(root/'effects-ledger')
    if state is None:return None
    path=root/'native-companions'/f"{state['step']:04d}.json"
    loop.root_path(path)
    if not path.is_file() or path.stat().st_size>MAX_COMPANION:raise ValueError('RECURSIVE_COMPANION_MISSING')
    companion=loop.checked(json.loads(path.read_bytes()))
    if companion['task_id']!=task_id or companion['loop_state_sha256']!=state['sha256'] or companion['manifest_sha256']!=pin:
        raise ValueError('RECURSIVE_COMPANION_IDENTITY')
    result=companion['result'];cp=result['checkpoint']
    loop.renew(state,cp)
    checked=proof_worker((bundle,manifest,pin,task_id,companion['before'],result,state,None))
    if not checked['verified']:raise ValueError('RECURSIVE_RESTORED_PROOF')
    return {'state':state,'checkpoint':deepcopy(cp),'field_checkpoint':deepcopy(result['field_checkpoint']),
        'restoration':checked,'companion':companion}

def _public_cycle(done,result,phase,question,restored):
    p=result['attestation']['realization_loop_proposal'];typed=done['state']['typed_assimilation']
    return {'phase':phase,'question':question,'step':done['state']['step'],
        'selected_node':done['artifact']['selected_id'],'selected_route':done['artifact']['route'],
        'selected_result':next(n['answer'] for n in result['public']['nodes'] if n['id']==done['artifact']['selected_id']),
        'native_receipts':result['public']['native_receipt_count'],'host_records':result['public']['host_calculations_created'],
        'before_state_sha256':done['state']['prior_state_sha256'],'after_state_sha256':done['state']['sha256'],
        'effect_sha256':done['receipt']['effect_sha256'],'effect_bytes':done['receipt']['readback']['bytes'],
        'effect_observed_by_fresh_interpreter':True,'source_pinned_native_proof_replayed':True,
        'native_typed_return_changed':typed['traversal']['state_changed'],
        'typed_next_state':{'previous_x_hash':typed['x']['previous_x_hash'],'x_hash':typed['x']['x_hash'],
            'theta_hash':typed['theta']['theta_hash'],'retained_observations':len(typed['x']['source_observations'])},
        'candidate_count':len(p['candidates']),'selection_policy':p['selection_policy'],
        'navigation':result['public'].get('canonical',{}).get('toroidal_realization',{}).get('navigation'),
        'qpre':{'actual':False,'authority':False,'rendered':True},'mirror_views':len(p['operators']['views']),
        'classification':'SYMBOLIC_ONLY','context_superseded_ids':done['state']['invalidated_ids'],
        'restored_prior_from_disk':restored,'stages':done['receipt']['stages'],
        'resources':{'whole_native':result['public'].get('canonical',{}).get('resources',{}),
            'artifact_action_and_verification':done['receipt']['resources']},
        'scope':'Actual private artifact and native conditional knowledge; context supersession is distinct from canonical fact correction'}

def execute(values,root,*,prior=None,field_mode='enabled',toroidal_parameters=None,automatic_renewal=True,remaining_native=20,pre_effect_gate=None):
    """HOST-only policy knobs. HTTP input cannot select tools, paths or authority."""
    from .service import disposable_native
    from .native_adapter import wrapper_signature
    loaded_wrapper=wrapper_signature()
    root=loop.root_path(root);bundle,manifest,pin,question,before,task_id,request_id,field_prior=values
    wall=time.perf_counter();cpu=time.process_time();cycles=[];operations=0;primary=None
    proof_resources=[]
    initial_step=(prior or {}).get('step',0)
    restored=restore(root,bundle,manifest,pin,task_id)
    if restored is not None:
        if before!=restored['checkpoint'] or field_prior!=restored['field_checkpoint'] or prior!=restored['state']:
            raise ValueError('RECURSIVE_MEMORY_SUBSTITUTION')
        before=restored['checkpoint'];field_prior=restored['field_checkpoint'];prior=restored['state']
        proof_resources.append(restored['restoration']['resources'])
    elif prior is not None:raise ValueError('RECURSIVE_STATE_WITHOUT_LEDGER')
    next_question=question;final=None;renewal_observation=None
    for index in range(2 if automatic_renewal else 1):
        if prior and prior['step']>=loop.MAX_CYCLES:break
        rid=request_id if index==0 else hashlib.sha256((request_id+':renewal').encode()).hexdigest()[:32]
        args=(bundle,manifest,pin,next_question,before,task_id,rid,field_prior,prior,
            {'field_mode':field_mode,'toroidal_parameters':toroidal_parameters},loaded_wrapper)
        result=disposable_native(args)
        # Preserve real native input/output even if a later effect fails. This
        # is a private diagnostic capture, not an assimilated consequence.
        captures=root/'native-captures'
        if len(list(captures.glob('*.json')))>=4:raise ValueError('RECURSIVE_CAPTURE_CAP')
        _write(captures/(rid+'.json'),{'schema':'se6-v11-native-pre-effect-capture','task_id':task_id,
            'before':before,'result':result,'status':'NATIVE_RETURNED_NOT_ARTIFACT_ASSIMILATED'})
        if primary is None:primary=deepcopy(result)
        operations+=result['operations'];proposal=result['attestation'].get('realization_loop_proposal')
        if operations>remaining_native:raise ValueError('RECURSIVE_NATIVE_ACTION_CAP_BEFORE_EFFECT')
        if proposal is None:
            final=result
            cycles.append({'phase':'OWNER_QUESTION' if index==0 else 'AUTOMATIC_RENEWAL','status':'NO_ADMISSIBLE_ARTIFACT',
                'scope':'Native work may complete; no verified selected traversal means no artifact effect or full-loop claim'})
            break
        tor=result['attestation']['canonical']['toroidal_realization']
        loop.verify_prepared(proposal,result['attestation']['raw_execution_out'],result['checkpoint'],tor['prepared'],tor['feedback'],prior)
        def verify(request):
            if request['checkpoint']!=result['checkpoint'] or request['out']!=result['attestation']['raw_execution_out']:
                raise ValueError('RECURSIVE_NATIVE_SUBSTITUTION')
            proof=proof_worker((bundle,manifest,pin,task_id,before,result,prior,None))
            proof_resources.append(proof['resources'])
            # Proof replay can consume its full deadline. Recheck current
            # authority after it, immediately before the actor claims/writes.
            if pre_effect_gate is not None and pre_effect_gate(operations) is not True:raise ValueError('RECURSIVE_HOST_EFFECT_DENIED_AFTER_PROOF')
            return proof['verified'] is True
        def finalize(prepared,observation,previous):
            if prepared!=proposal or previous!=prior:raise ValueError('RECURSIVE_FINALIZER_SUBSTITUTION')
            proof=proof_worker((bundle,manifest,pin,task_id,before,result,prior,observation))
            proof_resources.append(proof['resources'])
            if not proof['verified']:raise ValueError('RECURSIVE_FINALIZER_PROOF')
            return proof['typed_finalization']
        if pre_effect_gate is not None and pre_effect_gate(operations) is not True:raise ValueError('RECURSIVE_HOST_EFFECT_DENIED')
        done=loop.act_verify_assimilate(proposal,root/'effects-ledger',verify_native=verify,finalize=finalize)
        _write(root/'native-companions'/f"{done['state']['step']:04d}.json",{
            'schema':'se6-recursive-native-companion-v1','task_id':task_id,'manifest_sha256':pin,
            'loop_state_sha256':done['state']['sha256'],'before':before,'result':result})
        cycle=_public_cycle(done,result,'OWNER_QUESTION' if index==0 else 'AUTOMATIC_RENEWAL',next_question,
            restored is not None or index>0)
        cycle['renewal_source_effect_sha256']=(prior or {}).get('effect_sha256')
        cycles.append(cycle)
        renewal_observation=restore(root,bundle,manifest,pin,task_id)
        proof_resources.append(renewal_observation['restoration']['resources'])
        before=renewal_observation['checkpoint'];field_prior=renewal_observation['field_checkpoint'];prior=renewal_observation['state']
        final=result
        next_question=renewal_observation['restoration'].get('renewal_question')
        if not next_question:break
    if primary is None:raise ValueError('RECURSIVE_CYCLE_ALLOWANCE')
    if final is None:final=primary
    primary['attestation']['primary_native_checkpoint']=deepcopy(primary['checkpoint'])
    primary['attestation']['retained_native_attestation']=deepcopy(final['attestation'])
    primary['attestation']['retained_native_checkpoint']=deepcopy(final['checkpoint'])
    primary['attestation']['checkpoint_scope']='COMPOSITE_FINAL_RENEWAL_CHECKPOINT; primary raw out binds primary_native_checkpoint, each companion is independently replayable'
    primary['checkpoint']=final['checkpoint'];primary['field_checkpoint']=final['field_checkpoint']
    primary['operations']=operations
    primary['realization_state']=prior
    primary['attestation']['recursive_private']={'cycles':cycles,'latest_native_companion_step':(prior or {}).get('step'),
        'primary_before':values[4],'latest_checkpoint_sha256':loop.digest(final['checkpoint'])}
    primary['public']['realization_loop']={'schema':'se6-bounded-recursive-realization-v1',
        'status':'BOUNDED_END_TO_END_RENEWED' if len(cycles)==2 and all(c.get('effect_observed_by_fresh_interpreter') for c in cycles) else 'BOUNDED_PARTIAL_OR_IDENTITY',
        'cycles':cycles,'before_step':initial_step,
        'after_step':(prior or {}).get('step',0),'full_mathematical_se6':False,
        'scope':'Navigation-selected private artifact, actual finite typed operators, independent observation, durable native restoration and a new native renewal goal. Direct model receives only the original public question.',
        'resources':{'controller_wall_seconds':time.perf_counter()-wall,'controller_cpu_seconds':time.process_time()-cpu,
            'native_actions':operations,'artifact_actions':sum(bool(c.get('effect_observed_by_fresh_interpreter')) for c in cycles),
            'native_receipts_total':operations,
            'native_cpu_seconds_sum':sum(c.get('resources',{}).get('whole_native',{}).get('whole_execute_native_cpu_seconds',0) for c in cycles),
            'proof_worker_cpu_seconds_sum':sum(p['cpu_seconds'] for p in proof_resources),
            'proof_worker_wall_seconds_sum':sum(p['wall_seconds'] for p in proof_resources),
            'proof_worker_calls':len(proof_resources),'fresh_file_readback_child_cpu_seconds':None,
            'provider_calls':0,'local_monetary_cost_usd':None}}
    if len(loop.encode(primary['public']))>65536:raise ValueError('RECURSIVE_PUBLIC_BOUND')
    return primary
