"""Exclusive persisted invocation attempts; no automatic recovery of partial effects."""
from pathlib import Path
import json,os,hashlib
from copy import deepcopy
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def require(v,s):
 if not v:raise ValueError(s)
def write_once(path,value):
 with path.open('x',encoding='utf-8')as f:json.dump(value,f,allow_nan=False);f.flush();os.fsync(f.fileno())
class DurableAttempts:
 def __init__(self,root,identity):
  root=Path(root);require(root.is_absolute()and not root.is_symlink(),'OWNED_ABSOLUTE_ROOT');root.mkdir(parents=True,exist_ok=True)
  require(not any(p.is_symlink()for p in (root,*root.parents)),'NO_SYMLINK_ROOT');self.root=root/digest({'identity':identity});self.root.mkdir(exist_ok=True);require(not self.root.is_symlink(),'NO_SYMLINK_IDENTITY');self.identity=identity;self.lock=None;self.attempt=None
 def begin(self,attempt_id,binding,prior_head,prior_state=None):
  require(isinstance(attempt_id,str)and 0<len(attempt_id)<=64,'ATTEMPT_ID');self.attempt=self.root/(digest({'id':attempt_id})+'.attempt.json')
  require(not self.attempt.exists(),'DURABLE_DUPLICATE_ATTEMPT')
  try:write_once(self.root/'owned.lock',{'identity':self.identity,'PID':os.getpid()})
  except FileExistsError:raise ValueError('DURABLE_IDENTITY_BUSY')from None
  self.lock=self.root/'owned.lock'
  try:
   require(not(self.root/'partial.block').exists(),'UNRESOLVED_PARTIAL_ATTEMPT')
   current=self.root/'current.json'
   if current.exists():
    require(current.is_file()and not current.is_symlink(),'CURRENT_FILE_BOUNDARY');stored=json.loads(current.read_bytes());require(stored['core_head']==prior_head,'CURRENT_DURABLE_HEAD')
    if prior_state is not None:self.verify_external_renewal(stored,prior_state)
   else:require(prior_head is None,'INITIAL_DURABLE_HEAD')
   write_once(self.attempt,{'identity':self.identity,'attempt_id':attempt_id,'binding':binding,'binding_sha256':digest(binding),'status':'CLAIMED_NONREFUNDABLE'})
  except BaseException:self.close();raise
  return {'path_name':self.attempt.name,'binding_sha256':digest(binding),'status':'CLAIMED_NONREFUNDABLE'}
 def complete(self,state):
  require(self.lock is not None and self.attempt.exists(),'CLAIM_REQUIRED')
  write_once(self.attempt.with_suffix('.complete.json'),{'status':'COMPLETED_PENDING_EXTERNAL_CONSEQUENCE','state_sha256':digest(state),'core_head':state['core_head']})
  temp=self.root/'next.json';write_once(temp,{'core_head':state['core_head'],'attempt':self.attempt.name,'state_sha256':digest(state),'candidate_payload':state});os.replace(temp,self.root/'current.json')
 @staticmethod
 def verify_external_renewal(stored,prior):
  require(set(prior)=={'payload','seal'}and digest(prior['payload'])==prior['seal'],'DURABLE_PRIOR_SEAL')
  actual=deepcopy(prior['payload']);expected=stored['candidate_payload'];entry=actual['history'][-1]
  require(entry.get('candidate_state_sha256')==stored['state_sha256']and entry.get('actual_consequence_verified')is True,'DURABLE_OBSERVED_CANDIDATE_ANCESTRY')
  witness=entry.get('verification_witness');require(isinstance(witness,dict)and witness.get('status')=='OBSERVATION_BINDINGS_VERIFIED'and witness.get('actual_consequence_verified')is True,'DURABLE_ACTUAL_WITNESS')
  reply=entry['observed_consequence'];require(reply['legal']is True and actual['last_observed_self']==reply['self'],'DURABLE_OBSERVED_SELF')
  item=entry['decision'].get('item')
  if reply['goal_success']is False and item in actual['claims']:
   require(actual['claims'][item]['current_use']=='CONSEQUENCE_CONTRADICTED','DURABLE_CONTRADICTION');actual['claims'][item]['current_use']=expected['claims'][item]['current_use']
  for k in ('observed_consequence','actual_consequence_verified','verification_witness','candidate_state_sha256','operator_feedback'):entry.pop(k,None)
  for k in ('last_observed_self','navigation_checkpoint','field_checkpoint'):
   if k in expected:actual[k]=deepcopy(expected[k])
   else:actual.pop(k,None)
  require(actual==expected,'DURABLE_UNCHANGED_CANDIDATE_CONTENT')
 def failed(self,error,progress):
  if self.attempt is not None and self.attempt.exists():
   write_once(self.attempt.with_suffix('.failed.json'),{'status':'FAILED_NO_RETRY','error':error,'progress':progress});write_once(self.root/'partial.block',{'attempt':self.attempt.name,'scope':'Stop identity until explicit independent recovery; never silently replay'})
 def close(self):
  if self.lock is not None:self.lock.unlink();self.lock=None
