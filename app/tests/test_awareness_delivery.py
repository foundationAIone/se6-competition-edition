"""Delivery guards only; injected TEST_ONLY callbacks do not establish Native effects."""
import hashlib,json,subprocess,threading,time
import pytest
from hosted_judge.awareness_service import AwarenessService

TOKEN='a'*64
OTHER='b'*64
RID='1'*32
REQUEST={'request_id':RID,'scenario':'dependency-self-v1'}

def safe_fixture():
    return {'phases':[],'comparative_result':'NOT_ESTABLISHED','resources':{},'source_hashes':{},
        'limitations':['TEST_ONLY service-guard callback; no Native or World execution']}

def terminal(service):
    deadline=time.monotonic()+3
    while time.monotonic()<deadline:
        value=service.get(TOKEN,RID)
        if value['status']!='RUNNING':return value
        time.sleep(.005)
    raise AssertionError('Controlled callback did not reach a terminal state')

def test_construction_and_read_ports_do_not_execute(tmp_path):
    calls=[]
    service=AwarenessService(tmp_path/'state',runner=lambda path:calls.append(path))
    assert not calls and not service.active(TOKEN)
    with pytest.raises(ValueError,match='AWARENESS_REQUEST_NOT_FOUND'):service.get(TOKEN,RID)
    assert not calls and not list(service.root.glob('*/claim.json'))

@pytest.mark.parametrize('value,code',[
    ({'request_id':RID,'scenario':'unrestricted-repair'},'AWARENESS_SCENARIO_UNSUPPORTED'),
    ({'request_id':'../outside','scenario':'dependency-self-v1'},'AWARENESS_REQUEST_ID'),
    ({'request_id':RID,'scenario':'dependency-self-v1','correct_patch':'caller answer'},'AWARENESS_REQUEST_FIELDS'),
    ({'scenario':'dependency-self-v1'},'AWARENESS_REQUEST_FIELDS'),
    (None,'AWARENESS_REQUEST_FIELDS')])
def test_request_scope_refusals_do_not_claim_or_run(tmp_path,value,code):
    calls=[];service=AwarenessService(tmp_path/'state',runner=lambda path:calls.append(path))
    with pytest.raises(ValueError,match=code):service.submit(TOKEN,value)
    assert not calls and not list(service.root.glob('*/claim.json'))

@pytest.mark.parametrize('token',['',None,'../escape','A'*64,'a'*63])
def test_invalid_session_cannot_claim_or_export(tmp_path,token):
    service=AwarenessService(tmp_path/'state',runner=lambda path:safe_fixture())
    with pytest.raises(ValueError,match='AWARENESS_SESSION_REQUIRED'):service.submit(token,REQUEST)
    with pytest.raises(ValueError,match='AWARENESS_SESSION_REQUIRED'):service.export(token,RID)
    assert not list(service.root.glob('*/claim.json'))

def test_once_only_duplicate_session_isolation_and_exact_export(tmp_path):
    entered=threading.Event();release=threading.Event();calls=[]
    def runner(path):
        calls.append(path);entered.set();assert release.wait(3);return safe_fixture()
    service=AwarenessService(tmp_path/'state',runner=runner)
    try:
        initial=service.submit(TOKEN,REQUEST);assert initial['status']=='RUNNING'
        assert entered.wait(2)
        assert service.submit(TOKEN,dict(REQUEST))['status']=='RUNNING'
        assert len(calls)==1
        with pytest.raises(ValueError,match='AWARENESS_REQUEST_NOT_FOUND'):service.get(OTHER,RID)
        with pytest.raises(ValueError,match='AWARENESS_REQUEST_NOT_FOUND'):service.export(OTHER,RID)
        with pytest.raises(ValueError,match='AWARENESS_SESSION_ALLOWANCE'):
            service.submit(TOKEN,{**REQUEST,'request_id':'2'*32})
    finally:release.set()
    done=terminal(service);assert done['status']=='COMPLETE' and done['comparative_result']=='NOT_ESTABLISHED'
    assert service.export(TOKEN,RID)=={**done,'export_format':'se6-awareness-public-v1'}
    assert service.submit(TOKEN,REQUEST)==done and len(calls)==1
    assert len(list(service.root.glob('*/claim.json')))==1
    assert all(TOKEN not in p.read_text() for p in service.root.rglob('*.json'))

def test_failure_is_sanitized_and_permanently_claimed(tmp_path):
    calls=[]
    def runner(path):calls.append(path);raise RuntimeError('SYNTHETIC_PRIVATE_EXCEPTION_DO_NOT_EXPOSE')
    service=AwarenessService(tmp_path/'state',runner=runner);service.submit(TOKEN,REQUEST)
    done=terminal(service)
    assert done['status']=='FAILED_CLOSED' and done['error_code']=='AWARENESS_EXECUTION_FAILED_NO_RETRY'
    assert 'SYNTHETIC_PRIVATE_EXCEPTION' not in json.dumps(service.export(TOKEN,RID))
    assert service.submit(TOKEN,REQUEST)==done and len(calls)==1

@pytest.mark.parametrize('payload',[
    {**safe_fixture(),'private_path':'C:/Users/synthetic/private.sqlite3'},
    {**safe_fixture(),'resources':{'api_key':'synthetic'}},
    {**safe_fixture(),'limitations':['C:/Users/synthetic/private.sqlite3']},
    {**safe_fixture(),'status':'NOT_A_TERMINAL_STATUS'}])
def test_unsafe_or_invalid_callback_output_fails_closed(tmp_path,payload):
    service=AwarenessService(tmp_path/'state',runner=lambda path:payload)
    service.submit(TOKEN,REQUEST);done=terminal(service)
    assert done['status']=='FAILED_CLOSED'
    public=json.dumps(service.export(TOKEN,RID));assert 'private.sqlite3' not in public and 'api_key' not in public

def test_timeout_reports_uncertainty_without_retry(tmp_path):
    calls=[]
    def runner(path):calls.append(path);raise subprocess.TimeoutExpired('TEST_ONLY',1)
    service=AwarenessService(tmp_path/'state',runner=runner);service.submit(TOKEN,REQUEST)
    done=terminal(service)
    assert done['status']=='INTERRUPTED' and done['error_code']=='AWARENESS_DEADLINE_NO_RETRY'
    assert service.submit(TOKEN,REQUEST)==done and len(calls)==1

def test_cold_recovery_cannot_overwrite_interruption_or_repeat_claim(tmp_path):
    entered=threading.Event();release=threading.Event();calls=[]
    def runner(path):calls.append(path);entered.set();assert release.wait(3);return safe_fixture()
    service=AwarenessService(tmp_path/'state',runner=runner)
    try:
        service.submit(TOKEN,REQUEST);assert entered.wait(2)
        recovered=AwarenessService(tmp_path/'state',runner=lambda path:pytest.fail('Interrupted request was re-executed'))
        value=recovered.get(TOKEN,RID)
        assert value['status']=='INTERRUPTED' and value['error_code']=='AWARENESS_INTERRUPTED_NO_RETRY'
        assert recovered.submit(TOKEN,REQUEST)==value
    finally:release.set()
    assert terminal(service)['status']=='INTERRUPTED' and len(calls)==1

def test_corrupt_durable_state_is_rejected(tmp_path):
    service=AwarenessService(tmp_path/'state',runner=lambda path:safe_fixture())
    service.submit(TOKEN,REQUEST);terminal(service)
    state=service.root/hashlib.sha256(TOKEN.encode()).hexdigest()/'state.json'
    value=json.loads(state.read_bytes());value['status']='RUNNING';state.write_text(json.dumps(value))
    with pytest.raises(ValueError):service.get(TOKEN,RID)

def test_shared_computation_slot_denial_creates_no_claim(tmp_path):
    shared=threading.BoundedSemaphore(1);assert shared.acquire(blocking=False)
    calls=[];service=AwarenessService(tmp_path/'state',runner=lambda path:calls.append(path),shared_slots=shared)
    with pytest.raises(ValueError,match='AWARENESS_SHARED_WORKER_BUSY'):service.submit(TOKEN,REQUEST)
    assert not calls and not list(service.root.glob('*/claim.json'))
    shared.release()

@pytest.mark.parametrize('value',[float('nan'),float('inf'),float('-inf')])
def test_nonfinite_measurement_fails_closed_without_stuck_running(tmp_path,value):
    service=AwarenessService(tmp_path/'state',runner=lambda path:{**safe_fixture(),'resources':{'cpu_seconds':value}})
    service.submit(TOKEN,REQUEST);done=terminal(service)
    assert done['status']=='FAILED_CLOSED'
    assert done['error_code']=='AWARENESS_EXECUTION_FAILED_NO_RETRY'
    assert service.submit(TOKEN,REQUEST)==done
