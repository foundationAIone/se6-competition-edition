"""Pinned read-only evidence, privacy boundaries and anonymous display."""
import hashlib,http.client,json,threading
from pathlib import Path
import pytest
from hosted_judge.dynamic import load_dynamic
from hosted_judge.service import JudgeService,make_server

def write(tmp_path,data):
    raw=json.dumps(data).encode();p=tmp_path/'projection.json';p.write_bytes(raw)
    return p,hashlib.sha256(raw).hexdigest()

def test_dynamic_hash_and_private_record_rejection(tmp_path):
    p,pin=write(tmp_path,{'schema':'se6-dynamic-public-projection-v1','scenarios':[]})
    assert load_dynamic(p,pin)['scenarios']==[]
    with pytest.raises(ValueError):load_dynamic(p,'0'*64)
    for secret in ({'journal':[]},{'actual_pid':1},{'note':chr(67)+':'+'/'+'Users'+'/example/private/file'},{'secret':'synthetic'},{'private_root':'/home/synthetic/private'}):
        p,pin=write(tmp_path,{'schema':'se6-dynamic-public-projection-v1','scenarios':[],'extra':secret})
        with pytest.raises(ValueError):load_dynamic(p,pin)

def test_dynamic_get_has_no_session_or_execution():
    def forbidden(*a,**k):raise AssertionError('Read-only GET must not execute native work')
    data={'schema':'se6-dynamic-public-projection-v1','name':'pinned view','scenarios':[]}
    service=JudgeService(None,None,None,executor=forbidden,dynamic=data)
    server=make_server(service,'http://127.0.0.1:0',Path(__file__).resolve().parents[1]/'hosted_judge/static',0,loopback_development=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        for path,needle in (('/api/dynamic',b'pinned view'),('/dynamic',b'id="scenario"'),('/dynamic.js',b"fetch('/api/dynamic'")):
            c=http.client.HTTPConnection('127.0.0.1',server.server_port);c.request('GET',path)
            r=c.getresponse();body=r.read();assert r.status==200 and needle in body
            assert r.getheader('Set-Cookie') is None;c.close()
        assert not service.sessions
    finally:server.shutdown();server.server_close();thread.join()
