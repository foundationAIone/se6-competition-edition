"""SIMULATED coordinator only; no native operations/provider/credential lookup."""
import json,hashlib,os
from datetime import datetime,timezone,timedelta
import pytest
from hosted_judge import v8_run_both as module
from hosted_judge.common_pair_contract import PROTOCOL
from hosted_judge.simulation import SimulatedNebiusTransport
Q='Given equations:\nE1: av+bv=19.\nE2: bv=4.\nE3: cv=6.\nVariables are integers between 0 and 20.\nDerive a relation involving av.'

def test_simulated_common_pair_cached_exact_responses(tmp_path):
 c=module.RunBothCoordinator(tmp_path,transport_factory=SimulatedNebiusTransport,answer_protocol=PROTOCOL)
 value=c.run('a'*32,'b'*32,Q,'ACTUAL_NATIVE_CONTEXT_NOT_MODEL_RESULT',{},[])
 public=value['public'];assert public['provider_calls']==0 and public['simulated_calls']==2
 assert public['origin']=='SIMULATED' and public['common_user_answer_winner'] is None and public['overall_winner'] is None
 for lane in public['lanes'].values():
  assert lane['assessment']['user_answer_status']=='PASS' and lane['assessment']['maximum']==1
  assert set(json.loads(lane['response']))=={'relation'}
 assert c.replay(__import__('pathlib').Path(value['attestation']['archive']))==value
 with pytest.raises(module.Blocked):c.run('a'*32,'c'*32,Q,'changed context',{},[Q])

def test_matched_settings_own_histories_and_public_shape_no_truth():
 packet=module.prepare('Correct E2: bv=5. Derive a relation involving av.','NATIVE_ONLY',[Q],{'se6':[{'public_index':0,'text':'SE6_OWN'}],'baseline':[{'public_index':0,'text':'BASELINE_OWN'}]},protocol=PROTOCOL)
 assert packet['answer_protocol']==PROTOCOL
 assert packet['messages']['se6'][0]==packet['messages']['baseline'][0]
 assert 'SE6_OWN' not in json.dumps(packet['messages']['baseline']) and 'BASELINE_OWN' not in json.dumps(packet['messages']['se6'])
 assert 'NATIVE_ONLY' not in json.dumps(packet['messages']['baseline'])
 system=packet['messages']['baseline'][0]['content'];assert '"av":"NONZERO_RATIONAL"' in system and '"rhs":"14"' not in system
 assert packet['model']['max_output_tokens']==2048 and packet['model']['temperature']==0

def permit(packet,c,now):
 return {'schema':'se6-v8-one-pair-allowance-v1','permit_id':'1'*32,'campaign_id':'future-common-test','approved':True,'purpose':'ONE_MATCHED_NEMOTRON_PAIR','expires_at_utc':(now+timedelta(hours=1)).isoformat(),'allowed_question_hashes':[packet['question_sha256']],'packet_sha256':packet['packet_sha256'],'model_settings':packet['model'],'source_contract':packet['source_contract'],'claim_store_sha256':c.store_identity(),'max_pairs':1,'max_calls':2,'max_output_tokens':2048,'max_input_bytes':49152,'usd_cap':'0.20','tariff':{**module.TARIFF,'verified_date':now.date().isoformat()}}

def test_common_allowance_current_day_pinned_tariff_without_key_read(tmp_path):
 now=datetime(2026,10,13,12,tzinfo=timezone.utc);path=tmp_path/'permit.json'
 c=module.RunBothCoordinator(tmp_path,approval_path=path,approval_sha256='0'*64,live_enabled=True,answer_protocol=PROTOCOL,clock=lambda:now,credential_probe=lambda _:pytest.fail('secret consultation forbidden'))
 packet=module.prepare(Q,'native',[],{'se6':[],'baseline':[]},protocol=PROTOCOL);v=permit(packet,c,now)
 path.write_bytes(module.encoded(v));c.approval_sha256=module.file_hash(path)
 assert c.allowance(packet)==v and not c.root.exists()
 for field,bad in [('verified_date','2026-10-12'),('source','https://untrusted.invalid'),('input_usd_per_million','0.01')]:
  changed=json.loads(json.dumps(v));changed['tariff'][field]=bad;path.write_bytes(module.encoded(changed));c.approval_sha256=module.file_hash(path)
  with pytest.raises(module.Blocked):c.allowance(packet)
 assert not c.root.exists()

def test_historical_packet_cannot_authorize_current_protocol(tmp_path):
 now=datetime(2026,10,13,12,tzinfo=timezone.utc);path=tmp_path/'permit.json'
 c=module.RunBothCoordinator(tmp_path,approval_path=path,approval_sha256='0'*64,live_enabled=True,answer_protocol=PROTOCOL,clock=lambda:now)
 old=module.prepare(Q,'native',[],{'se6':[],'baseline':[]});current=module.prepare(Q,'native',[],{'se6':[],'baseline':[]},protocol=PROTOCOL)
 v=permit(old,c,now);path.write_bytes(module.encoded(v));c.approval_sha256=module.file_hash(path)
 with pytest.raises(module.Blocked):c.allowance(current)
 assert not c.root.exists()


def test_trusted_native_projection_separate_from_model_grade_and_private_scope(tmp_path):
 from hosted_judge.pair_gateway import PairGateway
 from pathlib import Path
 gateway=PairGateway(tmp_path,tmp_path/'store',native_manifest=tmp_path/'manifest',native_manifest_sha256='0'*64)
 native={'typed_answer':{'origin':'NATIVE_DETERMINISTIC','user_answer':{'relation':{'coefficients':{'av':'1'},'rhs':'15'}},'checks':{'schema':True,'semantic':True,'finish':True,'evidence':True},'scope':{'task_id':'PRIVATE_SCOPE'},'evidence':{'receipt_hashes':['PRIVATE_RECEIPT']}}}
 context=gateway.context(native,'native')
 assert 'PRIVATE_SCOPE' not in context and 'PRIVATE_RECEIPT' not in context and 'NATIVE_DETERMINISTIC' in context
 native['typed_answer']['checks']['semantic']=False
 assert 'user_answer' not in gateway.context(native,'native')

def test_current_sim_invalid_model_not_replaced_by_native(tmp_path):
 class Wrong(SimulatedNebiusTransport):
  def request(self,body,directory,timeout):
   from src.workbench.provider_router import payload_bytes,parse_nebius_completion
   text='{"relation":{"coefficients":{"av":"15"},"rhs":"15"}}'
   raw=module.encoded({'id':'SIMULATED_NOT_MODEL_EVIDENCE','model':self.settings.model,'choices':[{'message':{'content':text},'finish_reason':'stop'}],'usage':{'prompt_tokens':1,'completion_tokens':30,'total_tokens':31,'completion_tokens_details':{'reasoning_tokens':0}}})
   (directory/'request.json').write_bytes(payload_bytes(self.settings,body));(directory/'provider.json').write_bytes(raw);(directory/'returned-text.txt').write_bytes(text.encode())
   return parse_nebius_completion(raw,self.settings.model,provider_reasoning_control=self.settings.provider_reasoning_control)
 c=module.RunBothCoordinator(tmp_path,transport_factory=Wrong,answer_protocol=PROTOCOL)
 out=c.run('a'*32,'b'*32,Q,'Native verified av=15',{},[])['public']
 assert all(x['assessment']['user_answer_status']=='FAIL' for x in out['lanes'].values())
 assert all(json.loads(x['response'])['relation']['coefficients']['av']=='15' for x in out['lanes'].values())
 assert out['overall_winner'] is None and out['common_user_answer_winner'] is None


@pytest.mark.parametrize('reported',[None,1])
def test_current_none_missing_or_positive_stops_baseline_no_retry(tmp_path,reported):
 class Fault(SimulatedNebiusTransport):
  calls=0
  def request(self,body,directory,timeout):
   from src.workbench.provider_router import payload_bytes,parse_nebius_completion
   type(self).calls+=1
   text='{"relation":{"coefficients":{"av":"1"},"rhs":"15"}}'
   usage={'prompt_tokens':1,'completion_tokens':30,'total_tokens':31}
   if reported is not None:usage['completion_tokens_details']={'reasoning_tokens':reported}
   raw=module.encoded({'id':'SIMULATED_NOT_MODEL_EVIDENCE','model':self.settings.model,'choices':[{'message':{'content':text},'finish_reason':'stop'}],'usage':usage})
   (directory/'request.json').write_bytes(payload_bytes(self.settings,body));(directory/'provider.json').write_bytes(raw);(directory/'returned-text.txt').write_bytes(text.encode())
   return parse_nebius_completion(raw,self.settings.model,provider_reasoning_control=self.settings.provider_reasoning_control)
 c=module.RunBothCoordinator(tmp_path,transport_factory=Fault,answer_protocol=PROTOCOL)
 with pytest.raises(module.Pending):c.run('a'*32,'b'*32,Q,'native',{},[])
 archive=c.root/'requests'/('a'*32)/('b'*32)
 assert Fault.calls==1 and json.loads((archive/'reservation.json').read_bytes())['reserved_calls']==2
 assert (archive/'se6'/'provider.json').is_file() and not (archive/'baseline').exists()
 assert not (archive/'summary.json').exists() and not (archive/'final-manifest.json').exists()
 assert json.loads((archive/'failure.json').read_bytes())['retry_allowed'] is False
 with pytest.raises(module.Pending):c.run('a'*32,'b'*32,Q,'native',{},[])
 assert Fault.calls==1


def test_current_none_zero_is_explicit_in_both_frozen_captures(tmp_path):
 c=module.RunBothCoordinator(tmp_path,transport_factory=SimulatedNebiusTransport,answer_protocol=PROTOCOL)
 value=c.run('a'*32,'b'*32,Q,'native',{},[])
 assert all(v['reasoning_tokens']==0 for v in value['public']['measurements'].values())
 assert all(v['assessment']['user_answer_status']=='PASS' for v in value['public']['lanes'].values())
 assert value['public']['origin']=='SIMULATED' and value['public']['provider_calls']==0 and value['public']['common_user_answer_winner'] is None
