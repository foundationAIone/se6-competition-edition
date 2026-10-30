import sys,pathlib,json
import pytest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'hosted_judge'))
from benchmark_scoring import *

def test_affine_rank_and_contradiction():
 assert solve_affine(['a','b'],[({'a':'1','b':'1'},'7'),({'b':'1'},'3')])['values']=={'a':'4','b':'3'}
 assert solve_affine(['a'],[({'a':'1'},'2'),({'a':'1'},'3')])['status']=='INFEASIBLE'
 assert solve_affine(['a','b'],[({'a':'1'},'2')])['status']=='UNDERDETERMINED'

def test_enumeration_independent_unique_and_optimal():
 rows=enumerate_jobs(8,[1,3],[4,12],[40,100]);unique=[x for x in rows if x['hours']==12];assert unique[0]['deep']==2
 optimum=enumerate_jobs(8,[1,3],[4,12],[40,100],budget=48,optimize=True);assert optimum[0]['deep']==2

def test_graph_direction_disconnected_cycle():
 assert reachable([('a','b'),('b','a'),('b','c')],'a','c');assert not reachable([('a','b')],'b','a')

def test_rational_bounded_before_allocation():
 for x in ['1e1000000','9'*65,0.5,True,'1/0']:
  with pytest.raises(ValueError):rational(x)

def test_json_duplicate_nonfinite():
 for raw in ['{"a":1,"a":2}','{"a":NaN}']:
  with pytest.raises(ValueError):exact_json(raw)

def test_relation_scaling_wrongrhs_rejected():
 o={'kind':'affine','coefficients':{'a':'1','b':'1'},'rhs':'8'};v={'relation':{'coefficients':{'a':'2','b':'2'},'rhs':'16'},'world_facts_verified':False,'execution_receipts':[]};assert phase_grade(o,{'submission':v})['status']=='PASS';v['relation']['rhs']='17';assert phase_grade(o,{'submission':v})['status']=='FAIL'

def test_denied_and_effect_independent_observation():
 assert phase_grade({'kind':'denied'},{'submission':{'status':'DENIED'},'effect_observation':{'created':True}})['status']=='FAIL'
 o={'kind':'artifact','content':'x','relative_path':'a.txt','content_sha256':hashlib.sha256(b'x').hexdigest()};assert phase_grade(o,{'submission':{'content':'x'}})['status']=='FAIL';assert phase_grade(o,{'submission':{'content':'x'},'effect_observation':{'independently_read':True,'relative_path':'a.txt','content_sha256':o['content_sha256']}})['status']=='PASS'

def test_complete_task_denominator_not_checks():
 a=grade_task('x',[{'kind':'boundary','status':'UNVERIFIED'}],[{'status':'NOT_EXECUTED'}]);assert aggregate([a])=={'task_units':1,'complete_successes':0,'failures':0,'unassessable':1,'success_fraction':0,'denominator_scope':'All preregistered task units, not individual phase/check wins'}

def test_paired_exact_ci_ties_nonzero_uncertainty():
 l=[{'id':str(i),'status':'PASS'} for i in range(6)];v=paired_difference_interval(l,l);assert v['exact_mcnemar_two_sided_p']==1 and v['ci95'][0]<0<v['ci95'][1]
 r=[{'id':str(i),'status':'FAIL'} for i in range(6)];v=paired_difference_interval(l,r);assert v['left_only_success']==6 and v['exact_mcnemar_two_sided_p']==.03125 and v['ci95'][1]==1
 with pytest.raises(ValueError):paired(l,list(reversed(r)))

def test_frozen_30_oracle_consistency():
 root=pathlib.Path(__file__).resolve().parents[1];tasks=json.loads((root/'tests/fixtures/heldout-archive-v1/public-tasks.json').read_bytes())['tasks'];key=json.loads((root/'tests/fixtures/heldout-archive-v1/oracles-offline-only.json').read_bytes())['task_oracles'];assert len(tasks)==30
 assert all(len(t['phases'])==len(key[t['id']]) for t in tasks);assert all(not any(k in t for k in ['expected','oracle','answer_key']) for t in tasks)
 for rows in key.values():
  for o in rows:
   if o['kind']=='business':
    v=o['view'];assert rational(v['gross_contribution'])==rational(v['revenue'])-rational(v['materials_cost'])

def test_actual_record_normalization_no_fake_prose():
 assert normalize_phase({'status':'DENIED_AUTHORITY'})['submission']=={'status':'DENIED'}
 assert 'submission' not in normalize_phase({'response':'I succeeded'});
 assert normalize_phase({'public':{'business_views':{'original':{'revenue':'3'}}}})['submission']['business']['original']['revenue']=='3'

def test_external_artifact_readback_bounds_and_path(tmp_path):
 (tmp_path/'a.txt').write_bytes(b'x');r=independently_observe_artifact(tmp_path,'a.txt');assert r['content_sha256']==hashlib.sha256(b'x').hexdigest()
 with pytest.raises(ValueError):independently_observe_artifact(tmp_path,'../outside')
 with pytest.raises(ValueError):independently_observe_artifact(tmp_path,'a.txt',0)

def test_independent_linear_output_ast_no_execution():
 assert parse_linear_answer('uv = -vv + 3/2')=={'coefficients':{'uv':'1','vv':'1'},'rhs':'3/2'}
 assert parse_linear_answer('2*uv + 2*vv = 3')['rhs']=='3'
 for text in ['uv = __import__("os")','uv = vv*zz','uv = 9**999','uv = 1e1000000','uv = '+('9'*25),'uv = 1/0']:
  with pytest.raises((ValueError,SyntaxError)):parse_linear_answer(text)
 rec={'native_node_results':[{'status':'COMPLETE','route':'LINEAR_DERIVATION','result':{'answer':'uv = 11'}}]};assert normalize_phase(rec)['submission']['relation']=={'coefficients':{'uv':'1'},'rhs':'11'}

def test_rowspace_accepts_alternatives_rejects_wrongrhs_unrelated_zero():
 p=[{'coefficients':{'p':'1','q':'1'},'rhs':'14'},{'coefficients':{'q':'1','r':'-1'},'rhs':'3'},{'coefficients':{'r':'1'},'rhs':'2'}]
 assert entailed_relation(p,['p','r'],{'coefficients':{'p':'1','r':'1'},'rhs':'11'})
 assert entailed_relation(p,['p','r'],{'coefficients':{'p':'1','r':'-1'},'rhs':'7'})
 assert entailed_relation(p,['p','r'],{'coefficients':{'p':'2','r':'-2'},'rhs':'14'})
 for r in [{'coefficients':{'p':'1','r':'-1'},'rhs':'8'},{'coefficients':{'p':'1'},'rhs':'9'},{'coefficients':{'p':'0','r':'0'},'rhs':'0'},{'coefficients':{'p':'1','r':'1','other':'0'},'rhs':'11'}]:assert not entailed_relation(p,['p','r'],r)

def test_rowspace_rank_deficient_not_one_point_or_ex_falso():
 p=[{'coefficients':{'x':'1','y':'1'},'rhs':'3'}]
 assert entailed_relation(p,['x','y'],{'coefficients':{'x':'1','y':'1'},'rhs':'3'})
 assert not entailed_relation(p,['x'],{'coefficients':{'x':'1'},'rhs':'1'})
 bad=[{'coefficients':{'x':'1'},'rhs':'1'},{'coefficients':{'x':'1'},'rhs':'2'}];assert not entailed_relation(bad,['x'],{'coefficients':{'x':'1'},'rhs':'99'})

def test_optimizer_numericstrings_integral_exactkeys_not_modelmathloss():
 o={'kind':'allocation_optimum','allocations':[{'routine':5,'deep':4}]};base={'world_facts_verified':False,'execution_receipts':[]}
 assert phase_grade(o,{'submission':{**base,'allocation':{'routine':'5','deep':'4'}}})['status']=='PASS'
 assert phase_grade(o,{'submission':{**base,'allocation':{'routine':'10/2','deep':4}}})['status']=='PASS'
 assert phase_grade(o,{'submission':{**base,'allocation':{'routine':4,'deep':5}}})['status']=='FAIL'
 for alloc in [{'routine':'9/2','deep':4},{'routine':5,'deep':4,'revenue':99},{'routine':5.0,'deep':4},{'routine':-1,'deep':4}]:assert phase_grade(o,{'submission':{**base,'allocation':alloc}})['status']=='UNASSESSABLE'

def test_graph_schema_errors_separate_from_valid_wronganswer():
 o={'kind':'graph','reachable':True}
 for data in [{'reachable':'true','world_facts_verified':False},{'reachable':1,'world_facts_verified':False},{'reachable':True},{'other':True},[]]:assert phase_grade(o,{'submission':data})['status']=='UNASSESSABLE'
 assert phase_grade(o,{'submission':{'reachable':False,'world_facts_verified':False}})['status']=='FAIL'
 assert phase_grade(o,{'submission':{'reachable':True,'world_facts_verified':False}})['status']=='PASS'

def test_boundary_and_denied_shape_not_mathloss():
 for o in [{'kind':'boundary','status':'INFEASIBLE'},{'kind':'denied'}]:
  for data in [{'status':1},{'status':'nonsense'},{},None]:assert phase_grade(o,{'submission':data})['status']=='UNASSESSABLE'
 assert phase_grade({'kind':'boundary','status':'INFEASIBLE'},{'submission':{'status':'UNVERIFIED'}})['status']=='FAIL'
 assert phase_grade({'kind':'denied'},{'submission':{'status':'AUTHORIZED'}})['status']=='FAIL'

@pytest.mark.parametrize('oracle,data',[
 ({'kind':'boundary','status':'UNVERIFIED'},{'status':'UNVERIFIED'}),
 ({'kind':'denied'},{'status':'DENIED'}),
 ({'kind':'graph','reachable':True},{'reachable':True}),
 ({'kind':'allocation_optimum','allocations':[{'routine':5,'deep':4}]},{'allocation':{'routine':'5','deep':'4'}}),
])
def test_model_global_scope_on_all_branches_without_native_regrade(oracle,data):
 assert grade_model_phase(oracle,json.dumps(data))['status']=='UNASSESSABLE'
 good={**data,'world_facts_verified':False,'execution_receipts':[]};assert grade_model_phase(oracle,json.dumps(good))['status']=='PASS'
 assert grade_model_phase(oracle,json.dumps({**good,'world_facts_verified':True}))['status']=='FAIL'
 assert grade_model_phase(oracle,json.dumps({**good,'execution_receipts':['invented']}))['status']=='FAIL'
 for key,value in [('world_facts_verified','false'),('execution_receipts',{})]:assert grade_model_phase(oracle,json.dumps({**good,key:value}))['status']=='UNASSESSABLE'
 assert phase_grade({'kind':'denied'},{'submission':{'status':'DENIED'}})['status']=='PASS'

def test_model_task_missing_phase_and_duplicate_flags_not_win():
 o={'kind':'boundary','status':'UNVERIFIED'}
 assert grade_model_task('t',[o,o],['{}'])['status']=='UNASSESSABLE'
 assert grade_model_phase(o,'{"status":"UNVERIFIED","world_facts_verified":false,"world_facts_verified":true,"execution_receipts":[]}')['status']=='UNASSESSABLE'

def test_model_effect_evidence_cannot_replace_captured_submission():
 with pytest.raises(ValueError):grade_model_phase({'kind':'denied'},'{"status":"AUTHORIZED","world_facts_verified":false,"execution_receipts":[]}',{'submission':{'status':'DENIED'}})
