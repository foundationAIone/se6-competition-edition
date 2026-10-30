"""Pure HOST tests use fresh synthetic development evidence generated once/session.
Typed receipt deserialization below is not independent replay and establishes
no receipt truth. Production gate requires actual original replay-produced values.
"""
from copy import deepcopy
from dataclasses import asdict
import importlib.util
import json
import os
from pathlib import Path
import sys
import pytest
import subprocess

def source_bundle():
    configured = os.environ.get('HOSTED_TEST_COMPETITION_BUNDLE')
    if configured:
        value = Path(configured).resolve()
        if (value/'src/workbench/auto_intake.py').is_file(): return value
        if (value/'private-native/src/workbench/auto_intake.py').is_file(): return value/'private-native'
        raise AssertionError('Configured source bundle absent; no fallback')
    for parent in Path(__file__).resolve().parents:
        for relative in ('private-native', 'work/competition-v11-self-repair/private-native'):
            value = parent/relative
            if (value/'src/workbench/auto_intake.py').is_file(): return value
    raise AssertionError('Source bundle not found')
SOURCE = source_bundle()
sys.path.insert(0,str(SOURCE))
from src.workbench.canonical_core_vendor import se_core as api
from src.workbench import auto_intake as original_auto

from src.workbench.canonical_core_vendor.se_core.mathematics import math_observation_from_record
helper=Path(__file__).parents[1]/'hosted_judge/provisional_math_presentation.py'
if not helper.is_file():helper=SOURCE.parent/'hosted_judge/provisional_math_presentation.py'
spec=importlib.util.spec_from_file_location('presentation',helper)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
POLICY=m.formatter_policy(original_auto.AutoIntake)


def item(v):
    if v is None:return None
    if 'constraint_history' in v:return m.decode_state(api,v)
    if 'coefficients' in v:return api.LinearEquation(tuple(tuple(x) for x in v['coefficients']),v['rhs'])
    if 'label' in v:return api.MathConstraint(v['label'],item(v['equation']),tuple(v['source_ids']),v['previous_ref'])
    if 'verification' in v and 'equation' in v:return api.MathDeduction(item(v['equation']),item(v['proof']),item(v['verification']),v['isolate_variable'])
    if 'weights' in v:return api.MathProof(tuple(v['premise_refs']),tuple(v['weights']),v['rule'])
    if 'cells_checked' in v:return api.MathCheck(**{**v,'premise_refs':tuple(v['premise_refs']),'counterexample':tuple(tuple(x) for x in v['counterexample'])})
    if 'subject' in v:return api.SERelation(**{**v,'source_ids':tuple(v['source_ids'])})
    if 'state_before_hash' in v:return api.SECandidateTransition(**{**v,'relation':item(v['relation']),'prior_relations':tuple(item(x) for x in v['prior_relations']),'action':item(v['action'])})
    if 'checks' in v:return api.SEBoundaryDecision(v['outcome'],tuple(tuple(x) for x in v['checks']),tuple(v['reasons']))
    if 'action_id' in v:return api.SEConsequence(**{**v,'evidence_refs':tuple(v['evidence_refs'])})
    if 'passed' in v:return api.SEVerification(v['passed'],tuple(v['reasons']),tuple(v['evidence_refs']))
    if 'payload' in v:return api.SEAction(**v)
    raise AssertionError(v.keys())


def recorded_receipt(row):
    data=dict(row); data.pop('receipt_hash')
    for key in ('state_before','state_after','candidate','boundary','action','observed_consequence','verification'):data[key]=item(data[key])
    for key in ('relationships','assimilation'):data[key]=tuple(item(x) for x in data[key])
    data['observation']=math_observation_from_record(data['observation'])
    receipt=api.SETransitionReceipt(**data)
    assert receipt.receipt_hash == row['receipt_hash']
    return receipt


@pytest.fixture(scope="session")
def public_development_fixture(tmp_path_factory):
    target=tmp_path_factory.mktemp('public-native-development')/'fixture.json'
    recipe=Path(__file__).parents[1]/'tools/generate_public_development_fixture.py'
    env={k:os.environ[k] for k in os.environ if not k.startswith(('NEBIUS','OPENAI'))}
    env.update(PYTHONDONTWRITEBYTECODE='1',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
    process=subprocess.run([sys.executable,'-B',str(recipe),'--source',str(SOURCE.parent),'--output',str(target),'--seed','17'],env=env,capture_output=True,timeout=30)
    assert process.returncode==0, 'Fresh bounded development fixture generation failed; no retry'
    assert not target.resolve().is_relative_to(SOURCE.parent.resolve())
    record=json.loads(target.with_suffix('.provenance.json').read_bytes())
    assert record['provider_calls']==0 and record['production_connected'] is False
    assert record['origin']=='FRESH_REAL_NATIVE_SYNTHETIC_DEVELOPMENT_NOT_BENCHMARK'
    return json.loads(target.read_bytes())


@pytest.fixture
def case(monkeypatch,public_development_fixture):
    monkeypatch.setattr(api.SE,'restore',classmethod(lambda *a,**k: (_ for _ in ()).throw(AssertionError('NO REPLAY IN HOST FORMATTER/TEST'))))
    f=deepcopy(public_development_fixture)
    state=m.decode_state(api,f['journal']['state'])
    context=json.loads(f['summary']['context']);context['state_hash']=state.state_hash
    f['summary']['context']=json.dumps(context)
    f['typed']=[recorded_receipt(x) for x in f['journal']['receipts']]
    return f


def gate(f, **kwargs):
    return m.verify_presentations(api,f['out'],f['typed'],f['raw_answer'],{'business':None},POLICY,**kwargs)


def test_preserved_format_wire_equivalence_without_restore(case):
    shown=m.provisional_math(api,case['selection'],case['summary'],case['checkpoint'],POLICY)
    assert m.encoded(shown)==m.encoded(case['out']['nodes'][0]['result'])
    assert gate(case)['status']=='REPLAYED_SEMANTIC_FIELDS_MATCH'


@pytest.mark.parametrize('field,value', [('answer','p = 999'),('derivation','fake'),('proof',{}),('verification',{}),('deduction_reference','fake'),('head','0'*64),('receipt_hashes',['0'*64])])
def test_real_receipt_fake_shown_rejected(case,field,value):
    case['out']['nodes'][0]['result'][field]=value
    with pytest.raises(ValueError,match='PRESENTATION_'):gate(case)


@pytest.mark.parametrize('where',['context_answer','context_evidence','raw','foreign_context'])
def test_composition_tamper_rejected(case,where):
    context=json.loads(case['out']['context'])
    if where=='context_answer':context['results'][0]['answer']='999'
    elif where=='context_evidence':context['results'][0]['evidence']['proof']={}
    elif where=='foreign_context':context['results'].append({'node':'unknown'})
    else:case['raw_answer']='forged';return assert_raises_gate(case)
    case['out']['context']=json.dumps(context)
    assert_raises_gate(case)


def assert_raises_gate(case):
    with pytest.raises(ValueError,match='PRESENTATION_'):gate(case)


def test_provisional_journal_head_cp_seal_and_denial(case):
    for mutation in ('head','cp','deny','state'):
        f=deepcopy(case)
        if mutation=='head':f['checkpoint']['math']['head']='0'*64
        elif mutation=='cp':f['checkpoint']['task_id']='fake'
        elif mutation=='deny':f['summary']['receipts'][-1]['verification']['passed']=False
        else:
            j=json.loads(f['checkpoint']['math']['journal']);j['state']['extra']=1;f['checkpoint']['math']['journal']=json.dumps(j)
        with pytest.raises(ValueError):m.provisional_math(api,f['selection'],f['summary'],f['checkpoint'],POLICY)


def test_instance_lifetime_capture_deepcopy_and_fallback(case):
    class Auto:
        def native_result(self,*args):return {'fallback':True}
    auto=Auto();calls=[]
    with m.PresentationInvocation(auto,api,POLICY,lambda:calls.append('guard')) as handle:
        shown=auto.native_result(case['selection'],case['summary'],case['checkpoint'])
        assert gate(case,captures=handle.captures)['nodes']
        shown['answer']='mutated'
        assert handle.captures[(case['checkpoint']['math']['head'],case['checkpoint']['checkpoint_hash'])]['shown_sha256']==m.digest(case['out']['nodes'][0]['result'])
        assert auto.native_result({'route':'UNSUPPORTED'}, {}, {})=={'fallback':True}
    assert auto.native_result({}, {}, {})=={'fallback':True}
    assert 'native_result' not in auto.__dict__ and len(calls)==3


def test_no_capture_and_no_verified_derive_block(case):
    with pytest.raises(ValueError,match='CAPTURE_MISMATCH'):gate(case,captures={})
    # Only actual replayed receipt inputs may authorize the presentation gate.
    with pytest.raises(ValueError,match='TYPED_RECEIPT'):m.verify_presentations(api,case['out'],case['journal']['receipts'],case['raw_answer'],{},POLICY)


@pytest.mark.parametrize('field,value', [('contract','false'),('scope','world verified'),('local_seconds',-1),('local_seconds',float('nan')),('provider_calls',False),('production_connected',True)])
def test_scope_timing_types_rejected(case,field,value):
    case['out']['nodes'][0]['result'][field]=value
    assert_raises_gate(case)


def test_false_current_or_superseded_context_rejected(case):
    case['out']['nodes'][0]['knowledge_status']='SUPERSEDED'
    assert_raises_gate(case)


def test_existing_instance_override_refused(case):
    class Auto:
        def native_result(self,*args):return None
    auto=Auto();auto.native_result=lambda *args:None
    with pytest.raises(ValueError,match='EXISTING_OVERRIDE'):
        m.PresentationInvocation(auto,api,POLICY,lambda:None)


def test_runtime_identity_change_and_finally_restore(case):
    class Auto:
        def native_result(self,*args):return None
    auto=Auto();fn=Auto.native_result
    handle=m.PresentationInvocation(auto,api,POLICY,lambda:None)
    Auto.native_result=lambda *args:None
    try:
        with pytest.raises(ValueError,match='RUNTIME_IDENTITY'):
            auto.native_result(case['selection'],case['summary'],case['checkpoint'])
    finally:
        Auto.native_result=fn;handle.close()
    assert 'native_result' not in auto.__dict__


@pytest.mark.parametrize('key', ['world_truth_verified', 'authority', 'native_verified', 'unexpected'])
def test_rehashed_scope_inflation_rejected_without_captures(case,key):
    shown=case['out']['nodes'][0]['result'];shown[key]=True
    context=json.loads(case['out']['context']);context['results'][0]['evidence']=deepcopy(shown)
    case['out']['context']=json.dumps(context)
    assert_raises_gate(case)


def test_false_limitations_rejected_in_provisional_and_fresh_gate(case):
    case['selection']['limitations']=['World facts verified.']
    with pytest.raises(ValueError,match='LIMITATIONS_BINDING'):
        m.provisional_math(api,case['selection'],case['summary'],case['checkpoint'],POLICY)
    shown=case['out']['nodes'][0]['result'];shown['limitations']=['World facts verified.']
    context=json.loads(case['out']['context']);context['results'][0]['evidence']=deepcopy(shown)
    case['out']['context']=json.dumps(context)
    assert_raises_gate(case)


def test_guarded_original_separator_is_used(case):
    state=case['typed'][-1].state_after
    view=m.semantic_view(state,'p',case['out']['nodes'][0]['result']['receipt_hashes'],case['checkpoint']['math']['head'],'TEST_SEPARATOR ')
    assert 'TEST_SEPARATOR ' in view['derivation']
