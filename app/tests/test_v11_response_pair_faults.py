"""SIMULATED contract faults only; no provider/native calls or live evidence."""
import json,sys,hashlib,os
from pathlib import Path
from datetime import datetime,timezone,timedelta
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'private-native'))
from hosted_judge.v8_run_both import RunBothCoordinator,Blocked,Pending,encoded,prepare,TARIFF,MAX_OUTPUT
from src.workbench.provider_router import payload_bytes,parse_nebius_completion
Q='ROUTINE: 1 technician-hours, $11 materials cost, $62 customer revenue.\nDEEP: 3 technician-hours, $29 materials cost, $158 customer revenue.\nWe completed 13 jobs. The original log recorded 23 technician-hours. The materials budget is $240.\nCalculate revenue, materials and gross contribution. Determine whether materials exceed budget.'
A={'business':{'original':{'allocations':{'routine':'8','deep':'5'},'revenue':'1286','materials_cost':'233','gross_contribution':'1053','budget_variance':'-7','budget_exceeded':False}},'world_facts_verified':False,'execution_receipts':[]}
TASK='6'*32;REQUEST='7'*32
class Fake:
    SIMULATED=True;calls=[];fault=None
    def __init__(self,model):self.model=model
    def request(self,body,directory,timeout):
        type(self).calls.append(body);i=len(type(self).calls);fault=type(self).fault
        if fault=='timeout':raise TimeoutError('SIMULATED_ONLY')
        (directory/'request.json').write_bytes(payload_bytes(self.model,body))
        text=json.dumps(A);usage={'prompt_tokens':80,'completion_tokens':120,'total_tokens':200,'completion_tokens_details':{'reasoning_tokens':0}};finish='stop';model=self.model.model
        if fault=='missing_reasoning':usage.pop('completion_tokens_details')
        if fault=='null_reasoning':usage['completion_tokens_details']['reasoning_tokens']=None
        if fault=='positive_reasoning':usage['completion_tokens_details']['reasoning_tokens']=1
        if fault=='bad_reasoning':usage['completion_tokens_details']['reasoning_tokens']='0'
        if fault=='contradictory_reasoning':usage['completion_tokens_details']['reasoning_tokens']=121
        if fault=='truncated':finish='length';text='{"business":'
        if fault=='missing_usage':usage=None
        if fault=='wrong_total':usage['total_tokens']=201
        if fault=='excess_completion':usage.update(completion_tokens=MAX_OUTPUT+1,total_tokens=80+MAX_OUTPUT+1)
        if fault=='malformed_json':text='{"business":'
        if fault=='array_json':text='[]'
        if fault=='duplicate_json':text='{"business":{},"business":{}}'
        if fault=='wrong_model':model='wrong'
        if fault=='invalid_baseline' and i==2:text='{"wrong_schema":"SIMULATED"}'
        v={'id':'SIMULATED_NOT_PROVIDER_EVIDENCE','model':model,'choices':[{'message':{'content':text},'finish_reason':finish}],'usage':usage};raw=encoded(v)
        (directory/'provider.json').write_bytes(raw);(directory/'returned-text.txt').write_bytes(text.encode())
        return parse_nebius_completion(raw,self.model.model,provider_reasoning_control=self.model.provider_reasoning_control)
@pytest.fixture(autouse=True)
def reset():Fake.calls=[];Fake.fault=None

def run(c,request=REQUEST):return c.run(TASK,request,Q,'SIMULATED conditional native context',{'native_seconds':0,'native_operations':0,'provider_calls':0},[])

def test_simulated_pair_seven_checks_no_live_win_and_exact_profile(tmp_path):
    c=RunBothCoordinator(tmp_path,transport_factory=Fake);v=run(c);assert v['public']['origin']=='SIMULATED' and v['public']['provider_calls']==0 and v['public']['simulated_calls']==2
    assert all(x['assessment']['score']==7 for x in v['public']['lanes'].values());assert v['public']['arithmetic_winner'] is None and v['public']['overall_winner'] is None
    assert Fake.calls[0]['input'][:-1]==Fake.calls[1]['input'];assert 'SIMULATED conditional native context' not in json.dumps(Fake.calls[1])
    raw=json.loads((c.root/'requests'/TASK/REQUEST/'se6/request.json').read_bytes());assert raw['max_tokens']==2048 and raw['temperature']==0 and raw['reasoning_effort']=='none' and raw['response_format']=={'type':'json_object'}
    assert run(RunBothCoordinator(tmp_path,transport_factory=Fake))==v and len(Fake.calls)==2
@pytest.mark.parametrize('fault',['missing_reasoning','null_reasoning'])
def test_unknown_reasoning_is_unknown_not_claimed_zero(tmp_path,fault):
    Fake.fault=fault;c=RunBothCoordinator(tmp_path,transport_factory=Fake);v=run(c);assert len(Fake.calls)==2
    assert all(x['reasoning_tokens'] is None and x['non_reasoning_completion_tokens'] is None for x in v['public']['measurements'].values())
@pytest.mark.parametrize('fault',['positive_reasoning','bad_reasoning','contradictory_reasoning','truncated','missing_usage','wrong_total','excess_completion','malformed_json','array_json','duplicate_json','wrong_model'])
def test_first_fault_retains_partial_and_never_dispatches_baseline_or_retries(tmp_path,fault):
    Fake.fault=fault;c=RunBothCoordinator(tmp_path,transport_factory=Fake)
    with pytest.raises(Pending):run(c)
    d=c.root/'requests'/TASK/REQUEST;failure=json.loads((d/'failure.json').read_bytes());assert failure['attempts']==1 and failure['reserved_calls']==2 and failure['retry_allowed'] is False
    assert (d/'se6/provider.json').exists() and not (d/'baseline').exists() and (d/'failure-observation.json').exists()
    assert not (d/'summary.json').exists() and not (d/'freeze.json').exists()
    Fake.fault=None
    with pytest.raises(Pending):run(c)
    with pytest.raises(Blocked):run(c,'8'*32)
    assert len(Fake.calls)==1

def test_timeout_attempt_not_zero_paid_calls_assertion(tmp_path):
    Fake.fault='timeout';c=RunBothCoordinator(tmp_path,transport_factory=Fake)
    with pytest.raises(Pending):run(c)
    d=c.root/'requests'/TASK/REQUEST;v=json.loads((d/'failure-observation.json').read_bytes());assert len(Fake.calls)==1 and not list(d.rglob('provider.json'))
    assert v['actual_provider_calls'] is None and v['dispatch_intents']==1 and v['captured_provider_responses']==0

def test_valid_json_invalid_baseline_frozen_but_no_winner(tmp_path):
    Fake.fault='invalid_baseline';c=RunBothCoordinator(tmp_path,transport_factory=Fake);v=run(c);assert len(Fake.calls)==2
    assert v['public']['lanes']['se6']['assessment']['score']==7 and v['public']['lanes']['baseline']['assessment']['status']=='UNASSESSABLE'
    assert v['public']['arithmetic_winner'] is None and v['public']['overall_winner'] is None and (c.root/'requests'/TASK/REQUEST/'freeze.json').exists()

def test_exhausted_campaign_rejected_before_credential_lookup(tmp_path):
    packet=prepare(Q,'SIMULATED',[],{'se6':[],'baseline':[]});now=datetime.fromisoformat(TARIFF['verified_date']).replace(tzinfo=timezone.utc)
    store=str((tmp_path/'LIVE').resolve());store=os.path.normcase(store) if os.name=='nt' else store
    permit={'schema':'se6-v8-one-pair-allowance-v1','permit_id':'1'*32,'campaign_id':'mission-v11-dashboard-pair-v1','approved':True,'purpose':'ONE_MATCHED_NEMOTRON_PAIR','expires_at_utc':(now+timedelta(hours=1)).isoformat(),'allowed_question_hashes':[packet['question_sha256']],'packet_sha256':packet['packet_sha256'],'model_settings':packet['model'],'source_contract':packet['source_contract'],'claim_store_sha256':hashlib.sha256(store.encode()).hexdigest(),'max_pairs':1,'max_calls':2,'max_output_tokens':MAX_OUTPUT,'max_input_bytes':49152,'usd_cap':'0.20','tariff':TARIFF}
    path=tmp_path/'SIMULATED_NOT_AUTHORIZATION.json';path.write_bytes(encoded(permit));called=[];c=RunBothCoordinator(tmp_path,approval_path=path,approval_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),live_enabled=True,clock=lambda:now,credential_probe=lambda m:called.append(m))
    with pytest.raises(Blocked):c.allowance(packet)
    assert called==[] and Fake.calls==[]

