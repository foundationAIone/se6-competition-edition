"""Independent synthetic campaign boundary review; no held-out input or model."""
import hashlib,json,sys
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'private-native')]
from hosted_judge import benchmark_campaign as campaign
from hosted_judge.v8_run_both import digest
SOURCE=ROOT

def packet():
    tasks=[];controls={}
    for i,ident in enumerate(campaign.PILOT_IDS):
        phases=[{'id':'dev1','public_question':'SYNTHETIC DEVELOPMENT: insufficient conditional data.'}]
        if i==1:phases.append({'id':'dev2','public_question':'SYNTHETIC DEVELOPMENT: changed incomplete data.'})
        tasks.append({'id':ident,'category':'development','phases':phases})
        controls[ident]={c:{'task_id':ident,'condition':c,'provider_calls':0,'model_status':'NOT_EXECUTED',
            'phase_records':[{'status':'UNRESOLVED','response':'SYNTHETIC ONLY: insufficient data.','public':{}} for _ in phases]}
            for c in ('B','C','D')}
    return campaign.prepare_pilot(tasks,controls,SOURCE,suite_sha256='1'*64,scorer_sha256='2'*64)

class SyntheticTransport:
    SIMULATED=True
    requests=0
    def __init__(self,settings):self.settings=settings
    def request(self,body,directory,timeout):
        SyntheticTransport.requests+=1
        _,router=campaign.dependencies()
        raw=router.payload_bytes(self.settings,body)
        (directory/'request.json').write_bytes(raw)
        text='{"status":"UNDERDETERMINED","world_facts_verified":false,"execution_receipts":[]}'
        provider=json.dumps({'id':'SYNTHETIC_NOT_REAL_MODEL_EVIDENCE','model':campaign.MODEL,
            'choices':[{'index':0,'message':{'role':'assistant','content':text},'finish_reason':'stop'}],
            'usage':{'prompt_tokens':10,'completion_tokens':20,'total_tokens':30,
                'completion_tokens_details':{'reasoning_tokens':0}}}).encode()
        (directory/'provider.json').write_bytes(provider)
        (directory/'returned-text.txt').write_bytes(text.encode())
        return router.parse_nebius_completion(provider,campaign.MODEL,provider_reasoning_control=self.settings.provider_reasoning_control)

@pytest.fixture(autouse=True)
def no_network_or_credentials(monkeypatch,tmp_path):
    global SOURCE
    SOURCE=tmp_path/'exact_minimal_source'
    names=('hosted_judge/benchmark_campaign.py','hosted_judge/benchmark_controls.py',
        'hosted_judge/benchmark_scoring.py','hosted_judge/recursive_controller.py',
        'private-native/src/workbench/provider_router.py','private-native/src/workbench/provider_reasoning_control.py',
        'private-native/src/workbench/models.py','native-manifest.json')
    pins={}
    for name in names:
        raw=(ROOT/name).read_bytes();p=SOURCE/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
        pins[name]=hashlib.sha256(raw).hexdigest()
    (SOURCE/'COMPLETE_SOURCE_MANIFEST_PRIVATE.json').write_text(json.dumps({'file_count':len(pins)+1,'files':pins}))
    import socket
    def deny(*a,**k):raise AssertionError('Synthetic review forbids network/credential lookup')
    monkeypatch.setattr(socket.socket,'connect',deny)
    monkeypatch.setattr(socket,'create_connection',deny)
    monkeypatch.setattr(socket,'getaddrinfo',deny)
    _,router=campaign.dependencies()
    monkeypatch.setattr(router,'credential_status',deny)
    SyntheticTransport.requests=0

def test_real_parser_shape_accepts_sixteen_synthetic_responses(tmp_path):
    result=campaign.PilotCoordinator(tmp_path/'store',SOURCE,transport_factory=SyntheticTransport).run(packet())
    assert result['status']=='COMPLETE_AWAITING_INDEPENDENT_SCORE',result
    assert result['provider_calls']==0 and result['captured_complete_responses']==16
    assert SyntheticTransport.requests==16
    assert all(r['input_tokens']==10 and r['completion_tokens']==20 and r['total_tokens']==30 for r in result['rows'])

def test_blocked_default_never_claims_or_consults_credentials(tmp_path):
    with pytest.raises(Exception,match='approval absent'):
        campaign.PilotCoordinator(tmp_path/'store',SOURCE).run(packet())
    assert not tmp_path.joinpath('store/LIVE').exists() and SyntheticTransport.requests==0

def test_permanent_reservation_forbids_second_simulation(tmp_path):
    c=campaign.PilotCoordinator(tmp_path/'store',SOURCE,transport_factory=SyntheticTransport);p=packet()
    c.run(p);calls=SyntheticTransport.requests
    with pytest.raises(Exception,match='already reserved'):c.run(p)
    assert SyntheticTransport.requests==calls

class TamperedWire(SyntheticTransport):
    def request(self,body,directory,timeout):
        result=super().request(body,directory,timeout)
        (directory/'request.json').write_bytes(b'{"UNAPPROVED":"different request"}')
        return result

def test_raw_request_tamper_stops_without_second_call(tmp_path):
    r=campaign.PilotCoordinator(tmp_path/'store',SOURCE,transport_factory=TamperedWire).run(packet())
    assert r['status']=='UNASSESSABLE_PARTIAL_CAMPAIGN' and r['captured_complete_responses']==0
    assert SyntheticTransport.requests==1

class TamperedReturnedText(SyntheticTransport):
    def request(self,body,directory,timeout):
        result=super().request(body,directory,timeout)
        (directory/'returned-text.txt').write_bytes(b'{"status":"FORGED"}')
        return result

def test_returned_text_tamper_stops_without_second_call(tmp_path):
    r=campaign.PilotCoordinator(tmp_path/'store',SOURCE,transport_factory=TamperedReturnedText).run(packet())
    assert r['status']=='UNASSESSABLE_PARTIAL_CAMPAIGN' and r['captured_complete_responses']==0
    assert SyntheticTransport.requests==1

def test_fixed_matrix_rejects_missing_declared_task(tmp_path):
    p=packet()
    for call in p['calls']:
        call['task_id']=campaign.PILOT_IDS[0]
        call['phase_id']=call['id'].split('-')[-2]+'_'+str(call['phase_index'])+'_'+str(p['calls'].index(call)//4)
    p['packet_sha256']=digest({k:v for k,v in p.items() if k!='packet_sha256'})
    with pytest.raises(Exception):campaign.validate_packet(p,SOURCE)

@pytest.mark.parametrize('key,value',[('provider_calls',1),('combined_completion_tokens',2048),('combined_input_bytes',1),('retries',1)])
def test_packet_limits_cannot_misdescribe_actual_dispatch(key,value):
    p=packet();p['limits'][key]=value
    p['packet_sha256']=digest({k:v for k,v in p.items() if k!='packet_sha256'})
    with pytest.raises(Exception):campaign.validate_packet(p,SOURCE)

@pytest.mark.parametrize('fault',['length','reasoning','usage_sum','usage_bool','malformed','timeout'])
def test_fault_stops_campaign_and_never_retries(fault,tmp_path):
    class Fault(SyntheticTransport):
        def request(self,body,directory,timeout):
            if fault=='timeout':
                SyntheticTransport.requests+=1;raise TimeoutError('SYNTHETIC timeout no provider')
            result=super().request(body,directory,timeout)
            if fault=='malformed':(directory/'provider.json').write_bytes(b'{');return result
            data=json.loads((directory/'provider.json').read_bytes())
            if fault=='length':data['choices'][0]['finish_reason']='length'
            if fault=='reasoning':data['usage']['completion_tokens_details']['reasoning_tokens']=1
            if fault=='usage_sum':data['usage']['total_tokens']=31
            if fault=='usage_bool':data['usage']['prompt_tokens']=True
            raw=json.dumps(data).encode();(directory/'provider.json').write_bytes(raw)
            _,router=campaign.dependencies()
            return router.parse_nebius_completion(raw,campaign.MODEL,provider_reasoning_control=self.settings.provider_reasoning_control)
    c=campaign.PilotCoordinator(tmp_path/'store',SOURCE,transport_factory=Fault);p=packet();r=c.run(p)
    assert r['status']=='UNASSESSABLE_PARTIAL_CAMPAIGN' and r['captured_complete_responses']==0
    assert r['provider_calls']==0 and r['reserved_calls']==16 and r['failure']['retry_allowed'] is False
    assert SyntheticTransport.requests==1
    with pytest.raises(Exception,match='already reserved'):c.run(p)
    assert SyntheticTransport.requests==1

def test_changed_pinned_source_stops_before_claim(tmp_path):
    p=packet();(SOURCE/'hosted_judge/recursive_controller.py').write_bytes(b'SYNTHETIC_CHANGED_SOURCE_NOT_EXECUTED')
    with pytest.raises(Exception,match='source.*changed'):
        campaign.PilotCoordinator(tmp_path/'store',SOURCE,transport_factory=SyntheticTransport).run(p)
    assert SyntheticTransport.requests==0 and not (tmp_path/'store').exists()

def test_source_change_after_first_response_stops_remaining_calls(tmp_path):
    class Change(SyntheticTransport):
        def request(self,body,directory,timeout):
            result=super().request(body,directory,timeout)
            (SOURCE/'hosted_judge/recursive_controller.py').write_bytes(b'SYNTHETIC_CHANGED_SOURCE_NOT_EXECUTED')
            return result
    result=campaign.PilotCoordinator(tmp_path/'store',SOURCE,transport_factory=Change).run(packet())
    assert result['status']=='UNASSESSABLE_PARTIAL_CAMPAIGN' and result['captured_complete_responses']==1
    assert SyntheticTransport.requests==1

def allowance(tmp_path,clock):
    from datetime import timedelta
    p=packet();path=tmp_path/'SYNTHETIC_APPROVAL_NOT_OWNER_AUTHORITY.json'
    c=campaign.PilotCoordinator(tmp_path/'store',SOURCE,approval_path=path,live_enabled=True,clock=lambda:clock)
    value={'schema':'se6-v11-heldout-pilot-allowance-v1','approved':True,'permit_id':'3'*32,
        'campaign':campaign.CAMPAIGN,'packet_sha256':p['packet_sha256'],'source_contract':p['source_contract'],
        'store_sha256':c.store_identity(),'expires_at_utc':(clock+timedelta(hours=1)).isoformat(),'limits':p['limits'],
        'tariff':{'verified_date':clock.date().isoformat(),'input_usd_per_million':'0.30','output_usd_per_million':'0.90',
            'source':'https://nebius.com/services/token-factory/models/nvidia-nemotron-models-inference'}}
    return p,c,path,value

@pytest.mark.parametrize('fault',['expired','old_date','source','store','usd_cap'])
def test_exact_authorizer_rejects_changed_approval_without_key_lookup(tmp_path,fault):
    from datetime import datetime,timezone,timedelta
    clock=datetime(2026,10,11,20,0,tzinfo=timezone.utc);p,c,path,value=allowance(tmp_path,clock)
    if fault=='expired':value['expires_at_utc']=(clock-timedelta(seconds=1)).isoformat()
    if fault=='old_date':value['tariff']['verified_date']='2026-10-10'
    if fault=='source':value['source_contract']={}
    if fault=='store':value['store_sha256']='0'*64
    if fault=='usd_cap':value['limits']={**value['limits'],'usd_cap':'0.01'}
    path.write_text(json.dumps(value));c.approval_sha256=hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(Exception):c.authorize(p)
    assert SyntheticTransport.requests==0 and not (tmp_path/'store').exists()

@pytest.mark.parametrize('fault',['extra','missing','wrong_count'])
def test_complete_source_exact_inventory_and_manifest_count(fault):
    if fault=='extra':(SOURCE/'UNMANIFESTED.py').write_text('SYNTHETIC unexecuted extra')
    if fault=='missing':(SOURCE/'hosted_judge/recursive_controller.py').unlink()
    if fault=='wrong_count':
        path=SOURCE/'COMPLETE_SOURCE_MANIFEST_PRIVATE.json';value=json.loads(path.read_bytes())
        value['file_count']-=1;path.write_text(json.dumps(value))
    with pytest.raises(Exception):campaign.verify_complete_source(SOURCE)

def test_known_live_claim_blocks_before_any_credential_probe(tmp_path):
    from datetime import datetime,timezone
    p,c,path,value=allowance(tmp_path,datetime(2026,10,11,20,0,tzinfo=timezone.utc))
    path.write_text(json.dumps(value));c.approval_sha256=hashlib.sha256(path.read_bytes()).hexdigest()
    c.root.mkdir(parents=True)
    (c.root/(campaign.CAMPAIGN+'.claim.json')).write_text(json.dumps({'status':'SYNTHETIC_ALREADY_RESERVED'}))
    # Autouse credential hook raises AssertionError if consulted. Only the
    # expected spent-claim exception proves rejection precedes consultation.
    with pytest.raises(Exception,match='already reserved'):
        c.run(p)
    assert SyntheticTransport.requests==0 and not (c.root/campaign.CAMPAIGN).exists()
