"""Actual mapped edges, candidate metric field effect and post-proof state."""
import sys,math,copy,pytest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'private-native/canonical_operators'))
from native_bridge import preflight
import field_navigation as n
import toroidal_field_realization as f

def setup(polarities=[-1,1]):
 plan={'nodes':[{'id':'n'+str(i),'route':'RELATIONAL','connected':True,'input':'fixture relationship '+str(i),'depends_on':['n1'] if i in (2,6) else []} for i in range(1,7)]}
 pre=preflight('Fixture relational environment',plan);env=n.environment(pre['plan_mapping'],plan,pre['admitted_ids']);s=f.sources_from_plan(plan,pre['plan_mapping']);field=f.realize_toroidal(s['sources'],sample_points=env['sample_points'],parameters={**copy.deepcopy(f.DEFAULT),'polarities':polarities,'line_steps':8})
 goals={'goal_ids':pre['admitted_ids'],'budget':2,'audit_budget':1}
 return plan,pre,env,field,goals

def test_hex19_metric_and_actual_edges():
 _,pre,env,_,_=setup();assert len(env['circles'])==19 and max(math.hypot(*c['position']) for c in env['circles'])==pytest.approx(2)
 assert all(c['radius']==1 for c in env['circles'])
 assert env['flower_lineage']==pre['plan_mapping']['model']['flower_lineage']
 assert any(a['kind']=='DEPENDS_ON' and a['direction']=='REVERSE_INSPECTION' for a in env['arcs'])

def test_actual_field_changes_path_vs_matched_ordinary():
 _,pre,env,field,g=setup();a=n.navigate(env,None,field,g);b=n.navigate(env,None,field,g,mode='ordinary')
 assert a['trajectory']==['source','n1','n6'];assert b['trajectory']==['source','n1','n2']
 assert [r['reachable_choices'] for r in a['choices']][0][0]['field_score']==[r['reachable_choices'] for r in b['choices']][0][0]['field_score']
 assert a['selected_ids']==['n6'];done=n.finish_navigation(env,a,pre['admitted_ids']);assert done['checkpoint']['position']=='n6'

def test_zero_field_identity_and_ordinary_control():
 _,pre,env,field,g=setup();sources=field['inputs']['mapped_sources'];zero=f.realize_toroidal(sources,sample_points=env['sample_points'],parameters={**copy.deepcopy(f.DEFAULT),'source_gains':[0,0],'line_steps':8})
 a=n.navigate(env,None,zero,g);assert a['reason']=='ZERO_FIELD_IDENTITY' and a['trajectory']==['source'] and not a['selected_ids']
 assert len(n.navigate(env,None,zero,g,mode='ordinary')['trajectory'])>1

def test_boundary_unreachable_goals_and_map_tamper():
 plan,pre,env,field,g=setup();bad={**g,'goal_ids':['invented']}
 with pytest.raises(ValueError,match='GOAL_ADMISSION'):n.navigate(env,None,field,bad)
 e=copy.deepcopy(env);e['arcs'][0]['to']='invented'
 with pytest.raises(ValueError,match='ENVIRONMENT_SEAL'):n.navigate(e,None,field,g)
 result=n.navigate(env,None,field,g)
 with pytest.raises(ValueError,match='ACTUAL_NODE_NOT_VERIFIED'):n.finish_navigation(env,result,['n1'])
 with pytest.raises(ValueError,match='NAVIGATION_BUDGET'):n.navigate(env,None,field,{**g,'budget':True})

def test_state_and_orientation_seals_and_actual_binding():
 _,pre,env,field,g=setup();result=n.navigate(env,None,field,g);cp=n.finish_navigation(env,result,pre['admitted_ids'])['checkpoint'];nextresult=n.navigate(env,cp,field,g);assert nextresult['start']=='n6' and nextresult['navigation_step']==1
 forged=copy.deepcopy(result);forged['proposed_checkpoint']['orientation']=[0,0,0];forged['proposed_checkpoint']['state_sha256']=f.digest({k:v for k,v in forged['proposed_checkpoint'].items() if k!='state_sha256'});forged['navigation_sha256']=f.digest({k:v for k,v in forged.items() if k!='navigation_sha256'})
 with pytest.raises(ValueError,match='ACTUAL_ORIENTATION'):n.finish_navigation(env,forged,pre['admitted_ids'])

def test_changed_actual_identity_rebases_without_native_memory_claim():
 plan,pre,env,field,g=setup();cp=n.finish_navigation(env,n.navigate(env,None,field,g),pre['admitted_ids'])['checkpoint']
 plan['nodes'][0]['input']='changed relationship';newpre=preflight('Changed evidence',plan);newenv=n.environment(newpre['plan_mapping'],plan,newpre['admitted_ids']);newfield=f.realize_toroidal(f.sources_from_plan(plan)['sources'],sample_points=newenv['sample_points'],parameters=field['numeric']['parameters'])
 result=n.navigate(newenv,cp,newfield,g);assert result['start']=='source' and result['state_rebase'] and result['navigation_step']==1
