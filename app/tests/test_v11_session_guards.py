"""Snapshot/resource guards. These are synthetic fault tests, not native acceptance."""
import json,time
from pathlib import Path
import pytest
from hosted_judge import service as h,realization_loop as loop
from hosted_judge.durable_sessions import DurableSessions


def snapshot(tmp_path):
    store=DurableSessions(tmp_path/'sessions','a'*64)
    token='b'*64
    now=time.monotonic()
    session=h.Session('c'*64,now+300,'d'*32,rounds=1,actions=2,attempts=3,request_times=[now-1,now-2])
    store.save(token,session,time.monotonic)
    return store,token,session


def test_snapshot_restores_consumed_allowance_and_rate_window(tmp_path):
    store,token,session=snapshot(tmp_path)
    recovered=store.restore(token,time.monotonic)
    assert (recovered.rounds,recovered.actions,recovered.attempts)==(1,2,3)
    assert len(recovered.request_times)==2 and all(0<time.monotonic()-t<4 for t in recovered.request_times)
    assert token not in store.path(token).name


@pytest.mark.parametrize('fault',['bytes','source','busy','queued','expiry','rate'])
def test_corrupt_changed_source_or_uncertain_snapshot_cannot_restore(tmp_path,fault):
    store,token,_=snapshot(tmp_path);path=store.path(token)
    record=json.loads(path.read_bytes())
    if fault=='bytes':record['actions']=0  # Deliberately retain the old integrity digest.
    else:
        material={k:v for k,v in record.items() if k!='sha256'}
        if fault=='source':material['manifest_sha256']='e'*64
        if fault=='busy':material['busy']=True
        if fault=='queued':material['queued_id']='f'*32
        if fault=='expiry':material['expires_unix']=time.time()-1
        if fault=='rate':material['request_ages_seconds']=[1]*9
        record=loop.seal(material)
    path.write_bytes(loop.encode(record))
    if fault=='expiry':assert store.restore(token,time.monotonic) is None
    else:
        with pytest.raises(ValueError):store.restore(token,time.monotonic)


def test_snapshot_write_failure_releases_worker_and_caches_terminal_failure(tmp_path,monkeypatch):
    monkeypatch.setattr(h,'validate_bundle',lambda *a:None)
    service=h.JudgeService('x','y','z',executor=lambda _:pytest.fail('No native work after persistence failure'))
    token,data=service.new_session()
    class FailedDisk:
        def save(self,*a,**kw):raise OSError('synthetic private disk failure')
    service.durable=FailedDisk()
    question={'question':'A synthetic admitted request.','request_id':'a'*32}
    with pytest.raises(OSError):service.run(token,data['csrf_token'],question)
    assert not service.sessions[token].busy and service.sessions[token].attempts==1
    assert service.run(token,data['csrf_token'],question)['status']=='FAILED_CLOSED'
    assert service.workers.acquire(False) and service.workers.acquire(False)
    assert not service.workers.acquire(False)
    service.workers.release();service.workers.release()


def test_cold_snapshot_proof_uses_shared_compute_capacity(tmp_path,monkeypatch):
    store,token,_=snapshot(tmp_path)
    service=h.JudgeService(None,None,None)
    service.durable=store;service.realization_root=tmp_path
    assert service.workers.acquire(False) and service.workers.acquire(False)
    with pytest.raises(h.LimitError,match='capacity'):service.session(token)
    assert token not in service.sessions
    service.workers.release();service.workers.release()


def test_retired_cookie_cannot_recover_allowance_after_reset(tmp_path,monkeypatch):
    monkeypatch.setattr(h,'validate_bundle',lambda *a:None)
    service=h.JudgeService('x','y','z');service.durable=DurableSessions(tmp_path/'sessions','z');service.realization_root=tmp_path
    token,data=service.new_session();service.sessions[token].actions=7;service.sessions[token].attempts=3
    fresh,reset=service.reset(token,data['csrf_token'])
    assert reset['remaining_actions']==13 and reset['remaining_attempts']==5
    with pytest.raises(PermissionError):service.session(token)
    service.sessions.clear()
    recovered=service.session(fresh)
    assert recovered.actions==7 and recovered.attempts==3
