"""Focused computational fidelity tests, no physical/canonical equivalence."""
import math,copy,pytest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'private-native/canonical_operators'))
import toroidal_field_realization as f

def cfg(**kw):return {**copy.deepcopy(f.DEFAULT),**kw}
def src(a=1):return [{'id':'n1','amplitude':a}]
def test_geometry_and_reference_projection():
 g=f.geometry();assert len(g['stationary_vertices'])==8 and len(g['edges'])==12 and len(g['faces'])==8
 for ids in g['tetrahedra']:
  center=[sum(g['stationary_vertices'][i][j] for i in ids)/4 for j in range(3)];assert f.norm(center)<1e-12
  distances=[math.dist(g['stationary_vertices'][a],g['stationary_vertices'][b]) for a in ids for b in ids if a<b];assert max(distances)-min(distances)<1e-12
 outer=[r['point'] for r in g['projection'] if math.hypot(*r['point'])>1e-12];assert len(outer)==6
 angles=sorted(math.atan2(p[1],p[0]) for p in outer);assert all(((angles[(i+1)%6]-angles[i])%(2*math.pi))==pytest.approx(math.pi/3) for i in range(6))
def test_rigid_rotation_velocity():
 first=f.realize_toroidal(src());second=f.realize_toroidal(src(),prior_state=first['checkpoint'])
 for source in second['numeric']['moving_sources']:
  base=second['numeric']['geometry']['stationary_vertices'][source['vertex']]
  assert f.norm(source['position'])==pytest.approx(1)
  assert f.rotate(source['position'],-source['angle'])==pytest.approx(base)
  assert f.dot(source['position'],source['velocity'])==pytest.approx(0,abs=1e-12)
def test_stationary_and_zero_charge_controls():
 zero=f.realize_toroidal(src(0));assert zero['numeric']['coefficients']['ct']==zero['numeric']['coefficients']['cp']==0
 assert zero['numeric']['lines']['mixed']['status']=='ZERO_FIELD_STATIONARY'
 stat=f.realize_toroidal(src(),parameters=cfg(rates=[0,0]),sample_points=[{'id':'n1','position':f.mul(2,f.AXIS)}]);sample=stat['numeric']['samples'][0]
 assert stat['numeric']['coefficients']['ct']==stat['numeric']['coefficients']['cp']==0
 assert f.norm(sample['diagnostic_E'])>1e-5 and f.norm(sample['diagnostic_B'])==0
 assert stat['numeric']['lines']['toroidal']['closure']=='NO_CIRCULATION_ZERO_CT'
def test_polarity_and_rate_parity():
 a=f.realize_toroidal(src());b=f.realize_toroidal(src(),parameters=cfg(polarities=[-1,1]));ca=a['numeric']['coefficients'];cb=b['numeric']['coefficients']
 assert cb['ct']==pytest.approx(-ca['ct']) and cb['cp']==pytest.approx(ca['cp'])
 c=f.realize_toroidal(src(),parameters=cfg(directions=[-1,1]));assert c['numeric']['coefficients']['ct']==pytest.approx(-ca['ct']);assert c['numeric']['coefficients']['cp']==pytest.approx(-ca['cp'])
 co=f.realize_toroidal(src(),parameters=cfg(directions=[1,1]));assert abs(co['numeric']['coefficients']['ct'])<1e-12 and abs(co['numeric']['coefficients']['cp'])<1e-12
 unequal=f.realize_toroidal(src(),parameters=cfg(rates=[34/21,1]));assert unequal['numeric']['coefficients']!=ca

def test_point_charge_diagnostic_is_not_automatically_toroidal():
 a=f.realize_toroidal(src(),sample_points=[{'id':'n1','position':f.mul(2,f.AXIS)}]);d=a['numeric']['samples'][0]
 assert abs(f.dot(d['diagnostic_B'],f.AXIS))>1e-5
 assert f.norm(d['toroidal'])<1e-12

def test_solenoidal_axis_and_flux_invariant():
 p=cfg();axis=f.field_at([0,0,0],.3,.4,p);assert axis['field']==pytest.approx(f.mul(.8*axis['profile'],f.AXIS))
 for point in ([.1,.3,.2],[.5,-.2,.4],[1.,.2,-.4]):
  h=1e-5;div=0;grad=[]
  for i in range(3):
   a=list(point);b=list(point);a[i]+=h;b[i]-=h
   fa=f.field_at(a,.3,.4,p);fb=f.field_at(b,.3,.4,p)
   div+=(fa['field'][i]-fb['field'][i])/(2*h);grad.append((fa['flux']-fb['flux'])/(2*h))
  assert abs(div)<1e-7 and abs(f.dot(f.field_at(point,.3,.4,p)['field'],grad))<1e-7

def test_lines_and_nonclosure_claim():
 a=f.realize_toroidal(src());lines=a['numeric']['lines'];assert math.dist(lines['toroidal']['points'][0],lines['toroidal']['points'][-1])<1e-12
 assert lines['toroidal']['closure']=='EXACT_CIRCLE' and lines['mixed']['closure']=='NOT_ASSERTED_FROM_FINITE_PATH'
 assert lines['poloidal']['maximum_flux_drift']<1e-5
 assert len(lines['mixed']['points'])<=129

def test_state_feedback_rebase_and_matched_ablation():
 a=f.realize_toroidal(src(.6));b=f.realize_toroidal(src(.6),enabled=False);assert a['numeric']==b['numeric'] and a['checkpoint']==b['checkpoint']
 assert b['projection']['candidates'][0]['field_priority']==0
 cp=f.finish_toroidal(a,[{'id':'n1','passed':False}]);assert cp['amplitudes'][0]<a['checkpoint']['amplitudes'][0]
 c=f.realize_toroidal([{'id':'n2','amplitude':.5}],prior_state=cp);assert c['numeric']['state_rebase']['added_ids']==['n2'] and c['numeric']['step']==1

def test_hashes_and_inner_tamper_rejection():
 a=f.realize_toroidal(src());assert f.validate_result(a)
 b=copy.deepcopy(a);b['checkpoint']['amplitudes'][0]=0;b['result_sha256']=f.digest({k:v for k,v in b.items() if k!='result_sha256'})
 with pytest.raises(ValueError,match='CHECKPOINT_SEAL'):f.finish_toroidal(b,[])
 cp=copy.deepcopy(a['checkpoint']);cp['previous_numeric_sha256']=None;cp['state_sha256']=f.digest({k:v for k,v in cp.items() if k!='state_sha256'})
 with pytest.raises(ValueError,match='STATE_HASH_FORMAT'):f.realize_toroidal(src(),prior_state=cp)
 for changes in ({'dt':True},{'width_r':0},{'rates':[math.nan,1]}):
  with pytest.raises(ValueError):f.realize_toroidal(src(),parameters=cfg(**changes))

def test_mapped_sources_and_bounded_evolution():
 plan={'nodes':[{'id':'n1','route':'RELATIONAL','connected':True,'input':'known relation','depends_on':[]},{'id':'n2','route':'RELATIONAL','connected':True,'input':'retain changed relation','depends_on':['n1']}]}
 mapped=f.sources_from_plan(plan);a=f.realize_toroidal(mapped['sources'],sample_points=mapped['sample_points'],parameters=cfg(line_steps=8))
 for _ in range(20):
  cp=f.finish_toroidal(a,[{'id':'n1','passed':True}]);a=f.realize_toroidal(mapped['sources'],sample_points=mapped['sample_points'],prior_state=cp,parameters=cfg(line_steps=8))
 assert all(0<=v<=1 for v in a['checkpoint']['amplitudes']) and all(math.isfinite(v) for sample in a['numeric']['samples'] for v in sample['field'])
