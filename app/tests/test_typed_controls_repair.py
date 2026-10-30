"""Real public-only development controls; no current held-out oracle or model."""
import hashlib,json
from pathlib import Path
import pytest
from hosted_judge.typed_controls import run_condition

ROOT=Path(__file__).resolve().parents[1]
BUSINESS='ROUTINE: 1 technician-hours, $9 materials cost, $59 customer revenue.\nDEEP: 3 technician-hours, $26 materials cost, $133 customer revenue.\nWe completed 9 jobs. The original log recorded 15 technician-hours. The materials budget is $140. Calculate allocations, revenue, materials, contribution and budget variance.'

def task(questions,*,authorized=True):
    return {'id':'development-controls','category':'DEV_ONLY','max_actions':20,'automatic_renewal':False,
        'phases':[{'id':f'd{i+1}','public_question':q,'authorized':authorized} for i,q in enumerate(questions)]}
def execute(t,condition,root):
    m=ROOT/'native-manifest.json';return run_condition(t,condition,root,ROOT/'private-native',m,hashlib.sha256(m.read_bytes()).hexdigest())

@pytest.mark.parametrize('condition',['B','C','D'])
def test_actual_typed_public_control_conservation_and_complete_capture(tmp_path,condition):
    r=execute(task([BUSINESS]),condition,tmp_path/'control');assert r['status']=='COMPLETE',r
    row=r['phase_records'][0];assert row['user_answer']['allocations']=={'routine':'6','deep':'3'}
    assert row['typed_answer']['checks']['semantic'] and row['delivery_receipt']['independently_readback']
    assert (tmp_path/'control'/row['raw_native_relative']).is_file() and row['native_operations']>0
    memory=json.loads((tmp_path/'control/memory/0001.json').read_bytes())
    assert len(json.dumps(memory).encode())<=4*1024*1024 and r['provider_calls']==0
    if condition!='B':assert row['selected_context']['trajectory']
    assert 'receipt_hashes' not in json.dumps(row['selected_context'])
    with pytest.raises(ValueError,match='DESTINATION_ALREADY_EXISTS_NO_RETRY'):
        execute(task([BUSINESS]),condition,tmp_path/'control')

def test_actual_independent_deduction_survives_corrected_premise(tmp_path):
    public=[
      'Given equations:\nE1: mx + ny = 18.\nE2: ny = 4.\nE3: az + by = 12.\nVariables are integers between 0 and 20.\nDerive a relation involving mx.',
      'Derive a relation between az and by.',
      'Correct E2: ny = 5. Derive a relation involving mx.',
      'Derive a relation between az and by.'
    ]
    r=execute(task(public),'C',tmp_path/'correction');assert r['status']=='COMPLETE',r
    p=r['phase_records'];assert len(p)==4
    from fractions import Fraction
    value=lambda x:Fraction(x['user_answer']['relation']['rhs'])/Fraction(x['user_answer']['relation']['coefficients']['mx'])
    assert value(p[0])==14 and value(p[2])==13
    assert p[1]['user_answer']==p[3]['user_answer']
    before=json.loads((tmp_path/'correction/raw-native/0002.json').read_bytes())
    after=json.loads((tmp_path/'correction/raw-native/0003.json').read_bytes())
    old=before['attestation']['correction_state'];new=after['attestation']['correction_state']
    assert len(new['invalidated_deductions'])>len(old['invalidated_deductions'])
    assert set(old['active_deductions']) & set(new['active_deductions'])

def test_denied_controls_never_execute_tool_or_materialize(tmp_path,monkeypatch):
    import hosted_judge.typed_controls as c
    monkeypatch.setattr(c,'conventional_native',lambda *a:(_ for _ in ()).throw(AssertionError('Unexpected tool')))
    r=execute(task([BUSINESS],authorized=False),'B',tmp_path/'denied')
    assert r['status']=='BLOCKED' and r['phase_records'][0]['error_code']=='AUTHORITY_DENIED'
    assert not list((tmp_path/'denied').glob('conventional-effects/*'))

def test_missing_bounded_native_witness_abstains_without_false_global_inconsistency(tmp_path):
    q='Given equations:\nE1: mx + ny = 18.\nE2: ny = 4.\nE3: az + by = 12.\nDerive a relation involving mx.'
    r=execute(task([q]),'C',tmp_path/'bounded-resource')
    row=r['phase_records'][0]
    assert row['status']=='ABSTAINED' and row['user_answer']=={'status':'BLOCKED'}
    assert row['typed_answer']['checks']['semantic'] is None
    assert not row['typed_answer']['end_to_end_native_complete']
    assert row['delivery_receipt']['state'] is None and row['native_operations']==0

def test_no_direct_model_fixture_answer_generated_offline(tmp_path):
    r=execute(task([BUSINESS]),'A',tmp_path/'direct')
    assert r['status']=='NOT_EXECUTED' and r['phase_records']==[] and not (tmp_path/'direct').exists()

def test_context_policy_uses_first_current_actual_inspection_not_final_goal():
    from hosted_judge.typed_controls import selected_context
    # Explicit development fixture, no provider/native-execution claim.
    r={'attestation':{'raw_execution_out':{'nodes':[
        {'id':'stale','status':'COMPLETE','knowledge_status':'INVALIDATED','route':'LINEAR_MATH'},
        {'id':'premise','status':'COMPLETE','knowledge_status':'CURRENT','route':'LINEAR_MATH'},
        {'id':'goal','status':'COMPLETE','knowledge_status':'CURRENT','route':'LINEAR_DERIVATION'}]}},
        'public':{'nodes':[{'id':'premise','answer':'public premise fixture'},{'id':'goal','answer':'verified goal fixture'}],
            'canonical':{'toroidal_realization':{'navigation':{'actual_trajectory':['source','stale','premise','goal']}}},
            'realization_loop':{'cycles':[{'selected_node':'goal'}]}}}
    a=selected_context(r,'C');assert a['selected_id']=='premise' and a['artifact_selected_id']=='goal'
    assert a['task_relevant_data']['conditional_answer']=='public premise fixture'
    r['public']['canonical']['toroidal_realization']['navigation']['actual_trajectory']=['source','goal','premise']
    b=selected_context(r,'D');assert a['task_relevant_data_sha256']!=b['task_relevant_data_sha256']
