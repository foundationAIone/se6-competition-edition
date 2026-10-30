"""Reject incomplete/tampered capture and invalid independent algebra."""
import hashlib,json
from copy import deepcopy
from pathlib import Path
import pytest
from dynamic_score import validate_capture,unique_solution,num,score,delivered_math

def fixture(tmp_path):
    event={'phase':'before','question':'Derive x.','source':'OWNER_SUPPLIED'}
    spec={'offline_conditions':['SE6'],'scenarios':[{'id':'case','domain':'mathematical','events':[event]}]}
    row={'scenario':'case','domain':'mathematical','condition':'SE6','event':0,**event,'persistence':{'version':0}}
    raw=json.dumps(row).encode();(tmp_path/'row.json').write_bytes(raw)
    manifest={'source_start_matches_end':True,'conditions':['SE6'],'rows':['row.json'],'row_sha256':{'row.json':hashlib.sha256(raw).hexdigest()}}
    return spec,{'case':{}},manifest,row

def test_capture_identity_and_integrity(tmp_path):
    spec,key,manifest,row=fixture(tmp_path)
    assert validate_capture(spec,key,manifest,tmp_path)==[row]
    (tmp_path/'row.json').write_text('{}')
    with pytest.raises(ValueError,match='changed'):validate_capture(spec,key,manifest,tmp_path)

@pytest.mark.parametrize('mutation',['missing','repeat','question','source','version','path'])
def test_capture_completeness_and_inputs(tmp_path,mutation):
    spec,key,manifest,row=fixture(tmp_path)
    if mutation=='missing':manifest['rows']=[]
    elif mutation=='repeat':manifest['rows']=['row.json','row.json']
    elif mutation=='path':manifest['rows']=['../row.json'];manifest['row_sha256']={'../row.json':'x'}
    else:
        if mutation=='version':row['persistence']['version']=1
        else:row[mutation]='forged'
        raw=json.dumps(row).encode();(tmp_path/'row.json').write_bytes(raw);manifest['row_sha256']['row.json']=hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError):validate_capture(spec,key,manifest,tmp_path)

def test_scoring_refuses_empty_or_missing_cases():
    with pytest.raises(ValueError):score({'scenarios':[]},{},[])

def test_delivered_math_answer_not_replaced_by_valid_memory():
    assert delivered_math('n1: a = c + 5',{'a':7,'b':3,'c':2},{'a','c'})
    assert not delivered_math('n1: a = 999',{'a':7,'b':3,'c':2},{'a'})
    assert not delivered_math("n1: a = __import__('os').system('cmd')",{'a':7},{'a'})

def test_independent_algebra_full_rank_and_inconsistency():
    c=[{'coefficients':[['a',1],['b',1]],'rhs':10},{'coefficients':[['b',1]],'rhs':3}]
    assert unique_solution(c,['a','b'])=={'a':7,'b':3}
    assert unique_solution(c[:1],['a','b']) is None
    assert unique_solution(c+[{'coefficients':[['b',1]],'rhs':4}],['a','b']) is None

@pytest.mark.parametrize('pairs',[[['a',1],['z',1]],[['a',1],['a',2]]])
def test_independent_algebra_rejects_hidden_or_duplicate_symbols(pairs):
    with pytest.raises(ValueError):unique_solution([{'coefficients':pairs,'rhs':7}],['a','b'])

@pytest.mark.parametrize('value',['1e999999999','9'*129,'nan',True,'1/0'])
def test_numeric_boundaries(value):
    with pytest.raises(ValueError):num(value)
