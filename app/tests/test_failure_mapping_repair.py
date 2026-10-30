"""Separate development diagnostic graph; no frozen model answers as tests."""
import json,subprocess,sys,hashlib
from pathlib import Path
import pytest
from hosted_judge.failure_diagnosis import build_map,compare_inspections
ROOT=Path(__file__).resolve().parents[1]

def fixture():
    row={'task_id':'development-affine','phase_id':'dev1','condition':'C','official_status':'UNASSESSABLE',
        'public_question':'Given A: unit + offset = 23; B: offset = 4. Derive unit.',
        'actual_answer_text':'{"relation":{"coefficients":{"unit":"19"},"rhs":"19"}}',
        'request_sha256':'a'*64,'provider_response_sha256':'b'*64}
    diagnosis={'mathematical_observation':{'public_truth':'unit=19','submitted_implied':'unit=1'},
        'scope_observation':{'status':'Development fixture only'},'semantic_correct':False,
        'schema_compliant':False,'confirmed_causes':['COEFFICIENT_VALUE_CONFUSION','MISSING_SCOPE']}
    return {'row':row,'diagnostic':diagnosis,'contract_sha256':'c'*64}

def execute(mode):
    m=ROOT/'native-manifest.json';p=hashlib.sha256(m.read_bytes()).hexdigest()
    script='import sys,json;sys.dont_write_bytecode=True;sys.path.insert(0,sys.argv[1]);from hosted_judge.failure_diagnosis import inspect_maps;print(json.dumps(inspect_maps(sys.argv[2],sys.argv[3],sys.argv[4],json.load(sys.stdin),mode=sys.argv[5])))'
    done=subprocess.run([sys.executable,'-c',script,str(ROOT),str(ROOT/'private-native'),str(m),p,mode],input=json.dumps([fixture()]),text=True,capture_output=True,timeout=40)
    assert done.returncode==0,done.stderr
    return json.loads(done.stdout)

def test_typed_failure_graph_carries_real_provenance_and_topological_edges():
    item=fixture();plan=build_map(item['row'],item['diagnostic'],item['contract_sha256'])
    assert len(plan['nodes'])==8 and plan['nodes'][-1]['depends_on']==['mirror','request']
    assert json.loads(plan['nodes'][3]['input'])['provider_response_sha256']=='b'*64
    assert all(n['route']=='RELATIONAL' for n in plan['nodes'])

def test_actual_field_and_neutralized_dependency_inspection_independently_replay():
    c=execute('field');d=execute('ordinary');comparison=compare_inspections(c,d)
    for result in [c,d]:
        r=result['records'][0]
        assert r['navigation']['start']=='submission' and r['navigation_verification']['verified']
        assert r['numeric_verification']['verified'] and len(r['native_flower_centers'])>=1
        assert r['provider_calls']==0 and r['diagnostic']['semantic_correct'] is False
    assert comparison['improved_correctness_count']==0

def test_no_unadmitted_capture_becomes_a_diagnosed_truth():
    item=fixture();item['row']['official_status']='UNVERIFIED_CAPTURE'
    with pytest.raises(ValueError):build_map(item['row'],item['diagnostic'],item['contract_sha256'])
