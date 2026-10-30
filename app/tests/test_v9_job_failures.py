"""Safe asynchronous failures: private receipts, state isolation and unknown paid outcome."""
import hashlib,json,time
from pathlib import Path
from types import SimpleNamespace
import pytest
from hosted_judge import service as h

class Gateway:
 def __init__(self,root,fail=False):self.config={'storage_root':str(root)};self.fail=fail;self.calls=0
 def status(self):return {'mode':'NATIVE_ONLY','status':'BLOCKED'}
 def run(self,**kw):
  self.calls+=1
  if self.fail:raise RuntimeError('NEBIUS_API_KEY=PRIVATE_SECRET C:/private/source.py '+kw['question'])
  return {'public':{'provider_calls':0},'attestation':None}

def wait(service,token,rid):
 until=time.monotonic()+3
 while time.monotonic()<until:
  row=service.sessions[token].requests[rid][1]
  if row['status']!='RUNNING':return row
  time.sleep(.005)
 raise AssertionError('Terminal failure not delivered')

def test_private_timeout_receipt_preserves_committed_state_and_no_sensitive_text(tmp_path,monkeypatch):
 original=h.os.environ.__class__.__getitem__
 def guarded(self,key):
  if key in ('NEBIUS_API_KEY','OPENAI_API_KEY'):raise AssertionError('Credential access forbidden')
  return original(self,key)
 monkeypatch.setattr(h.os.environ.__class__,'__getitem__',guarded)
 monkeypatch.setattr(h,'validate_bundle',lambda *a:None)
 gateway=Gateway(tmp_path)
 def fail(values):
  values[4]['memory'].append('UNCOMMITTED');raise h.LimitError('Native time allowance exceeded; prior state preserved')
 service=h.JudgeService('x','y','z',executor=fail,pair_gateway=gateway,asynchronous=True)
 token,data=service.new_session();s=service.sessions[token];s.checkpoint={'memory':['COMMITTED']};s.field_checkpoint={'retained':True};s.rounds=1;s.actions=2
 before=json.loads(json.dumps(s.checkpoint));field=json.loads(json.dumps(s.field_checkpoint))
 rid='a'*32;service.run(token,data['csrf_token'],{'question':'PRIVATE_QUESTION','request_id':rid});row=wait(service,token,rid)
 assert row['error_code']=='NATIVE_TIMEOUT' and row['stage']=='native_phase' and row['failure_receipt_saved']
 assert row['provider_calls']==0 and row['paid_outcome']=='NOT_DISPATCHED';assert gateway.calls==0
 assert s.checkpoint==before and s.field_checkpoint==field and s.rounds==1 and s.actions==2 and s.attempts==1
 assert not s.busy and s.queued_id is None
 path=tmp_path/'job-failures'/s.task_id/(rid+'.json');record=json.loads(path.read_bytes())
 assert record['prior_native_state_sha256']==record['current_native_state_sha256'] and not record['native_state_committed']
 raw=path.read_text()+json.dumps(row)
 assert all(secret not in raw for secret in ('PRIVATE_QUESTION',data['csrf_token'],token,'UNCOMMITTED','C:/'))
 assert service.run(token,data['csrf_token'],{'question':'PRIVATE_QUESTION','request_id':rid})==row and s.attempts==1
 # Reset succeeds after terminal failure; preserved allowance prevents free attempt refill.
 _,fresh=service.reset(token,data['csrf_token']);assert fresh['remaining_attempts']==h.MAX_ATTEMPTS-1

def test_provider_phase_failure_reports_unknown_and_actual_native_commit(tmp_path,monkeypatch):
 monkeypatch.setattr(h,'validate_bundle',lambda *a:None)
 gateway=Gateway(tmp_path,True)
 def success(values):return {'checkpoint':{'memory':['NEW']},'public':{'provider_calls':0,'answer':'synthetic native answer'},'operations':1,'attestation':None}
 service=h.JudgeService('x','y','z',executor=success,pair_gateway=gateway,asynchronous=True)
 token,data=service.new_session();s=service.sessions[token];rid='b'*32
 service.run(token,data['csrf_token'],{'question':'PRIVATE_QUESTION','request_id':rid});row=wait(service,token,rid)
 assert row['provider_calls'] is None and row['paid_outcome']=='UNKNOWN' and row['stage']=='provider_phase'
 record=json.loads((tmp_path/'job-failures'/s.task_id/(rid+'.json')).read_bytes())
 assert record['native_state_committed'] and record['completed_rounds']==1 and s.checkpoint=={'memory':['NEW']}
 assert all(secret not in json.dumps(record)+json.dumps(row) for secret in ('PRIVATE_SECRET','NEBIUS','PRIVATE_QUESTION','C:/'))
 assert gateway.calls==1

def test_safe_child_classification_and_failed_storage_not_promised(tmp_path,monkeypatch):
 monkeypatch.setattr(h,'execute_native',lambda *a:(_ for _ in ()).throw(ValueError('AUTO checkpoint hash mismatch')))
 class Pipe:
  def send(self,row):self.row=row
  def close(self):pass
 p=Pipe();h._child(p,());assert p.row=={'ok':False,'error_code':'NATIVE_VERIFICATION_REJECTED'}
 service=h.JudgeService(None,None,None);s=h.Session('SECRET',99,'a'*32)
 context={'stage':'native_phase','committed':False,'wall_start':time.perf_counter(),'cpu_start':time.process_time(),'prior_native_hash':None,'prior_field_hash':None}
 row=service._record_failure(s,'b'*32,RuntimeError('PRIVATE_SECRET'),context)
 assert row['failure_receipt_saved'] is False and 'private job record' not in row['error']

 # Capacity/admission rejection is not an admitted attempt and saves no disk receipt.
 service.pair_gateway=Gateway(tmp_path)
 context['stage']='admission'
 rejected=service._record_failure(s,'c'*32,h.LimitError('Native worker capacity reached; no queue or provider fallback'),context)
 assert rejected['failure_receipt_saved'] is False and not list(tmp_path.rglob('*.json'))
