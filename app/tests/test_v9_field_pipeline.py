"""Actual fresh native workers, candidate pipeline, independent lanes and journals."""
import hashlib,json,time
from pathlib import Path
from hosted_judge.service import JudgeService
from hosted_judge.pair_gateway import PairGateway
ROOT=Path(__file__).resolve().parents[1]

def test_actual_field_pipeline_changes_typed_candidates_and_retains_knowledge(tmp_path):
    manifest=ROOT/'native-manifest.json';pin=hashlib.sha256(manifest.read_bytes()).hexdigest()
    bundle=ROOT/'private-native'
    service=JudgeService(bundle,manifest,pin,pair_gateway=PairGateway(bundle,tmp_path,native_manifest=manifest,native_manifest_sha256=pin))
    token,s=service.new_session();previous=None;fields=[]
    qs=[('Given equations:\nE1: jv+kv=23\nE2: kv=7\nE3: mv=5\nVariables are integers between 0 and 20.\nDerive a relation involving jv.','jv = 16'),
        ('Correct E2 to kv=8.\nDerive a relation involving jv.','jv = 15'),
        ('Derive a relation involving mv.','mv = 5')]
    for i,(question,answer) in enumerate(qs):
        r=service.run(token,s['csrf_token'],{'question':question,'request_id':str(i+1)*32})
        assert answer in r['answer'] and r['provider_calls']==0
        f=r['canonical']['field_realization'];fields.append(f)
        assert f['numeric']['step']==i and f['next_step']==i+1 and f['typed_roundtrip_verified']
        assert f['qpre']['rendered'] and not f['qpre']['actual'] and not f['qpre']['authority']
        assert f['selected_extra_audits'] and all(a['passed'] for a in f['selected_extra_audits'])
        assert len(f['numeric']['rotating_frames'])==2
        assert all(v['norm_bound']==1 and sum(x*x for x in v['field'])<=1+1e-12 for v in f['numeric']['samples'])
        assert f['mirror_comparison']['same_source_and_provenance'] and not f['full_se6_executed']
        assert not f['native_truth_modified'] and not f['mandatory_verification_skipped']
        assert any(a['operator']=='Full-form T / P / physical coupling' and a['status']=='UNAVAILABLE' for a in f['stages'])
        at=service.sessions[token].attestation
        raw=Path(at['field_journal']['private_path']).read_bytes();record=json.loads(raw)
        assert hashlib.sha256(raw).hexdigest()==at['field_journal']['sha256']
        assert record['previous']==previous and record['next']==service.sessions[token].field_checkpoint
        assert record['relational_realization']['feedback']['checkpoint']==record['next']['relational_checkpoint']
        previous=record['next']
        assert r['comparison']['baseline_status']=='NOT_EXECUTED_NOT_AUTHORIZED'
    assert fields[0]['numeric']['samples']!=fields[1]['numeric']['samples']
    assert not list(tmp_path.glob('LIVE/**/attempt-*.json'))


def test_actual_plan_rebase_between_mixed_and_retained_problem(tmp_path):
    manifest=ROOT/'native-manifest.json';pin=hashlib.sha256(manifest.read_bytes()).hexdigest();bundle=ROOT/'private-native'
    service=JudgeService(bundle,manifest,pin,pair_gateway=PairGateway(bundle,tmp_path,native_manifest=manifest,native_manifest_sha256=pin))
    token,s=service.new_session()
    q='Given equations:\nE1: uv+vv=17\nE2: vv=6\nDerive a relation involving uv.\nBASIC: 1 technician-hours, $10 materials cost, $50 customer revenue.\nDEEP: 3 technician-hours, $30 materials cost, $120 customer revenue.\nWe completed 10 jobs with 18 technician-hours. Calculate the revenue.'
    a=service.run(token,s['csrf_token'],{'question':q,'request_id':'a'*32})
    assert 'uv = 11' in a['answer']
    b=service.run(token,s['csrf_token'],{'question':'Derive a relation involving uv.','request_id':'b'*32})
    assert 'uv = 11' in b['answer'] and b['canonical']['independent_checkpoint_replay']
    assert b['canonical']['field_realization']['numeric']['state_rebase']['removed_ids']

