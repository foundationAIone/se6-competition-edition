"""Actual one-question jobs, independent simulated wires and immutable replay; zero paid calls."""
import hashlib,json,time
from pathlib import Path
import pytest
from hosted_judge.service import JudgeService,UnavailableError
from hosted_judge.pair_gateway import PairGateway
from hosted_judge.replays import load_replays
ROOT=Path(__file__).resolve().parents[1]
QUESTION='Given equations:\nE1: av+bv=19\nE2: bv=4\nE3: cv=6\nVariables are integers between 0 and 20.\nDerive a relation involving av.'

def bundle():
    manifest=ROOT/'native-manifest.json'
    return ROOT/'private-native',manifest,hashlib.sha256(manifest.read_bytes()).hexdigest()

def gateway(tmp_path,simulated=False):
    root,manifest,pin=bundle()
    return PairGateway(root,tmp_path,native_manifest=manifest,native_manifest_sha256=pin,simulated=simulated)

def wait(service,token,request_id):
    until=time.monotonic()+70
    while time.monotonic()<until:
        with service.lock:row=service.sessions[token].requests[request_id][1]
        if row.get('status')!='RUNNING':return row
        time.sleep(.03)
    raise AssertionError('Bounded job did not complete')

def test_run_both_default_real_native_and_exact_preparation_no_authority(tmp_path):
    service=JudgeService(*bundle(),pair_gateway=gateway(tmp_path),asynchronous=True)
    token,session=service.new_session();value={'question':QUESTION,'request_id':'a'*32}
    ack=service.run(token,session['csrf_token'],value)
    assert ack['status']=='RUNNING'
    assert service.run(token,session['csrf_token'],value)['status']=='RUNNING'
    with pytest.raises(ValueError):service.run(token,session['csrf_token'],{**value,'question':'changed'})
    result=wait(service,token,value['request_id'])
    assert result['answer']=='n1: av = 15' and result['native_receipt_count']==2
    assert result['provider_calls']==0 and result['comparison']['baseline_status']=='NOT_EXECUTED_NOT_AUTHORIZED'
    assert result['canonical']['components']['periodic_dimensions']==1
    assert result['canonical']['components']['legacy_advisory_counts']['merkabah_rotation_questions']==8
    assert result['canonical']['independent_checkpoint_replay'] and result['canonical']['returned_center_changed']
    packet=service.sessions[token].attestation['matched_pair']['prepared_pair']
    assert packet['messages']['se6'][:-1]==packet['messages']['baseline']
    assert len(packet['packet_sha256'])==64 and not (tmp_path/'LIVE').exists()
    assert service.run(token,session['csrf_token'],value)==result and service.sessions[token].attempts==1

def test_same_button_runs_two_explicit_simulated_wires_then_independent_scoring(tmp_path):
    service=JudgeService(*bundle(),pair_gateway=gateway(tmp_path,True),asynchronous=True)
    token,session=service.new_session();request='b'*32
    service.run(token,session['csrf_token'],{'question':QUESTION,'request_id':request})
    result=wait(service,token,request);comparison=result['comparison']
    assert comparison['mode']=='SIMULATED_TEST' and result['provider_calls']==0 and comparison['simulated_calls']==2
    assert comparison['baseline_answer'] and comparison['assisted_answer']
    assert all(v['score']==1 and v['maximum']==1 and v['schema_compliance'] is True and v['semantic_correctness'] is True and v['user_answer_status']=='PASS' for v in comparison['score']['lanes'].values())
    assert comparison['score']['answer_protocol']=='SE6_COMMON_PUBLIC_ANSWER_V1' and comparison['score']['common_user_answer_winner'] is None
    assert comparison['score']['arithmetic_winner'] is None and comparison['actual_billed_usd'] is None
    correction='Correct E2 to bv=5.\nDerive a relation involving av.'
    service.run(token,session['csrf_token'],{'question':correction,'request_id':'c'*32})
    corrected=wait(service,token,'c'*32)
    assert corrected['answer']=='n1: av = 14' and all(v['score']==1 and v['maximum']==1 and v['schema_compliance'] is True and v['semantic_correctness'] is True for v in corrected['comparison']['score']['lanes'].values())
    archive=Path(service.sessions[token].attestation['matched_pair']['archive'])
    packet=json.loads((archive/'prepared.json').read_bytes())
    assert packet['messages']['se6'][0]==packet['messages']['baseline'][0]
    for lane in ('se6','baseline'):
        assistants=[r for r in packet['messages'][lane] if r['role']=='assistant']
        assert len(assistants)==1
    assert 'LOCAL SE6 CONTEXT' not in json.dumps(packet['messages']['baseline'])
    private=service.sessions[token].attestation['matched_pair']
    sidecar=private['durable_worker_source'];record_path=Path(sidecar['private_path'])
    assert hashlib.sha256(record_path.read_bytes()).hexdigest()==sidecar['sha256']
    record=json.loads(record_path.read_bytes());source=record['source_preflight']
    assert hashlib.sha256(Path(source['private_path']).read_bytes()).hexdigest()==source['sha256']
    assert json.loads(Path(source['private_path']).read_bytes())['provider_execution_proven'] is False
    assert record['compiled_private_src_after']['disk_matches_loaded']
    assert record['final_manifest_sha256']==hashlib.sha256((archive/'final-manifest.json').read_bytes()).hexdigest()
    frozen=json.loads((archive/'final-manifest.json').read_bytes())
    assert set(frozen)=={p.relative_to(archive).as_posix() for p in archive.rglob('*') if p.is_file()}-{'final-manifest.json'}
    assert 'worker-attestations' not in json.dumps(frozen)
    first_field=result['canonical']['field_candidate'];next_field=corrected['canonical']['field_candidate']
    assert first_field['step']==0 and next_field['step']==1 and next_field['configuration_changed']
    assert next_field['feedback_applied'] and next_field['selected_extra_audits'][0]['passed'] is True
    assert first_field['samples'][0]['field']!=next_field['samples'][0]['field']
    assert not next_field['mandatory_verification_skipped'] and not next_field['native_evidence_truth_changed']
    journal=service.sessions[token].attestation['field_journal'];record=Path(journal['private_path'])
    assert hashlib.sha256(record.read_bytes()).hexdigest()==journal['sha256']
    retained=json.loads(record.read_bytes());assert retained['previous']['field_state']['step']==1
    assert retained['next']==service.sessions[token].field_checkpoint
    service.run(token,session['csrf_token'],{'question':'Derive a relation involving cv.','request_id':'f'*32})
    transfer=wait(service,token,'f'*32)
    assert 'cv = 6' in transfer['answer'] and transfer['canonical']['field_candidate']['step']==2
    assert all(v['score']==1 and v['maximum']==1 and v['schema_compliance'] is True and v['semantic_correctness'] is True for v in transfer['comparison']['score']['lanes'].values())

def test_offline_replay_preserves_all_original_scores_and_pin(tmp_path):
    path=ROOT/'frozen-replays.json';pin=hashlib.sha256(path.read_bytes()).hexdigest()
    replay=load_replays(path,pin)
    assert len(replay['cases'])==4
    mixed=next(r for r in replay['cases'] if r['id']=='successor/mixed-business/0')
    assert mixed['scores']['lanes']['se6']['score']==16 and mixed['scores']['lanes']['baseline']['score']==3
    wrong=json.loads(path.read_bytes());wrong['cases'][-1]['scores']['lanes']['se6']['score']=15
    altered=tmp_path/'altered.json';altered.write_text(json.dumps(wrong),encoding='utf-8')
    with pytest.raises(ValueError):load_replays(altered,hashlib.sha256(altered.read_bytes()).hexdigest())

def test_permission_before_any_queued_native_or_pair_action():
    service=JudgeService(None,None,None,asynchronous=True);token,s=service.new_session()
    with pytest.raises(PermissionError):service.run(token,'wrong',{'question':QUESTION,'request_id':'d'*32})
    with pytest.raises(UnavailableError):service.run(token,s['csrf_token'],{'question':QUESTION,'request_id':'d'*32})
    assert service.sessions[token].requests=={} and service.sessions[token].attempts==0

def test_modified_bundle_is_rejected_before_any_private_import(tmp_path):
    import shutil
    root,manifest,pin=bundle();copied=tmp_path/'bundle';shutil.copytree(root,copied,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    marker=tmp_path/'UNAUTHORIZED_IMPORT'
    target=copied/'src'/'workbench'/'runtime_revision.py'
    target.write_text('from pathlib import Path\nPath('+repr(str(marker))+').write_text("executed")\n',encoding='utf-8')
    pair=PairGateway(copied,tmp_path/'store',native_manifest=manifest,native_manifest_sha256=pin)
    result=pair.run(task_id='1'*32,request_id='2'*32,question=QUESTION,native_context='test',native_public={},public_history=[])
    assert result['public']['mode']=='OFFLINE_PREPARATION_FAILED' and result['public']['provider_calls']==0
    assert not marker.exists() and not (tmp_path/'store').exists()

def test_store_identity_preserves_posix_case(monkeypatch,tmp_path):
    from types import SimpleNamespace
    import hosted_judge.v8_run_both as module
    first=module.RunBothCoordinator(tmp_path/'Case');second=module.RunBothCoordinator(tmp_path/'case')
    monkeypatch.setattr(module,'os',SimpleNamespace(name='posix'))
    assert first.store_identity()!=second.store_identity()

def test_current_coverage_is_separate_pinned_public_projection(tmp_path):
    from hosted_judge.canonical import load_current_coverage
    path=ROOT/'current-operator-coverage.json';pin=hashlib.sha256(path.read_bytes()).hexdigest()
    values=load_current_coverage(path,pin)
    assert len(values)==17 and values[:15]==json.loads((ROOT/'tests/fixtures/V9_2_OPERATOR_COVERAGE.json').read_bytes())
    assert {v['id'] for v in values[15:]}=={'K_Merkabah 3D toroidal candidate','Field-guided Flower navigation'}
    assert any(v['id']=='D_substrate' and 'SYMBOLIC_ONLY' in v['description'] for v in values)
    private=tmp_path/'private.json';raw=json.dumps([{**values[0],'description':str(tmp_path)}]).encode();private.write_bytes(raw)
    # Public path detector rejects home-directory metadata even with a new hash.
    injected=json.dumps([{**values[0],'description':'C:'+'\\Users\\private\\runtime'}]).encode();private.write_bytes(injected)
    with pytest.raises(ValueError):load_current_coverage(private,hashlib.sha256(injected).hexdigest())

def test_field_controls_have_independent_numeric_oracle_and_are_pinned():
    from hosted_judge.canonical import load_field_controls
    path=ROOT/'candidate-field-controls.json';value=load_field_controls(path,hashlib.sha256(path.read_bytes()).hexdigest())
    assert len(value['controls'])==5
    for control in value['controls']:
        for frame in control['frames']:assert frame['independent_oracle_max_error']<1e-12
    assert value['controls'][0]['frames'][2]['samples'][1]['energy']==0
    assert value['controls'][3]['frames'][2]['samples'][1]['magnitude']<1e-12
