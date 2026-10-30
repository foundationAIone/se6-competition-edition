import copy,json,socket,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'private-native/canonical_operators'))
import pytest
from native_bridge import preflight
from component_layer import inspect_components

@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def deny(*a,**k):raise AssertionError('Network forbidden')
    monkeypatch.setattr(socket.socket,'connect',deny)

def prepared():
    return preflight('Two actual symbolic plan nodes',{'nodes':[{'id':'n1','route':'LINEAR_MATH','connected':True,'depends_on':[]},
        {'id':'n2','route':'HOST_BUSINESS','connected':True,'depends_on':['n1']}]},None)

def test_components_preserve_dependency_provenance_and_nonactual():
    p=prepared();r=inspect_components('Two actual symbolic plan nodes',p['plan_mapping'],p['operators']['models']['qpre'])
    assert all(v is True for v in r['invariants'].values())
    assert r['roundtrip_verified']
    dimension=r['periodic_map']['dimensions'][-1];assert len(dimension['terminals'])==2
    assert r['numerical_geometric_rotation']['status']=='UNAVAILABLE'
    assert len(r['legacy_advisory']['merkabah_rotation_questions'])==8
    assert len(r['legacy_advisory']['sphere_reflection_questions'])==8

def test_dangling_graph_is_not_admitted():
    p=prepared();p['plan_mapping']['model']['vertices'].pop()
    with pytest.raises(ValueError):inspect_components('Two actual symbolic plan nodes',p['plan_mapping'])

def test_false_qpre_actuality_rejected():
    p=prepared();q=p['operators']['models']['qpre'];q['actual']=True
    with pytest.raises(ValueError):inspect_components('Two actual symbolic plan nodes',p['plan_mapping'],q)

def test_plan_binding_mismatch_rejected():
    p=prepared();p['plan_mapping']['node_bindings'][0]['route']='HOST_BUDGET'
    with pytest.raises(ValueError,match='NODE_BINDING'):inspect_components('Two actual symbolic plan nodes',p['plan_mapping'])

def test_repeat_reprojection_equal_and_inputs_immutable():
    p=prepared();before=copy.deepcopy(p)
    one=inspect_components('Two actual symbolic plan nodes',p['plan_mapping']);two=inspect_components('Two actual symbolic plan nodes',p['plan_mapping'])
    assert one['periodic_map']==two['periodic_map'] and p==before

def test_empty_and_bounded_source():
    p=preflight('Empty plan',{'nodes':[]},None)
    assert inspect_components('Empty plan',p['plan_mapping'])['roundtrip_verified']
    with pytest.raises(ValueError):inspect_components('x'*4097,p['plan_mapping'])

def test_competent_independent_control_accepts_same_valid_information():
    from independent_component_control import validate
    p=prepared();assert validate('Two actual symbolic plan nodes',p['plan_mapping'],p['operators']['models']['qpre'])
