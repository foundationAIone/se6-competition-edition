"""Local mock HTTP and bounded sessions; actual native tests use private QA copy."""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import pytest
from hosted_judge import service as h
from hosted_judge.native_adapter import validate_bundle
from hosted_judge.review import load_review


def minimal_bundle(tmp_path):
    root=tmp_path/'bundle';(root/'src').mkdir(parents=True)
    (root/'src/__init__.py').write_bytes(b'')
    raw=json.dumps({'src/__init__.py':hashlib.sha256(b'').hexdigest()}).encode()
    manifest=tmp_path/'manifest.json';manifest.write_bytes(raw)
    return root,manifest,hashlib.sha256(raw).hexdigest()


@pytest.fixture
def app(tmp_path):
    calls=[];clock=[0.0]
    def fake(values):
        calls.append(values)
        return {'checkpoint':{'own_task':values[-2],'question':values[3]},'operations':1,
            'public':{'answer':values[3],'provider_calls':0}}
    service=h.JudgeService(*minimal_bundle(tmp_path),clock=lambda:clock[0],executor=fake)
    return service,calls,clock


def test_sessions_isolate_state_and_idempotence(app):
    service,calls,clock=app;a,aa=service.new_session();b,bb=service.new_session()
    value={'question':'Remember: Orion priority is proof.','request_id':'1'*32}
    out=service.run(a,aa['csrf_token'],value)
    assert service.run(a,aa['csrf_token'],value)==out and len(calls)==1
    assert service.sessions[b].checkpoint is None
    assert service.sessions[a].checkpoint['own_task']!=service.sessions[b].task_id
    with pytest.raises(ValueError):service.run(a,aa['csrf_token'],{**value,'question':'changed'})
    with pytest.raises(PermissionError):service.run(b,aa['csrf_token'],value)
    assert len(calls)==1


def test_failure_and_expiry_do_not_commit_native_state(app):
    service,calls,clock=app;token,data=service.new_session()
    def fail(values):raise h.LimitError('deadline')
    service.executor=fail
    with pytest.raises(h.LimitError):service.run(token,data['csrf_token'],{'question':'x=1','request_id':'a'*32})
    assert service.sessions[token].checkpoint is None and not service.sessions[token].busy
    service.executor=lambda values: (clock.__setitem__(0,601) or {'checkpoint':{'changed':True},'operations':1,'public':{}})
    with pytest.raises(h.LimitError):service.run(token,data['csrf_token'],{'question':'x=1','request_id':'b'*32})
    assert service.sessions[token].checkpoint is None


def test_session_reset_never_changes_another_user_or_busy_state(app):
    service,calls,clock=app;a,aa=service.new_session();b,bb=service.new_session()
    service.sessions[a].busy=True
    with pytest.raises(h.LimitError):service.reset(a,aa['csrf_token'])
    service.sessions[a].busy=False
    new,data=service.reset(a,aa['csrf_token'])
    assert a not in service.sessions and b in service.sessions and new in service.sessions
    assert service.sessions[new].checkpoint is None and data['native_available']
    assert not calls


def test_reset_preserves_ttl_rate_and_total_action_budget(app):
    service,calls,clock=app;token,data=service.new_session();s=service.sessions[token]
    s.actions=19;s.attempts=7;s.checkpoint={'old':'own state'};s.requests={'a':('digest',{})};s.rounds=4;s.request_times=[0.0]
    clock[0]=10
    fresh,info=service.reset(token,data['csrf_token'])
    after=service.sessions[fresh]
    assert after.expires==600 and after.actions==19 and after.request_times==[0.0,10]
    assert after.checkpoint is None and after.requests=={} and after.rounds==0
    assert info['remaining_actions']==1 and info['expires_in_seconds']==590
    assert info['remaining_attempts']==1 and after.attempts==7


def test_failed_attempts_irrevocably_consume_compute_quota(app):
    service,calls,clock=app;token,data=service.new_session()
    service.executor=lambda values: (_ for _ in ()).throw(h.LimitError('timeout'))
    for i in range(h.MAX_ATTEMPTS):
        with pytest.raises(h.LimitError):service.run(token,data['csrf_token'],{'question':'attempt','request_id':str(i)*32})
        clock[0]+=8
    assert service.sessions[token].attempts==h.MAX_ATTEMPTS
    fresh,info=service.reset(token,data['csrf_token'])
    assert info['remaining_attempts']==0
    with pytest.raises(h.LimitError):service.run(fresh,info['csrf_token'],{'question':'still capped','request_id':'a'*32})


def test_duplicate_session_cookie_rejected_not_last_wins(http):
    req,app=http;headers=credentials(http);headers['Cookie']+='; '+headers['Cookie']
    assert req('/api/run','POST',headers,b'{}')[0]==403 and not app[1]


def test_loopback_development_binds_only_127_and_omits_secure_cookie(app,monkeypatch):
    class NoSocket:
        def __init__(self,address,handler):self.address=address;self.server_port=address[1];self.RequestHandlerClass=handler
    monkeypatch.setattr(h,'ThreadingHTTPServer',NoSocket)
    server=h.make_server(app[0],'http://127.0.0.1:8088',Path(h.__file__).with_name('static'),8088,loopback_development=True)
    assert server.address==('127.0.0.1',8088)
    raw=b'GET /api/session HTTP/1.1\r\nHost: 127.0.0.1:8088\r\nConnection: close\r\n\r\n'
    connection=Connection(raw);server.RequestHandlerClass(connection,('127.0.0.1',1),server)
    output=connection.output.getvalue();head,body=output.split(b'\r\n\r\n',1)
    assert b' 200 ' in head and b'HttpOnly; SameSite=Strict' in head and b'Secure;' not in head
    assert json.loads(body)['loopback_development'] is True
    assert server.public_origin=='http://127.0.0.1:8088'


@pytest.mark.parametrize('value',['http://0.0.0.0:8088','http://localhost:8088','https://127.0.0.1:8088','http://127.0.0.1:8089'])
def test_dev_flag_cannot_weaken_external_origin_boundary(value):
    with pytest.raises(ValueError):h.public_origin(value,loopback_development=True,port=8088)


def test_round_and_global_worker_caps(app):
    service,calls,clock=app;token,data=service.new_session()
    for i in range(4):service.run(token,data['csrf_token'],{'question':'question '+str(i),'request_id':str(i)*32})
    with pytest.raises(h.LimitError):service.run(token,data['csrf_token'],{'question':'fifth','request_id':'5'*32})
    other,oo=service.new_session()
    assert service.workers.acquire(False) and service.workers.acquire(False)
    try:
        with pytest.raises(h.LimitError):service.run(other,oo['csrf_token'],{'question':'capacity','request_id':'6'*32})
    finally:service.workers.release();service.workers.release()
    assert len(calls)==4


def test_request_body_cannot_supply_state_or_escalate_authority(app):
    service,calls,clock=app;token,data=service.new_session()
    for value in [{'question':'x=1','request_id':'a'*32,'checkpoint':{}},
                  {'question':'x'*4097,'request_id':'a'*32}, {'question':'ok','request_id':'../../path'}]:
        with pytest.raises(ValueError):service.run(token,data['csrf_token'],value)
    assert not calls


def test_bounded_session_capacity_and_unavailable_native_truth(app):
    service,calls,clock=app
    for i in range(h.MAX_SESSIONS):service.new_session()
    with pytest.raises(h.LimitError):service.new_session()
    clock[0]=h.SESSION_TTL+1;service.new_session();assert len(service.sessions)==1
    missing=h.JudgeService(None,None,None);token,data=missing.new_session()
    with pytest.raises(h.UnavailableError):missing.run(token,data['csrf_token'],{'question':'ordinary question','request_id':'a'*32})


def test_source_pin_mutation_and_path_escape_rejected(tmp_path):
    root,manifest,digest=minimal_bundle(tmp_path)
    (root/'src/__init__.py').write_bytes(b'changed')
    with pytest.raises(ValueError):validate_bundle(root,manifest,digest)
    raw=json.dumps({'src/__init__.py':hashlib.sha256(b'changed').hexdigest(),'../escape':'0'*64}).encode()
    manifest.write_bytes(raw)
    with pytest.raises(ValueError):validate_bundle(root,manifest,hashlib.sha256(raw).hexdigest())


class Connection:
    def __init__(self,raw):self.input=io.BytesIO(raw);self.output=io.BytesIO()
    def makefile(self,*args):return self.input
    def sendall(self,data):self.output.write(data)
    def settimeout(self,*args):pass


@pytest.fixture
def http(app,monkeypatch):
    class NoSocketServer:
        def __init__(self,address,handler):self.RequestHandlerClass=handler;self.server_port=address[1]
    monkeypatch.setattr(h,'ThreadingHTTPServer',NoSocketServer)
    server=h.make_server(app[0],'https://judge.example.com',Path(h.__file__).with_name('static'))
    def request(path='/api/session',method='GET',headers=None,body=b''):
        fields={'Host':'judge.example.com'};fields.update(headers or {})
        if body:fields.setdefault('Content-Length',str(len(body)));fields.setdefault('Content-Type','application/json')
        raw=(method+' '+path+' HTTP/1.1\r\n'+''.join(k+': '+v+'\r\n' for k,v in fields.items())+'\r\n').encode()+body
        connection=Connection(raw);server.RequestHandlerClass(connection,('127.0.0.1',1),server)
        head,value=connection.output.getvalue().split(b'\r\n\r\n',1)
        status=int(head.split(b' ')[1]);return status,head,json.loads(value) if path not in ('/','/app.js','/style.css') else value
    return request,app


def credentials(http):
    req,app=http;status,head,data=req()
    assert status==200 and b'HttpOnly; Secure; SameSite=Strict' in head
    cookie=next(line.split(b': ',1)[1].split(b';',1)[0].decode() for line in head.split(b'\r\n') if line.startswith(b'Set-Cookie:'))
    return {'Origin':'https://judge.example.com','Cookie':cookie,'X-Judge-CSRF':data['csrf_token']}


@pytest.mark.parametrize('change',[{'Host':'attacker.example.com'},{'Origin':'https://evil.example'}, {'Origin':'null'}, {'X-Judge-CSRF':'bad'}, {'Cookie':'se6_judge_session=bad'}])
def test_exact_https_host_origin_cookie_csrf_before_native(http,change):
    req,app=http;headers=credentials(http);headers.update(change)
    status,head,data=req('/api/run','POST',headers,json.dumps({'question':'x=1','request_id':'a'*32}).encode())
    assert status==403 and not app[1]


@pytest.mark.parametrize('path',['/api/campaign','/api/settings','/api/shell','/api/dispatch','/api/run/../../private'])
def test_unknown_effectful_routes_not_available(http,path):
    req,app=http;headers=credentials(http)
    assert req(path,'POST',headers,b'{}')[0]==404 and not app[1]


@pytest.mark.parametrize('body',[b'{"question":"a","question":"b","request_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}',b'{"question":NaN}',b'[]'])
def test_untrusted_json_rejected_without_execution(http,body):
    req,app=http;assert req('/api/run','POST',credentials(http),body)[0]==400 and not app[1]


def test_no_cross_site_session_api_or_forwarded_host_trust(http):
    req,app=http
    assert req('/api/session',headers={'Sec-Fetch-Site':'cross-site'})[0]==403
    assert req('/api/session',headers={'Host':'evil','X-Forwarded-Host':'judge.example.com'})[0]==403


@pytest.mark.parametrize('change',[{'Origin':'https://judge.example.com\r\nOrigin: https://evil.example'},
    {'Host':'judge.example.com\r\nHost: evil.example'}])
def test_duplicate_security_headers_rejected(http,change):
    req,app=http;headers=credentials(http);headers.update(change)
    assert req('/api/run','POST',headers,b'{}')[0]==403 and not app[1]


@pytest.mark.parametrize('change',[{'Transfer-Encoding':'chunked'},{'Content-Length':'2\r\nContent-Length: 3'}, {'Content-Length':'9000'}])
def test_ambiguous_or_oversized_framing_rejected(http,change):
    req,app=http;headers=credentials(http);headers.update(change)
    assert req('/api/run','POST',headers,b'{}')[0]==400 and not app[1]


def test_read_only_frozen_review_does_not_create_native_operations(http):
    req,app=http;status,head,data=req('/api/review')
    assert status==200 and data['records']==[] and not app[1]


def test_health_probe_discloses_no_session_state_or_source(http):
    req,app=http
    status,head,data=req('/healthz',headers={'Host':'internal-health-probe'})
    assert status==200 and data=={'status':'ok','scope':'HOSTED_NATIVE_ONLY','provider_calls':0}
    assert b'Set-Cookie' not in head and not app[1] and not app[0].sessions
    assert req('/api/session',headers={'Host':'internal-health-probe'})[0]==403


def test_public_score_projection_cannot_contain_raw_or_secret_fields(tmp_path):
    raw=json.dumps({'schema':'se6-public-frozen-score-review-v1','records':[{'authorization':'SYNTHETIC_PRIVATE'}]}).encode()
    file=tmp_path/'review.json';file.write_bytes(raw)
    with pytest.raises(ValueError):load_review(file,hashlib.sha256(raw).hexdigest())


@pytest.mark.parametrize('change',['winner','case','capture_count','duplicate_case','maximum'])
def test_public_projection_consistency_rejects_clerical_false_results(tmp_path,change):
    record={'campaign':'mission-first-linear-v1','scorer_sha256':'a'*64,'public_evidence_manifest_sha256':'b'*64,
        'scores':[{'case':'first-linear','se6':None,'baseline':0,'maximum':3,'winner':None,'correction_retention':None}],
        'measurements':{'captured_requests':2,'tariff_estimate_usd':0.0008922,'actual_billed_usd':None}}
    if change=='winner':record['scores'][0]['winner']='se6'
    elif change=='case':record['scores'][0]['case']='mixed-business/0'
    elif change=='capture_count':record['measurements']['captured_requests']=6
    elif change=='maximum':record['scores'][0]['maximum']=16
    else:record['scores'].append(deepcopy(record['scores'][0]))
    raw=json.dumps({'schema':'se6-public-frozen-score-review-v1','records':[record]}).encode()
    path=tmp_path/'review.json';path.write_bytes(raw)
    with pytest.raises(ValueError):load_review(path,hashlib.sha256(raw).hexdigest())


@pytest.mark.parametrize('origin',['http://judge.example.com','https://user:password@judge.example.com','https://judge.example.com/a','https://judge.example.com:8443'])
def test_origin_configuration_rejects_weaker_modes(origin):
    with pytest.raises(ValueError):h.public_origin(origin)
