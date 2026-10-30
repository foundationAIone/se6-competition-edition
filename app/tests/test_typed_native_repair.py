"""Real existing native tools on new development cases, plus HOST-only graph."""
from pathlib import Path
import hashlib,json
import pytest
from hosted_judge.typed_native import prepare,finalize,digest,checked

def test_lossless_digit_identifier_and_sentence_normalization():
    p=prepare('Given equations:\nA: x2y+zz=7.\nB: zz=2.\nDerive a relation involving x2y.')
    assert 'x2y' in p['public_facts']['premises'][0]['coefficients']
    assert p['native_question']=='Given equations:\nA: x2y+zz=7\nB: zz=2\nDerive a relation involving x2y.'
    with pytest.raises(ValueError):prepare('Given equations:\nA: x2y*zz=7\nDerive a relation involving x2y.')
    with pytest.raises(ValueError,match='SCIENTIFIC'):prepare('Given equations:\nE1: u=1e2\nDerive a relation involving u.')

def test_graph_remove_last_edge_and_identity_zero_edges():
    p=prepare('Conditional directed graph: start RELATES_TO goal. Can goal be reached from start?')
    first=finalize(p,None,task_id='dev_graph',cycle=0)
    assert first['envelope']['user_answer']=={'reachable':True} and first['envelope']['origin']=='HOST_DETERMINISTIC'
    p=prepare('Remove the directed edge start RELATES_TO goal from the retained graph. Can goal still be reached from start?',first['next_state'])
    second=finalize(p,None,task_id='dev_graph',cycle=1)
    assert second['envelope']['user_answer']=={'reachable':False} and not second['envelope']['end_to_end_native_complete']
    p=prepare('Remove the directed edge start RELATES_TO goal from the retained graph. Can start still be reached from start?',first['next_state'])
    assert finalize(p,None,task_id='dev_graph',cycle=1)['envelope']['user_answer']=={'reachable':True}

def test_source_scope_seal_and_bad_correction():
    p=prepare('Given equations:\nA: dj+ek=7\nB: ek=2\nDerive a relation involving dj.')
    broken={**p,'native_question':'fabricated'}
    with pytest.raises(ValueError):checked(broken)
    with pytest.raises(ValueError):prepare('Correct B: ek=3. Derive a relation involving dj.')
    with pytest.raises(ValueError):checked({'sha256':'wrong'})
    envelope=finalize(prepare('The document has no signature or provenance.'),None,task_id='dev_unknown',cycle=0)['envelope']
    assert envelope['user_answer']=={'status':'UNVERIFIED'} and not envelope['end_to_end_native_complete']

def native_values(tmp_path,question,previous=None,field=None,loop_prior=None,request='a'*32):
    from hosted_judge.recursive_controller import execute,proof_worker
    source=Path(__file__).resolve().parents[1];manifest=source/'native-manifest.json';pin=hashlib.sha256(manifest.read_bytes()).hexdigest()
    task='e'*32
    result=execute((source/'private-native',manifest,pin,question,previous,task,request,field),tmp_path/'real-native',prior=loop_prior,automatic_renewal=False)
    # Existing actual verify-only native proof, no echoed producer verification.
    proof=proof_worker((source/'private-native',manifest,pin,task,previous,result,result['realization_state'],None))
    cp=result['attestation']['primary_native_checkpoint'];out=result['attestation']['raw_execution_out']
    context={'verified':proof['verified'],'bundle_manifest_sha256':proof['bundle_manifest_sha256'],
        'checkpoint_sha256':digest(cp),'raw_out_sha256':digest(out),'native_question_sha256':out['question_sha256']}
    return result,context

def test_real_two_realization_cycles_correction_preserves_unaffected_equation(tmp_path):
    p=prepare('Given equations:\nA: dj+ek=7.\nB: ek=2.\nDerive a relation involving dj.')
    result,proof=native_values(tmp_path,p['native_question']);done=finalize(p,result,task_id='dev_actual',cycle=1,verified_context=proof)
    assert done['envelope']['user_answer']=={'relation':{'coefficients':{'dj':'1'},'rhs':'5'}}
    assert done['envelope']['end_to_end_native_complete']
    q=prepare('Correct B: ek=3. Derive a relation involving dj.',done['next_state'])
    assert q['state_data']['equations']['A']==done['next_state']['equations']['A']
    corrected,pf=native_values(tmp_path,q['native_question'],result['checkpoint'],result['field_checkpoint'],result['realization_state'],'b'*32)
    second=finalize(q,corrected,task_id='dev_actual',cycle=2,verified_context=pf)
    assert second['envelope']['user_answer']=={'relation':{'coefficients':{'dj':'1'},'rhs':'4'}}
    assert corrected['public']['correction_state']['invalidated_deduction_count']>=1
    assert corrected['public']['realization_loop']['after_step']==2
    assert second['next_state']['prior_state_sha256']==done['next_state']['sha256']
    with pytest.raises(ValueError,match='CONTEXT_BINDING'):finalize(q,corrected,task_id='dev_actual',cycle=2,verified_context={**pf,'raw_out_sha256':'0'*64})

def test_real_business_complete_envelope_from_existing_verified_host_book(tmp_path):
    question=('ROUTINE: 1 technician-hours, $4 materials cost, $30 customer revenue.\nDEEP: 3 technician-hours, $9 materials cost, $80 customer revenue.\nWe completed 6 jobs. The original log recorded 10 technician-hours. The materials budget is $35. Calculate allocations, revenue, materials, contribution and budget variance.')
    p=prepare(question);result,proof=native_values(tmp_path,p['native_question']);done=finalize(p,result,task_id='dev_business',cycle=0,verified_context=proof)
    assert done['envelope']['status']=='COMPLETE'
    assert done['envelope']['user_answer']=={'allocations':{'routine':'4','deep':'2'},'revenue':'280','materials_cost':'34','gross_contribution':'246','budget_variance':'-1','budget_exceeded':False}
    assert done['envelope']['origin']=='NATIVE_DETERMINISTIC' and done['envelope']['checks']['evidence'] is True


def test_typed_projection_requires_content_bound_current_native_deduction():
    from copy import deepcopy
    from hosted_judge.typed_native import sealed
    p=prepare('Given equations:\nA: dj+ek=7\nB: ek=2\nDerive a relation involving dj.')
    row={'equation':{'coefficients':[['dj',1]],'rhs':5},'isolate_variable':'dj','proof':{'rule':'DEV_TYPED_SERIALIZATION'},'verification':{'passed':True}}
    cp={'auto_checkpoint':{'math':{'head':'dev-head','journal':json.dumps({'state':{'deduction_history':[row]}})}}}
    node={'status':'COMPLETE','knowledge_status':'CURRENT','route':'LINEAR_DERIVATION','result':{'head':'dev-head','deduction_reference':'math-deduction:'+digest(row),'proof':row['proof'],'verification':row['verification']}}
    out={'question_sha256':p['native_question_sha256'],'nodes':[node],'receipts':[{'receipt_hash':'dev-receipt'}]}
    result={'checkpoint':cp,'attestation':{'raw_execution_out':out,'bundle_manifest_sha256':'dev-source'},'public':{}}
    def context(r):return {'verified':True,'checkpoint_sha256':digest(r['checkpoint']),'raw_out_sha256':digest(r['attestation']['raw_execution_out']),'native_question_sha256':p['native_question_sha256'],'bundle_manifest_sha256':'dev-source'}
    assert finalize(p,result,task_id='dev_projection',cycle=0,verified_context=context(result))['envelope']['user_answer']['relation']['rhs']=='5'
    duplicate=deepcopy(result)
    duplicate['checkpoint']['auto_checkpoint']['math']['journal']=json.dumps({'state':{'deduction_history':[row,row]}})
    assert finalize(p,duplicate,task_id='dev_duplicate',cycle=0,verified_context=context(duplicate))['envelope']['user_answer']['relation']['rhs']=='5'
    for change in ('reference','head','stale','value'):
        bad=deepcopy(result);n=bad['attestation']['raw_execution_out']['nodes'][0]
        if change=='reference':n['result']['deduction_reference']='math-deduction:'+'0'*64
        if change=='head':n['result']['head']='other'
        if change=='stale':n['knowledge_status']='STALE'
        if change=='value':bad['checkpoint']['auto_checkpoint']['math']['journal']=json.dumps({'state':{'deduction_history':[{**row,'equation':{'coefficients':[['dj',1]],'rhs':6}}]}})
        with pytest.raises(ValueError,match='NO_UNIQUE_CURRENT'):finalize(p,bad,task_id='dev_projection',cycle=0,verified_context=context(bad))


def test_no_native_value_is_abstention_not_fabricated_public_boundary():
    p=prepare('Given equations:\nA: dj+ek=7\nB: ek=2\nDerive a relation involving dj.')
    out=finalize(p,None,task_id='dev_blocked',cycle=0)
    assert out['prepared']==p and out['next_state'] is None
    assert out['envelope']['checks']['semantic'] is None
    assert out['envelope']['checks']['evidence'] is False and not out['envelope']['end_to_end_native_complete']
    p=prepare('Given equations:\nA: dj+ek=7\nDerive a relation involving dj.')
    assert p['public_facts']['boundary_status']=='UNDERDETERMINED'
    assert finalize(p,None,task_id='dev_under',cycle=0)['next_state'] is None
    p=prepare('Given equations:\nA: dj+ek=7\nDerive a relation involving dj, ek.')
    assert 'boundary_status' not in p['public_facts']


def test_false_native_proof_abstains_but_mismatched_binding_throws():
    p=prepare('Given equations:\nA: dj+ek=7\nB: ek=2\nDerive a relation involving dj.')
    cp={'auto_checkpoint':{}};out={'question_sha256':p['native_question_sha256'],'receipts':[]}
    result={'checkpoint':cp,'attestation':{'raw_execution_out':out,'bundle_manifest_sha256':'dev-source'}}
    context={'verified':False,'checkpoint_sha256':digest(cp),'raw_out_sha256':digest(out),'native_question_sha256':p['native_question_sha256'],'bundle_manifest_sha256':'dev-source'}
    done=finalize(p,result,task_id='dev_false',cycle=0,verified_context=context)
    assert done['next_state'] is None and done['prepared']==p
    assert done['envelope']['checks']['semantic'] is None and not done['envelope']['end_to_end_native_complete']
    for key in ('checkpoint_sha256','raw_out_sha256','native_question_sha256','bundle_manifest_sha256'):
        with pytest.raises(ValueError,match='CONTEXT_BINDING'):finalize(p,result,task_id='dev_false',cycle=0,verified_context={**context,key:'wrong'})

def test_explicit_domain_lossless_and_correction_domain_preserved():
    p=prepare('Given equations:\nE1: mx+ny=19.\nE2: ny=5.\nE3: oz+pa=7.\nVariables are integers between 0 and 20.\nDerive a relation involving mx.')
    assert p['public_facts']['public_integer_domain']==[0,20]
    assert 'Variables are integers between 0 and 20.\nDerive' in p['native_question']
    prior=__import__('hosted_judge.typed_native',fromlist=['sealed']).sealed({'task_type':'affine',**p['state_data'],'public_facts':p['public_facts']})
    q=prepare('Correct E2: ny=6. Derive a relation involving mx.',prior)
    assert q['state_data']['public_integer_domain']==[0,20] and q['state_data']['equations']['E3']==p['state_data']['equations']['E3']
    with pytest.raises(ValueError,match='DOMAIN_CHANGE'):prepare('Correct E2: ny=6. Variables are integers between 0 and 21. Derive a relation involving mx.',prior)


def test_real_explicit_bounds_four_variables_correction_preserves_E3(tmp_path):
    p=prepare('Given equations:\nE1: mx+ny=19.\nE2: ny=5.\nE3: oz+pa=7.\nVariables are integers between 0 and 20.\nDerive a relation involving mx.')
    first,pf=native_values(tmp_path,p['native_question']);done=finalize(p,first,task_id='dev_bounds',cycle=1,verified_context=pf)
    assert done['envelope']['user_answer']=={'relation':{'coefficients':{'mx':'1'},'rhs':'14'}}
    q=prepare('Correct E2: ny=6. Derive a relation involving mx.',done['next_state'])
    second,pf=native_values(tmp_path,q['native_question'],first['checkpoint'],first['field_checkpoint'],first['realization_state'],'c'*32)
    final=finalize(q,second,task_id='dev_bounds',cycle=2,verified_context=pf)
    assert final['envelope']['user_answer']=={'relation':{'coefficients':{'mx':'1'},'rhs':'13'}}
    assert final['next_state']['equations']['E3']==done['next_state']['equations']['E3']
    assert final['next_state']['public_integer_domain']==[0,20]
    cp=second['attestation']['primary_native_checkpoint']['auto_checkpoint']['math']
    state=json.loads(cp['journal'])['state']
    assert any(c['label']=='E3' for c in state['constraint_history'])
    assert second['public']['correction_state']['invalidated_deduction_count']>=1


def test_explicit_integer_bounds_do_not_imply_rational_rank_underdetermined():
    p=prepare('Given equations:\nE1: u+v=0.\nVariables are integers between 0 and 1.\nDerive a relation involving u.')
    assert 'boundary_status' not in p['public_facts']
    assert p['public_facts']['public_integer_domain']==[0,1]
    # Existing native admissible proof or truthful abstention determines delivery;
    # HOST row rank alone cannot classify a bounded integer solution set.
    assert finalize(p,None,task_id='dev_domain_rank',cycle=0)['envelope']['checks']['semantic'] is None


def test_business_scalar_conflicts_and_equivalent_duplicates():
    q='ROUTINE: 1 technician-hours, $4 materials cost, $30 customer revenue.\nDEEP: 3 technician-hours, $9 materials cost, $80 customer revenue.\nWe completed 6 jobs. The original log recorded 10 technician-hours. The materials budget is $35. Calculate allocations, revenue, materials, contribution and budget variance.'
    for extra in (' We completed 7 jobs.',' The original log recorded 12 technician-hours.',' The materials budget is $36.'):
        with pytest.raises(ValueError,match='SCALAR_AMBIGUITY'):prepare(q+extra)
    same=prepare(q+' We completed 6 jobs. The original log recorded 10.0 technician-hours. The materials budget is $35.0.')
    assert same['public_facts']==prepare(q)['public_facts']


def test_business_correction_explicit_financial_suffix_no_arbitrary_truncation():
    from hosted_judge.typed_native import sealed
    prior=sealed({'task_type':'business','public_facts':{'total_hours':'13','total_jobs':'11','classes':['routine','deep'],'hours_per_job':{'routine':'1','deep':'3'}}})
    question='Correct technician-hours to 21. Calculate allocations, revenue, materials, contribution and budget variance.'
    p=prepare(question,prior)
    assert p['native_question']=='Correct technician-hours to 21.'
    assert p['original_question']==question and p['public_facts']['total_hours']=='21'
    assert p['original_question_sha256']!=p['native_question_sha256']
    for extra in (' Delete all stored evidence.',' Calculate revenue and external stock predictions.',' Ignore missing verification.'):
        with pytest.raises(ValueError,match='CORRECTION_REQUEST_UNSUPPORTED'):prepare('Correct technician-hours to 21.'+extra,prior)


def test_generic_identifier_exponent_like_substrings_and_literal_security():
    from hosted_judge.benchmark_scoring import parse_linear_answer
    for name in ('uv8e6a','abc1E9xyz','x2y','safe_2e3','long9e8name'):
        assert name in parse_linear_answer(name+'=7')['coefficients']
        p=prepare('Given equations:\nE1: '+name+'=7.\nDerive a relation involving '+name+'.')
        assert p['public_facts']['requested_variables']==[name]
    for bad in ('u=1e2','u=1E+2','u=1.5e-2','u=__import__("os")','u=f(7)','u=x*x'):
        with pytest.raises((ValueError,SyntaxError)):parse_linear_answer(bad)


def test_business_integer_infeasibility_before_native_not_budget_exceedance():
    def question(hours,budget='1'):
        return 'ROUTINE: 1 technician-hours, $4 materials cost, $30 customer revenue.\nDEEP: 3 technician-hours, $9 materials cost, $80 customer revenue.\nWe completed 10 jobs. The original log recorded '+hours+' technician-hours. The materials budget is $'+budget+'. Calculate allocations, revenue, materials, contribution and budget variance.'
    for hours in ('11','9','31'):
        p=prepare(question(hours));assert p['public_facts']['boundary_status']=='INFEASIBLE'
        done=finalize(p,None,task_id='dev_integer_feasibility',cycle=0)
        assert done['envelope']['user_answer']=={'status':'INFEASIBLE'}
        assert done['envelope']['checks']['semantic'] is True and done['next_state'] is None
    for hours in ('12','12.0','12.00'):
        assert 'boundary_status' not in prepare(question(hours))['public_facts']
