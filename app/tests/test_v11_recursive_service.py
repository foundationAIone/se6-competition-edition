"""Real native cycles, effect readback and a fresh service-object restoration."""
import hashlib,json
from pathlib import Path
from hosted_judge.service import JudgeService
from hosted_judge.pair_gateway import PairGateway
from hosted_judge.recursive_controller import restore

ROOT=Path(__file__).resolve().parents[1]
QUESTION='ROUTINE: 1 technician-hours, $11 materials cost, $65 customer revenue.\nDEEP: 3 technician-hours, $27 materials cost, $145 customer revenue.\nWe completed 12 jobs. The original log recorded 20 technician-hours. The materials budget is $210.\nCalculate revenue, materials and gross contribution.\nDetermine whether materials exceed budget.'

def make(tmp_path):
    manifest=ROOT/'native-manifest.json';pin=hashlib.sha256(manifest.read_bytes()).hexdigest();bundle=ROOT/'private-native'
    return JudgeService(bundle,manifest,pin,pair_gateway=PairGateway(bundle,tmp_path/'pairs',native_manifest=manifest,native_manifest_sha256=pin),realization_root=tmp_path/'realization')

def test_actual_automatic_two_cycles_cold_service_restoration_and_correction(tmp_path):
    service=make(tmp_path);token,session=service.new_session();question={'question':QUESTION,'request_id':'a'*32}
    first=service.run(token,session['csrf_token'],question)
    assert first['realization_loop']['status']=='BOUNDED_END_TO_END_RENEWED'
    assert first['realization_loop']['after_step']==2 and first['remaining_realization_cycles']==2
    assert first['realization_loop']['cycles'][1]['question']=='Derive a relation involving deep.'
    assert 'deep = 4' in first['realization_loop']['cycles'][1]['selected_result']
    assert 'Revenue: $1100.00' in first['answer'] and first['provider_calls']==0
    assert service.run(token,session['csrf_token'],question)==first
    before=service.sessions[token].checkpoint;task=service.sessions[token].task_id
    assert len(list((tmp_path/'realization/tasks'/task/'effects-ledger/effects').glob('*.json')))==2
    # A different service object receives no in-memory checkpoint or session.
    recovered=make(tmp_path);restored=recovered.session(token)
    assert restored.restored_from_disk and restored.checkpoint==before and restored.actions==4
    assert recovered.run(token,session['csrf_token'],question)==first
    second=recovered.run(token,session['csrf_token'],{'question':'Correct technician-hours to 22.','request_id':'b'*32})
    assert 'Revenue: $1180.00' in second['answer'] and 'Budget exceeded: YES' in second['answer']
    assert second['realization_loop']['after_step']==4 and second['remaining_realization_cycles']==0
    assert 'deep = 5' in second['realization_loop']['cycles'][1]['selected_result']
    assert second['realization_loop']['cycles'][0]['before_state_sha256']==first['realization_loop']['cycles'][1]['after_state_sha256']
    assert second['realization_loop']['cycles'][0]['restored_prior_from_disk']
    assert recovered.sessions[token].checkpoint['business']['inputs']['facts']['routine:expense']['value']=='11'
    ledger=tmp_path/'realization/tasks'/task/'effects-ledger'
    assert len(list((ledger/'effects').glob('*.json')))==4
    assert len(list((ledger/'attempts').glob('*.json')))==4
    assert not list((tmp_path/'pairs').glob('LIVE/**/attempt-*.json'))
    field_record=json.loads(Path(recovered.sessions[token].attestation['field_journal']['private_path']).read_bytes())
    assert field_record['schema']=='se6-v11-private-field-journal' and field_record['recursive_scope']
    assert field_record['next']==recovered.sessions[token].field_checkpoint
