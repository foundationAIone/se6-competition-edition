"""Development fixtures only; no held-out tasks or model responses."""
import hashlib,json
from pathlib import Path
import pytest
from hosted_judge import benchmark_controls as controls

def task(question='For av=4, derive av+3.',**kw):
    return {'id':'development_arithmetic','category':'development','phases':[{'id':'p1','public_question':question}],**kw}

def test_direct_model_is_not_faked_or_dispatched(tmp_path):
    root=tmp_path/'absent'
    result=controls.run_condition(task(),'A',root,None,None,None)
    assert result['status']==result['model_status']=='NOT_EXECUTED'
    assert result['provider_calls']==0 and result['phase_records']==[] and not root.exists()

@pytest.mark.parametrize('change',[
    {'expected_answer':'7'}, {'max_actions':True}, {'max_actions':21},
    {'automatic_renewal':'true'}, {'phases':[{'id':'p1','public_question':'x','answer_key':7}]},
    {'phases':[{'id':'p1','public_question':'x','authorized':'yes'}]},
    {'phases':[{'id':'p1','public_question':'x'*4097}]},
])
def test_no_hidden_keys_or_unsafe_budgets(change):
    with pytest.raises(ValueError):controls.valid({**task(),**change},'C')

def test_d_is_neutralized_not_missing_field_architecture(tmp_path,monkeypatch):
    from hosted_judge import native_adapter,recursive_controller
    calls=[]
    monkeypatch.setattr(native_adapter,'validate_bundle',lambda *args:None)
    def denied(values,root,**kw):
        calls.append(kw);raise ValueError('NATIVE_EXECUTION_REJECTED')
    monkeypatch.setattr(recursive_controller,'execute',denied)
    result=controls.run_condition(task(),'D',tmp_path/'d',None,None,None)
    assert result['configuration']['field_mode']=='neutralized'
    assert calls[0]['field_mode']=='neutralized' and calls[0]['automatic_renewal'] is False
    assert result['status']=='STOPPED' and result['phase_records'][0]['status']=='FAILED_CLOSED'
    assert len(list((tmp_path/'d'/'attempts').glob('*.json')))==1
    with pytest.raises(ValueError,match='DESTINATION_ALREADY_EXISTS'):
        controls.run_condition(task(),'D',tmp_path/'d',None,None,None)

def test_denied_authority_never_calls_tools_or_writes_effects(tmp_path,monkeypatch):
    from hosted_judge import native_adapter,recursive_controller
    monkeypatch.setattr(native_adapter,'validate_bundle',lambda *args:None)
    def reject(*a,**k):raise AssertionError('Denied phase attempted native work')
    monkeypatch.setattr(recursive_controller,'execute',reject)
    monkeypatch.setattr(controls,'conventional_native',reject)
    denied=task();denied['phases'][0]['authorized']=False
    for condition in ('B','C','D'):
        root=tmp_path/condition;result=controls.run_condition(denied,condition,root,None,None,None)
        assert result['phase_records'][0]['status']=='DENIED_AUTHORITY'
        assert not (root/'attempts').exists() and not list(root.rglob('effects'))

def test_conventional_effect_is_verified_immutable_and_dependency_sink(tmp_path):
    result={'checkpoint':{'fixture':'native-result-not-real-benchmark'},'attestation':{
        'plan':{'nodes':[{'id':'n1','depends_on':[]},{'id':'n2','depends_on':['n1']}]},
        'raw_execution_out':{'nodes':[
            {'id':'n1','status':'COMPLETE','knowledge_status':'CURRENT','route':'LINEAR_MATH','result':{'answer':(1,2)}},
            {'id':'n2','status':'COMPLETE','knowledge_status':'CURRENT','route':'LINEAR_DERIVATION','result':{'answer':(3,4)}}]}}}
    record=controls._conventional_effect(tmp_path,result,None,'development')
    assert record['verified'] and record['selected_node']=='n2'
    path=tmp_path/'conventional-effects'/(record['effect_sha256']+'.json')
    raw=path.read_bytes();assert hashlib.sha256(raw).hexdigest()==record['effect_sha256']
    assert json.loads(raw)['verified_native_result']['answer']==[3,4]
    with pytest.raises(FileExistsError):controls._conventional_effect(tmp_path,result,None,'development')

def test_actual_conventional_arithmetic_memory_and_correction(tmp_path):
    source=Path(__file__).resolve().parents[1]
    manifest=source/'native-manifest.json'
    if not manifest.exists():pytest.skip('Requires verified source development fixture')
    value={'id':'development_actual_correction','category':'development','phases':[
        {'id':'original','public_question':'Given equations:\nE1: uv+vv=17\nE2: vv=6\nDerive a relation involving uv.'},
        {'id':'correction','public_question':'Correct E1 to uv+vv=16.\nDerive a relation involving uv.'}]}
    result=controls.run_condition(value,'B',tmp_path/'b',source/'private-native',manifest,hashlib.sha256(manifest.read_bytes()).hexdigest())
    assert result['provider_calls']==0 and result['model_status']=='NOT_EXECUTED'
    assert len(result['phase_records'])==2
    assert all(row['status']=='COMPLETE' for row in result['phase_records'])
    assert all(row['artifact_records'][0]['verified'] for row in result['phase_records'])
    assert result['phase_records'][0]['checkpoint_sha256']!=result['phase_records'][1]['checkpoint_sha256']
    assert result['phase_records'][1]['public']['correction_state']['invalidated_deduction_count']>0

def test_conventional_effect_rejects_stale_complete_knowledge(tmp_path):
    result={'checkpoint':{},'attestation':{'plan':{'nodes':[]},'raw_execution_out':{'nodes':[
        {'id':'stale','status':'COMPLETE','knowledge_status':'INVALIDATED','route':'LINEAR_DERIVATION','result':{'answer':(3,4)}}]}}}
    assert controls._conventional_effect(tmp_path,result,None,'development') is None
    assert not list(tmp_path.rglob('*.json'))

@pytest.mark.parametrize('condition',['C','D'])
def test_actual_recursive_development(condition,tmp_path):
    source=Path(__file__).resolve().parents[1];manifest=source/'native-manifest.json'
    if not manifest.exists():pytest.skip('Requires verified source development fixture')
    value=task('Given equations:\nE1: uv+vv=17\nE2: vv=6\nDerive a relation involving uv.')
    result=controls.run_condition(value,condition,tmp_path/condition,source/'private-native',manifest,hashlib.sha256(manifest.read_bytes()).hexdigest())
    assert result['status']=='COMPLETE',result['phase_records']
    row=result['phase_records'][0]
    assert len(row['artifact_records'])==1 and row['artifact_records'][0]['verified']
    assert row['public']['realization_loop']['after_step']==1
    assert row['public']['canonical']['toroidal_mode']==('enabled' if condition=='C' else 'neutralized')
    assert result['provider_calls']==0 and result['model_status']=='NOT_EXECUTED'

def test_actual_recursive_correction_restores_prior_effect_and_memory(tmp_path):
    source=Path(__file__).resolve().parents[1];manifest=source/'native-manifest.json'
    if not manifest.exists():pytest.skip('Requires verified source development fixture')
    value={'id':'development_recursive_correction','category':'development','phases':[
        {'id':'initial','public_question':'Given equations:\nE1: uv+vv=17\nE2: vv=6\nDerive a relation involving uv.'},
        {'id':'update','public_question':'Correct E1 to uv+vv=16.\nDerive a relation involving uv.'}]}
    result=controls.run_condition(value,'C',tmp_path/'actual-c',source/'private-native',manifest,hashlib.sha256(manifest.read_bytes()).hexdigest())
    assert result['status']=='COMPLETE',result['phase_records']
    assert result['phase_records'][1]['public']['realization_loop']['after_step']==2
    assert result['phase_records'][1]['public']['correction_state']['invalidated_deduction_count']>0
    for index,row in enumerate(result['phase_records']):
        assert row['artifact_records'][0]['verified'] and row['native_node_results'][0]['result']['answer']==f'uv = {11-index}'
        path=tmp_path/'actual-c'/row['artifact_records'][0]['relative_path']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==row['artifact_records'][0]['effect_sha256']
