import copy,importlib.util,json,pathlib,sys
import pytest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'private-native/canonical_operators'))
import toroidal_field_realization as field
from hosted_judge import navigation_oracle as o
spec=importlib.util.spec_from_file_location('nav_producer',ROOT/'private-native/canonical_operators/field_navigation.py');n=importlib.util.module_from_spec(spec);spec.loader.exec_module(n)
PUBLIC=json.loads((ROOT/'tests/fixtures/NAVIGATION_FIXTURE_PREREGISTRATION.json').read_text(encoding='utf-8'))['cases']
MAPS=json.loads((ROOT/'tests/fixtures/TYPED_MAP_FIXTURES_PRIVATE.json').read_text(encoding='utf-8'))

def fixture(index=0,state=None,priorfield=None,mode='field'):
    public=PUBLIC[index];stored=MAPS[index];plan=public['plan'];mapping=stored['plan_mapping']
    env=n.environment(mapping,plan,stored['admitted_ids'])
    source=field.sources_from_plan(plan,mapping)['sources']
    f=field.realize_toroidal(source,prior_state=priorfield,sample_points=env['sample_points'])
    result=n.navigate(env,state,f,{'goal_ids':stored['admitted_ids'],'budget':4,'audit_budget':1},mode)
    return env,result,f,plan,mapping

def reseal(r):
    cp=r['proposed_checkpoint'];cp['state_sha256']=field.digest({k:v for k,v in cp.items() if k!='state_sha256'})
    r['navigation_sha256']=field.digest({k:v for k,v in r.items() if k!='navigation_sha256'})
    return r

def test_positive_all_maps():
    for i in range(24):
        env,r,f,p,m=fixture(i)
        assert o.verify_navigation(env,r,None,f,p,m)['verified']

def test_persistent_location_and_same_field_ordinary():
    env,r,f,p,m=fixture();state=n.finish_navigation(env,r,MAPS[0]['admitted_ids'])['checkpoint']
    env,r2,f2,p,m=fixture(state=state,priorfield=f['checkpoint'])
    assert o.verify_navigation(env,r2,state,f2,p,m)['verified']
    ordinary=n.navigate(env,state,f2,r2['U'],'ordinary')
    assert o.verify_navigation(env,ordinary,state,f2,p,m)['verified']

def test_unicode_native_plan_vs_candidate_hash_contract():
    sys.path.insert(0,str(ROOT/'work/v10-field-evaluation/navigation/copied_operators'))
    import native_bridge
    plan={'nodes':[{'id':'nodeα','route':'RELATIONAL','connected':True,'input':'Remember α is café.','depends_on':[],'source_spans':[]}]}
    pre=native_bridge.preflight('Remember α is café.',plan)
    env=n.environment(pre['plan_mapping'],plan,pre['admitted_ids'])
    sources=field.sources_from_plan(plan,pre['plan_mapping'])['sources']
    f=field.realize_toroidal(sources,sample_points=env['sample_points'])
    result=n.navigate(env,None,f,{'goal_ids':pre['admitted_ids'],'budget':4,'audit_budget':1})
    assert o.verify_navigation(env,result,None,f,plan,pre['plan_mapping'])['verified']

@pytest.mark.parametrize('tamper',[
 lambda r:r['proposed_checkpoint'].__setitem__('step',999),
 lambda r:r['proposed_checkpoint'].__setitem__('orientation',[0,0,0]),
 lambda r:r['proposed_checkpoint'].__setitem__('field_numeric_sha256','0'*64),
 lambda r:r['selected_ids'].append('invented'),
 lambda r:r['trajectory'].__setitem__(-1,'invented'),
 lambda r:r['traversed_relationships'][0].__setitem__('direction','PHYSICAL_CAUSAL_REVERSE'),
 lambda r:r['choices'][0]['reachable_choices'][0].__setitem__('effective_score',999),
])
def test_semantic_tamper_after_rehash(tamper):
    env,r,f,p,m=fixture();r=copy.deepcopy(r);tamper(r)
    with pytest.raises(ValueError):o.verify_navigation(env,reseal(r),None,f,p,m)
