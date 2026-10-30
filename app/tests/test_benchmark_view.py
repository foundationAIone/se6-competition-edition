import hashlib,json,sys,threading,http.client
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from hosted_judge.benchmark_view import load_benchmark,BenchmarkTaskRunner
from hosted_judge.service import JudgeService,make_server

def view():
    return {'schema':'se6-v11-benchmark-view-v1','status':'FROZEN_OFFLINE','provider_calls':0,
        'tasks':[{'id':f'dev-{i}','category':'development','phases':1,'conditions':{c:{'model_status':'NOT_EXECUTED','native_status':'UNASSESSABLE'} for c in 'ABCD'}} for i in range(30)]}

def saved(tmp,value):
    path=tmp/'view.json';path.write_text(json.dumps(value));return path,hashlib.sha256(path.read_bytes()).hexdigest()

def test_hash_pinned_offline_view_and_no_model_fabrication(tmp_path):
    path,pin=saved(tmp_path,view());assert len(load_benchmark(path,pin)['tasks'])==30
    with pytest.raises(ValueError):load_benchmark(path,'0'*64)
    assert load_benchmark(None,None)['status']=='NOT_CONFIGURED'

@pytest.mark.parametrize('fault',['model','private','calls','duplicate'])
def test_rejects_false_model_evidence_private_records_and_denominator_tampering(tmp_path,fault):
    value=view()
    if fault=='model':value['tasks'][0]['conditions']['C']['model_status']='LIVE'
    if fault=='private':value['private_approval']='secret'
    if fault=='calls':value['provider_calls']=2
    if fault=='duplicate':value['tasks'][-1]['id']=value['tasks'][0]['id']
    path,pin=saved(tmp_path,value)
    with pytest.raises(ValueError):load_benchmark(path,pin)

def test_absolute_local_metadata_is_rejected(tmp_path):
    value=view();value['scope']='C:/Users/private_owner/private-store';path,pin=saved(tmp_path,value)
    with pytest.raises(ValueError):load_benchmark(path,pin)

def test_actual_backslash_path_stays_rejected_after_json_decoding(tmp_path):
    value=view();value['scope']='Z:\\private-owner\\private-store';path,pin=saved(tmp_path,value)
    with pytest.raises(ValueError):load_benchmark(path,pin)

def test_colon_newline_label_is_not_a_windows_drive(tmp_path):
    value=view();value['scope']='Supplied premises:\nThen verify the consequences.'
    path,pin=saved(tmp_path,value);assert load_benchmark(path,pin)['scope']==value['scope']

def test_task_runner_accepts_only_frozen_tasks_and_native_conditions(tmp_path):
    suite={'tasks':[{'id':f'dev-{i}','category':'development','phases':[{'id':'one','public_question':'Missing public premise.'}]} for i in range(30)]}
    path=tmp_path/'public.json';path.write_text(json.dumps(suite));pin=hashlib.sha256(path.read_bytes()).hexdigest()
    runner=BenchmarkTaskRunner(path,pin,ROOT/'private-native',ROOT/'native-manifest.json','0'*64,tmp_path/'repeat',threading.BoundedSemaphore(0))
    with pytest.raises(ValueError,match='Known native'):runner.submit('s',{'request_id':'1'*32,'task_id':'not-frozen','condition':'C'})
    with pytest.raises(ValueError,match='Known native'):runner.submit('s',{'request_id':'1'*32,'task_id':'dev-0','condition':'A'})
    with pytest.raises(ValueError,match='slots busy'):runner.submit('s',{'request_id':'1'*32,'task_id':'dev-0','condition':'C'})
    with pytest.raises(ValueError):runner.get('s','1'*32)
    assert not (tmp_path/'repeat').exists()

class FakeRunner:
    def __init__(self):self.calls=0
    def submit(self,session_id,value):
        self.calls+=1;return {'status':'RUNNING','request_id':value['request_id'],'provider_calls':0}
    def get(self,session_id,request):return {'status':'STOPPED','request_id':request,'provider_calls':0,'model_status':'NOT_EXECUTED'}

def test_actual_http_origin_csrf_polling_and_session_repeat_cap():
    service=JudgeService(None,None,None,benchmark=view());runner=FakeRunner();service.benchmark_runner=runner
    server=make_server(service,'http://127.0.0.1:0',ROOT/'hosted_judge/static',0,loopback_development=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    def request(method,path,data=None,headers=None):
        conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
        conn.request(method,path,body=None if data is None else json.dumps(data),headers=headers or {})
        response=conn.getresponse();raw=response.read();row=(response.status,json.loads(raw) if raw and path.startswith('/api') else raw,dict(response.getheaders()));conn.close();return row
    try:
        status,session,headers=request('GET','/api/session');assert status==200
        base={'Origin':server.public_origin,'Content-Type':'application/json','Cookie':headers['Set-Cookie'].split(';')[0],'X-Judge-CSRF':session['csrf_token']}
        value={'request_id':'1'*32,'task_id':'dev-0','condition':'C'}
        assert request('POST','/api/benchmark/run',value,{**base,'Origin':'https://other.invalid'})[0]==403
        assert request('POST','/api/benchmark/run',value,{**base,'X-Judge-CSRF':'wrong'})[0]==403
        assert runner.calls==0
        assert request('POST','/api/benchmark/run',value,base)[0]==202
        assert request('GET','/api/benchmark/result/'+'1'*32,headers={'Cookie':base['Cookie']})[1]['provider_calls']==0
        assert runner.calls==1
        assert request('POST','/api/benchmark/run',{**value,'request_id':'2'*32},base)[0]==202
        assert request('POST','/api/benchmark/run',{**value,'request_id':'3'*32},base)[0]==429
        assert runner.calls==2
        assert request('POST','/api/benchmark/authorize',{},base)[0]==404
        assert request('GET','/api/benchmark')[1]['provider_calls']==0
    finally:server.shutdown();server.server_close();thread.join(timeout=2)
