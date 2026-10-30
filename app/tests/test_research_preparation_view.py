import copy,hashlib,json
from pathlib import Path
import pytest
from hosted_judge import research_preparation_view as view
from hosted_judge.service import JudgeService,UnavailableError

def record():
    return dict(schema='se6-research-preparation-view-v1',status='PREPARATION_COMPLETE_EXTERNAL_RUN_BLOCKED',
        provider_calls=0,production_connected=False,alpha_changed=False,adapter='TEST_ONLY',dataset='BLOCKED',
        control='TEST_ONLY',isolation='TEST_ONLY',secondary='TEST_ONLY',paid_proposal='NOT_AUTHORIZED',
        remaining_blockers=['Test-only schema fixture'],evidence_pins={})

@pytest.mark.parametrize('fault',['pin','scope','provider','production','gold','nested_gold','nested_question_id','secret','private_path'])
def test_invalid_preparation_projection_fails_closed(tmp_path,fault):
    row=record()
    if fault=='scope':row['status']='SUPERIORITY_PROVEN'
    if fault=='provider':row['provider_calls']=1
    if fault=='production':row['production_connected']=True
    if fault=='gold':row['gold_answer']='not allowed'
    if fault=='nested_gold':row['dataset']={'answer':'not allowed'}
    if fault=='nested_question_id':row['adapter']={'question_id':'not allowed'}
    if fault=='secret':row['adapter']={'api_key':'not allowed'}
    if fault=='private_path':row['adapter']='C:/private/key'
    path=tmp_path/'projection.json';path.write_text(json.dumps(row))
    pin=hashlib.sha256(path.read_bytes()).hexdigest() if fault!='pin' else '0'*64
    with pytest.raises(ValueError):view.load(path,pin)

def test_authenticated_read_does_not_submit_or_change_session(tmp_path):
    path=tmp_path/'projection.json';path.write_text(json.dumps(record()))
    service=JudgeService(None,None,None)
    service.research_preparation_evidence=view.load(path,hashlib.sha256(path.read_bytes()).hexdigest())
    with pytest.raises(PermissionError):service.read_research_preparation_evidence(None)
    token,_=service.new_session();before=copy.deepcopy(service.sessions[token])
    value=service.read_research_preparation_evidence(token);value['remaining_blockers'].clear()
    assert service.read_research_preparation_evidence(token)['remaining_blockers']
    assert service.sessions[token]==before
    service.research_preparation_evidence=None
    with pytest.raises(UnavailableError):service.read_research_preparation_evidence(token)

def test_preparation_view_has_only_manual_read_no_execution():
    root=Path(__file__).resolve().parents[1]
    script=(root/'hosted_judge/static/research-preparation.js').read_text()
    assert script.count('fetch(')==1 and "addEventListener('click'" in script
    assert 'innerHTML' not in script and 'POST' not in script and 'setInterval' not in script
    assert 'same-origin' in script and 'no-store' in script

def test_external_component_result_keeps_all_cases_and_refuses_inflated_scores(tmp_path):
    row=dict(schema='se6-retrieval-result-view-v1',status='COMPLETED_FROZEN_EXTERNAL_RETRIEVAL',provider_calls=0,
        production_connected=False,alpha_changed=False,label='Custom LongMemEval-S retrieval subset — SE6 versus BM25 — no answering model.',
        selection={'selected':2,'attempted':2},scores={arm:dict(cases=2,recall_at_5=.5,all_evidence_success=.5,successfully_processed=1,failures=1) for arm in ['se6','bm25']},
        resources={},limitations=['TEST_ONLY reader fixture'],qa_proposal={},evidence_pins={})
    path=tmp_path/'result.json'
    def save():
        path.write_text(json.dumps(row));return hashlib.sha256(path.read_bytes()).hexdigest()
    assert view.load(path,save())['selection']['selected']==2
    row['scores']['se6']['recall_at_5']=1.1
    with pytest.raises(ValueError):view.load(path,save())

def repair_record():
    def block(identity):
        return dict(identity=identity,label='TEST_ONLY independent comparison',selection={'selected':2,'attempted':2},
            scores={arm:dict(cases=2,recall_at_5=.5,all_evidence_success=.5,successfully_processed=2,failures=0) for arm in ['se6','bm25']})
    return dict(schema='se6-research-repair-result-view-v1',status='COMPLETED_FRESH_LOCAL_RETRIEVAL_REPAIR',
        provider_calls=0,production_connected=False,alpha_changed=False,historical=block('preserved'),
        fresh_evaluation=block('fresh'),development={},reader_recovery=dict(new_provider_calls=0,grading_status='NOT_EXECUTED',completed_responses=30),
        architecture=[],resources={},limitations=['TEST_ONLY schema fixture'],paid_proposal='NOT_AUTHORIZED',evidence_pins={})

@pytest.mark.parametrize('fault',[None,'merged_identity','dropped_case','unfunded_grade','new_call','private_answer'])
def test_distinct_repair_preserves_history_coverage_and_unpaid_scope(tmp_path,fault):
    row=repair_record()
    if fault=='merged_identity':row['fresh_evaluation']['identity']='preserved'
    if fault=='dropped_case':row['fresh_evaluation']['scores']['se6']['cases']=1
    if fault=='unfunded_grade':row['reader_recovery']['grading_status']='ACCURACY_PROVEN'
    if fault=='new_call':row['reader_recovery']['new_provider_calls']=1
    if fault=='private_answer':row['reader_recovery']['answer']='private evaluator material'
    path=tmp_path/'repair.json';path.write_text(json.dumps(row));pin=hashlib.sha256(path.read_bytes()).hexdigest()
    if fault:
        with pytest.raises(ValueError):view.load(path,pin)
    else:
        loaded=view.load(path,pin)
        assert loaded['historical']['identity']=='preserved' and loaded['fresh_evaluation']['identity']=='fresh'

@pytest.mark.parametrize('fault',[None,'extra_call','reader_regeneration','wrong_denominator','false_rate','missing_receipt'])
def test_recorded_grades_are_read_only_and_keep_exact_partial_scope(tmp_path,fault):
    row=repair_record();row.update(schema='se6-research-repair-result-view-v2',status='COMPLETED_FRESH_REPAIR_AND_SAVED_GRADING',provider_calls=30)
    row['reader_recovery'].update(new_provider_calls=30,new_reader_calls=0,complete_pairs=15,
        grading_status='RECOVERED_PARTIAL_SEMANTIC_GRADING_COMPLETE',grade_result_sha256='a'*64,
        paired_accuracy={arm:dict(correct=correct,denominator=15,accuracy=correct/15) for arm,correct in [('se6',6),('bm25',8)]})
    if fault=='extra_call':row['provider_calls']=31
    if fault=='reader_regeneration':row['reader_recovery']['new_reader_calls']=1
    if fault=='wrong_denominator':row['reader_recovery']['paired_accuracy']['se6']['denominator']=20
    if fault=='false_rate':row['reader_recovery']['paired_accuracy']['se6']['accuracy']=1
    if fault=='missing_receipt':del row['reader_recovery']['grade_result_sha256']
    path=tmp_path/'graded.json';path.write_text(json.dumps(row));pin=hashlib.sha256(path.read_bytes()).hexdigest()
    if fault:
        with pytest.raises(ValueError):view.load(path,pin)
    else:
        loaded=view.load(path,pin)
        assert loaded['reader_recovery']['paired_accuracy']['se6']['correct']==6
