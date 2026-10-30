"""Read-only display acceptance; actual captures never become a new model run."""
from pathlib import Path
from copy import deepcopy
import hashlib,json,sys,threading,http.client
import pytest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from hosted_judge.benchmark_view import load_benchmark
from hosted_judge.service import JudgeService,make_server

def actual():return json.loads((ROOT/'heldout/benchmark-public-view.json').read_bytes())
def saved(tmp,value):
    path=tmp/'public.json';path.write_text(json.dumps(value));return path,hashlib.sha256(path.read_bytes()).hexdigest()

def test_actual_frozen16_remain_separate_from_original30(tmp_path):
    value=actual();path,pin=saved(tmp_path,value);loaded=load_benchmark(path,pin)
    assert len(loaded['tasks'])==30 and len(loaded['live_pilot']['rows'])==16
    assert loaded['provider_calls']==0 and loaded['live_pilot']['fresh_provider_calls_on_view']==0
    assert loaded['live_pilot']['overall_winner'] is None
    assert [loaded['live_pilot']['aggregates'][a]['complete_successes'] for a in 'ABCD']==[0,1,1,1]
    assert all(r['conditions']['A']['model_status']=='NOT_EXECUTED' for r in loaded['tasks'])

@pytest.mark.parametrize('fault',['winner','fresh','partial','duplicate','private','invalid_status'])
def test_readonly_frozen_view_refuses_false_claims_or_private_data(tmp_path,fault):
    value=deepcopy(actual());pilot=value['live_pilot']
    if fault=='winner':pilot['overall_winner']='C'
    if fault=='fresh':pilot['fresh_provider_calls_on_view']=16
    if fault=='partial':pilot['rows'].pop()
    if fault=='duplicate':pilot['rows'][-1]=deepcopy(pilot['rows'][0])
    if fault=='private':pilot['rows'][0]['actual_answer_text']='C:/Users/private-owner/token'
    if fault=='invalid_status':pilot['rows'][0]['official_status']='INFERRED_WIN'
    path,pin=saved(tmp_path,value)
    with pytest.raises(ValueError):load_benchmark(path,pin)

def test_actual_http_view_returns_frozen_answers_without_action(tmp_path):
    value=actual();path,pin=saved(tmp_path,value);service=JudgeService(None,None,None,benchmark=load_benchmark(path,pin))
    def forbidden(*a,**kw):raise AssertionError('Read-only evidence must not submit work')
    service.submit=forbidden
    server=make_server(service,'http://127.0.0.1:0',ROOT/'hosted_judge/static',0,loopback_development=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5);conn.request('GET','/api/benchmark')
        response=conn.getresponse();data=json.loads(response.read());conn.close()
        assert response.status==200 and data['live_pilot']['rows']==value['live_pilot']['rows']
        assert data['live_pilot']['provider_calls_in_frozen_campaign']==16
        assert data['live_pilot']['fresh_provider_calls_on_view']==0
    finally:server.shutdown();server.server_close();thread.join()
