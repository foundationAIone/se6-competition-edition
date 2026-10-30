"""Hash-pinned preparation evidence only; no experiment or provider entrypoint."""
import hashlib,json,re
import math
from pathlib import Path
from .agent_realization_view import _public

FIELDS={'schema','status','provider_calls','production_connected','alpha_changed','adapter',
        'dataset','control','isolation','secondary','paid_proposal','remaining_blockers','evidence_pins'}
RESULT_FIELDS={'schema','status','provider_calls','production_connected','alpha_changed','label',
               'selection','scores','resources','limitations','qa_proposal','evidence_pins'}
REPAIR_FIELDS={'schema','status','provider_calls','production_connected','alpha_changed',
               'historical','fresh_evaluation','development','reader_recovery','architecture',
               'resources','limitations','paid_proposal','evidence_pins'}

def _score_block(value):
    if not isinstance(value,dict) or not isinstance(value.get('label'),str) or not value['label']:
        raise ValueError('Explicit comparison label required')
    selected=value['selection']['selected'];attempted=value['selection']['attempted']
    if type(selected) is not int or selected<1 or attempted!=selected:
        raise ValueError('All selected cases must remain in the result')
    if set(value['scores'])!={'se6','bm25'}:raise ValueError('Two complete arms required')
    for row in value['scores'].values():
        if type(row['cases']) is not int or row['cases']!=selected:raise ValueError('Scored denominator mismatch')
        for key in ('recall_at_5','all_evidence_success'):
            number=row[key]
            if type(number) not in (int,float) or not math.isfinite(number) or not 0<=number<=1:
                raise ValueError('Finite recall and all-evidence rates required')
        if any(type(row[k]) is not int or not 0<=row[k]<=selected for k in ('successfully_processed','failures')):
            raise ValueError('Integer coverage counts required')
        if row['successfully_processed']+row['failures']!=selected:
            raise ValueError('Coverage must include failures')

def _repair(value):
    graded=value['schema']=='se6-research-repair-result-view-v2'
    expected='COMPLETED_FRESH_REPAIR_AND_SAVED_GRADING' if graded else 'COMPLETED_FRESH_LOCAL_RETRIEVAL_REPAIR'
    if set(value)!=REPAIR_FIELDS or value['status']!=expected:
        raise ValueError('Completed distinct repair result required')
    for key in ('historical','fresh_evaluation'):_score_block(value[key])
    if value['historical'].get('identity')==value['fresh_evaluation'].get('identity') or not all(
        isinstance(value[k].get('identity'),str) and value[k]['identity'] for k in ('historical','fresh_evaluation')):
        raise ValueError('Historical and fresh identities must be distinct')
    recovery=value['reader_recovery']
    if graded:
        if (type(value['provider_calls']) is not int or value['provider_calls']!=30
            or recovery.get('new_provider_calls')!=30 or recovery.get('new_reader_calls')!=0
            or recovery.get('grading_status')!='RECOVERED_PARTIAL_SEMANTIC_GRADING_COMPLETE'
            or recovery.get('complete_pairs')!=15
            or not re.fullmatch('[0-9a-f]{64}',recovery.get('grade_result_sha256',''))):
            raise ValueError('Exact saved-output grading receipt and coverage required')
        if set(recovery.get('paired_accuracy',{}))!={'se6','bm25'}:raise ValueError('Two graded arms required')
        for row in recovery['paired_accuracy'].values():
            if (row.get('denominator')!=15 or type(row.get('correct')) is not int or not 0<=row['correct']<=15
                or row.get('accuracy')!=row['correct']/15):raise ValueError('Explicit graded subset denominator required')
    elif recovery.get('new_provider_calls')!=0 or recovery.get('grading_status')!='NOT_EXECUTED':
        raise ValueError('Unpaid repair cannot claim new grading')

def _result(value):
    if set(value)!=RESULT_FIELDS or value['status']!='COMPLETED_FROZEN_EXTERNAL_RETRIEVAL':
        raise ValueError('Frozen retrieval result scope required')
    if value['label']!='Custom LongMemEval-S retrieval subset — SE6 versus BM25 — no answering model.':
        raise ValueError('Exact custom component label required')
    _score_block(value)
def _no_evaluator_fields(node):
    if isinstance(node,dict):
        if set(node)&{'answer','gold','question_id','question_type','eval_function','reference_answer','private_manifest'}:
            raise ValueError('Evaluator fields cannot enter presentation')
        for value in node.values():_no_evaluator_fields(value)
    elif isinstance(node,list):
        for value in node:_no_evaluator_fields(value)
def load(path,pin):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size>32768:
        raise ValueError('Research projection regular bounded file required')
    if not isinstance(pin,str) or not re.fullmatch('[0-9a-f]{64}',pin):
        raise ValueError('Research projection pin required')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=pin:raise ValueError('Research projection hash mismatch')
    value=json.loads(raw)
    result=value.get('schema')=='se6-retrieval-result-view-v1'
    repair=value.get('schema') in {'se6-research-repair-result-view-v1','se6-research-repair-result-view-v2'}
    if result:_result(value)
    elif repair:_repair(value)
    elif set(value)!=FIELDS or value['schema']!='se6-research-preparation-view-v1' or value['status']!='PREPARATION_COMPLETE_EXTERNAL_RUN_BLOCKED':
        raise ValueError('Research preparation scope required')
    recorded_calls=30 if value.get('schema')=='se6-research-repair-result-view-v2' else 0
    if type(value['provider_calls']) is not int or value['provider_calls']!=recorded_calls or value['production_connected'] is not False or value['alpha_changed'] is not False:
        raise ValueError('Research non-authorizing scope required')
    if not result and not repair and (not value['remaining_blockers'] or not isinstance(value['remaining_blockers'],list)):
        raise ValueError('Blocked experiment must retain its blockers')
    _no_evaluator_fields(value);_public(value)
    return value
