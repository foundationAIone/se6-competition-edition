"""Pure proposal-port checks; no provider, project effect, or Native receipt claim.

The source certificate authentication stub is explicitly TEST_ONLY. The actual
Native preparation and original Core Boundary execute on a visible unit case.
Coordinator acceptance must separately exercise the real read/effect/witness ports.
"""
from copy import deepcopy
from pathlib import Path
import hashlib,json,shutil,subprocess,sys,tempfile
import pytest

APP=Path(__file__).resolve().parents[1]
CORE=APP/'awareness_native/work/qpre-calibration-integration-20261026/dev'
sys.path.insert(0,str(CORE))
from hosted_judge.model_native_workflow import (
    proposal_gate,require_exact_selected_action,validate_proposal)
from hosted_judge import model_native_workflow as workflow
from scripts.run_native_qpre_learning import dependencies
from se666_core import native_dependency_relation_v1 as domain
from se666_core.grounded_native_input import GroundedNativeConsumer,prepare_native_input


class TestOnlyCertificateAuthority:
    """Unit schema fixture only. Does not authorize any dispatch or World action."""
    def authenticate_dependency_certificate(self,value):return True


@pytest.fixture
def actual_boundary_case():
    reference,composer,_=dependencies();core=reference.canonical.core
    engine=core.SE(core.SEState(identity='unit'))
    consumer=GroundedNativeConsumer(reference,dict(core_journal=engine.dumps(),core_head=None),
        TestOnlyCertificateAuthority(),composer)
    observation=dict(context=dict(cwd='/visible-unit/A',observed_root='/visible-unit/A',entity_id='unit',situated_frame_hash='frame'),
        manifest={'entry':'blue','profiles':{'red':{'config':'a.json','gain':2,'offset':0},'blue':{'config':'b.json','gain':3,'offset':0}}},
        schema={'version':domain.VERSION,'goal':18,'setting_bounds':[0,100],'operation':'gain*limit+offset'},
        configs={'a.json':{'limit':1},'b.json':{'limit':1}},failure={'output':3},file_hashes={'workload.py':'program'})
    history=[dict(source='src',epoch='program',raw=[3])]
    binding=dict(entity_id='unit',entity_state=consumer.engine.state.state_hash,source='src',epoch='program',memory_head='head')
    actions=[dict(id=n,payload={'op':'SET_INTEGER','field':'limit','path':n+'.json'},cost=1) for n in ('a','b')]
    certificate=domain.certificate(observation,history,binding)
    prepared=prepare_native_input(certificate,history,binding,actions,TestOnlyCertificateAuthority())
    boundary=dict(identity='unit',authorized=True,permissions=['a','b'],max_native_actions=10)
    proposal={'type':'act','path':'b.json','field':'limit','value':6,'prediction':{'expected_output':18}}
    return dict(observation=observation,prepared=prepared,consumer=consumer,boundary=boundary,actions=actions,proposal=proposal)


def gate(case):
    return proposal_gate(case['proposal'],case['observation'],case['prepared'],case['consumer'],case['boundary'],case['actions'])


def test_valid_untrusted_proposal_is_consumed_by_actual_core_boundary_without_effect(actual_boundary_case):
    case=actual_boundary_case;before=deepcopy(case['proposal']);result=gate(case)
    assert result['allowed'] and result['boundary']['outcome']=='ALLOW'
    assert result['world_effects']==0 and result['fallback_used'] is False
    assert case['consumer'].pending is None and case['consumer'].engine.receipts==()
    assert case['proposal']==before


@pytest.mark.parametrize('fault',['inactive_target','wrong_value','wrong_prediction','unknown_target','revoked_permission','no_authority','wrong_identity'])
def test_model_error_or_absent_authority_is_refused_without_substituting_answer(actual_boundary_case,fault):
    case=actual_boundary_case
    if fault=='inactive_target':case['proposal'].update(path='a.json',value=9)
    if fault=='wrong_value':case['proposal']['value']=7
    if fault=='wrong_prediction':case['proposal']['prediction']['expected_output']=17
    if fault=='unknown_target':case['proposal']['path']='unknown.json'
    if fault=='revoked_permission':case['boundary']['permissions']=['a']
    if fault=='no_authority':case['boundary']['authorized']=False
    if fault=='wrong_identity':case['boundary']['identity']='another'
    original=deepcopy(case['proposal']);result=gate(case)
    assert result['boundary']['outcome']=='REFUSE' and not result['allowed']
    assert result['world_effects']==0 and result['fallback_used'] is False
    assert case['consumer'].pending is None and case['proposal']==original


@pytest.mark.parametrize('fault',['cwd','frame','state','entity'])
def test_stale_source_root_or_native_state_cannot_pass_preflight(actual_boundary_case,fault):
    case=actual_boundary_case
    if fault=='cwd':case['observation']['context']['cwd']='/wrong'
    if fault=='frame':case['prepared']['operating_context']['situated_frame_hash']='changed'
    if fault=='state':case['prepared']['binding']['entity_state']='old-state'
    if fault=='entity':case['prepared']['binding']['entity_id']='other'
    with pytest.raises(ValueError,match='MODEL_(CURRENT_ROOT|NATIVE_FRAME)_BINDING'):gate(case)
    assert case['consumer'].pending is None


@pytest.mark.parametrize('fault',['extra','bool_value','escape','absolute','reserved','bool_prediction','missing_prediction'])
def test_exact_public_model_schema_rejects_unadmitted_directives(actual_boundary_case,fault):
    p=actual_boundary_case['proposal']
    if fault=='extra':p['owner_approved']=True
    if fault=='bool_value':p['value']=True
    if fault=='escape':p['path']='../b.json'
    if fault=='absolute':p['path']='C:/b.json'
    if fault=='reserved':p['path']='manifest.json'
    if fault=='bool_prediction':p['prediction']['expected_output']=True
    if fault=='missing_prediction':p.pop('prediction')
    with pytest.raises(ValueError):validate_proposal(p)


def test_native_selection_must_equal_the_original_model_proposal(actual_boundary_case):
    p=actual_boundary_case['proposal'];original=deepcopy(p)
    right={'payload':{'op':'SET_INTEGER','path':'b.json','field':'limit','value':6}}
    require_exact_selected_action(p,right)
    wrong=deepcopy(right);wrong['payload']['value']=7
    with pytest.raises(ValueError,match='NO_FALLBACK'):require_exact_selected_action(p,wrong)
    assert p==original


@pytest.mark.parametrize('mode',['nonzero','timeout','success'])
def test_child_transport_preserves_private_evidence_without_retry_or_public_secret(monkeypatch,mode):
    # Only the host transport runs; subprocess is controlled and no Native
    # fixture, Entity, model, or World action is executed in this unit check.
    root=Path(tempfile.mkdtemp(prefix='SE6-NATIVE-QPRE-'))
    (root/'.SE6_NATIVE_QPRE_DISPOSABLE').write_text('explicit-simulated-development-only-v1')
    workflow._register_native_root(root)
    calls=[]
    def controlled(*args,**kwargs):
        calls.append((args,kwargs))
        if mode=='timeout':raise subprocess.TimeoutExpired(args[0],120,output=b'private partial stdout',stderr=b'private partial stderr')
        return subprocess.CompletedProcess(args[0],7 if mode=='nonzero' else 0,
            'private failed stdout' if mode=='nonzero' else '{"goal":true,"actual_effects":1}',
            'private child stderr')
    monkeypatch.setattr(workflow.subprocess,'run',controlled)
    try:
        value=workflow._command('run',root=root,world='projectA',phase=1,
            proposal={'type':'act','path':'b.json','field':'limit','value':6,'prediction':{'expected_output':18}})
        assert len(calls)==1 and len(value['private_evidence_sha256'])==64
        assert 'private child' not in json.dumps(value) and str(root) not in json.dumps(value)
        records=list((root/'model-stage-logs').glob('*.json'));assert len(records)==1
        record=json.loads(records[0].read_bytes());stem=records[0].stem
        stdout=(records[0].parent/(stem+'.stdout')).read_bytes()
        stderr=(records[0].parent/(stem+'.stderr')).read_bytes()
        assert record['stdout_sha256']==hashlib.sha256(stdout).hexdigest()
        assert record['stderr_sha256']==hashlib.sha256(stderr).hexdigest()
        assert record['retry_permitted'] is False
        if mode!='success':assert value['actual_effects'] is None and value['retry_permitted'] is False
        else:assert value['goal'] is True
    finally:shutil.rmtree(root)
