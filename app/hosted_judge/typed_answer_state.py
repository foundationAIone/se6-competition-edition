"""Append-only typed delivery receipts alongside, never inside, native journals."""
from copy import deepcopy
from pathlib import Path
import json,re,os
from . import realization_loop as loop
from .answer_contract import digest,encode,verify_user_answer
from .typed_native import checked

MAX_RECORD=256*1024

def append(root,task_id,request_id,prepared,result,prior_state,*,native_checkpoint):
    if not re.fullmatch('[0-9a-f]{32}',task_id) or not re.fullmatch('[0-9a-f]{32}',request_id):raise ValueError('TYPED_LEDGER_IDENTITY')
    checked(prepared);envelope=result['envelope'];state=result['next_state']
    if state is not None:
        checked(state)
        if state['prior_state_sha256']!=(prior_state or {}).get('sha256'):raise ValueError('TYPED_STATE_ANCESTRY')
        if state['question_sha256']!=prepared['original_question_sha256']:raise ValueError('TYPED_SCOPE_SUBSTITUTION')
    if envelope['scope']['task_id']!=task_id or envelope['scope']['question_sha256']!=prepared['original_question_sha256']:raise ValueError('TYPED_SCOPE_SUBSTITUTION')
    independently=verify_user_answer(prepared['task_type'],envelope['user_answer'],prepared['public_facts'])
    abstention=(set(envelope['user_answer'])=={'status'} and independently['schema'] is True
        and envelope['status']!='COMPLETE' and envelope['checks'].get('finish') is True)
    if not abstention and (independently['schema'] is not True or independently['semantic'] is not True):raise ValueError('TYPED_LEDGER_UNVERIFIED_ANSWER')
    if envelope['status']=='COMPLETE' and (state is None or envelope['checks'].get('finish') is not True):raise ValueError('TYPED_COMPLETE_STATE_OR_FINISH_MISSING')
    if abstention and (state is not None or envelope.get('end_to_end_native_complete')):raise ValueError('ABSTENTION_MUST_NOT_ASSIMILATE_VALUE')
    # An abstention is recorded as a delivery consequence, but does not replace
    # the last verified task premises or native checkpoint.
    retained=state if envelope['status']=='COMPLETE' else deepcopy(prior_state)
    record={'schema':'se6-v11-typed-delivery-receipt-v1','task_id':task_id,'request_id':request_id,
        'prepared_sha256':prepared['sha256'],'envelope':envelope,'proposed_state':state,
        'retained_state':retained,'prior_state_sha256':(prior_state or {}).get('sha256'),
        'native_checkpoint_sha256':digest(native_checkpoint),'native_state_mutated_by_formatter':False,
        'semantic_recheck':independently,'historical_model_answer_replaced':False,
        'scope':'Verified local conditional delivery; no new model response, world truth or native journal rewrite'}
    record=loop.seal(record);path=loop.root_path(root)/'typed-deliveries'/task_id/(request_id+'.json')
    loop.root_path(path);path.parent.mkdir(parents=True,exist_ok=True);raw=encode(record)
    if len(raw)>MAX_RECORD:raise ValueError('TYPED_DELIVERY_BOUND')
    if len(list(path.parent.glob('*.json')))>=8:raise ValueError('TYPED_DELIVERY_ALLOWANCE')
    loop.exclusive(path,raw)
    # Independently read the actual append, not only its in-memory proposal.
    observed=loop.checked(json.loads(path.read_bytes()))
    if observed!=record:raise ValueError('TYPED_DELIVERY_READBACK')
    return {'state':retained,'receipt_sha256':record['sha256'],'relative_receipt':path.relative_to(root).as_posix(),
        'independently_readback':True,'verified_conditional_answer':independently,'append_only':True}

def verify_retained(root,task_id,state,native_checkpoint):
    if state is None:return None
    checked(state);base=loop.root_path(root)/'typed-deliveries'/task_id
    loop.root_path(base)
    matches=[]
    for path in base.glob('*.json'):
        loop.root_path(path)
        if path.stat().st_size>MAX_RECORD:raise ValueError('TYPED_DELIVERY_BOUND')
        record=loop.checked(json.loads(path.read_bytes()))
        if record['task_id']!=task_id:raise ValueError('TYPED_TASK_SUBSTITUTION')
        if record['retained_state']==state:matches.append(record)
    if not matches:raise ValueError('TYPED_RETAINED_RECEIPT_MISSING')
    if not any(r['native_checkpoint_sha256']==digest(native_checkpoint) for r in matches):raise ValueError('TYPED_NATIVE_STATE_BINDING')
    return {'verified':True,'state_sha256':state['sha256'],'matching_receipts':len(matches)}
