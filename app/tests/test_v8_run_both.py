import json,hashlib
import sys,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'private-native'))
from datetime import datetime,timezone,timedelta
import pytest
from hosted_judge.v8_run_both import RunBothCoordinator,Blocked,Pending,prepare,dependencies,encoded,TARIFF,MAX_OUTPUT
from hosted_judge.v8_scoring import assess,rational,derived_question

QUESTION='Given equations:\nE1: a+b=14\nE2: b=3\nDerive a relation involving a.'
ANSWER=json.dumps({'relation':{'coefficients':{'a':'1'},'rhs':'11'},'certificate':{'E1':'1','E2':'-1'},'world_facts_verified':False,'execution_receipts':[]})
TASK='a'*32;REQUEST='b'*32

class SimulatedTransport:
    SIMULATED=True;calls=[];usage_missing=False;fail=False;wrong_model=False;invalid_schema=False
    def __init__(self,model):self.model=model
    def request(self,body,directory,timeout):
        from src.workbench.provider_router import payload_bytes,parse_nebius_completion
        type(self).calls.append(body)
        if type(self).fail:raise ValueError('PRIVATE_SECRET_MUST_NOT_ESCAPE')
        (directory/'request.json').write_bytes(payload_bytes(self.model,body))
        text=json.dumps({'unsupported':'SIMULATED invalid scoring schema'}) if type(self).invalid_schema else ANSWER
        payload={'model':'wrong-model' if type(self).wrong_model else self.model.model,'id':'SIMULATED_RESPONSE_NOT_PROVIDER_EVIDENCE','choices':[{'message':{'content':text},'finish_reason':'stop'}],
            'usage':None if type(self).usage_missing else {'prompt_tokens':100,'completion_tokens':50,'total_tokens':150}}
        raw=encoded(payload);(directory/'provider.json').write_bytes(raw);(directory/'returned-text.txt').write_bytes(text.encode())
        return parse_nebius_completion(raw,self.model.model,provider_reasoning_control=self.model.provider_reasoning_control)

@pytest.fixture(autouse=True)
def reset_fake():
    SimulatedTransport.calls=[];SimulatedTransport.usage_missing=False;SimulatedTransport.fail=False
    SimulatedTransport.wrong_model=False;SimulatedTransport.invalid_schema=False

def run(coordinator,question=QUESTION,request=REQUEST):return coordinator.run(TASK,request,question,'Conditional native algebra only',{'native_seconds':.1,'native_operations':2,'provider_calls':0},[])

def test_default_blocked_before_credentials_and_any_transport(tmp_path):
    called=[];c=RunBothCoordinator(tmp_path,credential_probe=lambda x:called.append(x))
    assert c.status()['status']=='BLOCKED' and c.status()['credentials_consulted'] is False
    with pytest.raises(Blocked):run(c)
    assert called==[] and not (tmp_path/'LIVE').exists()

def test_simulated_matched_pair_and_no_live_winner(tmp_path):
    c=RunBothCoordinator(tmp_path,transport_factory=SimulatedTransport);value=run(c)
    assert value['public']['origin']=='SIMULATED' and value['public']['provider_calls']==0 and value['public']['simulated_calls']==2
    assert value['public']['arithmetic_winner'] is None and value['public']['overall_winner'] is None
    assert all(v['assessment']['score']==3 for v in value['public']['lanes'].values())
    left,right=SimulatedTransport.calls
    assert left['input'][:-1]==right['input']
    assert not any('Conditional native algebra only' in m['content'] for m in right['input'])
    assert 'approval' not in json.dumps(value['public']).lower() and 'PRIVATE_SECRET' not in json.dumps(value)

def test_restart_cached_exact_pair_no_second_dispatch_and_history_recovered(tmp_path):
    c=RunBothCoordinator(tmp_path,transport_factory=SimulatedTransport);first=run(c)
    history=c.root/'histories'/f'{TASK}.json';history.unlink()
    c2=RunBothCoordinator(tmp_path,transport_factory=SimulatedTransport);second=run(c2)
    assert second==first and len(SimulatedTransport.calls)==2 and history.exists()

def test_missing_usage_stops_second_call_and_consumed_claim_blocks_retry(tmp_path):
    SimulatedTransport.usage_missing=True;c=RunBothCoordinator(tmp_path,transport_factory=SimulatedTransport)
    with pytest.raises(Pending):run(c)
    assert len(SimulatedTransport.calls)==1
    SimulatedTransport.usage_missing=False
    with pytest.raises(Pending):run(c)
    assert len(SimulatedTransport.calls)==1
    with pytest.raises(Blocked):run(c,request='c'*32)
    assert len(SimulatedTransport.calls)==1

def test_failure_never_exposes_exception_secret_or_retries(tmp_path):
    SimulatedTransport.fail=True;c=RunBothCoordinator(tmp_path,transport_factory=SimulatedTransport)
    with pytest.raises(Pending) as failure:run(c)
    assert 'PRIVATE_SECRET' not in str(failure.value)
    assert all('PRIVATE_SECRET' not in p.read_text() for p in c.root.rglob('*.json'))
    assert len(SimulatedTransport.calls)==1

def test_same_global_question_cannot_spend_again_with_different_task(tmp_path):
    c=RunBothCoordinator(tmp_path,transport_factory=SimulatedTransport);run(c)
    with pytest.raises(Blocked):c.run('d'*32,'e'*32,QUESTION,'native',{},[])
    assert len(SimulatedTransport.calls)==2

def test_assistant_history_cannot_cross_or_be_injected(tmp_path):
    c=RunBothCoordinator(tmp_path,transport_factory=SimulatedTransport);run(c)
    with pytest.raises(Blocked):c.run(TASK,'c'*32,'another','native',{},[QUESTION],{'se6':[],'baseline':[]})
    packet=prepare('current','SE6_CURRENT',[QUESTION],{'se6':[{'public_index':0,'text':'SE6_OWN_OLD'}],'baseline':[{'public_index':0,'text':'BASELINE_OWN_OLD'}]})
    assert 'SE6_OWN_OLD' not in json.dumps(packet['messages']['baseline']) and 'BASELINE_OWN_OLD' not in json.dumps(packet['messages']['se6'])
    assert packet['messages']['baseline'][1]['role']=='user' and packet['messages']['baseline'][2]['role']=='assistant'

def test_cache_metadata_tampering_rejected(tmp_path):
    c=RunBothCoordinator(tmp_path,transport_factory=SimulatedTransport);run(c)
    p=c.root/'requests'/TASK/REQUEST/'summary.json';v=json.loads(p.read_text());v['origin']='NEBIUS_TRANSPORT_CAPTURE';p.write_text(json.dumps(v))
    with pytest.raises(Blocked):run(c)
    assert len(SimulatedTransport.calls)==2

def test_rehashed_archive_cannot_hide_cross_lane_message_injection(tmp_path):
    c=RunBothCoordinator(tmp_path,transport_factory=SimulatedTransport);run(c);d=c.root/'requests'/TASK/REQUEST
    packet=json.loads((d/'prepared.json').read_text());packet['messages']['baseline'].append({'role':'system','content':'SE6 CONTEXT INJECTION'})
    (d/'prepared.json').write_bytes(encoded(packet))
    # Rehash all local capture manifests; semantic reconstruction must still fail.
    freeze=json.loads((d/'freeze.json').read_text());(d/'freeze.json').write_bytes(encoded({n:hashlib.sha256((d/n).read_bytes()).hexdigest() for n in freeze}))
    final=json.loads((d/'final-manifest.json').read_text());(d/'final-manifest.json').write_bytes(encoded({n:hashlib.sha256((d/n).read_bytes()).hexdigest() for n in final}))
    with pytest.raises(Blocked,match='lane messages/isolation'):run(c)
    assert len(SimulatedTransport.calls)==2

def allowance(packet,now,root):
    return {'schema':'se6-v8-one-pair-allowance-v1','permit_id':'1'*32,'campaign_id':'fresh-v8-owner-pair','approved':True,'purpose':'ONE_MATCHED_NEMOTRON_PAIR','expires_at_utc':(now+timedelta(hours=1)).isoformat(),
      'allowed_question_hashes':[packet['question_sha256']],'packet_sha256':packet['packet_sha256'],'model_settings':packet['model'],'source_contract':packet['source_contract'],
      'claim_store_sha256':hashlib.sha256((os.path.normcase(str((root/'LIVE').resolve())) if os.name == 'nt' else str((root/'LIVE').resolve())).encode()).hexdigest(),
      'max_pairs':1,'max_calls':2,'max_output_tokens':MAX_OUTPUT,'max_input_bytes':49152,'usd_cap':'0.20','tariff':TARIFF}

def test_pinned_new_allowance_binds_question_settings_source_caps_without_key_read(tmp_path):
    now=datetime.fromisoformat(TARIFF['verified_date']).replace(tzinfo=timezone.utc);packet=prepare(QUESTION,'native',[],{'se6':[],'baseline':[]});permit=allowance(packet,now,tmp_path);path=tmp_path/'allowance.json';path.write_bytes(encoded(permit))
    called=[];c=RunBothCoordinator(tmp_path,approval_path=path,approval_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),live_enabled=True,credential_probe=lambda m:called.append(m),clock=lambda:now)
    assert c.allowance(packet)==permit and called==[]
    for key,value in [('campaign_id','mission-successor-v2'),('max_calls',3),('usd_cap','0.01'),('allowed_question_hashes',['0'*64]),('source_contract',{}),('model_settings',{})]:
        changed=dict(permit);changed[key]=value;path.write_bytes(encoded(changed));c.approval_sha256=hashlib.sha256(path.read_bytes()).hexdigest()
        with pytest.raises(Blocked):c.allowance(packet)
    assert called==[]

def test_stale_pricing_expired_and_earlier_approval_rejected(tmp_path):
    now=datetime.fromisoformat(TARIFF['verified_date']).replace(tzinfo=timezone.utc);packet=prepare(QUESTION,'native',[],{'se6':[],'baseline':[]});permit=allowance(packet,now,tmp_path);path=tmp_path/'allowance.json';path.write_bytes(encoded(permit));c=RunBothCoordinator(tmp_path,approval_path=path,approval_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),live_enabled=True,clock=lambda:now+timedelta(days=1))
    with pytest.raises(Blocked):c.allowance(packet)

def test_stale_quote_refused_while_otherwise_valid_allowance_is_unexpired(tmp_path):
    now=datetime.fromisoformat(TARIFF['verified_date']).replace(tzinfo=timezone.utc)
    packet=prepare(QUESTION,'native',[],{'se6':[],'baseline':[]})
    permit=allowance(packet,now,tmp_path)
    permit['expires_at_utc']=(now+timedelta(days=2)).isoformat()
    path=tmp_path/'permit.json';path.write_bytes(encoded(permit));called=[]
    coordinator=RunBothCoordinator(tmp_path,approval_path=path,
        approval_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),live_enabled=True,
        credential_probe=lambda model:called.append(model),clock=lambda:now+timedelta(days=1))
    with pytest.raises(Blocked,match='Pricing provenance stale'):
        coordinator.allowance(packet)
    assert called==[] and not (tmp_path/'LIVE').exists()

def test_copying_same_allowance_to_new_storage_cannot_reset_claims(tmp_path):
    now=datetime.fromisoformat(TARIFF['verified_date']).replace(tzinfo=timezone.utc);packet=prepare(QUESTION,'native',[],{'se6':[],'baseline':[]});path=tmp_path/'permit.json';path.write_bytes(encoded(allowance(packet,now,tmp_path/'original')))
    copied=tmp_path/'copy.json';copied.write_bytes(path.read_bytes());called=[]
    c=RunBothCoordinator(tmp_path/'new-store',approval_path=copied,approval_sha256=hashlib.sha256(copied.read_bytes()).hexdigest(),live_enabled=True,credential_probe=lambda m:called.append(m),clock=lambda:now)
    with pytest.raises(Blocked,match='different persistent claim store'):c.allowance(packet)
    assert called==[]

def test_changed_native_context_cannot_reuse_cached_request_id(tmp_path):
    c=RunBothCoordinator(tmp_path,transport_factory=SimulatedTransport);run(c)
    with pytest.raises(Blocked):c.run(TASK,REQUEST,QUESTION,'changed native context',{},[])
    assert len(SimulatedTransport.calls)==2

def test_model_mismatch_stops_pair_without_retry_or_winner(tmp_path):
    SimulatedTransport.wrong_model=True;c=RunBothCoordinator(tmp_path,transport_factory=SimulatedTransport)
    with pytest.raises(Pending):run(c)
    assert len(SimulatedTransport.calls)==1
    with pytest.raises(Pending):run(c)
    assert len(SimulatedTransport.calls)==1

def test_invalid_output_schema_frozen_unassessable_no_simulated_win(tmp_path):
    SimulatedTransport.invalid_schema=True;c=RunBothCoordinator(tmp_path,transport_factory=SimulatedTransport);result=run(c)['public']
    assert all(l['assessment']['status']=='UNASSESSABLE' for l in result['lanes'].values())
    assert result['arithmetic_winner'] is None and result['tariff_estimate_usd']==0 and result['simulated_tariff_estimate_usd']>0

def test_credential_probe_exception_does_not_escape_private_value(tmp_path):
    now=datetime.fromisoformat(TARIFF['verified_date']).replace(tzinfo=timezone.utc);packet=prepare(QUESTION,'Conditional native algebra only',[],{'se6':[],'baseline':[]});path=tmp_path/'permit.json';path.write_bytes(encoded(allowance(packet,now,tmp_path)))
    def broken(model):raise ValueError('PRIVATE_KEY_VALUE')
    c=RunBothCoordinator(tmp_path,approval_path=path,approval_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),live_enabled=True,credential_probe=broken,clock=lambda:now)
    with pytest.raises(Blocked) as error:run(c)
    assert 'PRIVATE_KEY_VALUE' not in str(error.value) and not list((tmp_path/'LIVE').rglob('reservation.json'))

def test_public_history_correction_and_transfer_truth_no_unannounced_replacement():
    corrected=derived_question('Correct E2 to b=4.\nDerive a relation involving a.',[QUESTION])
    value=json.loads(ANSWER);value['relation']['rhs']='10'
    assert assess(corrected,json.dumps(value))['score']==3
    transferred=derived_question('Derive a relation involving a.',[QUESTION,'Correct E2 to b=4.\nDerive a relation involving a.'])
    assert assess(transferred,json.dumps(value))['score']==3
    with pytest.raises(ValueError):derived_question('E2: b=5\nDerive a relation involving a.',[QUESTION])
    resolved=derived_question('Correct E2 to b=4.\nDerive a relation involving a.',[QUESTION,'E2: b=5\nDerive a relation involving a.'])
    assert assess(resolved,json.dumps(value))['score']==3

def test_business_price_correction_from_public_history_independent_parser():
    original='We completed 10 jobs. The original log recorded 28 technician-hours.\nbasic: 2 technician-hours, $3 materials cost, $10 customer revenue\ndeep: 4 technician-hours, $5 materials cost, $20 customer revenue\nThe materials budget is $35.'
    normalized=derived_question('Correct deep customer revenue to $25. Verify it.',[original])
    value={'business':{'original':{'allocations':{'basic':'6','deep':'4'},'revenue':'160','materials_cost':'38','gross_contribution':'122','budget_variance':'3','budget_exceeded':True}},'world_facts_verified':False,'execution_receipts':[]}
    assert assess(normalized,json.dumps(value))['score']==7

def test_prose_no_automatic_winner_and_duplicate_json_rational_bounded():
    assert assess('Recommend a strategy','good advice')['status']=='UNASSESSABLE'
    assert assess(QUESTION,'{"relation":{},"relation":{}}')['status']=='UNASSESSABLE'
    for token in ['1e1000000','9'*100000,True]:
        with pytest.raises(ValueError):rational(token)

def test_linear_exact_scalar_certificate_and_wrong_rhs():
    value=json.loads(ANSWER);value['relation']={'coefficients':{'a':'2'},'rhs':'22'};value['certificate']={'E1':'2','E2':'-2'}
    assert assess(QUESTION,json.dumps(value))['score']==3
    value['relation']['rhs']='21';assert assess(QUESTION,json.dumps(value))['score']==1

def test_business_independent_public_allocation_and_financial_arithmetic():
    question='We completed 10 jobs. The original log recorded 28 technician-hours.\nbasic: 2 technician-hours, $3 materials cost, $10 customer revenue\ndeep: 4 technician-hours, $5 materials cost, $20 customer revenue\nThe materials budget is $35.'
    value={'business':{'original':{'allocations':{'basic':'6','deep':'4'},'revenue':'140','materials_cost':'38','gross_contribution':'102','budget_variance':'3','budget_exceeded':True}},'world_facts_verified':False,'execution_receipts':[]}
    result=assess(question,json.dumps(value));assert result['status']=='ASSESSABLE' and result['score']==7
