import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"private-native/canonical_operators"))
import copy,json,math
import pytest
import computational_interference_field as f

def config(forces=((1,0),(1,0)),phases=(0,0),omega=1,dt=.25):
    return {'sources':[{'position':[0,0],'force':list(v),'phase':p,'direction':d} for v,p,d in zip(forces,phases,(1,-1))],
        'omega':omega,'dt':dt,'decay':1,'learning_rate':.25}
S=[{'id':'origin','position':[0,0]}]
def test_constructive_cancellation_zero_controls():
    constructive=f.evaluate(config(omega=0),S);assert constructive['samples'][0]['field']==[2,0]
    cancellation=f.evaluate(config(phases=(0,math.pi),omega=0),S);assert cancellation['samples'][0]['magnitude']<1e-12
    zero=f.evaluate(config(forces=((0,0),(0,0))),S);assert zero['samples'][0]['field']==[0,0]

def test_counterrotation_time_not_static_geometry():
    c=config(dt=math.pi/4);first=f.evaluate(c,S);second=f.evaluate(c,S,first['checkpoint']);third=f.evaluate(c,S,second['checkpoint'])
    assert third['samples'][0]['magnitude']<1e-12
    assert second['samples'][0]['magnitude']==pytest.approx(math.sqrt(2))

def test_opposite_forces_become_constructive_after_quarter_turn():
    c=config(forces=((1,0),(-1,0)),dt=math.pi/4);r=f.evaluate(c,S)
    r=f.evaluate(c,S,r['checkpoint']);r=f.evaluate(c,S,r['checkpoint'])
    assert r['samples'][0]['field']==pytest.approx([0,2])

def test_symmetry_norm_conservation_interference_identity():
    c=config();samples=[{'id':'a','position':[-1,1]},{'id':'b','position':[1,1]}]
    r=f.evaluate(c,samples);swap=copy.deepcopy(c);swap['sources'].reverse()
    assert f.evaluate(swap,samples)['samples']==r['samples']
    assert r['samples'][0]['energy']==r['samples'][1]['energy']
    for row in r['samples']:
        assert row['rotation_norm_error']<1e-12 and row['energy_identity_error']<1e-12
        assert row['magnitude']<=row['analytic_norm_bound']+1e-12<=2+1e-12

def test_roundtrip_persistence_and_feedback_bounded():
    c=config();r=f.evaluate(c,S);cp=json.loads(json.dumps(r['checkpoint']))
    feedback={'error_vectors':[[1,1],[-1,1]],'reference':'closed-host-error'}
    for _ in range(100):
        r=f.evaluate(c,S,cp,feedback);cp=json.loads(json.dumps(r['checkpoint']))
        assert max(r['next_force_norms'])<=1+1e-12 and r['samples'][0]['magnitude']<=2+1e-12
    assert cp['step']==101

@pytest.mark.parametrize('key,value',[('step',5),('previous_result_sha256','f'*64),('config_sha256','0'*64)])
def test_state_tamper_rejected(key,value):
    c=config();cp=f.evaluate(c,S)['checkpoint'];cp[key]=value
    with pytest.raises(ValueError):f.evaluate(c,S,cp)

def plan():return {'nodes':[{'id':x,'route':'RELATIONAL','connected':True,'depends_on':[]} for x in ('left','center','right')]}
def test_field_directs_actual_extra_audit_and_retains_separate_state():
    p=plan();before=copy.deepcopy(p);step=f.plan_field_step(p,'Owner supplied public relation')
    assert step['verification_work']['selected_ids']==['center']
    assert sum(r['attention_weight'] for r in step['projection']['rows'])==pytest.approx(1)
    seen=[]
    def independent(req):seen.append(req['id']);return False
    actual={'question_sha256':step['question_sha256'],'nodes':copy.deepcopy(p['nodes'])}
    done=f.advance_field_feedback(step,actual,independent_audit=independent)
    assert seen==['center'] and done['audits'][0]['status']=='HOST_AUDIT_FAILED'
    assert done['feedback'] and not done['evidence_truth_changed'] and p==before
    second=f.plan_field_step(p,'Correct the supplied relation',done['checkpoint'])
    assert second['configuration_rebase'] and second['field']['step']==1
    assert second['field']['samples']!=step['field']['samples']

def test_absent_audit_is_not_verification_and_bad_actual_binding_rejects():
    p=plan();step=f.plan_field_step(p,'public');out={'question_sha256':step['question_sha256'],'nodes':p['nodes']}
    r=f.advance_field_feedback(step,out);assert r['audits'][0]['status']=='NOT_AUDITED' and r['feedback'] is None
    out['question_sha256']='0'*64
    with pytest.raises(ValueError):f.advance_field_feedback(step,out)

def test_boundaries_and_no_authority_or_physical_claim():
    c=config();c['sources'][1]['direction']=1
    with pytest.raises(ValueError):f.evaluate(c,S)
    with pytest.raises(ValueError):f.evaluate(config(),[{'id':'bad','position':[2,0]}])
    c=config();c['omega']=float('nan')
    with pytest.raises(ValueError):f.evaluate(c,S)
    r=f.plan_field_step(plan(),'public');assert r['source_construction']['physical_claim'] is False
    assert f.select_verification_work(plan(),r['field'],0)['selected_ids']==[]

def test_disconnected_or_blocked_dependency_never_receives_audit_work():
    p={'nodes':[{'id':'blocked','route':'DIRECT_MODEL','connected':True,'depends_on':[]},
        {'id':'child','route':'RELATIONAL','connected':True,'depends_on':['blocked']}]}
    step=f.plan_field_step(p,'public')
    assert step['verification_work']['selected_ids']==[]
