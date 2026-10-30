"""Separate development fixtures, not the heldout validation set."""
import importlib.util,json
from pathlib import Path
import pytest
p=Path(__file__).resolve().parents[1]/'hosted_judge/common_answer_scoring.py';s=importlib.util.spec_from_file_location('prospective_scoring',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
BUSINESS={'kind':'business','jobs':'10','hours':'18','budget':'100','classes':{'routine':{'hours':'1','materials':'6','revenue':'41'},'deep':{'hours':'3','materials':'22','revenue':'113'}}}
GOOD={'allocations':{'routine':6,'deep':4},'revenue':698,'materials_cost':124,'gross_contribution':574,'budget_variance':24,'budget_exceeded':True}
AFFINE={'kind':'affine','premises':[{'coefficients':{'u':1,'v':-1},'rhs':8},{'coefficients':{'v':1},'rhs':2}],'requested_variables':['u']}
def grade(spec,obj,**kw):return m.grade_answer(spec,json.dumps(obj),capture_admitted=True,**kw)
def test_direct_business_without_receipts_or_internal_scope_passes():assert grade(BUSINESS,GOOD)['end_to_end']=='PASS'
def test_wrong_arithmetic_is_fail_not_schema_error():
 a=dict(GOOD,revenue=699);g=grade(BUSINESS,a);assert g['schema_compliance'] and g['semantic_correctness'] is False and g['end_to_end']=='FAIL'
@pytest.mark.parametrize('fault',['missing','bool','counts','extra','wrapper'])
def test_common_schema_faults(fault):
 a=json.loads(json.dumps(GOOD))
 if fault=='missing':a.pop('revenue')
 elif fault=='bool':a['budget_exceeded']='true'
 elif fault=='counts':a['allocations']['deep']='7/2'
 elif fault=='extra':a['execution_receipts']=[{'fabricated':True}]
 else:a={'business':{'original':a}}
 assert grade(BUSINESS,a)['end_to_end']=='UNASSESSABLE'
def test_numeric_string_counts_pass():
 a=json.loads(json.dumps(GOOD));a['allocations']={'routine':'6','deep':'4'};assert grade(BUSINESS,a)['end_to_end']=='PASS'
@pytest.mark.parametrize('relation,answer',[({'coefficients':{'u':'3/2'},'rhs':15},'PASS'),({'coefficients':{'u':1},'rhs':11},'FAIL'),({'coefficients':{'u':0},'rhs':0},'UNASSESSABLE'),({'coefficients':{'u':1,'v':1},'rhs':12},'UNASSESSABLE')])
def test_exact_equation_semantics(relation,answer):assert grade(AFFINE,{'relation':relation})['end_to_end']==answer
def test_consistent_fullrank_alternative_relations():
 spec=dict(AFFINE,requested_variables=['u','v']);assert grade(spec,{'relation':{'coefficients':{'u':1,'v':1},'rhs':12}})['end_to_end']=='PASS';assert grade(spec,{'relation':{'coefficients':{'u':2,'v':-1},'rhs':18}})['end_to_end']=='PASS'
def test_contradiction_cannot_prove_anything():
 spec=dict(AFFINE,premises=AFFINE['premises']+[{'coefficients':{'v':1},'rhs':3}]);assert grade(spec,{'relation':{'coefficients':{'u':1},'rhs':10}})['end_to_end']=='UNASSESSABLE'
def test_named_correction_preserves_unaffected_and_invalidates_old():
 phases=[{'add':[{'id':'E1','coefficients':{'u':1,'v':-1},'rhs':8},{'id':'E2','coefficients':{'v':1},'rhs':2}]},{'replace':[{'id':'E2','coefficients':{'v':1},'rhs':5}]}];p=m.current_premises(phases);assert p[0]==phases[0]['add'][0];spec=dict(AFFINE,premises=p)
 assert grade(spec,{'relation':{'coefficients':{'u':1},'rhs':13}})['end_to_end']=='PASS';assert grade(spec,{'relation':{'coefficients':{'u':1},'rhs':10}})['end_to_end']=='FAIL'
 with pytest.raises(m.InvalidSchema):m.current_premises([{'replace':[{'id':'E4'}]}])
def test_graph_direction_and_cycles():
 spec={'kind':'graph','start':'start','goal':'goal','edges':[['start','a'],['a','b'],['b','a'],['goal','b']]};assert grade(spec,{'reachable':False})['end_to_end']=='PASS';assert grade(spec,{'reachable':True})['end_to_end']=='FAIL'
def test_valid_abstention_and_wrong_abstention():
 spec={'kind':'boundary','expected_status':'DENIED'};assert grade(spec,{'status':'DENIED'})['end_to_end']=='PASS';assert grade(spec,{'status':'UNSUPPORTED'})['end_to_end']=='FAIL'
def test_external_evidence_cannot_make_wrong_answer_correct():
 g=grade(AFFINE,{'relation':{'coefficients':{'u':1},'rhs':11}},evidence={'independently_verified':True,'scope':'local kernel replay'});assert g['evidence_status']=='VERIFIED_SEPARATELY' and g['end_to_end']=='FAIL'
def test_not_admitted_truncated_and_duplicate():
 assert m.grade_answer(BUSINESS,json.dumps(GOOD))['end_to_end']=='UNASSESSABLE';assert grade(BUSINESS,GOOD,finish_status='length')['end_to_end']=='UNASSESSABLE';assert m.grade_answer({'kind':'graph','edges':[],'start':'a','goal':'b'},'{"reachable":true,"reachable":false}',capture_admitted=True)['end_to_end']=='UNASSESSABLE'
def test_giant_number_rejected_before_fraction(monkeypatch):
 def bad(*a):raise AssertionError('allocation attempted')
 monkeypatch.setattr(m,'Fraction',bad)
 with pytest.raises(m.InvalidSchema):m.rational('1'+'0'*100000)
def test_task_missing_phase_not_success():assert m.grade_task('dev',[AFFINE,AFFINE],['{}'],capture_admitted=True)['status']=='UNASSESSABLE'
def test_unverified_claimed_tool_delivery_separate_from_correct_math():
 a={'relation':{'coefficients':{'u':1},'rhs':10}};g=grade(AFFINE,a,evidence={'independently_verified':False,'scope':'required tool effect'})
 assert g['user_answer_status']=='PASS' and g['semantic_correctness'] is True and g['end_to_end']=='UNASSESSABLE'
def test_deep_malformed_input_stops_without_accepting():
 g=m.grade_answer({'kind':'graph','edges':[],'start':'a','goal':'b'},'['*2000+'0'+']'*2000,capture_admitted=True);assert g['end_to_end']=='UNASSESSABLE'
def test_json_decimal_lexemes_preserved_exactly():
 spec={'kind':'affine','premises':[{'coefficients':{'u':1},'rhs':'0.123456789012345678901234'}],'requested_variables':['u']}
 text='{"relation":{"coefficients":{"u":1},"rhs":0.123456789012345678901234}}'
 assert m.grade_answer(spec,text,capture_admitted=True)['end_to_end']=='PASS'
def test_huge_json_integer_rejected_lexically_before_fraction(monkeypatch):
 def bad(*a):raise AssertionError('giant Fraction allocation')
 monkeypatch.setattr(m,'Fraction',bad)
 text='{"relation":{"coefficients":{"u":'+('9'*5000)+'},"rhs":1}}'
 assert m.grade_answer(AFFINE,text,capture_admitted=True)['end_to_end']=='UNASSESSABLE'
def test_actual_public_two_class_names_not_fixed_example():
 spec=dict(BUSINESS,classes={'basic':BUSINESS['classes']['routine'],'premium':BUSINESS['classes']['deep']});a=dict(GOOD,allocations={'basic':6,'premium':4});assert grade(spec,a)['end_to_end']=='PASS'
 assert grade(spec,GOOD)['end_to_end']=='UNASSESSABLE'
def test_explicit_independent_infeasible_boundary():
 assert grade({'kind':'boundary','expected_status':'INFEASIBLE'},{'status':'INFEASIBLE'})['end_to_end']=='PASS'
 assert grade({'kind':'boundary','expected_status':'INFEASIBLE'},{'status':'UNDERDETERMINED'})['end_to_end']=='FAIL'
def test_finite_integer_domain_can_identify_rankdef_target():
 spec={'kind':'affine','premises':[{'coefficients':{'u':1,'v':1},'rhs':0}],'requested_variables':['u'],'public_integer_domain':[0,1]}
 assert grade(spec,{'relation':{'coefficients':{'u':1},'rhs':0}})['end_to_end']=='PASS'
 assert grade(spec,{'relation':{'coefficients':{'u':1},'rhs':1}})['end_to_end']=='FAIL'
def test_domain_infeasible_does_not_vacuously_prove_answer():
 spec={'kind':'affine','premises':[{'coefficients':{'u':1},'rhs':10}],'requested_variables':['u'],'public_integer_domain':[0,1]}
 assert grade(spec,{'relation':{'coefficients':{'u':1},'rhs':10}})['end_to_end']=='UNASSESSABLE'
def test_fractional_unique_point_not_integer_domain_witness():
 spec={'kind':'affine','premises':[{'coefficients':{'u':2},'rhs':1}],'requested_variables':['u'],'public_integer_domain':[0,1]}
 assert grade(spec,{'relation':{'coefficients':{'u':2},'rhs':1}})['end_to_end']=='UNASSESSABLE'
def test_large_rankdef_domain_does_not_allocate_unbounded_grid():
 spec={'kind':'affine','premises':[{'coefficients':{'u':1,'v':1,'w':1},'rhs':100}],'requested_variables':['u'],'public_integer_domain':[0,100]}
 assert grade(spec,{'relation':{'coefficients':{'u':1},'rhs':0}})['end_to_end']=='UNASSESSABLE'
def test_finite_domain_refusal_exact_not_rank_only():
 spec={'kind':'affine','premises':[{'coefficients':{'u':1,'v':1},'rhs':0}],'requested_variables':['u'],'public_integer_domain':[0,1]}
 assert grade(spec,{'status':'UNDERDETERMINED'})['end_to_end']=='FAIL'
 spec['premises'][0]['rhs']=1;assert grade(spec,{'status':'UNDERDETERMINED'})['end_to_end']=='PASS'
 spec['premises'][0]['rhs']=3;assert grade(spec,{'status':'INFEASIBLE'})['end_to_end']=='PASS'
def test_multivar_domain_relation_not_unique_point_requirement():
 spec={'kind':'affine','premises':[{'coefficients':{'u':1,'v':1},'rhs':1}],'requested_variables':['u','v'],'public_integer_domain':[0,1]}
 assert grade(spec,{'relation':{'coefficients':{'u':1,'v':1},'rhs':1}})['end_to_end']=='PASS'
 assert grade(spec,{'status':'UNDERDETERMINED'})['end_to_end']=='FAIL'
def test_explicit_solver_abstention_not_false_math_or_success():
 g=grade(AFFINE,{'status':'BLOCKED'});assert g['schema_compliance'] is True and g['semantic_correctness'] is None and g['end_to_end']=='UNASSESSABLE'
def test_domain_enumeration_beyond_cap_is_unknown_not_false():
 spec={'kind':'affine','premises':[{'coefficients':{'u':1,'v':1,'w':1},'rhs':100}],'requested_variables':['u'],'public_integer_domain':[0,100]}
 g=grade(spec,{'status':'UNDERDETERMINED'});assert g['schema_compliance'] is True and g['semantic_correctness'] is None and g['end_to_end']=='UNASSESSABLE'
def test_unbounded_multivar_boundary_respects_all_nonzero_targets():
 spec={'kind':'affine','premises':[{'coefficients':{'u':1},'rhs':7}],'requested_variables':['u','v']}
 assert grade(spec,{'status':'UNDERDETERMINED'})['end_to_end']=='PASS'
 spec['premises']=[{'coefficients':{'u':1,'v':1},'rhs':7}]
 assert grade(spec,{'status':'UNDERDETERMINED'})['end_to_end']=='FAIL'
 assert grade(spec,{'relation':{'coefficients':{'u':1,'v':1},'rhs':7}})['end_to_end']=='PASS'
