"""Pure contract tests. These stubs are not World-effect demonstration evidence."""
from copy import deepcopy
import pytest
from se666_core import native_dependency_relation_v1 as d
from se666_core.observation_grounding import digest
from se666_core.grounded_native_input import GroundedNativeConsumer

class ContractUnitAuthority:
    def authenticate_dependency_certificate(self,value):return True

def inputs():
    b=dict(entity_id='unit',entity_state='state',source='src',epoch='program',memory_head='head')
    obs=dict(context=dict(cwd='/case/A',observed_root='/case/A',entity_id='unit',situated_frame_hash='frame'),
        manifest={'entry':'blue','profiles':{'red':{'config':'a.json','gain':2,'offset':0},'blue':{'config':'b.json','gain':3,'offset':0}}},
        schema={'version':d.VERSION,'goal':18,'setting_bounds':[0,100],'operation':'gain*limit+offset'},
        configs={'a.json':{'limit':1},'b.json':{'limit':1}},failure={'output':3},file_hashes={'workload.py':'program'})
    h=[dict(source='src',epoch='program',raw=[3])]
    a=[dict(id=n,payload={'op':'SET_INTEGER','field':'limit','path':n+'.json'},cost=1) for n in ('a','b')]
    return obs,h,b,a

def prepared(obs,h,b,a,memory=None):
    return d.prepare(d.certificate(obs,h,b,memory=memory),h,b,a,ContractUnitAuthority())

def decision(p,a):
    graph={'vertices':[{'label':'center','description':'{}'}]+[{'label':'continuation:'+str(i),'description':__import__('json').dumps(v)} for i,v in enumerate(p['predictions'])]+[{'label':'dependency:extra','description':'{}'}]}
    return GroundedNativeConsumer._choose_from_map(graph,a,dict(remaining_actions=1,remaining_effects=1,remaining_cost=1,selection_policy={}))

def test_actual_map_consumer_binds_derived_parameters_not_host_patch():
    obs,h,b,a=inputs();p=prepared(obs,h,b,a);choice=decision(p,a)
    assert choice['actions']==['b']
    assert 'value' not in a[1]['payload']
    assert d.instantiate(a[1],choice['prediction'])['payload']['value']==6

def test_changed_dependency_recomputes_target_and_parameter():
    obs,h,b,a=inputs();before=decision(prepared(obs,h,b,a),a)
    obs['manifest']['entry']='red';after=decision(prepared(obs,h,b,a),a)
    assert before['actions']==['b'] and after['actions']==['a']
    assert after['prediction']['derived_values']=={'a':9}

def test_retained_edges_are_consumed_but_narrow_ablation_can_tie():
    obs,h,b,a=inputs();memory={'observation':deepcopy(obs)};obs['manifest']['entry']='red'
    on=decision(prepared(obs,h,b,a,memory),a);off=decision(prepared(obs,h,b,a),a)
    assert on['actions']==off['actions']==['a'] and on['prediction']['reused_edge_ids']
    assert off['prediction']['reused_edge_ids']==[]

def test_self_root_change_invalidates_old_relation_cache_without_blocking_rederivation():
    obs,h,b,a=inputs();memory={'observation':deepcopy(obs)}
    obs['context'].update(cwd='/case/B',observed_root='/case/B')
    result=decision(prepared(obs,h,b,a,memory),a)
    assert result['actions']==['b'] and not result['prediction']['reused_edge_ids']

@pytest.mark.parametrize('fault',['seal','epoch','frame','self','escape','answer','gain'])
def test_invalid_or_unadmitted_inputs_fail_closed(fault):
    obs,h,b,a=inputs()
    if fault=='epoch':b['epoch']='wrong'
    if fault=='frame':obs['context']['situated_frame_hash']=''
    if fault=='self':obs['context']['cwd']='/wrong'
    if fault=='escape':obs['manifest']['profiles']['red']['config']='../a.json'
    if fault=='answer':obs['schema']['expected_patch']='unadmitted'
    if fault=='gain':obs['manifest']['profiles']['red']['gain']=0
    cert=d.certificate(obs,h,b)
    if fault=='seal':cert['certificate_sha256']='bad'
    with pytest.raises(ValueError):d.prepare(cert,h,b,a,ContractUnitAuthority())

def test_missing_independent_source_is_not_approval():
    obs,h,b,a=inputs()
    with pytest.raises(ValueError,match='INDEPENDENT_SOURCE'):d.prepare(d.certificate(obs,h,b),h,b,a,object())

def test_noninteger_solution_is_unknown_not_a_manufactured_action():
    obs,h,b,a=inputs();obs['schema']['goal']=17
    assert decision(prepared(obs,h,b,a),a)['status']=='UNKNOWN'
