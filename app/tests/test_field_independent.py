import importlib.util, pathlib, math, json, random, copy
import pytest
P=pathlib.Path(__file__).resolve().parents[1]/'private-native/canonical_operators/computational_interference_field.py'
s=importlib.util.spec_from_file_location('field_under_test',P); f=importlib.util.module_from_spec(s);s.loader.exec_module(f)
def config(a=(1,0),b=(1,0),omega=1,dt=1):
 return {'sources':[{'position':[0,0],'force':list(a),'phase':0,'direction':1},{'position':[0,0],'force':list(b),'phase':0,'direction':-1}], 'omega':omega,'dt':dt,'decay':1,'learning_rate':0}
S=[{'id':'origin','position':[0,0]}]
def row(c,state=None): return f.evaluate(c,S,state)['samples'][0]
def test_zeros_cancellation_reinforcement_and_counterrotation():
 assert row(config((0,0),(0,0)))['energy']==0
 assert row(config((1,0),(-1,0)))['energy']==0
 assert row(config(omega=0))['field']==[2,0]
 c=config((1,0),(-1,0),omega=math.pi/2)
 r=f.evaluate(c,S); assert row(c,r['checkpoint'])['field']==pytest.approx([0,2],abs=1e-12)
 c=config(omega=math.pi/2);r=f.evaluate(c,S)
 assert row(c,r['checkpoint'])['energy']==pytest.approx(0,abs=1e-24)
def test_independent_formula_fresh_parameters_symmetry_boundary():
 rng=random.Random(761938)
 for _ in range(40):
  c=config(omega=rng.uniform(0,10),dt=rng.random())
  for src in c['sources']:
   src['position']=[rng.uniform(-1,1),rng.uniform(-1,1)];angle=rng.uniform(-math.pi,math.pi);amp=rng.random()
   src['force']=[amp*math.cos(angle),amp*math.sin(angle)];src['phase']=rng.uniform(-math.pi,math.pi)
  points=[{'id':'p','position':[rng.uniform(-1,1),rng.uniform(-1,1)]},{'id':'edge','position':[1,-1]}]
  prior=f.evaluate(c,points);actual=f.evaluate(c,points,prior['checkpoint'])
  for q,r in zip(points,actual['samples']):
   expected=complex(0)
   for z in c['sources']:
    angle=z['direction']*c['omega']*c['dt']+z['phase'];v=complex(*z['force'])*complex(math.cos(angle),math.sin(angle))
    expected+=v/(1+sum((x-y)**2 for x,y in zip(q['position'],z['position'])))
   assert r['field']==pytest.approx([expected.real,expected.imag],abs=1e-12)
   assert r['magnitude']<=2+1e-12 and r['energy_identity_error']<1e-12
 c=config();pts=[{'id':'left','position':[-1,0]},{'id':'right','position':[1,0]}]
 assert f.evaluate(c,pts)['samples'][0]['energy']==f.evaluate(c,pts)['samples'][1]['energy']
def test_feedback_persistence_and_bounded_stability():
 c=config();c.update(decay=.5,learning_rate=.25)
 feedback={'error_vectors':[[0,1],[0,-1]],'reference':'independent-local-error'}
 a=f.evaluate(c,S,feedback=feedback)
 assert a['checkpoint']['forces']==[[.5,.25],[.5,-.25]]
 saved=json.loads(json.dumps(a['checkpoint']));b=f.evaluate(c,S,saved)
 assert b['previous_result_sha256']==a['result_sha256']
 assert b['samples'][0]['field']==pytest.approx([math.cos(1)-.5*math.sin(1),0])
 state=b['checkpoint']
 for _ in range(100):
  result=f.evaluate(c,S,state,feedback);state=result['checkpoint'];assert result['samples'][0]['magnitude']<=2+1e-12
 broken=copy.deepcopy(state);broken['forces'][0][0]+=.1
 with pytest.raises(ValueError):f.evaluate(c,S,broken)
 changed=copy.deepcopy(c);changed['omega']=2
 with pytest.raises(ValueError):f.evaluate(changed,S,state)
def test_actual_field_changes_optional_selection_not_truth():
 plan={'nodes':[{'id':str(i),'connected':True,'route':'LINEAR_MATH','depends_on':[]} for i in range(5)]}
 samples=f.samples_from_plan(plan);c=f.default_config()
 a=f.evaluate(c,samples);chosen=f.select_verification_work(plan,a,1)
 assert chosen['selected_ids']==['2']
 c['sources'][0]['position']=[-1,0];c['sources'][1]['position']=[-1,0]
 b=f.evaluate(c,samples);assert f.select_verification_work(plan,b,1)['selected_ids']==['0']
 assert plan=={'nodes':[{'id':str(i),'connected':True,'route':'LINEAR_MATH','depends_on':[]} for i in range(5)]}
 assert 'answer' not in chosen and 'truth' not in chosen

def test_wrapper_field_projection_and_actual_selected_callback_feedback():
 plan={'nodes':[{'id':str(i),'connected':True,'route':'LINEAR_MATH','depends_on':[]} for i in range(5)]}
 original=copy.deepcopy(plan);step=f.plan_field_step(plan,'Derive exact relation.',budget=1)
 assert sum(r['attention_weight'] for r in step['projection']['rows'])==pytest.approx(1)
 assert step['verification_work']['selected_ids']==['2']
 actual={'question_sha256':step['question_sha256'],'nodes':copy.deepcopy(plan['nodes'])}
 called=[]
 def audit(request):called.append(request);return request['id']=='2'
 advanced=f.advance_field_feedback(step,actual,independent_audit=audit)
 assert [r['id'] for r in called]==['2'] and advanced['audits'][0]['status']=='HOST_AUDIT_PASSED'
 assert advanced['feedback']['error_vectors']==[[1,0],[0,1]]
 nextstep=f.plan_field_step(plan,'Derive exact relation.',json.loads(json.dumps(advanced['checkpoint'])))
 assert nextstep['field']['step']==1
 assert nextstep['field']['source_force_norms']!=step['field']['source_force_norms'] or nextstep['field']['samples'][0]['field']!=step['field']['samples'][0]['field']
 no_audit=f.advance_field_feedback(step,actual)
 assert no_audit['audits'][0]['status']=='NOT_AUDITED' and no_audit['feedback'] is None
 assert advanced['evidence_truth_changed'] is False and not advanced['mandatory_native_verification_skipped'] and plan==original
 changed=copy.deepcopy(actual);changed['nodes'][2]['route']='OTHER'
 with pytest.raises(ValueError):f.advance_field_feedback(step,changed,independent_audit=audit)
 changed=copy.deepcopy(actual);changed['question_sha256']='0'*64
 with pytest.raises(ValueError):f.advance_field_feedback(step,changed,independent_audit=audit)
