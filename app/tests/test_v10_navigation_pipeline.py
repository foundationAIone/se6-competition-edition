"""Actual native workers, independent replay, corrected and unaffected state."""
import hashlib,json,subprocess,sys
from pathlib import Path
from hosted_judge.service import JudgeService
from hosted_judge.pair_gateway import PairGateway
ROOT=Path(__file__).resolve().parents[1]
BUSINESS='BASIC: 1 technician-hours, $10 materials cost, $50 customer revenue.\nDEEP: 3 technician-hours, $30 materials cost, $120 customer revenue.\nWe completed 8 jobs. The original log recorded 14 technician-hours. The materials budget is $150.\nCalculate the revenue and materials.\nDetermine whether materials exceed budget.'


def test_real_business_navigation_correction_and_retained_quantity(tmp_path):
    m=ROOT/'native-manifest.json';pin=hashlib.sha256(m.read_bytes()).hexdigest();b=ROOT/'private-native'
    service=JudgeService(b,m,pin,pair_gateway=PairGateway(b,tmp_path,native_manifest=m,native_manifest_sha256=pin))
    token,s=service.new_session();previous=None
    for i,(q,expected) in enumerate([(BUSINESS,'Revenue: $610.00'),('Correct technician-hours to 16.','Revenue: $680.00'),('Derive a relation involving deep.','deep = 4')]):
        r=service.run(token,s['csrf_token'],{'question':q,'request_id':str(i+1)*32})
        assert expected in r['answer'] and r['provider_calls']==0
        assert r['comparison']['baseline_status']=='NOT_EXECUTED_NOT_AUTHORIZED'
        f=r['canonical']['toroidal_realization'];nav=f['navigation']
        assert f['numeric']['step']==i and f['next_step']==i+1
        assert nav['next_step']==i+1 and nav['status']=='HOST_VERIFIED_NAVIGATION'
        assert f['independent_numeric_replay']['verified'] and nav['independent_replay']['verified']
        assert nav['typed_recenter_roundtrip_verified'] and nav['actual_relationships']
        assert r['canonical']['independent_checkpoint_replay']
        assert not f['native_truth_modified'] and not f['mandatory_verification_skipped']
        if i==0:
            assert nav['actual_trajectory']==['source','n1','n2','n3','n4']
            assert nav['native_flower_recenter_count']==4
            assert any(len(c['reachable_choices'])>1 for c in nav['choices'])
        if i==1:assert 'Materials cost: $160.00' in r['answer'] and 'Budget exceeded: YES' in r['answer']
        at=service.sessions[token].attestation;record=json.loads(Path(at['field_journal']['private_path']).read_bytes())
        assert record['previous']==previous
        assert record['toroidal_realization']['feedback']['checkpoint']==record['next']['toroidal_checkpoint']
        assert record['toroidal_realization']['feedback']['navigation']['checkpoint']==record['next']['navigation_checkpoint']
        assert record['toroidal_realization']['prepared']['typed']['qpre'] is not None
        previous=record['next']
    assert service.sessions[token].checkpoint['business']['inputs']['facts']['basic:expense']['value']=='10'
    assert not list(tmp_path.glob('LIVE/**/attempt-*.json'))


def test_toroidal_only_host_mode_retains_state_in_fresh_workers(tmp_path):
    # Experimental ablation kwargs are HOST-only; the public question API cannot supply them.
    code="""import json,sys,hashlib
from pathlib import Path
from hosted_judge.native_adapter import execute_native
p=json.loads(sys.stdin.read());r=Path.cwd();m=r/'native-manifest.json'
v=execute_native(r/'private-native',m,hashlib.sha256(m.read_bytes()).hexdigest(),p['question'],p['checkpoint'],'c'*32,p['round'],p['field'],field_mode='disabled',toroidal_mode='enabled')
Path(sys.argv[1]).write_text(json.dumps(v),encoding='utf-8')
"""
    cp=None;fc=None
    for i,q in enumerate(['Given equations:\nE1: xw+yw=13\nE2: yw=5\nDerive a relation involving xw.','Derive a relation involving yw.']):
        out=tmp_path/(str(i)+'.json')
        p=subprocess.run([sys.executable,'-B','-c',code,str(out)],input=json.dumps({'question':q,'checkpoint':cp,'field':fc,'round':str(i+1)*32}),cwd=ROOT,capture_output=True,text=True,timeout=25)
        assert p.returncode==0,p.stderr
        v=json.loads(out.read_text(encoding='utf-8'));cp=v['checkpoint'];fc=v['field_checkpoint']
        assert set(fc)=={'toroidal_checkpoint','navigation_checkpoint'}
        assert fc['toroidal_checkpoint']['step']==fc['navigation_checkpoint']['step']==i+1
        assert v['public']['canonical']['toroidal_realization']['navigation']['typed_recenter_roundtrip_verified']
