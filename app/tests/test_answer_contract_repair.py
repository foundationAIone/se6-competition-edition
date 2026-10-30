"""Separate development contracts, no historical response mutation/regrading."""
import pytest
from hosted_judge.answer_contract import decode_final,verify_user_answer,make_envelope
from hosted_judge.typed_native import prepare

BUSINESS=('ROUTINE: 1 technician-hours, $4 materials cost, $30 customer revenue.\n'
 'DEEP: 3 technician-hours, $9 materials cost, $80 customer revenue.\n'
 'We completed 6 jobs. The original log recorded 10 technician-hours. The materials budget is $35. Calculate allocations, revenue, materials, contribution and budget variance.')
VALID={'allocations':{'routine':'4','deep':'2'},'revenue':'280','materials_cost':'34','gross_contribution':'246','budget_variance':'-1','budget_exceeded':False}

def test_complete_business_and_wrong_calculation_rejected_without_internal_model_fields():
    p=prepare(BUSINESS);assert verify_user_answer('business',VALID,p['public_facts'])['semantic']
    wrong={**VALID,'revenue':'279'};assert verify_user_answer('business',wrong,p['public_facts'])=={'schema':True,'semantic':False,'reason':'SEMANTIC_MISMATCH'}
    missing={k:v for k,v in VALID.items() if k!='budget_exceeded'}
    assert verify_user_answer('business',missing,p['public_facts'])['schema'] is False
    fake={**VALID,'execution_receipts':['model-invented-receipt']}
    assert verify_user_answer('business',fake,p['public_facts'])['schema'] is False

def test_model_scope_is_server_bound_not_a_required_model_payload():
    p=prepare(BUSINESS);e=make_envelope(p,VALID,task_id='development',cycle=1,origin='MODEL')
    assert e['status']=='COMPLETE' and e['checks']['evidence'] is False
    assert e['scope']['question_sha256']==p['original_question_sha256'] and e['scope']['world_facts_verified'] is False
    assert not e['end_to_end_native_complete'] and not e['provenance']['model_answer_substituted']
    with pytest.raises(ValueError):make_envelope(p,VALID,task_id='',cycle=1,origin='MODEL')

@pytest.mark.parametrize('text,finish',[('{','stop'),('{}','length'),('```json\n{}\n```','stop'),('[{}]','stop'),('{},{}','stop'),('{"x":1,"x":2}','stop'),('{"x":NaN}','stop')])
def test_malformed_duplicate_truncated_nonfinal_rejected(text,finish):
    with pytest.raises(ValueError):decode_final(text,finish)

def test_decimal_lexeme_preserved_and_finish_separate():
    assert decode_final('{"v":0.000000000000000000000001}','stop')['v']=='0.000000000000000000000001'
    p=prepare(BUSINESS);e=make_envelope(p,VALID,task_id='dev',cycle=0,origin='MODEL',finish_reason='length')
    assert e['checks']['semantic'] is True and not e['checks']['finish'] and e['status']=='BLOCKED'

def test_correct_equation_not_coefficient_value_confusion():
    p=prepare('Given equations:\nA: dj+ek=7.\nB: ek=2.\nDerive a relation involving dj.')
    good={'relation':{'coefficients':{'dj':'1'},'rhs':'5'}}
    wrong={'relation':{'coefficients':{'dj':'5'},'rhs':'5'}}
    assert verify_user_answer('affine',good,p['public_facts'])['semantic'] is True
    assert verify_user_answer('affine',wrong,p['public_facts'])['semantic'] is False

def test_valid_alternative_and_nonzero_targets():
    p=prepare('Given equations:\nA: dj+ek=7\nB: ek=2\nDerive a relation between dj, ek.')
    alternate={'relation':{'coefficients':{'dj':'1','ek':'-1'},'rhs':'3'}}
    assert verify_user_answer('affine',alternate,p['public_facts'])['semantic'] is True
    bad={'relation':{'coefficients':{'dj':'1','ek':'0'},'rhs':'5'}}
    assert verify_user_answer('affine',bad,p['public_facts'])['schema'] is False

def test_contradictions_do_not_entail_arbitrary_answer_and_abstain():
    p=prepare('Given equations:\nA: dj=3\nB: dj=4\nDerive a relation involving dj.')
    assert p['public_facts']['boundary_status']=='INFEASIBLE'
    assert verify_user_answer('affine',{'relation':{'coefficients':{'dj':'1'},'rhs':'999'}},p['public_facts'])['semantic'] is False
    assert verify_user_answer('affine',{'status':'INFEASIBLE'},p['public_facts'])['semantic'] is True

def test_underconstrained_relation_can_be_verified_not_single_variable_guess():
    p=prepare('Given equations:\nA: dj+ek=7\nDerive a relation between dj, ek.')
    assert verify_user_answer('affine',{'relation':{'coefficients':{'dj':'1','ek':'1'},'rhs':'7'}},p['public_facts'])['semantic'] is True

def test_graph_directed_no_geometric_or_reverse_edges():
    p=prepare('Conditional directed graph: start RELATES_TO gate; goal RELATES_TO gate. Can goal be reached from start?')
    assert verify_user_answer('graph',{'reachable':False},p['public_facts'])['semantic'] is True
    assert verify_user_answer('graph',{'reachable':True},p['public_facts'])['semantic'] is False


def test_explicit_domain_singleton_infeasible_and_no_vacuous_relation():
    from hosted_judge.answer_contract import verify_user_answer
    facts={'premises':[{'coefficients':{'u':'1','v':'1'},'rhs':'0'}],'requested_variables':['u'],'public_integer_domain':[0,1]}
    valid=verify_user_answer('affine',{'relation':{'coefficients':{'u':'1'},'rhs':'0'}},facts)
    assert valid['semantic'] is True and valid['cells_checked']==4
    assert valid['verification_scope']=='EXHAUSTIVE_EXPLICIT_PUBLIC_INTEGER_DOMAIN_ONLY'
    assert verify_user_answer('affine',{'status':'UNDERDETERMINED'},facts)['semantic'] is False
    bad={**facts,'premises':[{'coefficients':{'u':'1','v':'1'},'rhs':'3'}]}
    assert verify_user_answer('affine',{'status':'INFEASIBLE'},bad)['semantic'] is True
    assert verify_user_answer('affine',{'relation':{'coefficients':{'u':'1'},'rhs':'0'}},bad)['semantic'] is False


def test_public_domain_genuine_underdetermination_and_verifier_cap():
    from hosted_judge.answer_contract import verify_user_answer
    facts={'premises':[{'coefficients':{'u':'1','v':'1'},'rhs':'1'}],'requested_variables':['u'],'public_integer_domain':[0,1]}
    assert verify_user_answer('affine',{'status':'UNDERDETERMINED'},facts)['semantic'] is True
    assert verify_user_answer('affine',{'relation':{'coefficients':{'u':'1'},'rhs':'0'}},facts)['semantic'] is False
    wide={**facts,'premises':[{'coefficients':{k:'1' for k in ('u','v','w','x')},'rhs':'1'}],'public_integer_domain':[0,20]}
    checked=verify_user_answer('affine',{'status':'UNDERDETERMINED'},wide)
    assert checked['semantic'] is True and checked['cells_checked']==194481
    over={**wide,'public_integer_domain':[0,22]}
    checked=verify_user_answer('affine',{'status':'INFEASIBLE'},over)
    assert checked['semantic'] is None and checked['reason']=='PUBLIC_DOMAIN_RESOURCE_BOUND'


def test_business_infeasible_status_independent_of_claimed_boundary_flag():
    from hosted_judge.answer_contract import verify_user_answer
    facts={'classes':['basic','deep'],'hours_per_job':{'basic':'1','deep':'3'},'total_jobs':'10','total_hours':'11','budget':'1'}
    assert verify_user_answer('business',{'status':'INFEASIBLE'},facts)['semantic'] is True
    for hours in ('12','12.0','10','30'):
        valid={**facts,'total_hours':hours,'boundary_status':'INFEASIBLE'}
        checked=verify_user_answer('business',{'status':'INFEASIBLE'},valid)
        assert checked['semantic'] is False
        assert checked['verification_scope']=='PUBLIC_COMPLETED_JOBS_NONNEGATIVE_INTEGER_CONSERVATION_ONLY'
    for hours in ('9','31'):
        assert verify_user_answer('business',{'status':'INFEASIBLE'},{**facts,'total_hours':hours})['semantic'] is True
    equal={**facts,'hours_per_job':{'basic':'2','deep':'2'},'total_hours':'20'}
    assert verify_user_answer('business',{'status':'INFEASIBLE'},equal)['semantic'] is False
    assert verify_user_answer('business',{'status':'INFEASIBLE'},{**equal,'total_hours':'21'})['semantic'] is True
