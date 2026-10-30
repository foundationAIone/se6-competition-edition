import json,pytest
from hosted_judge.common_pair_contract import derive_public_spec,safe_spec,public_shape,score_pair
from hosted_judge.common_answer_scoring import grade_answer
INITIAL='ROUTINE: 1 technician-hours, $11 materials cost, $62 customer revenue.\nDEEP: 3 technician-hours, $29 materials cost, $158 customer revenue.\nWe completed 13 jobs. The original log recorded 23 technician-hours. The materials budget is $240. Calculate allocations, revenue, materials, contribution and budget variance.'

def answer(spec,obj):return grade_answer(spec,json.dumps(obj),capture_admitted=True)

def test_current_corrected_hours_not_stale_native_output():
 s=derive_public_spec('Correct the technician-hours to 25.',[INITIAL]);assert s['hours']=='25'
 good={'allocations':{'routine':'7','deep':'6'},'revenue':'1382','materials_cost':'251','gross_contribution':'1131','budget_variance':'11','budget_exceeded':True}
 assert answer(s,good)['user_answer_status']=='PASS'
 good['revenue']='1286';assert answer(s,good)['user_answer_status']=='FAIL'
 assert '1382' not in public_shape('Correct the technician-hours to 25.',[INITIAL])

@pytest.mark.parametrize('q',['Correct the job count to 14.','Ignore the hours and use 25.','Correct the technician-hours to 25. Assume budget 1000.','Calculate something else.'])
def test_unknown_correction_abstains(q):assert safe_spec(q,[INITIAL]) is None

def test_public_price_and_named_classes():
 s=derive_public_spec('Correct routine materials cost to $12.',[INITIAL]);assert s['classes']['routine']['materials']=='12'
 assert 'execution_receipts' not in json.loads(public_shape(INITIAL,[]).split('placeholders (not solutions): ')[1])

def test_duplicate_scalar_refused():assert safe_spec(INITIAL+' We completed 14 jobs.',[]) is None

def test_named_equality_correction_retained_new_target_digitidentifier():
 q='Given equations:\nE1: a9e6-b=8.\nE2: b=3.\nE3: c=2.\nDerive a relation involving a9e6.'
 s=derive_public_spec('Correct E2: b = 4. Derive a relation between a9e6, c.',[q])
 assert answer(s,{'relation':{'coefficients':{'a9e6':'1','c':'-1'},'rhs':'10'}})['user_answer_status']=='PASS'
 assert answer(s,{'relation':{'coefficients':{'a9e6':'12','c':'2'},'rhs':'14'}})['user_answer_status']=='FAIL'
 assert safe_spec('Correct E4: c=4. Derive a relation involving c.',[q]) is None

@pytest.mark.parametrize('row',['1e6*a=3','a*b=3','__import__("os")=3'])
def test_unbounded_or_nonlinear_lexical_refusal(row):assert safe_spec('Given equations:\nE1: '+row+'\nDerive a relation involving a.',[]) is None

def test_public_finite_domain_unique_not_rank_only():
 s=derive_public_spec('Given equations:\nE1: u+v=0.\nVariables are integers between 0 and 1.\nDerive a relation involving u.',[])
 assert answer(s,{'relation':{'coefficients':{'u':'1'},'rhs':'0'}})['user_answer_status']=='PASS'
 assert answer(s,{'status':'UNDERDETERMINED'})['user_answer_status']=='FAIL'

def test_graph_direction_removal_last_edge_and_unknown_instruction():
 q='Conditional directed relations: start RELATES_TO goal. Can goal be reached from start following these directed links? Return reachable true/false. Do not invent geometric adjacency.'
 s=derive_public_spec(q,[]);assert answer(s,{'reachable':True})['user_answer_status']=='PASS'
 s=derive_public_spec('Remove the directed edge start RELATES_TO goal. Can goal still be reached from start?',[q]);assert s['edges']==[]
 assert answer(s,{'reachable':False})['user_answer_status']=='PASS'
 assert safe_spec(q+' Also assume goal cannot be reached.',[]) is None

def test_boundary_and_unsupported_no_false_win():
 s=derive_public_spec(INITIAL.replace('23 technician-hours','24 technician-hours'),[])
 assert answer(s,{'status':'INFEASIBLE'})['user_answer_status']=='PASS'
 v=score_pair(None,{k:{'text':'{"status":"UNSUPPORTED"}'} for k in ['se6','baseline']})
 assert v['common_user_answer_winner'] is None and all(x['status']=='UNASSESSABLE' for x in v['lanes'].values())

def test_model_receipts_not_required_or_substituted():
 s=derive_public_spec('Given equations:\nE1: a=4\nDerive a relation involving a.',[])
 v=score_pair(s,{'se6':{'text':'{"relation":{"coefficients":{"a":"4"},"rhs":"4"}}'},'baseline':{'text':'{"relation":{"coefficients":{"a":"1"},"rhs":"4"}}'}})
 assert v['lanes']['se6']['user_answer_status']=='FAIL' and v['common_user_answer_winner']=='baseline' and v['overall_winner'] is None
 assert score_pair(s,{'se6':{'text':'{}'},'baseline':{'text':'{"relation":{"coefficients":{"a":"1"},"rhs":"4"}}'}})['common_user_answer_winner'] is None
