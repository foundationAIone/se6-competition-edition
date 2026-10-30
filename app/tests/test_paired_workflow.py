"""Focused offline checks. Injected replies/witnesses are SIMULATED, not a pilot."""
from pathlib import Path
import hashlib,json,subprocess,sys

import pytest

from paired_workflow import protocol as p,tasks
from paired_workflow.tools import ProjectTools,checked_files
from paired_workflow.runner import execute_stage,public_projection,independently_assessed
from paired_workflow.control import ConventionalNotes


@pytest.fixture
def public(tmp_path):
    root=tmp_path/'projectA';root.mkdir()
    files={'workload.py':tasks.WORKLOAD,'manifest.json':{'entry':'birch','profiles':{
        'amber':{'config':'amber.json','gain':2,'offset':0},'birch':{'config':'birch.json','gain':3,'offset':0}}},
        'goal.json':{'version':p.NATIVE_DOMAIN,'goal':18,'setting_bounds':[0,100],'operation':'gain*limit+offset'},
        'amber.json':{'limit':1},'birch.json':{'limit':1}}
    for name,value in files.items():(root/name).write_bytes(value.encode() if type(value) is str else p.encode(value))
    (tmp_path/'EVALUATOR_ONLY').mkdir();(tmp_path/'EVALUATOR_ONLY'/'private.json').write_text('EVALUATOR_SENTINEL_DO_NOT_EXPOSE')
    return root


def witness(root,*,goal=False):
    files=checked_files(root)
    return dict(output=18 if goal else 3,returncode=0 if goal else 3,cwd=str(root),
        source_hashes={k:hashlib.sha256(v).hexdigest() for k,v in files.items()},child_cpu_seconds=None)


def tools(public,tmp_path,**kwargs):
    return ProjectTools(public,root_alias='projectA',state_root=tmp_path/'state',stage_id='visible-unit-stage',
        effect_admission=None,readback=lambda root:witness(root),simulation=True,**kwargs)


def test_frozen_limits_and_no_scored_generation_before_source_freeze(tmp_path):
    assert p.LIMITS['projects']*p.LIMITS['stages_per_project']*p.LIMITS['arms']==12
    assert p.LIMITS['max_provider_requests']==36 and p.LIMITS['max_effects']==12
    with pytest.raises(ValueError,match='PILOT_SOURCE_FREEZE_REQUIRED'):
        tasks.generate_scored_cases(tmp_path/'not-generated',{},Path.cwd())
    assert not (tmp_path/'not-generated').exists()


@pytest.mark.parametrize('command',[{'type':'inspect','target':'../EVALUATOR_ONLY/private.json'},
    {'type':'act','path':'../secret.json','field':'limit','value':6,'prediction':{'expected_output':18}},
    {'type':'calculate','gain':True,'offset':0,'goal':18},
    {'type':'shell','command':'anything'}])
def test_model_command_cannot_expand_read_or_execution_boundary(command):
    with pytest.raises(ValueError):p.directive(command)


def test_actual_tool_read_boundary_no_evaluator_data(public,tmp_path):
    shared=tools(public,tmp_path)
    for path in ('../EVALUATOR_ONLY/private.json',str(tmp_path/'EVALUATOR_ONLY'/'private.json'),'private.json'):
        with pytest.raises(ValueError,match='PILOT_FILE_READ_DENIED'):shared.read_file(path)
    raw=shared.execute_non_effect({'type':'inspect','target':'project'})
    text=json.dumps(raw)
    assert 'EVALUATOR_SENTINEL' not in text and str(tmp_path) not in text
    assert raw['manifest']['entry']=='birch' and raw['goal']['goal']==18
    assert 'expected_patch' not in text and 'selected_action' not in text


def test_unexpected_evaluator_file_inside_public_scope_is_refused(public):
    (public/'private.json').write_text('{}')
    with pytest.raises(ValueError,match='PILOT_UNEXPECTED_PUBLIC_FILE'):checked_files(public)


def test_hidden_answer_field_cannot_be_added_to_public_goal(public):
    goal=json.loads((public/'goal.json').read_bytes());goal['expected_patch']='PRIVATE_ANSWER'
    (public/'goal.json').write_bytes(p.encode(goal))
    with pytest.raises(ValueError,match='PILOT_PUBLIC_GOAL_NO_PRIVATE_FIELDS'):checked_files(public)


def test_same_exact_arithmetic_utility_does_not_choose_target(public,tmp_path):
    shared=tools(public,tmp_path)
    calculated=shared.execute_non_effect({'type':'calculate','gain':3,'offset':0,'goal':18})
    assert calculated['numerator']==6 and calculated['denominator']==1
    assert not {'path','profile','selected_action'} & set(calculated)


def test_simulation_transport_cannot_execute_a_world_mutation(public,tmp_path):
    shared=tools(public,tmp_path);before=checked_files(public)
    with pytest.raises(ValueError,match='PILOT_SIMULATED_TRANSPORT_CANNOT_WRITE_WORLD'):
        shared.apply_action({'type':'act','path':'birch.json','field':'limit','value':6,'prediction':{'expected_output':18}})
    assert checked_files(public)==before


class SimulatedGateway:
    SIMULATED=True
    def __init__(self,replies):self.replies=iter(replies);self.requests=[];self.invokes=0
    def require_admission(self):return {'status':'SIMULATED_TEST_ONLY'}
    def prepare(self,request):
        self.requests.append(request)
        return dict(request_id=request['request_id'],request_sha256=p.digest(request),request_metadata={'record_kind':'SIMULATED_TEST_ONLY'})
    def invoke(self,prepared,permit=None):
        self.invokes+=1
        reply=next(self.replies)
        if isinstance(reply,Exception):raise reply
        return dict(status='SIMULATED_TEST_ONLY',response=json.dumps(reply),usage={'prompt_tokens':10,'completion_tokens':5},
            provider_request_id='SIMULATED-NOT-A-PROVIDER',returned_model=p.MODEL_SETTINGS['model'])


def test_model_tool_loop_is_bounded_and_records_simulation_without_spending(public,tmp_path):
    gateway=SimulatedGateway([{'type':'inspect','target':'project'},
        {'type':'calculate','gain':3,'offset':0,'goal':18},{'type':'finish','notes':'unit-only abstention'}])
    result=execute_stage(project_id='project-001',stage=1,arm='conventional',tools=tools(public,tmp_path),
        notes={'verified_observations':[]},output=tmp_path/'attempt',gateway=gateway,simulation=True)
    assert gateway.invokes==3 and result['record_kind']=='SIMULATED_TEST_ONLY'
    assert result['independent_verdict']['goal'] is False
    assert result['independent_verdict']['assessment_status']=='INDEPENDENTLY_ASSESSED'
    assert all('EVALUATOR_SENTINEL' not in json.dumps(req) for req in gateway.requests)
    assert result['resources']['provider_calls_attempted']==3
    assert result['resources']['total_cpu_seconds'] is None
    view=public_projection([],p.digest(p.PROTOCOL),simulation=True)
    assert view['record_kind']=='SIMULATED_TEST_ONLY' and view['projects']==[] and view['aggregate'] is None


def test_missing_gateway_blocks_before_tool_or_world_access(public,tmp_path):
    shared=tools(public,tmp_path)
    result=execute_stage(project_id='project-001',stage=1,arm='conventional',tools=shared,
        notes={},output=tmp_path/'blocked',gateway=None)
    assert result['status']=='BLOCKED_PENDING_EXACT_BUDGET'
    assert result['resources']['provider_calls_attempted']==0 and shared.cli_processes==0
    assert not (tmp_path/'state').exists()


def test_uncertain_provider_call_is_never_retried_or_reported_zero_cost(public,tmp_path):
    gateway=SimulatedGateway([TimeoutError('unit-only uncertain call')])
    result=execute_stage(project_id='project-001',stage=1,arm='conventional',tools=tools(public,tmp_path),
        notes={},output=tmp_path/'uncertain',gateway=gateway,simulation=True)
    assert gateway.invokes==1 and result['status']=='FAILED_CLOSED'
    assert result['provider_outcome']=='UNKNOWN_CHECK_GATEWAY_CLAIM'
    assert result['resources']['provider_calls_attempted']==1
    assert result['resources']['input_tokens'] is None and result['resources']['tariff_estimate_usd'] is None


def test_interrupted_native_with_goal_readback_does_not_claim_completed_cycle(public,tmp_path):
    shared=ProjectTools(public,root_alias='projectA',state_root=tmp_path/'state',stage_id='visible-unit-stage',
        effect_admission=None,readback=lambda root:witness(root,goal=True),simulation=True)
    gateway=SimulatedGateway([{'type':'act','path':'birch.json','field':'limit','value':6,'prediction':{'expected_output':18}}])
    result=execute_stage(project_id='project-001',stage=1,arm='se6',tools=shared,notes={},
        output=tmp_path/'interrupted',gateway=gateway,simulation=True,
        native_dispatch=lambda proposal:{'status':'INTERRUPTED','actual_effects':None,'retry_permitted':False})
    assert result['native_outcome']=='UNKNOWN' and result['halt_batch'] is True
    assert result['independent_verdict']['actual_cli_goal'] is True
    assert result['independent_verdict']['goal'] is False and result['retention']['status']=='NOT_VERIFIED_UNCERTAIN_NATIVE_CYCLE'
    assert result['independent_verdict']['assessment_status']=='UNKNOWN'


def test_conventional_postclaim_exception_halts_without_retry(public,tmp_path,monkeypatch):
    shared=tools(public,tmp_path)
    def interrupted(_):
        shared.effect_attempt_state='CLAIMED_OUTCOME_UNKNOWN'
        raise OSError('SIMULATED postclaim interruption; no actual write')
    monkeypatch.setattr(shared,'apply_action',interrupted)
    gateway=SimulatedGateway([{'type':'act','path':'birch.json','field':'limit','value':6,'prediction':{'expected_output':18}}])
    result=execute_stage(project_id='project-001',stage=1,arm='conventional',tools=shared,notes={},
        output=tmp_path/'control-uncertain',gateway=gateway,simulation=True)
    assert result['halt_batch'] is True and result['effect_outcome']=='UNKNOWN'
    assert gateway.invokes==1 and result['independent_verdict'] is None


def test_known_failure_is_assessed_but_unknown_is_not():
    # Pure record predicates, not provider replies or comparison evidence.
    known_failure={'independent_verdict':{'status':'NOT_VERIFIED','assessment_status':'INDEPENDENTLY_ASSESSED','goal':False}}
    known_success={'independent_verdict':{'status':'INDEPENDENTLY_VERIFIED','assessment_status':'INDEPENDENTLY_ASSESSED','goal':True}}
    unknown={'independent_verdict':{'status':'NOT_VERIFIED','assessment_status':'UNKNOWN','goal':False}}
    assert independently_assessed(known_failure) and independently_assessed(known_success)
    assert not independently_assessed(unknown)


def test_notes_require_own_verified_lineage(tmp_path):
    notes=ConventionalNotes(tmp_path/'notes','project-001')
    assert notes.load(stage=2)['status']=='NO_VERIFIED_PREDECESSOR'
    assert notes.retain(stage=1,public_observation={},proposal={},independent_verdict={'goal':False})['status']=='NOT_RETAINED_UNVERIFIED_OUTCOME'
    assert not (tmp_path/'notes').exists()


def test_actual_child_read_audit_denies_forbidden_path_without_world(public,tmp_path):
    source=Path.cwd();freeze=tmp_path/'freeze.json';freeze.write_text('{}')
    spec=tmp_path/'spec.json';spec.write_text('{}')
    descriptor=dict(source_root=str(source),root=str(public.parent/'registered'),output=str(tmp_path/'own-arm'/'stage1'),
        notes_directory=str(tmp_path/'own-arm'/'notes'),world='projectA',gateway_config={'root':str(tmp_path/'gateway'),'spec_path':str(spec)},freeze_path=str(freeze))
    Path(descriptor['root']).mkdir()
    code='from paired_workflow.runner import _install_read_boundary; import json; print(json.dumps(_install_read_boundary('+repr(descriptor)+')))'
    run=subprocess.run([sys.executable,'-B','-c',code],cwd=source,capture_output=True,text=True,timeout=10)
    assert run.returncode==0,run.stderr
    assert json.loads(run.stdout)['private_probe']=='DENIED'
