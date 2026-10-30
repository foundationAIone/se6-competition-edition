"""SIMULATED admission checks only. No live credential/provider/World work."""
import hashlib,json
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import pytest
from hosted_judge.model_pilot_gateway import PilotGateway,Blocked,MODEL,ENDPOINT,TOTAL_RESERVE,verified_usage

def save(p,v):p.write_text(json.dumps(v));return hashlib.sha256(p.read_bytes()).hexdigest()
class Fake:
    SIMULATED=True;calls=0;fail=False
    def __init__(self,model):pass
    def request(self,body,directory,timeout):
        Fake.calls+=1
        if Fake.fail:raise TimeoutError()
        return dict(text='{"type":"inspect"}',usage={},model=MODEL,response_id='SIMULATED')
@pytest.fixture
def rig(tmp_path,monkeypatch):
    Fake.calls=0;Fake.fail=False
    g=PilotGateway(tmp_path/'claims',spec_path=tmp_path/'spec',spec_sha256='0'*64,approval_path=tmp_path/'approval',approval_sha256='0'*64,transport_factory=Fake)
    s=dict(schema='se6-model-workflow-batch-v1',model=MODEL,endpoint=ENDPOINT,max_requests=36,max_output_tokens=2048,max_wire_input_bytes=24576,model_context_token_upper_bound=262144,max_tool_turns_per_stage=3,max_effects_per_stage=1,usd_cap='3.00',tariff={'input_usd_per_million':'0.30','output_usd_per_million':'0.90'},allowed_projects=['project-001','project-002','project-003'],claim_store_sha256=g.store_identity(),source_manifest_sha256='0'*64)
    g.spec_sha256=save(g.spec_path,s)
    a=dict(schema='se6-model-workflow-owner-decision-v1',permit_id='a'*32,owner_identifier='programmerONE',decision='APPROVE_ONE_PAIRED_MODEL_WORKFLOW_PILOT',approved=True,spec_sha256=g.spec_sha256,claim_store_sha256=g.store_identity(),expires_at_utc=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),max_requests=36,usd_cap='3.00',authorization_provenance={'kind':'SIMULATED_TEST_ONLY'})
    g.approval_sha256=save(g.approval_path,a)
    monkeypatch.setattr(g,'_check_sources',lambda spec:None) # Gate-unit fixture, not source admission.
    def credential(model):raise AssertionError('No simulation credential lookup')
    g._model_parts=(object(),SimpleNamespace(payload_bytes=lambda model,body:json.dumps(body).encode(),credential_status=credential),{},SimpleNamespace(public=lambda:dict(disk_matches_loaded=True)))
    r=dict(request_id='b'*32,messages=[dict(role='user',content='SIMULATED raw task')],project_id='project-001',stage=1,arm='conventional',turn=1)
    return g,s,a,r

def test_prepare_is_effect_free(rig):
    g,s,a,r=rig;p=g.prepare(r);assert p['request_metadata']['provider_calls']==0 and Fake.calls==0 and not g.root.exists()
def test_no_budget_no_call(rig):
    g,s,a,r=rig;g.simulated=False;g.live_enabled=False
    with pytest.raises(Blocked,match='BLOCKED_PENDING_EXACT_BUDGET'):g.invoke(g.prepare(r))
    assert not g.root.exists() and Fake.calls==0
@pytest.mark.parametrize('field,value',[('owner_identifier','programmeONE'),('approved',False),('spec_sha256','f'*64),('claim_store_sha256','e'*64),('max_requests',37),('usd_cap','4.00'),('expires_at_utc','2020-01-01T00:00:00+00:00'),('schema','se6-v8-one-pair-allowance-v1')])
def test_forged_or_old_approval_refused(rig,field,value):
    g,s,a,r=rig;a[field]=value;g.approval_sha256=save(g.approval_path,a)
    with pytest.raises(Blocked):g.invoke(g.prepare(r))
    assert Fake.calls==0

def test_caller_echo_not_authority(rig):
    g,s,a,r=rig
    with pytest.raises(Blocked):g.invoke(g.prepare(r),a)

def test_simulated_cell_exactly_once(rig):
    g,s,a,r=rig;p=g.prepare(r);assert g.invoke(p)['provider_calls']==0
    with pytest.raises(Blocked):g.invoke(p)
    assert Fake.calls==1

def test_uncertain_outcome_blocks_later_turn(rig):
    g,s,a,r=rig;Fake.fail=True
    with pytest.raises(Blocked):g.invoke(g.prepare(r))
    r['turn']=2
    with pytest.raises(Blocked):g.invoke(g.prepare(r))
    assert Fake.calls==1 and (g.root/'STOP.json').is_file()

def test_mutated_request_refused(rig):
    g,s,a,r=rig;p=g.prepare(r);r['messages'][0]['content']='Changed'
    with pytest.raises(Blocked):g.invoke(p)
    assert Fake.calls==0

def test_wire_cap_before_claim(rig):
    g,s,a,r=rig;r['messages'][0]['content']='x'*24577
    with pytest.raises(Blocked):g.prepare(r)
    assert Fake.calls==0 and not g.root.exists()

def test_source_mismatch_refused(rig,monkeypatch):
    g,s,a,r=rig
    def bad(s):raise Blocked('SOURCE_CHANGED')
    monkeypatch.setattr(g,'_check_sources',bad)
    with pytest.raises(Blocked,match='SOURCE_CHANGED'):g.invoke(g.prepare(r))

def test_fixture_cannot_become_live_authority(rig):
    g,s,a,r=rig;g.simulated=False;g.live_enabled=True
    with pytest.raises(Blocked,match='provenance'):g.invoke(g.prepare(r))
    assert Fake.calls==0

def test_conservative_cap(rig):
    g,s,a,r=rig;assert TOTAL_RESERVE<=3 and str(TOTAL_RESERVE)=='2.8975104'
    s['max_requests']=37;g.spec_sha256=save(g.spec_path,s)
    with pytest.raises(Blocked):g.prepare(r)

@pytest.mark.parametrize('usage',[None,{},dict(prompt_tokens=1,completion_tokens=1,total_tokens=3),dict(prompt_tokens=262145,completion_tokens=1,total_tokens=262146),dict(prompt_tokens=1,completion_tokens=2049,total_tokens=2050)])
def test_missing_invalid_or_overbudget_usage_refuses(usage):
    with pytest.raises(Blocked):verified_usage(usage)

def test_failed_outcome_without_stop_file_still_blocks(rig):
    g,s,a,r=rig;Fake.fail=True
    with pytest.raises(Blocked):g.invoke(g.prepare(r))
    (g.root/'STOP.json').unlink() # Reproduce crash window between outcome and STOP writes.
    r['turn']=2
    with pytest.raises(Blocked,match='Prior provider outcome'):g.invoke(g.prepare(r))
    assert Fake.calls==1
