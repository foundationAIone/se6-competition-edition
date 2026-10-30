"""Candidate numerical/graph/persistence controls; no canonical authority claim."""
import sys,copy,math,hashlib
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'private-native/canonical_operators'))
import relational_field_realization as f

def plan(count=3):
 return {'nodes':[{'id':'n'+str(i),'route':'LINEAR_DERIVATION','connected':True,'input':'derive supported relation','depends_on':[] if not i else ['n'+str(i-1)]} for i in range(count)]}
def config(**changes):return {**copy.deepcopy(f.DEFAULT),**changes}
def test_stationary_geometry_and_actual_rotation():
 p=plan();a=f.realize_field(p);b=f.realize_field(p,prior_state=a['checkpoint'])
 assert a['numeric']['G0']==b['numeric']['G0']
 for frame,k in zip(b['numeric']['rotating_frames'],(0,1)):
  assert frame['angle']==[.25,-.25][k]
  for src,base in zip(frame['sources'],b['numeric']['G0']):assert math.hypot(*src['position'])==pytest.approx(math.hypot(*base['position']))
 assert a['numeric']['samples']!=b['numeric']['samples']
def test_zero_source_and_zero_rotation():
 p=plan();zero=f.realize_field(p,parameters=config(source_gains=[0,0]));assert all(s['field']==[0,0] for s in zero['numeric']['samples'])
 a=f.realize_field(p,parameters=config(rates=[0,0],decay=1,gain=0));b=f.realize_field(p,prior_state=a['checkpoint'],parameters=config(rates=[0,0],decay=1,gain=0))
 assert a['numeric']['rotating_frames']==b['numeric']['rotating_frames']
 assert [s['field'] for s in a['numeric']['samples']]==[s['field'] for s in b['numeric']['samples']]
def test_reinforce_cancel_and_independent_rates():
 p=plan(1);a=f.realize_field(p,parameters=config(phases=[0,math.pi]));assert math.hypot(*a['numeric']['samples'][0]['field'])<1e-12
 b=f.realize_field(p);assert b['numeric']['samples'][0]['energy']>0
 for rates,dirs in [([1,1],[1,1]),([1,1],[1,-1]),([34/21,1],[1,-1])]:
  c=config(rates=rates,directions=dirs);first=f.realize_field(p,parameters=c);second=f.realize_field(p,parameters=c,prior_state=first['checkpoint'])
  assert second['numeric']['rotating_frames'][0]['angle']==pytest.approx(rates[0]*dirs[0]*.25)
def test_matched_ablation_and_checkpoint_feedback():
 p=plan();a=f.realize_field(p);b=f.realize_field(p,enabled=False)
 assert a['numeric']==b['numeric'] and a['checkpoint']==b['checkpoint']
 assert any(x['field_priority'] for x in a['projection']['candidates']);assert all(x['field_priority']==0 for x in b['projection']['candidates'])
 cp=f.finish_field(a,[{'id':'n1','passed':False}]);assert cp!=a['checkpoint'];f.realize_field(p,prior_state=cp)
 with pytest.raises(ValueError):f.finish_field(a,[{'id':'invented','passed':True}])
def test_dependency_and_blocked_routes():
 p=plan();p['nodes'][0]['connected']=False;assert not f.realize_field(p)['projection']['ranking']
 p=plan();p['nodes'][0]['depends_on']=['n1']
 with pytest.raises(ValueError):f.realize_field(p)
def test_tamper_parameters_and_state():
 a=f.realize_field(plan());cp=copy.deepcopy(a['checkpoint']);cp['forces'][0][0][0]+=1
 with pytest.raises(ValueError,match='STATE_SEAL'):f.realize_field(plan(),prior_state=cp)
 with pytest.raises(ValueError):f.realize_field(plan(),parameters=config(rates=[float('nan'),1]))
 assert f.realize_field(plan(),prior_state=a['checkpoint'],parameters=config(dt=.5))['numeric']['state_rebase']['parameters_changed']
def test_real_mapping_and_flower_lineage():
 from native_bridge import preflight
 p=plan();pre=preflight('derive supported relation',p)
 a=f.realize_field(p,actual_mapping=pre['plan_mapping']);assert a['lineage'] and all(r['mapped_node_id'] for r in a['numeric']['G0'])
 bad=copy.deepcopy(pre['plan_mapping']);bad['node_bindings'][0]['input_sha256']='0'*64
 with pytest.raises(ValueError,match='MAPPING_INPUT'):f.realize_field(p,actual_mapping=bad)
def test_twelve_nodes_hundred_steps_stability():
 p=plan(12);cp=None
 for _ in range(100):
  a=f.realize_field(p,prior_state=cp);cp=f.finish_field(a,[{'id':'n0','passed':True}])
  for row in a['numeric']['samples']:
   assert math.hypot(*row['field'])<=1+1e-12
   assert row['energy']==pytest.approx(sum(sum(x*x for x in term) for term in row['components'])+row['interference'])
 assert cp['step']==100

def test_graph_membership_rebase_and_source_identity():
 a=f.realize_field(plan(3));b=f.realize_field(plan(1),prior_state=a['checkpoint'])
 assert b['numeric']['state_rebase']['removed_ids']==['n1','n2']
 c=f.realize_field(plan(4),prior_state=b['checkpoint'])
 assert c['numeric']['state_rebase']['added_ids']==['n1','n2','n3']
 assert c['numeric']['state_rebase']['retained_ids']==['n0']
 assert c['checkpoint']['step']==3 and len(c['checkpoint']['forces'][0])==4
 for frame in c['numeric']['rotating_frames']:
  assert all(s['rotation_norm_error']<1e-12 and s['base_force_norm']<=1+1e-12 for s in frame['sources'])
def test_coupling_has_real_effect_and_rotation_roundtrip():
 p=plan(3);a=f.realize_field(p,parameters=config(decay=1,gain=.5,interaction=0))
 off=f.realize_field(p,prior_state=a['checkpoint'],parameters=config(decay=1,gain=.5,interaction=0))
 on=f.realize_field(p,prior_state=a['checkpoint'],parameters=config(decay=1,gain=.5,interaction=1))
 assert off['numeric']['samples']==on['numeric']['samples']
 assert off['checkpoint']['forces']!=on['checkpoint']['forces']
 for frame in on['numeric']['rotating_frames']:
  for row,src in zip(on['numeric']['G0'],frame['sources']):
   assert f.rotate(src['position'],-frame['angle'])==pytest.approx(row['position'])
  before=math.dist(on['numeric']['G0'][0]['position'],on['numeric']['G0'][1]['position'])
  after=math.dist(frame['sources'][0]['position'],frame['sources'][1]['position'])
  assert before==pytest.approx(after)
