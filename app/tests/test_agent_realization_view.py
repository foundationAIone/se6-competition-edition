"""Reader/session/UI guards only. TEST_ONLY records are not execution evidence."""
from copy import deepcopy
from pathlib import Path
import hashlib,json
import pytest
from hosted_judge import agent_realization_view as view
from hosted_judge.service import JudgeService,UnavailableError

ROOT=Path(__file__).resolve().parents[1]


def fixture_record():
    def phase(number,bridge):
        count=1 if number==2 and bridge else 2
        return dict(phase=number,pid=1000+number,goal=True,public_goal=20 if number==1 else 26,
            actual_effects=1,agent_implementation='TEST_ONLY reader fixture; no Native execution',
            configuration_mode='TEST_ONLY',capability_status='TEST_ONLY',
            configured_candidates=['candidate-'+str(x) for x in range(count)],candidate_count=count,
            memory_consumed=number==2 and bridge,cold_restored=number==2,verified_memory_id=None,
            entity_version=4 if number==1 else 11,entity_receipt_id='entity_commit_receipt_'+'a'*64,
            native_receipt_hash='b'*64,witness_sha256='c'*64,retained_state_sha256='d'*64,
            worker_wall_seconds=None,worker_cpu_seconds=None,peak_traced_python_bytes=None)
    return dict(schema=view.SCHEMA,status=view.STATUS,record_kind=view.KIND,provider_calls=0,
        source_manifest_sha256='1'*64,raw_result_sha256='2'*64,independent_review_sha256='3'*64,
        completion_repair=dict(description='TEST_ONLY reader fixture',tests=34,independent_checks=3,regrade=False),
        conditions=[dict(name=name,phases=[phase(1,name=='retained-bridge'),phase(2,name=='retained-bridge')])
            for name in ('retained-bridge','bridge-disabled')],limitations=['TEST_ONLY projection fixture, not a proof run'],
        production_connected=False,alpha_changed=False)


def save(tmp_path,value):
    path=tmp_path/'public-development.json';path.write_text(json.dumps(value),encoding='utf-8')
    return path,hashlib.sha256(path.read_bytes()).hexdigest()


def test_hash_pinned_reader_does_not_execute_or_modify_its_source(tmp_path):
    value=fixture_record();path,pin=save(tmp_path,value);before=path.read_bytes()
    assert view.load(path,pin)==value and path.read_bytes()==before
    assert len(value['conditions'])==2 and all(len(x['phases'])==2 for x in value['conditions'])


@pytest.mark.parametrize('fault',['hash','missing_pin','schema','kind','status','provider','production','alpha','regrade',
    'review_hash','condition','phase','bool_phase','candidate_count','bool_count','nonfinite'])
def test_unpinned_or_scope_inconsistent_records_fail_closed(tmp_path,fault):
    value=fixture_record()
    if fault=='schema':value['schema']='se6-model-workflow-view-v1'
    if fault=='kind':value['record_kind']='LIVE_MODEL_REASONING'
    if fault=='status':value['status']='GENERAL_NURSERY_COMPLETE'
    if fault=='provider':value['provider_calls']=1
    if fault=='production':value['production_connected']=True
    if fault=='alpha':value['alpha_changed']=True
    if fault=='regrade':value['completion_repair']['regrade']=True
    if fault=='review_hash':value['independent_review_sha256']=None
    if fault=='condition':value['conditions'][1]['name']='retained-bridge'
    if fault=='phase':value['conditions'][0]['phases'][1]['phase']=1
    if fault=='bool_phase':value['conditions'][0]['phases'][0]['phase']=True
    if fault=='candidate_count':value['conditions'][0]['phases'][0]['candidate_count']=7
    if fault=='bool_count':value['conditions'][0]['phases'][0]['candidate_count']=True
    if fault=='nonfinite':value['conditions'][0]['phases'][0]['worker_cpu_seconds']=float('nan')
    path,pin=save(tmp_path,value)
    if fault=='hash':pin='0'*64
    if fault=='missing_pin':pin=None
    with pytest.raises(ValueError):view.load(path,pin)


@pytest.mark.parametrize('private',['C:\\Users\\private-owner\\entity.sqlite3','C:/Users/private-owner/key',
    '/tmp/private/entity.sqlite3','/etc/owner-secret','file:///tmp/private/entity.sqlite3','\\\\private-server\\store'])
def test_private_workstation_paths_never_enter_the_public_projection(tmp_path,private):
    value=fixture_record();value['limitations'].append(private);path,pin=save(tmp_path,value)
    with pytest.raises(ValueError,match='Private development path'):view.load(path,pin)


@pytest.mark.parametrize('private',['session_token','cookie','csrf_token','nebius_api_key','owner_password'])
def test_nested_secret_material_never_enters_the_public_projection(tmp_path,private):
    value=fixture_record();value['conditions'][0]['phases'][0][private]='SECRET_NOT_FOR_EXPORT';path,pin=save(tmp_path,value)
    with pytest.raises(ValueError,match='Private development field'):view.load(path,pin)


def test_real_judge_session_required_and_reader_returns_a_defensive_copy(tmp_path):
    path,pin=save(tmp_path,fixture_record());service=JudgeService(None,None,None)
    service.agent_realization_evidence=view.load(path,pin)
    for token in (None,'bad'):
        with pytest.raises(PermissionError):service.read_agent_realization_evidence(token)
    token,_=service.new_session();session=service.sessions[token]
    before=(session.rounds,session.actions,session.attempts,deepcopy(session.requests))
    result=service.read_agent_realization_evidence(token);result['conditions'].clear()
    assert len(service.read_agent_realization_evidence(token)['conditions'])==2
    assert (session.rounds,session.actions,session.attempts,session.requests)==before
    assert service.native_available is False


def test_expired_session_or_unconfigured_record_cannot_disclose_evidence():
    now=[0.0];service=JudgeService(None,None,None,clock=lambda:now[0]);token,_=service.new_session()
    with pytest.raises(UnavailableError):service.read_agent_realization_evidence(token)
    now[0]=1e9
    with pytest.raises(PermissionError):service.read_agent_realization_evidence(token)


def test_view_uses_only_existing_authenticated_get_and_manual_text_rendering():
    script=(ROOT/'hosted_judge/static/agent-realization.js').read_text(encoding='utf-8')
    html=(ROOT/'hosted_judge/static/index.html').read_text(encoding='utf-8')
    service=(ROOT/'hosted_judge/service.py').read_text(encoding='utf-8')
    launcher=(ROOT/'tools/run_dashboard.py').read_text(encoding='utf-8')
    assert script.count('fetch(')==1 and "method: 'GET'" in script and 'same-origin' in script and 'no-store' in script
    assert 'POST' not in script and 'innerHTML' not in script and 'setInterval' not in script
    assert "addEventListener('click', read)" in script and 'textContent' in script
    assert '/api/agent-realization/evidence' in service and 'service.read_agent_realization_evidence(self.token())' in service
    assert 'READ SAVED DEVELOPMENT RECORD · NO EXECUTION' in html and 'agent-realization-read' in html
    assert '--agent-realization-evidence-sha256' in launcher and 'agent_realization_view.load' in launcher
    assert 'general agent nursery' in script and 'new model benchmark' in script
