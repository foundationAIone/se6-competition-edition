"""Public package tests: deterministic arithmetic, isolation and redaction."""
from pathlib import Path
from fractions import Fraction
from copy import deepcopy
import ast,importlib.util,json,re
import pytest
ROOT=Path(__file__).parent
spec=importlib.util.spec_from_file_location('independent_public_scorer',ROOT/'public_scorer.py');s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
def data():return json.loads((ROOT/'BENCHMARK_EVIDENCE.json').read_bytes())
def test_replays_all_positive_and_negative_results():
    result=s.replay(data())['pairs']
    assert result['first-linear/0']['lanes']['se6']['status']=='UNASSESSABLE'
    assert result['first-linear/0']['lanes']['baseline']['score']==0
    assert result['first-linear/0']['arithmetic_winner'] is None
    for name in ('successor/linear-correction/0','successor/linear-correction/1'):
        assert result[name]['arithmetic_winner']=='TIE'
        assert all(v['score']==3 for v in result[name]['lanes'].values())
    assert all(v['correction_retention_correct'] for v in result['successor/linear-correction/1']['lanes'].values())
    assert result['successor/mixed-business/0']['lanes']['se6']['score']==16
    assert result['successor/mixed-business/0']['lanes']['baseline']['score']==3
def test_followups_contain_exact_own_model_output_and_shared_instruction():
    pairs=data()['pairs'];original=pairs[1];follow=pairs[2]
    for lane in ('se6','baseline'):
        history=[m['content'] for m in follow['lanes'][lane]['request_messages'] if m['role']=='assistant']
        assert len(history)==1 and s.decode(history[0])==s.decode(original['lanes'][lane]['response_content'])
    for pair in pairs:
        messages={k:v['request_messages'] for k,v in pair['lanes'].items()}
        assert [x for x in messages['se6'] if x['role']=='system']==[x for x in messages['baseline'] if x['role']=='system']
        se6users=[x['content'] for x in messages['se6'] if x['role']=='user'];baseusers=[x['content'] for x in messages['baseline'] if x['role']=='user']
        assert se6users[:len(baseusers)]==baseusers and len(se6users)==len(baseusers)+1
def test_public_projection_has_no_sensitive_paths_ids_private_blobs():
    d=data();text=json.dumps(d)
    def strings(value):
        if isinstance(value,str):yield value
        elif isinstance(value,dict):
            for item in value.values():yield from strings(item)
        elif isinstance(value,list):
            for item in value:yield from strings(item)
    assert all(not re.search(r'(?i)(?<![a-z])[a-z]:[\\/]',value) for value in strings(d))
    assert not re.search(r'(?i)\b(?:chatcmpl-|sk-[a-z0-9]{16,}|[a-z0-9_]+_api_key)\b',text)
    for pair in d['pairs']:
        for capture in pair['lanes'].values():
            assert 'response_id' not in capture and 'approval' not in capture and 'checkpoint' not in capture
            for m in capture['request_messages']:
                assert not re.search(r'\b[0-9a-f]{16,}\b',m['content'],re.I)
                assert not re.search(r'"(?:journal|checkpoint|owner_approval|authority)"\s*:',m['content'],re.I)
def test_scorer_imports_only_standard_library():
    imports=[]
    for node in ast.walk(ast.parse((ROOT/'public_scorer.py').read_text())):
        if isinstance(node,ast.ImportFrom):imports.append(node.module)
        elif isinstance(node,ast.Import):imports.extend(x.name for x in node.names)
    assert set(imports)<={'fractions','pathlib','hashlib','json','re','sys'}
@pytest.mark.parametrize('value',['1e1000000000','9'*65,'NaN','1_000'])
def test_unsafe_number_rejected_before_fraction(value,monkeypatch):
    monkeypatch.setattr(s,'Fraction',lambda _:pytest.fail('Unsafe input allocated'))
    with pytest.raises(ValueError):s.number(value)
def test_proportional_certificate_and_invalid_step():
    original=s.decode(data()['pairs'][1]['lanes']['se6']['response_content']);v=deepcopy(original)
    v['answer']['relation']={'coefficients':{'p':'-1/2','q':'-1/2','s':'1/2'},'rhs':-6}
    assert s.linear(v,'successor',0)['score']==3
    v['answer']['steps'][0]['weights']={'E1':1,'E2':1}
    assert not s.linear(v,'successor',0)['valid_certificate']
def test_boolean_not_business_number():
    v=s.decode(data()['pairs'][3]['lanes']['se6']['response_content']);v['original']['routine']=True
    with pytest.raises(ValueError):s.business(v)
def test_duplicate_fields_fail_closed():
    with pytest.raises(ValueError):s.decode('{"answer":{},"answer":{}}')
def test_usage_cost_and_limits_from_selected_metrics():
    result=s.replay(data())['resources']
    assert result['successor']['selected_capture_count']==6
    assert result['successor']['completion_tokens_reported']==1349
    assert result['successor']['original_input_bytes_reported']==28902
    assert result['successor']['tariff_estimate_usd']==pytest.approx(.0037671)
    assert result['first-linear']['tariff_estimate_usd']==pytest.approx(.0008922)
