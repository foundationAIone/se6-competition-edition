from pathlib import Path
from copy import deepcopy
from decimal import Decimal
import hashlib,json
import pytest
from research_evaluation.s_qa_recovery import classify,binary_judge_result,ResponseJournal,MODEL,ENDPOINT
from research_evaluation.s_qa_saved_grader import SavedGrader,execute,TOTAL
from research_evaluation.s_qa_reader_v2 import prepare_reader_v2

def pin(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def put(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value));return path
def response(text='yes',finish='stop',*,usage=True,reasoning=''):
    value=dict(model=MODEL,choices=[dict(finish_reason=finish,message=dict(role='assistant',content=text,reasoning_content=reasoning))])
    if usage:value['usage']=dict(prompt_tokens=10,completion_tokens=5,total_tokens=15,completion_tokens_details=dict(reasoning_tokens=2))
    return json.dumps(value).encode()

@pytest.mark.parametrize('text,finish,status,code',[
    ('complete','stop','COMPLETE','KNOWN_TERMINAL_FINAL_CONTENT'),
    ('partial','length','ITEM_INCOMPLETE','LENGTH_CAP_REACHED'),
    ('','stop','ITEM_INCOMPLETE','EMPTY_FINAL_CONTENT_REASONING_NOT_AN_ANSWER'),
    ('unknown','other','GLOBAL_STOP','UNRESOLVED_OR_NONTERMINAL_PROVIDER_COMPLETION')])
def test_final_reasoning_and_incomplete_are_distinct(text,finish,status,code):
    value=classify(response(text,finish,reasoning='PRIVATE_TEST_REASONING'))
    assert (value['status'],value['reason'])==(status,code)
    assert 'PRIVATE_TEST_REASONING' not in json.dumps(value)
    assert value['usage']['completion_tokens']==5 and Decimal(value['tariff_estimate_usd'])>0
    assert value['reported_reasoning_tokens']==2 and value['reported_non_reasoning_completion_tokens']==3

@pytest.mark.parametrize('fault',['missing_usage','model','usage_overrun','duplicate','negative'])
def test_unknown_or_invalid_cost_and_identity_stop_globally(fault):
    value=json.loads(response())
    if fault=='missing_usage':del value['usage']
    if fault=='model':value['model']='different-model'
    if fault=='usage_overrun':value['usage'].update(completion_tokens=513,total_tokens=523)
    if fault=='negative':value['usage'].update(prompt_tokens=-1,total_tokens=4)
    raw=json.dumps(value).encode()
    if fault=='duplicate':raw=b'{"model":"a","model":"b"}'
    result=classify(raw,max_output_tokens=512)
    assert result['status']=='GLOBAL_STOP' and result['retry_permitted'] is False
    assert 'not zero' in result['cost_policy']

def test_crash_after_capture_recovers_without_duplicate_inference(tmp_path):
    journal=ResponseJournal(tmp_path,max_output_tokens=512);journal.reserve('a'*64);journal.capture(response())
    # A different process creates the durable outcome after the first process died.
    cold=ResponseJournal(tmp_path,max_output_tokens=512)
    result=cold.recover();assert result['status']=='COMPLETE' and not cold.inference_allowed()
    assert cold.recover()==result
    with pytest.raises(FileExistsError):cold.reserve('a'*64)
    with pytest.raises(FileExistsError):cold.capture(response())
    assert binary_judge_result(result)['label'] is True

def test_intent_without_raw_is_uncertain_and_never_retryable(tmp_path):
    journal=ResponseJournal(tmp_path,max_output_tokens=512);journal.reserve('a'*64)
    result=journal.recover();assert result['status']=='GLOBAL_STOP' and not journal.inference_allowed()

def test_binary_parser_does_not_substitute_reference_exact_match():
    assert binary_judge_result(classify(response('No.')))['label'] is False
    assert binary_judge_result(classify(response('A plausible reference answer')))['status']=='ITEM_INCOMPLETE'
    assert binary_judge_result(classify(response('',reasoning='yes')))['label'] is None

class FakeFactory:
    SIMULATED=True
    def __init__(self,outputs=None):self.calls=[];self.outputs=outputs or {}
    def __call__(self,settings):
        parent=self
        class Transport:
            def request(self,body,directory,timeout):
                parent.calls.append(deepcopy(body));raw=parent.outputs.get(len(parent.calls),response())
                with (directory/'provider.json').open('xb') as file:file.write(raw)
                return dict(text='SIMULATED_ONLY')
        return Transport()

def fixture(tmp_path,factory):
    source=tmp_path/'app';source.mkdir();manifest=put(source/'COMPLETE_SOURCE_MANIFEST_PRIVATE.json',dict(files={}))
    spec_path=tmp_path/'spec.json';store=tmp_path/'claims'
    preliminary=SavedGrader(store,spec_path=spec_path,spec_pin='0'*64,transport_factory=factory,source_root=source)
    items=[];evidence=[]
    for index in range(30):
        bid='saved-'+str(index).zfill(24)
        path=put(tmp_path/'packets'/(bid+'.json'),dict(blind_id=bid,messages=[dict(role='user',content='SIMULATED_TEST_ONLY original semantic rubric')],saved_answer_sha256='a'*64,rubric_source_sha256='b'*64))
        items.append(dict(blind_id=bid,packet_path=str(path),packet_sha256=pin(path)));evidence.append(dict(path=str(path),sha256=pin(path)))
    mapping=put(tmp_path/'private-mapping.json',[dict(blind_id=i['blind_id'],case_id='synthetic-pair-'+str(n//2),arm=['se6','bm25'][n%2]) for n,i in enumerate(items)])
    evidence.append(dict(path=str(mapping),sha256=pin(mapping)))
    spec=dict(schema='se6-saved-answers-grader-only-v1',model=MODEL,endpoint=ENDPOINT,max_calls=30,max_output_tokens=512,max_wire_bytes=24576,input_token_reserve_per_call=262144,private_mapping_path=str(mapping),
        timeout_seconds=30,usd_cap='2.40',claim_store_sha256=preliminary.store_identity(),items=items,evidence_files=evidence,
        source_manifest_path=str(manifest),source_manifest_sha256=pin(manifest))
    put(spec_path,spec)
    approval=put(tmp_path/'SIMULATED-owner.json',dict(schema='se6-saved-answer-grader-owner-decision-v1',owner_identifier='programmerONE',approved=True,
        decision='APPROVE_ONE_SAVED_LONGMEMEVAL_S_GRADER_ONLY_RECOVERY',permit_id='1'*32,spec_sha256=pin(spec_path),claim_store_sha256=preliminary.store_identity(),
        max_calls=30,usd_cap='2.40',authorization_provenance=dict(kind='SIMULATED_TEST_ONLY'),expires_at_utc='2099-01-01T00:00:00+00:00'))
    gateway=SavedGrader(store,spec_path=spec_path,spec_pin=pin(spec_path),approval_path=approval,approval_pin=pin(approval),transport_factory=factory,source_root=source)
    return gateway,spec_path,approval,source

def test_thirty_saved_items_grade_without_forty_reader_global_barrier_and_no_reinference(tmp_path):
    fake=FakeFactory();gateway,*_=fixture(tmp_path,fake);result=execute(gateway)
    assert result['status']=='RECOVERED_PARTIAL_SEMANTIC_GRADING_COMPLETE' and result['reader_calls']==0
    assert result['provider_calls']==0 and len(fake.calls)==30 and all(row['judge']['status']=='GRADED' for row in result['results'])
    # Restarting with the same authorized claims reads durable raw captures only.
    assert execute(gateway)['status']==result['status'] and len(fake.calls)==30
    assert TOTAL==Decimal('2.37312')

def test_known_item_truncation_does_not_abort_other_saved_items(tmp_path):
    fake=FakeFactory({3:response('partial','length')});gateway,*_=fixture(tmp_path,fake);result=execute(gateway)
    assert len(fake.calls)==30 and result['results'][2]['judge']['status']=='ITEM_INCOMPLETE'
    assert not gateway.path('STOP.json').exists()
    measurement=result['measurement']
    assert measurement['jointly_graded_pairs']==14 and measurement['unmeasured_pairs']==1
    assert measurement['per_arm']['se6']['graded']==14 and measurement['per_arm']['se6']['unmeasured']==1
    assert measurement['per_arm']['bm25']['graded']==15 and measurement['paired_accuracy']['bm25']['denominator']==14
    assert measurement['resources']['known_usage_items']==30 and measurement['resources']['actual_invoice_status']=='UNKNOWN'

def test_unknown_usage_stops_globally_and_preserves_intent(tmp_path):
    fake=FakeFactory({1:response(usage=False)});gateway,*_=fixture(tmp_path,fake);result=execute(gateway)
    assert len(fake.calls)==1 and result['results'][0]['status']=='GLOBAL_STOP'
    assert gateway.path('STOP.json').is_file()
    assert result['measurement']['resources']['unknown_usage_items']==1
    assert Decimal(result['measurement']['resources']['unknown_usage_full_reservation_usd'])==Decimal('0.079104')
    assert result['measurement']['unmeasured_pairs']==15
    with pytest.raises(ValueError,match='globally stopped'):gateway.invoke('saved-'+str(1).zfill(24))
    assert len(fake.calls)==1

def test_first_two_incomplete_are_bounded_completion_calibration_not_extra_calls(tmp_path):
    fake=FakeFactory({1:response('','stop'),2:response('partial','length')});gateway,*_=fixture(tmp_path,fake);result=execute(gateway)
    assert len(fake.calls)==2 and result['status']=='PARTIAL_OR_SYSTEMICALLY_STOPPED_NO_RETRY'
    assert 'SYSTEMIC_COMPLETION' in gateway.path('STOP.json').read_text()

@pytest.mark.parametrize('fault',['old_approval','missing_approval','expired','wrong_store','tamper'])
def test_approval_and_source_guards_precede_transport(tmp_path,fault):
    fake=FakeFactory();gateway,spec,approval,source=fixture(tmp_path,fake)
    if fault=='tamper':Path(json.loads(spec.read_text())['items'][0]['packet_path']).write_text('{}')
    elif fault=='missing_approval':gateway.approval_path=None
    else:
        value=json.loads(approval.read_text())
        if fault=='old_approval':value['schema']='se6-longmemeval-s-answer-owner-decision-v1'
        if fault=='expired':value['expires_at_utc']='2000-01-01T00:00:00+00:00'
        if fault=='wrong_store':value['claim_store_sha256']='0'*64
        put(approval,value);gateway.approval_sha256=pin(approval)
    with pytest.raises(ValueError):gateway.invoke('saved-'+str(0).zfill(24))
    assert not fake.calls

def test_persistent_batch_deadline_cannot_reset_on_restart(tmp_path):
    fake=FakeFactory();gateway,*_=fixture(tmp_path,fake);gateway.invoke('saved-'+str(0).zfill(24))
    path=gateway.path('batch-claim.json');value=json.loads(path.read_text());value['started_at_utc']='2000-01-01T00:00:00+00:00';put(path,value)
    with pytest.raises(ValueError,match='persistent batch deadline'):gateway.invoke('saved-'+str(1).zfill(24))
    assert len(fake.calls)==1

def test_reader_conciseness_retains_real_context_and_does_not_emit_unverified_reasoning_controls():
    from research_evaluation.s_qa_gateway import model_parts
    public=dict(question='Synthetic question',question_date='2026-10-29')
    session=dict(session_id='s1',timestamp='2025-01-01',turns=[dict(role='user',content='Source observation')],source_ref='history:source',content_sha256='a'*64)
    result=prepare_reader_v2(public,dict(sessions=[session]));settings,router=model_parts('reader')
    wire=json.loads(router.payload_bytes(settings,{'input':result['messages']}))
    assert set(wire)=={'model','messages','max_tokens','stream','temperature'} and wire['max_tokens']==2048
    assert '120 words' in result['messages'][0]['content'] and 'Source observation' in result['messages'][1]['content']
    assert result['authorizing'] is False and result['provider_calls']==0 and result['proposal'].startswith('NONE')
