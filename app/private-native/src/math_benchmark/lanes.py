"""Offline lane preparation using actual existing SE Core bookkeeping only.

This module deliberately does not import the exhaustive verifier/evaluator,
read an answer key, import Entity Mirror, or submit model requests.
"""
from copy import deepcopy
import hashlib
import json
import time

from src.workbench.native_core import NativeCore, KERNEL_SHA256

CAPABILITIES={
    'structured_relation_recording':True,
    'exact_record_value_conflict_detection':True,
    'explicit_assertion_correction':True,
    'receipt_and_checkpoint_verification':True,
    'bookkeeping_next_state':True,
    'mathematical_relation_semantics':False,
    'mathematical_constraint_comparison':False,
    'mathematical_contradiction_detection':False,
    'mathematical_candidate_pruning':False,
    'verified_deduction_retention':False,
    'deduction_dependency_invalidation':False,
    'mathematical_next_state_projection':False,
}


def encoded(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)


def require_math_ready():
    raise ValueError('MATH_INTEGRATION_MISSING: executable Core records assertions; no mathematical deduction/pruning/verified-retention adapter exists.')


def prepare_bookkeeping(public):
    """Execute genuine local records, keeping their mathematical limits explicit."""
    if set(public)!={'schema','rounds','statements','change'} or public['schema']!='se6-math-benchmark-public-v1':
        raise ValueError('Public problem-only package required; private keys/hints are rejected.')
    before,after=public['rounds']
    for problem in (before,after):
        if set(problem)!={'schema','variables','domain','constraints'}:
            raise ValueError('Only public problem fields may reach a lane.')
        for row in problem['constraints']:
            if set(row) not in ({'id','terms','op','rhs'},{'id','terms','op','rhs','mod'}):
                raise ValueError('Constraint fields cannot contain private hints or solutions.')
    if any(before[field]!=after[field] for field in ('schema','variables','domain')):
        raise ValueError('Domain and variables must remain unchanged.')
    changed=[a['id'] for a,b in zip(before['constraints'],after['constraints']) if a!=b]
    if changed!=[public['change']['id']] or len(before['constraints'])!=len(after['constraints']):
        raise ValueError('Exactly one identified public constraint must change.')
    core=NativeCore()
    if core.blocker:raise ValueError(core.blocker)
    task_id=hashlib.sha256(encoded(public).encode()).hexdigest()[:32]
    checkpoint=head=None;calls=0;contexts=[];receipts=[];times=[]
    def record(row,correction=False):
        nonlocal checkpoint,head,calls
        observation={'schema':'se-core-observation-v1','observation':{
            'kind':'ASSERT','subject':'math-problem-definition','predicate':row['id'],
            'value':encoded({k:v for k,v in row.items() if k!='id'}),
            'source':'public-problem-givens','evidence_refs':['given:'+row['id']],
            'correction':correction},
            'question':'Retain this public given exactly. No mathematical deduction is asserted.'}
        calls+=1
        checkpoint,head,receipt,summary=core.advance(task_id,f'{calls:032x}',encoded(observation),checkpoint,head,20)
        receipts.append(receipt)
        return summary
    def context(summary):
        return ('EXECUTED SE CORE CONSTRAINT-RECORD BOOKKEEPING ONLY. '
            'These are copies of the public givens, not verified mathematical deductions. '
            'The kernel has not solved, pruned candidates or checked numerical satisfiability. '
            'Local consequence verification checks recording/receipt integrity only. '
            'No Entity identity Mirror is included.\n'+encoded({
                'kernel_sha256':KERNEL_SHA256,'records':summary['state_after']['relations'],
                'latest_boundary':summary['boundary'],'local_record_verification':summary['verification'],
                'receipt_hash':summary['receipt_hash'],'previous_receipt_hash':summary['previous_receipt_hash'],
                'scope':'OWNER_SUPPLIED givens; mathematical deductions NONE','world_truth_verified':False}))
    started=time.perf_counter()
    for row in before['constraints']:summary=record(row)
    times.append(time.perf_counter()-started);contexts.append(context(summary))
    started=time.perf_counter()
    revised=next(c for c in after['constraints'] if c['id']==public['change']['id'])
    probe=record(revised)
    assert probe['boundary']['outcome']=='REFUSE' and probe['conflict']
    summary=record(revised,correction=True)
    assert summary['boundary']['outcome']=='ALLOW' and summary['verification']['passed']
    times.append(time.perf_counter()-started);contexts.append(context(summary))
    return {'capabilities':deepcopy(CAPABILITIES),'benchmark_ready':False,
        'blocked_reason':'Mathematical operator/verified-deduction integration is missing.',
        'contexts':contexts,'local_operations_by_round':[len(before['constraints']),2],
        'local_kernel_calls':calls,'local_kernel_seconds_by_round':times,
        'receipts':receipts,'final_checkpoint':checkpoint,'final_head':head,
        'inference_calls':0,'oracle_access':False,'mirror_included':False}


def lane_messages(public,contexts,round_index,prior_outputs=None):
    """Same statements; own history only; executable records only in LEFT."""
    if round_index not in (0,1) or len(contexts)!=2:raise ValueError('Two prepared rounds required.')
    result={}
    for lane in ('se6','baseline'):
        messages=[]
        if round_index:
            messages.append({'role':'user','content':public['statements'][0]})
            if prior_outputs is not None:
                if set(prior_outputs)!={'se6','baseline'} or not all(isinstance(v,str) for v in prior_outputs.values()):
                    raise ValueError('Only completed lane-owned responses can fill history.')
                messages.append({'role':'assistant','content':prior_outputs[lane]})
        messages.append({'role':'user','content':public['statements'][round_index]})
        if lane=='se6':messages.append({'role':'user','content':contexts[round_index]})
        result[lane]=messages
    return result
