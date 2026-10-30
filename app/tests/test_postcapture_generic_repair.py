"""New DEVELOPMENT fixtures; never reexecute or regrade the frozen cohort."""
import hashlib
from pathlib import Path
from fractions import Fraction
from hosted_judge.service import JudgeService

ROOT=Path(__file__).resolve().parents[1]
def service(root):
    m=ROOT/'native-manifest.json'
    return JudgeService(ROOT/'private-native',m,hashlib.sha256(m.read_bytes()).hexdigest(),realization_root=root)

def test_actual_exponent_like_identifier_correction_and_cold_restore(tmp_path):
    s=service(tmp_path);t,n=s.new_session()
    q='Given equations:\nE1: signal3e2 + offsetQ = 16.\nE2: offsetQ = 7.\nE3: sideA + sideB = 5.\nVariables are integers between 0 and 10.\nDerive a relation involving signal3e2.'
    a=s.run(t,n['csrf_token'],{'question':q,'request_id':'1'*32})
    r=a['typed_answer']['user_answer']['relation']
    assert Fraction(r['rhs'])/Fraction(r['coefficients']['signal3e2'])==9
    assert a['typed_answer']['checks']['semantic'] and a['typed_answer']['checks']['evidence']
    old=s.sessions[t].typed_task_state
    cold=service(tmp_path);assert cold.session(t).typed_task_state==old
    b=cold.run(t,n['csrf_token'],{'question':'Correct E2: offsetQ = 6. Derive a relation involving signal3e2.','request_id':'2'*32})
    r=b['typed_answer']['user_answer']['relation']
    assert Fraction(r['rhs'])/Fraction(r['coefficients']['signal3e2'])==10
    assert b['realization_loop']['after_step']==4 and b['correction_state']['invalidated_deduction_count']>0
    assert cold.sessions[t].typed_task_state['equations']['E3']==old['equations']['E3']
    assert service(tmp_path).session(t).typed_task_state==cold.sessions[t].typed_task_state

def test_actual_integer_business_infeasible_boundary_without_fake_native(tmp_path):
    q='SIMPLE: 1 technician-hours, $12 materials cost, $60 customer revenue.\nDEEP: 3 technician-hours, $30 materials cost, $150 customer revenue.\nWe completed 10 jobs. The original log recorded 17 technician-hours. The materials budget is $220. Calculate allocations, revenue, materials, contribution and budget variance.'
    s=service(tmp_path);t,n=s.new_session()
    a=s.run(t,n['csrf_token'],{'question':q,'request_id':'3'*32})
    assert a['typed_answer']['user_answer']=={'status':'INFEASIBLE'}
    assert a['typed_answer']['checks']['semantic'] and a['typed_answer']['checks']['evidence']
    assert a['typed_answer']['origin']=='HOST_DETERMINISTIC' and not a['typed_answer']['end_to_end_native_complete']
    assert a['native_receipt_count']==0 and a['session_actions']==0 and a['provider_calls']==0
    assert s.sessions[t].typed_task_state is None and s.sessions[t].checkpoint is None
    assert service(tmp_path).session(t).typed_task_state is None
