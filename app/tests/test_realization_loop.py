"""Synthetic native records; actual copied typed contracts and filesystem effects.
No fixture declares synthetic native flags genuine certificate replay.
"""
import sys,copy,json,hashlib
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'private-native/canonical_operators')]
from hosted_judge import realization_loop as l
from native_bridge import preflight
from hosted_judge.toroidal_pipeline import prepare,finish
from toroidal_field_realization import DEFAULT

CONTEXTS={}
def candidate(prior=None,change=False,enabled=True):
 plan={'nodes':[{'id':'n'+str(i),'route':'RELATIONAL','connected':True,'input':('changed' if change and i==1 else 'fixture')+' relationship '+str(i),'depends_on':['n1'] if i in (2,6) else []} for i in range(1,7)]}
 p=preflight('Synthetic supplied evidence '+str(change),plan)
 t=prepare(p,plan,enabled=enabled,parameters={**copy.deepcopy(DEFAULT),'polarities':[-1,1],'line_steps':8})
 cp={'checkpoint_hash':hashlib.sha256(str(change).encode()).hexdigest(),'previous_checkpoint_hash':prior['native_checkpoint_identity'] if prior else None}
 out={'question_sha256':t['question_sha256'],'checkpoint_hash':cp['checkpoint_hash'],'receipts':[],
  'nodes':[dict(n,status='COMPLETE',result={'answer':'SYNTHETIC relationship '+n['id'],'receipt_hashes':[]}) for n in plan['nodes']]}
 feedback=finish(t,out,True,p['admitted_ids'])
 result=l.prepare_candidates(t,feedback,out,cp,prior)
 CONTEXTS[result['sha256']]=copy.deepcopy((out,cp,t,feedback,prior))
 return result

def host_fixture_verifier(prepared):
 # Closed-host fixture comparison, NOT proof of genuine native journal.
 return lambda r:r['checkpoint']==prepared['native_checkpoint'] and r['out']==prepared['native_out'] and r['artifact']==prepared['artifact']

def test_actual_post_result_typed_operators_and_navigation_causal_payload(tmp_path):
 a=candidate();b=candidate(enabled=False)
 assert a['artifact']['selected_id']!=b['artifact']['selected_id']
 assert a['artifact']['verified_native_result']!=b['artifact']['verified_native_result']
 assert len(a['candidates'])==2 and a['operators']['qpre'] and len(a['operators']['views'])==2
 assert a['operators']['symbolic_dimension'] and a['selection_policy'].startswith('HOST')
 done=l.act_verify_assimilate(a,tmp_path/'effects',verify_native=host_fixture_verifier(a),finalize=l.finalize_verified)
 assert done['receipt']['readback']['bytes']>0 and done['state']==l.load_restore(tmp_path/'effects')
 assert l.renew(done['state'],a['native_checkpoint'])['next_step']==2

def test_two_cycles_correction_immutable_effect_and_restart(tmp_path):
 a=candidate();d=l.act_verify_assimilate(a,tmp_path/'sandbox',verify_native=host_fixture_verifier(a),finalize=l.finalize_verified);old=list((tmp_path/'sandbox/effects').glob('*'))[0].read_bytes()
 b=candidate(d['state'],change=True);e=l.act_verify_assimilate(b,tmp_path/'sandbox',verify_native=host_fixture_verifier(b),finalize=l.finalize_verified)
 assert e['state']['step']==2 and e['state']['prior_state_sha256']==d['state']['sha256']
 assert d['artifact']['selected_id'] in e['state']['invalidated_ids']
 assert len(list((tmp_path/'sandbox/effects').glob('*')))==2 and old in [p.read_bytes() for p in (tmp_path/'sandbox/effects').glob('*')]
 assert l.load_restore(tmp_path/'sandbox')==e['state']
 with pytest.raises(ValueError,match='STALE_DURABLE'):l.act_verify_assimilate(a,tmp_path/'sandbox',verify_native=host_fixture_verifier(a),finalize=l.finalize_verified)

def test_proof_denial_before_effect_and_nonverified_path(tmp_path):
 a=candidate()
 with pytest.raises(ValueError,match='PROOF_REQUIRED'):l.act_verify_assimilate(a,tmp_path/'denied',verify_native=lambda r:False,finalize=l.finalize_verified)
 assert not (tmp_path/'denied').exists()
 a['artifact']['route']='DIRECT_MODEL'
 with pytest.raises(ValueError,match='LOOP_SEAL'):l.act_verify_assimilate(a,tmp_path/'bad',verify_native=lambda r:True,finalize=l.finalize_verified)

def test_readback_corruption_no_assimilation(tmp_path,monkeypatch):
 a=candidate();monkeypatch.setattr(l,'fresh_readback',lambda path:{'sha256':'0'*64,'bytes':1})
 with pytest.raises(ValueError,match='READBACK_MISMATCH'):l.act_verify_assimilate(a,tmp_path/'failure',verify_native=host_fixture_verifier(a),finalize=l.finalize_verified)
 assert len(list((tmp_path/'failure/effects').glob('*')))==1 and not (tmp_path/'failure/cycles').exists()

def test_corrupt_ledger_or_effect_rejects_restore(tmp_path):
 a=candidate();l.act_verify_assimilate(a,tmp_path/'sandbox',verify_native=host_fixture_verifier(a),finalize=l.finalize_verified)
 path=list((tmp_path/'sandbox/effects').glob('*'))[0];path.write_bytes(b'{}')
 with pytest.raises(ValueError,match='READBACK_MISMATCH'):l.load_restore(tmp_path/'sandbox')

def test_forbidden_source_directory_and_budget(tmp_path):
 a=candidate()
 with pytest.raises(ValueError,match='PRODUCTION_OR_SOURCE'):l.act_verify_assimilate(a,tmp_path/'private-native',verify_native=host_fixture_verifier(a),finalize=l.finalize_verified)
 cp=copy.deepcopy(a['native_checkpoint']);cp['checkpoint_hash']='0'*64
 state=l.act_verify_assimilate(a,tmp_path/'sandbox',verify_native=host_fixture_verifier(a),finalize=l.finalize_verified)['state']
 with pytest.raises(ValueError,match='RENEW_NATIVE'):l.renew(state,cp)


def test_finalizer_denial_leaves_effect_unassimilated(tmp_path):
 a=candidate()
 def failed(*args):raise ValueError('FRESH_NATIVE_PROOF_FAILED')
 with pytest.raises(ValueError,match='FRESH_NATIVE_PROOF_FAILED'):l.act_verify_assimilate(a,tmp_path/'failed-finalize',verify_native=host_fixture_verifier(a),finalize=failed)
 assert len(list((tmp_path/'failed-finalize/effects').glob('*')))==1
 with pytest.raises(ValueError,match='ORPHAN_EFFECT'):l.load_restore(tmp_path/'failed-finalize')

def test_rehashed_state_knowledge_forgery_rejected(tmp_path):
 a=candidate();done=l.act_verify_assimilate(a,tmp_path/'sandbox',verify_native=host_fixture_verifier(a),finalize=l.finalize_verified)
 state=copy.deepcopy(done['state']);state['knowledge']={};state=l.seal({k:v for k,v in state.items() if k!='sha256'})
 (tmp_path/'sandbox/states'/(state['sha256']+'.json')).write_bytes(l.encode(state))
 cycle=tmp_path/'sandbox/cycles/0001.json';r=json.loads(cycle.read_bytes());r['next_state_sha256']=state['sha256'];r=l.seal({k:v for k,v in r.items() if k!='sha256'});cycle.write_bytes(l.encode(r))
 with pytest.raises(ValueError,match='KNOWLEDGE_REPLAY'):l.load_restore(tmp_path/'sandbox')

def test_zero_or_unverified_path_and_unsupported_fail_before_action(monkeypatch):
 original=finish
 def blocked(*args):
  r=original(*args);r['navigation']['status']='BLOCKED_UNVERIFIED_PATH';return r
 monkeypatch.setitem(candidate.__globals__,'finish',blocked)
 with pytest.raises(ValueError,match='VERIFIED_PATH_REQUIRED'):candidate()
 def unsupported(t,out,*args):
  r=original(t,out,*args);out['nodes'][int(t['typed']['selected_ids'][0][1:])-1]['route']='DIRECT_MODEL';return r
 monkeypatch.setitem(candidate.__globals__,'finish',unsupported)
 with pytest.raises(ValueError,match='UNSUPPORTED_OR_INCOMPLETE'):candidate()

def test_four_cycle_limit_no_fifth_action(tmp_path):
 state=None
 for i in range(4):
  a=candidate(state,change=bool(i%2));state=l.act_verify_assimilate(a,tmp_path/'sandbox',verify_native=host_fixture_verifier(a),finalize=l.finalize_verified)['state']
 assert state['step']==4 and len(list((tmp_path/'sandbox/effects').glob('*')))==4
 with pytest.raises(ValueError,match='STATE_CAP'):candidate(state)



def test_expected_context_rejects_rehashed_artifact_and_typed_replay(tmp_path):
 a=candidate();context=CONTEXTS[a['sha256']]
 assert l.verify_prepared(a,*context)
 bad=copy.deepcopy(a);bad['artifact']['verified_native_result']['answer']='fabricated';bad=l.seal({k:v for k,v in bad.items() if k!='sha256'})
 with pytest.raises(ValueError,match='EXPECTED_ARTIFACT'):l.verify_prepared(bad,*context)
 forged=copy.deepcopy(a);forged['operators']['views'][0]['representation']='forged';forged=l.seal({k:v for k,v in forged.items() if k!='sha256'})
 with pytest.raises(ValueError,match='OPERATOR_REPLAY'):l.act_verify_assimilate(forged,tmp_path/'forged',verify_native=host_fixture_verifier(forged),finalize=l.finalize_verified)
 assert not (tmp_path/'forged/cycles').exists()

def test_canonical_restore_child_checks_inner_models(tmp_path):
 a=candidate();state=l.act_verify_assimilate(a,tmp_path/'sandbox',verify_native=host_fixture_verifier(a),finalize=l.finalize_verified)['state']
 assert l.verify_restored_canonical(state)
 bad=copy.deepcopy(state);bad['typed_assimilation']['x']['state_summary']='forged';bad['typed_assimilation']=l.seal({k:v for k,v in bad['typed_assimilation'].items() if k!='sha256'});bad=l.seal({k:v for k,v in bad.items() if k!='sha256'})
 with pytest.raises(ValueError):l.verify_restored_canonical(bad)

def test_native_tuple_result_preserves_exact_json_bytes_and_real_readback(tmp_path,monkeypatch):
 original=finish
 def tuple_native_result(t,out,*args):
  feedback=original(t,out,*args)
  for row in out['nodes']:
   row['result']['source_spans']=((0,12),(13,24))
   row['result']['coefficients']=(('av',1),('bv',-1))
  return feedback
 monkeypatch.setitem(candidate.__globals__,'finish',tuple_native_result)
 prepared=candidate();context=CONTEXTS[prepared['sha256']];selected=prepared['artifact']['selected_id']
 native=next(n['result'] for n in prepared['native_out']['nodes'] if n['id']==selected)
 assert isinstance(native['source_spans'],tuple)
 projected=prepared['artifact']['verified_native_result']
 assert projected['source_spans']==[[0,12],[13,24]] and l.encode(projected)==l.encode(native)
 assert l.verify_prepared(prepared,*context)
 done=l.act_verify_assimilate(prepared,tmp_path/'tuple-native',verify_native=host_fixture_verifier(prepared),finalize=l.finalize_verified)
 raw=(tmp_path/'tuple-native/effects'/(done['state']['effect_sha256']+'.json')).read_bytes()
 assert raw==l.encode(prepared['artifact']) and json.loads(raw)==prepared['artifact']
 assert l.load_restore(tmp_path/'tuple-native')==done['state'] and l.verify_restored_canonical(done['state'])
 assert isinstance(prepared['native_out']['nodes'][0]['result']['source_spans'],tuple)
