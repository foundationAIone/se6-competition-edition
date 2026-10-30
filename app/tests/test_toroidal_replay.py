"""Tests producer outputs against independently implemented verifier, no native run."""
import copy,importlib.util,pathlib
import pytest
from hosted_judge import toroidal_field_oracle as o

PATH=pathlib.Path(__file__).parents[1]/'private-native'/'canonical_operators'/'toroidal_field_realization.py'
spec=importlib.util.spec_from_file_location('candidate_field_test',PATH)
f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
S=[{'id':'a','amplitude':.7},{'id':'b','amplitude':.3}]

def reseal(r):
    r['numeric_sha256']=o.digest(r['numeric'])
    r['checkpoint']['previous_numeric_sha256']=r['numeric_sha256']
    r['checkpoint']['state_sha256']=o.digest({k:v for k,v in r['checkpoint'].items() if k!='state_sha256'})
    r['result_sha256']=o.digest({k:v for k,v in r.items() if k!='result_sha256'})
    return r

def test_full_replay_and_neutralization():
    a=f.realize_toroidal(S);b=f.realize_toroidal(S,enabled=False)
    assert a['numeric']==b['numeric'] and a['checkpoint']==b['checkpoint']
    assert o.verify_result(a)['verified'] and o.verify_result(b)['verified']
    assert all(row['field_priority']==0 for row in b['projection']['candidates'])

def test_persistence_feedback_rebase():
    a=f.realize_toroidal(S);cp=f.finish_toroidal(a,[{'id':'a','passed':False}])
    b=f.realize_toroidal([{'id':'a','amplitude':.2},{'id':'c','amplitude':.9}],prior_state=cp)
    assert o.verify_result(b)['step']==1
    assert b['numeric']['state_rebase']['added_ids']==['c']
    assert b['numeric']['state_rebase']['removed_ids']==['b']

@pytest.mark.parametrize('change',[
 lambda r:r['numeric']['samples'][0].__setitem__('id','invented'),
 lambda r:r['numeric']['samples'][0]['field'].__setitem__(0,9),
 lambda r:r['numeric']['coefficients'].__setitem__('ct',.5),
 lambda r:r['numeric']['moving_sources'][0].__setitem__('charge',.9),
 lambda r:r['numeric']['geometry']['edges'].pop(),
 lambda r:r['numeric']['lines']['mixed'].__setitem__('closure','PROVEN_CLOSED'),
 lambda r:r['checkpoint'].__setitem__('step',999),
 lambda r:r['projection'].__setitem__('ranking',['b','a']),
 lambda r:r['inputs']['sample_points'].pop(),
 lambda r:r['numeric'].__setitem__('extra_unverified',True),
])
def test_semantic_tampers_rejected_after_rehash(change):
    r=copy.deepcopy(f.realize_toroidal(S));change(r)
    with pytest.raises(ValueError):o.verify_result(reseal(r))

def test_source_controls_and_nonlinear_sign():
    p=copy.deepcopy(f.DEFAULT);p['rates']=[0,0]
    a=f.realize_toroidal(S,parameters=p);assert a['numeric']['coefficients']['ct']==a['numeric']['coefficients']['cp']==0
    assert o.verify_result(a)['verified']
    p=copy.deepcopy(f.DEFAULT);p['directions']=[1,1]
    a=f.realize_toroidal(S,parameters=p);assert abs(a['numeric']['coefficients']['ct'])<1e-15 and a['numeric']['coefficients']['cp']==0
    p=copy.deepcopy(f.DEFAULT);p['polarities']=[-1,1]
    neg=f.realize_toroidal(S,parameters=p);pos=f.realize_toroidal(S)
    assert neg['numeric']['coefficients']['ct']==pytest.approx(-pos['numeric']['coefficients']['ct'])
    assert neg['numeric']['coefficients']['cp']==pytest.approx(pos['numeric']['coefficients']['cp'])
    assert o.verify_result(neg)['verified']
