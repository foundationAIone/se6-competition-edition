"""New development examples; no historical model answers or provider calls."""
import copy,hashlib,json
from pathlib import Path
import pytest
from hosted_judge.service import JudgeService
from hosted_judge.pair_gateway import PairGateway
from hosted_judge.typed_native import prepare
from hosted_judge.answer_contract import make_envelope
from hosted_judge import typed_answer_state

ROOT=Path(__file__).resolve().parents[1]
MATH='Given equations:\nA: uu + vv = 17.\nB: vv = 7.\nC: zz + ww = 11.\nDerive a relation involving uu.'
BUSINESS='ROUTINE: 1 technician-hours, $13 materials cost, $68 customer revenue.\nDEEP: 3 technician-hours, $32 materials cost, $147 customer revenue.\nWe completed 11 jobs. The original log recorded 19 technician-hours. The materials budget is $230. Calculate allocations, revenue, materials, contribution and budget variance.'

def service(root):
    m=ROOT/'native-manifest.json';pin=hashlib.sha256(m.read_bytes()).hexdigest();b=ROOT/'private-native'
    return JudgeService(b,m,pin,pair_gateway=PairGateway(b,root/'pairs',native_manifest=m,native_manifest_sha256=pin),realization_root=root/'realization')

def run(s,t,csrf,q,r):return s.run(t,csrf,{'question':q,'request_id':r*32})

def test_real_math_delivery_correction_cold_restore_and_unchanged_relations(tmp_path):
    s=service(tmp_path);t,new=s.new_session();a=run(s,t,new['csrf_token'],MATH,'a')
    typed=a['typed_answer'];assert typed['status']=='COMPLETE' and typed['origin']=='NATIVE_DETERMINISTIC'
    assert typed['checks']['schema'] and typed['checks']['semantic'] and typed['end_to_end_native_complete']
    relation=typed['user_answer']['relation'];assert int(relation['rhs'])/int(relation['coefficients']['uu'])==10
    assert a['provider_calls']==0 and a['realization_loop']['after_step']==2
    before=copy.deepcopy(s.sessions[t].typed_task_state);assert s.run(t,new['csrf_token'],{'question':MATH,'request_id':'a'*32})==a
    fresh=service(tmp_path);restored=fresh.session(t);assert restored.restored_from_disk
    assert restored.typed_task_state==before
    b=run(fresh,t,new['csrf_token'],'Correct B: vv = 9. Derive a relation involving uu.','b')
    relation=b['typed_answer']['user_answer']['relation'];assert int(relation['rhs'])/int(relation['coefficients']['uu'])==8
    after=fresh.sessions[t].typed_task_state
    assert after['equations']['A']==before['equations']['A'] and after['equations']['C']==before['equations']['C']
    assert after['equations']['B']!=before['equations']['B'] and after['prior_state_sha256']==before['sha256']
    assert b['correction_state']['invalidated_deduction_count']>0 and b['realization_loop']['after_step']==4
    ledger=tmp_path/'realization/typed-deliveries'/restored.task_id
    assert len(list(ledger.glob('*.json')))==2
    assert service(tmp_path).session(t).typed_task_state==after

def test_real_business_complete_typed_arithmetic(tmp_path):
    s=service(tmp_path);t,new=s.new_session();r=run(s,t,new['csrf_token'],BUSINESS,'c')
    u=r['typed_answer']['user_answer']
    assert u['allocations']=={'routine':'7','deep':'4'}
    from fractions import Fraction
    assert Fraction(u['revenue'])==1064 and Fraction(u['materials_cost'])==219
    assert Fraction(u['gross_contribution'])==845 and Fraction(u['budget_variance'])==-11
    assert u['budget_exceeded'] is False
    assert r['typed_answer']['checks']['semantic'] and r['typed_answer']['checks']['evidence']
    assert r['typed_answer']['origin']=='NATIVE_DETERMINISTIC' and r['provider_calls']==0
    assert r['typed_answer']['delivery_receipt']['append_only']

def test_real_graph_two_phases_retains_public_edges_without_fake_math(tmp_path):
    s=service(tmp_path);t,new=s.new_session()
    q='Conditional directed relations: hub RELATES_TO leaf; leaf RELATES_TO end. Can end be reached from hub following these directed links?'
    a=run(s,t,new['csrf_token'],q,'d');assert a['typed_answer']['user_answer']=={'reachable':True}
    assert a['typed_answer']['origin']=='HOST_DETERMINISTIC' and not a['typed_answer']['end_to_end_native_complete']
    assert a['native_receipt_count']==1 and a['realization_loop']['resources']['native_actions']==2 and a['realization_loop']['after_step']==2
    fresh=service(tmp_path);assert fresh.session(t).typed_task_state==s.sessions[t].typed_task_state
    b=run(fresh,t,new['csrf_token'],'Remove the directed edge leaf RELATES_TO end. Can end still be reached from hub?','e')
    assert b['typed_answer']['user_answer']=={'reachable':False} and b['provider_calls']==0
    assert fresh.sessions[t].typed_task_state['graph_edges']==[['hub','leaf']]

def test_real_business_financial_correction_and_ambiguous_input_preserve_cold_state(tmp_path):
    s=service(tmp_path);t,new=s.new_session();run(s,t,new['csrf_token'],BUSINESS,'1')
    before=s.sessions[t].typed_task_state;checkpoint=s.sessions[t].checkpoint
    c=run(s,t,new['csrf_token'],BUSINESS+' The original log recorded 21 technician-hours.','2')
    assert c['typed_contract_status']['status']=='BLOCKED' and c['native_receipt_count']==0
    assert s.sessions[t].typed_task_state==before and s.sessions[t].checkpoint==checkpoint
    assert service(tmp_path).session(t).typed_task_state==before
    b=run(s,t,new['csrf_token'],'Correct technician-hours to 21. Calculate allocations, revenue, materials, contribution and budget variance.','3')
    from fractions import Fraction
    u=b['typed_answer']['user_answer'];assert u['allocations']=={'routine':'6','deep':'5'}
    assert Fraction(u['revenue'])==1143 and Fraction(u['materials_cost'])==238 and Fraction(u['gross_contribution'])==905
    assert Fraction(u['budget_variance'])==8 and u['budget_exceeded'] is True
    assert b['realization_loop']['after_step']==4 and b['typed_answer']['checks']['semantic']
    assert service(tmp_path).session(t).typed_task_state==s.sessions[t].typed_task_state

def test_reject_unsupported_or_fabricated_typed_delivery_receipts(tmp_path):
    p=prepare('Given equations:\nA: unit = 12.\nDerive a relation involving unit.')
    e=make_envelope(p,{'relation':{'coefficients':{'unit':'1'},'rhs':'19'}},task_id='a'*32,cycle=1,origin='MODEL',evidence={'verified':False})
    with pytest.raises(ValueError,match='TYPED_LEDGER_UNVERIFIED_ANSWER'):
        typed_answer_state.append(tmp_path,'a'*32,'b'*32,p,{'envelope':e,'next_state':None},None,native_checkpoint=None)
    assert not list(tmp_path.rglob('*.json'))

def test_common_request_cannot_supply_evidence_or_select_operator(tmp_path):
    s=service(tmp_path);t,new=s.new_session()
    for extra in ['verified_context','receipt','field_mode']:
        with pytest.raises(ValueError,match='question and request_id only'):
            s.run(t,new['csrf_token'],{'question':MATH,'request_id':'f'*32,extra:True})
    assert s.sessions[t].attempts==0 and s.sessions[t].actions==0

@pytest.mark.parametrize('status',['FABRICATED','BLOCKED'])
def test_invalid_or_truncated_abstention_cannot_append(tmp_path,status):
    p=prepare('Given equations:\nA: unit = 12.\nDerive a relation involving unit.')
    e=make_envelope(p,{'status':status},task_id='a'*32,cycle=1,origin='MODEL',finish_reason='length')
    with pytest.raises(ValueError,match='TYPED_LEDGER_UNVERIFIED_ANSWER'):
        typed_answer_state.append(tmp_path,'a'*32,'b'*32,p,{'envelope':e,'next_state':None},None,native_checkpoint=None)
    assert not list(tmp_path.rglob('*.json'))
