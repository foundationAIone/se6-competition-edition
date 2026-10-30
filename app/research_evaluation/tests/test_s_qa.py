from pathlib import Path
from decimal import Decimal
from copy import deepcopy
import hashlib,json
import pytest
from research_evaluation.s_qa_gateway import MemoryQAGateway,TOTAL_RESERVE,MODEL,ENDPOINT,official_judge_prompt
from research_evaluation.s_qa import execute,reader_messages
from research_evaluation import s_qa_transport_child

APP=Path(__file__).resolve().parents[2];LANE=APP.parent
def pin(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def put(path,value):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value));return path

class FakeFactory:
    SIMULATED=True
    def __init__(self,*,bad_usage=False):self.calls=[];self.bad_usage=bad_usage
    def __call__(self,settings):
        parent=self
        class Transport:
            def request(self,body,directory,timeout):
                parent.calls.append((settings.max_output_tokens,deepcopy(body)))
                return dict(text='yes' if settings.max_output_tokens==512 else 'SIMULATED_TEST_ONLY answer',
                    usage=None if parent.bad_usage else dict(prompt_tokens=10,completion_tokens=1,total_tokens=11),model=MODEL,response_id='SIMULATED_ONLY')
        return Transport()

def fixture(tmp_path,factory):
    source=tmp_path/'app';source.mkdir()
    manifest=put(source/'COMPLETE_SOURCE_MANIFEST_PRIVATE.json',dict(files={}))
    reader=put(tmp_path/'reader.json',dict(messages=[dict(role='system',content='TEST_ONLY'),dict(role='user',content='Synthetic test question')]))
    public=put(tmp_path/'public.json',dict(question='Synthetic question',question_date='2026-10-29'))
    private=put(tmp_path/'private.json',dict(question_type='single-session-user',answer='Synthetic reference'))
    official=LANE/'external/longmemeval/src/evaluation/evaluate_qa.py'
    spec_path=tmp_path/'spec.json';store=tmp_path/'claims'
    provisional=MemoryQAGateway(store,spec_path=spec_path,spec_sha256='0'*64,transport_factory=factory,source_root=source)
    cases=[dict(case_id='test-'+str(i).zfill(3),public_path=str(public),public_sha256=pin(public),private_path=str(private),
        private_sha256=pin(private),readers={a:dict(path=str(reader),sha256=pin(reader)) for a in ['se6','bm25']},abstention=False) for i in range(20)]
    spec=dict(schema='se6-longmemeval-s-final-answer-v1',model=MODEL,endpoint=ENDPOINT,max_requests=80,max_reader_calls=40,max_judge_calls=40,
        max_reader_output_tokens=2048,max_judge_output_tokens=512,max_wire_input_bytes=24576,input_token_reserve_per_call=262144,
        timeout_seconds=30,batch_timeout_seconds=1800,usd_cap='6.50',tariff=dict(input_usd_per_million='0.30',output_usd_per_million='0.90'),
        claim_store_sha256=provisional.store_identity(),cases=cases,source_manifest_path=str(manifest),source_manifest_sha256=pin(manifest),
        evidence_files=[dict(path=str(p),sha256=pin(p)) for p in [reader,public,private,official]],
        official_judge_source=dict(path=str(official),sha256=pin(official)))
    put(spec_path,spec)
    approval=put(tmp_path/'SIMULATED-owner-decision.json',dict(schema='se6-longmemeval-s-answer-owner-decision-v1',
        permit_id='1'*32,owner_identifier='programmerONE',decision='APPROVE_ONE_CUSTOM_LONGMEMEVAL_S_FINAL_ANSWER_BATCH',approved=True,
        spec_sha256=pin(spec_path),claim_store_sha256=provisional.store_identity(),expires_at_utc='2099-01-01T00:00:00+00:00',
        max_requests=80,usd_cap='6.50',authorization_provenance=dict(kind='SIMULATED_TEST_ONLY')))
    gateway=MemoryQAGateway(store,spec_path=spec_path,spec_sha256=pin(spec_path),approval_path=approval,approval_sha256=pin(approval),
        transport_factory=factory,source_root=source)
    return gateway,spec_path,store,approval,source,reader

def test_all_eighty_cells_execute_only_through_explicit_simulated_transport(tmp_path):
    fake=FakeFactory();gateway,spec,store,approval,source,_=fixture(tmp_path,fake)
    result=execute(spec,pin(spec),store,approval,pin(approval),transport_factory=fake,source_root=source)
    assert result['status']=='SIMULATED_TEST_ONLY' and result['provider_calls']==0
    assert len(fake.calls)==80 and [v[0] for v in fake.calls]==[2048]*40+[512]*40
    assert result['accuracy']=={'se6':1.0,'bm25':1.0}
    assert result['resources']['input_tokens']==800 and result['resources']['output_tokens']==80
    assert Decimal(result['resources']['tariff_estimate_usd'])==Decimal('0.000312')
    assert all('se6' not in json.dumps(body).lower() and 'bm25' not in json.dumps(body).lower() for _,body in fake.calls[40:])

def test_replay_cell_denied_without_second_transport_attempt(tmp_path):
    fake=FakeFactory();gateway,*_=fixture(tmp_path,fake)
    gateway.invoke_cell('reader','test-000','se6')
    with pytest.raises(ValueError,match='already claimed'):gateway.invoke_cell('reader','test-000','se6')
    assert len(fake.calls)==1

def test_unknown_usage_stops_and_preserves_full_reservation(tmp_path):
    fake=FakeFactory(bad_usage=True);gateway,*_=fixture(tmp_path,fake)
    with pytest.raises(ValueError,match='outcome failed or uncertain'):gateway.invoke_cell('reader','test-000','se6')
    assert gateway.path('STOP.json').is_file()
    assert json.loads(gateway.path('calls','test-000-reader-se6','outcome.json').read_text())['reserved_cost_usd']=='0.0804864'
    with pytest.raises(ValueError,match='stopped'):gateway.invoke_cell('reader','test-001','se6')
    assert len(fake.calls)==1

def test_missing_owner_approval_cannot_reach_credential_or_transport(tmp_path):
    fake=FakeFactory();gateway,spec,store,approval,source,_=fixture(tmp_path,fake)
    blocked=MemoryQAGateway(store,spec_path=spec,spec_sha256=pin(spec),transport_factory=fake,source_root=source)
    with pytest.raises(ValueError,match='owner decision required'):blocked.invoke_cell('reader','test-000','se6')
    assert not fake.calls

def test_authority_is_rechecked_at_exclusive_intent_boundary(tmp_path):
    fake=FakeFactory();gateway,*_=fixture(tmp_path,fake)
    original=gateway._approval;count=[0]
    def expires_between_preparation_and_dispatch():
        count[0]+=1
        if count[0]>1:raise ValueError('TEST_ONLY_EXPIRED_AT_INTENT')
        return original()
    gateway._approval=expires_between_preparation_and_dispatch
    with pytest.raises(ValueError,match='EXPIRED_AT_INTENT'):gateway.invoke_cell('reader','test-000','se6')
    assert not fake.calls and not list(gateway.root.glob('calls/*/intent.json'))

@pytest.mark.parametrize('fault',['old_schema','wrong_owner','expired','caps'])
def test_old_forged_or_expired_approval_rejected_before_transport(tmp_path,fault):
    fake=FakeFactory();gateway,spec,store,approval,source,_=fixture(tmp_path,fake)
    value=json.loads(approval.read_text())
    if fault=='old_schema':value['schema']='se6-model-workflow-owner-decision-v1'
    if fault=='wrong_owner':value['owner_identifier']='programmeONE'
    if fault=='expired':value['expires_at_utc']='2000-01-01T00:00:00+00:00'
    if fault=='caps':value['max_requests']=800
    put(approval,value)
    changed=MemoryQAGateway(store,spec_path=spec,spec_sha256=pin(spec),approval_path=approval,approval_sha256=pin(approval),
        transport_factory=fake,source_root=source)
    with pytest.raises(ValueError):changed.invoke_cell('reader','test-000','se6')
    assert not fake.calls

def test_judge_cannot_open_until_all_reader_answers_committed(tmp_path):
    fake=FakeFactory();gateway,*_=fixture(tmp_path,fake)
    with pytest.raises(ValueError,match='forty reader answers'):gateway.invoke_cell('judge','test-000','se6')
    assert not fake.calls

def test_source_bound_input_tamper_rejected_before_transport(tmp_path):
    fake=FakeFactory();gateway,_,_,_,_,reader=fixture(tmp_path,fake)
    put(reader,dict(messages=[dict(role='user',content='unapproved input')]))
    with pytest.raises(ValueError,match='evidence changed'):gateway.invoke_cell('reader','test-000','se6')
    assert not fake.calls

def test_reader_context_truncates_utf8_equally_without_dropping_intake_records():
    session=dict(session_id='session-test',timestamp='2025-01-01',turns=[dict(role='assistant',content='界'*20000)],
        source_ref='SOURCE_TEST_ONLY',content_sha256='a'*64)
    public=dict(question='Synthetic question',question_date='2026-10-29')
    original=deepcopy(session);messages,trace=reader_messages(public,dict(sessions=[session]))
    assert session==original and trace['context_bytes']<=16384 and trace['serialized_wire_bytes']<=24576
    assert trace['selected_sources'][0]['truncated'] is True
    assert 'answer_session_ids' not in json.dumps(messages) and 'question_type' not in json.dumps(messages)

def test_original_answer_rubric_is_source_bound_and_preserved():
    path=LANE/'external/longmemeval/src/evaluation/evaluate_qa.py'
    prompt=official_judge_prompt(path,pin(path),task='temporal-reasoning',question='Synthetic question',answer='18 days',response='19 days')
    assert 'do not penalize off-by-one errors' in prompt and 'Correct Answer: 18 days' in prompt
    with pytest.raises(ValueError,match='rubric source changed'):
        official_judge_prompt(path,'0'*64,task='multi-session',question='x',answer='y',response='z')
    assert TOTAL_RESERVE==Decimal('6.383616')

def test_real_transport_child_refuses_test_decision_before_any_model_or_credential_access(tmp_path,monkeypatch):
    fake=FakeFactory();gateway,spec,store,approval,source,_=fixture(tmp_path,fake)
    calls=[]
    monkeypatch.setattr(s_qa_transport_child,'model_parts',lambda kind:calls.append(kind))
    from types import SimpleNamespace
    args=SimpleNamespace(store=store,spec=spec,spec_pin=pin(spec),approval=approval,approval_pin=pin(approval),
        kind='reader',case_id='test-000',arm='se6')
    with pytest.raises(ValueError):s_qa_transport_child.run(args)
    assert not calls and not fake.calls
