"""Development regressions, not a benchmark or new live-model result.

Recorded finish strings are replayed with explicit offline model transports.
The allowlisted CLI actually runs on disposable public files. No action,
Native transition, production store, provider request or private oracle runs.
"""
from copy import deepcopy
import json
import pytest

from paired_workflow import protocol,tasks
from paired_workflow import runner
from paired_workflow.tools import ProjectTools,checked_files

RECORDED_FINISH={
    'conventional':{'type':'finish','notes':'Goal already reached: coral-settings.json limit=9 yields expected output 116.'},
    'se6':{'type':'finish','notes':'Goal already reached with limit=9 in coral-settings.json'},
}


def public_project(tmp_path,*,limit=94,goal=116,name='projectA'):
    """Relevant actual V2 public cold-contract values; no expected repair field."""
    root=tmp_path/name;root.mkdir()
    files={'workload.py':tasks.WORKLOAD,'manifest.json':{'entry':'grove','profiles':{
        'coral':{'config':'coral-settings.json','gain':6,'offset':62},
        'grove':{'config':'grove-settings.json','gain':5,'offset':36}}},
        'goal.json':{'version':protocol.NATIVE_DOMAIN,'goal':goal,'setting_bounds':[0,100],'operation':'gain*limit+offset'},
        'coral-settings.json':{'limit':9},'grove-settings.json':{'limit':limit}}
    for key,value in files.items():
        (root/key).write_bytes(value.encode() if type(value) is str else protocol.encode(value))
    return root


def tools(root,tmp_path):
    return ProjectTools(root,root_alias=root.name,state_root=tmp_path/'tool-state',stage_id='completion-development',effect_admission=None)


class RecordedDevelopmentGateway:
    """Explicit model-response fixture. Never imports or invokes a provider."""
    SIMULATED=True
    def __init__(self,replies):self.replies=iter(deepcopy(replies));self.requests=[];self.invocations=0
    def require_admission(self):return {'status':'SIMULATED_TEST_ONLY'}
    def prepare(self,value):
        self.requests.append(deepcopy(value));return {'request_sha256':protocol.digest(value)}
    def invoke(self,prepared,permit=None):
        self.invocations+=1
        return dict(status='SIMULATED_TEST_ONLY',returned_model=protocol.MODEL_SETTINGS['model'],
            response=json.dumps(next(self.replies)),provider_request_id='OFFLINE_RECORDED_DEVELOPMENT_NOT_PROVIDER',
            usage={'prompt_tokens':0,'completion_tokens':0})


def execute(root,tmp_path,arm,replies,*,notes=None):
    shared=tools(root,tmp_path);gateway=RecordedDevelopmentGateway(replies)
    def no_native_effect(_):raise AssertionError('Finish-only regression must not invoke Native')
    result=runner.execute_stage(project_id='recorded-finish-development',stage=2,arm=arm,
        tools=shared,notes=notes or {'status':'OWN_PRIOR_VERIFIED_NOTES','verified_observations':[
            {'old_cli_goal':116,'old_action':{'path':'coral-settings.json','value':9}}]},
        output=tmp_path/'attempt',gateway=gateway,native_dispatch=no_native_effect,simulation=True)
    return result,shared,gateway


def test_current_success_is_reused_without_an_unnecessary_cli_or_mutation(tmp_path):
    root=public_project(tmp_path,limit=16);shared=tools(root,tmp_path);before=checked_files(root)
    context=shared.public_context();assert context['initial_cli']=={'output':116,'returncode':0}
    assert shared.cli_processes==1
    completion=shared.check_completion()
    assert completion['goal'] is True and completion['status']=='CURRENT_GOAL_VERIFIED'
    assert completion['observation_performed'] is False and shared.cli_processes==1
    assert checked_files(root)==before and shared.act_proposals==0 and shared.effect_attempt_state=='NOT_ATTEMPTED'


def test_current_failure_rejects_completion_without_repeating_valid_observation(tmp_path):
    root=public_project(tmp_path);shared=tools(root,tmp_path);shared.public_context()
    completion=shared.check_completion()
    assert completion['goal'] is False and completion['current_output']==506
    assert completion['reason_codes']==['CURRENT_CLI_OUTPUT_DOES_NOT_MEET_PUBLIC_GOAL']
    assert completion['observation_performed'] is False and shared.cli_processes==1


def test_missing_witness_uses_one_existing_authorized_cli_observation(tmp_path):
    root=public_project(tmp_path);shared=tools(root,tmp_path);before=checked_files(root)
    assert shared._completion_witness is None
    completion=shared.check_completion()
    assert completion['observation_performed'] is True and shared.cli_processes==1
    assert completion['current_output']==506 and not completion['goal']
    assert shared.events[-1]['command']=={'type':'run_cli'} and checked_files(root)==before


def test_stale_success_cannot_complete_after_current_goal_changes(tmp_path):
    root=public_project(tmp_path,limit=16);shared=tools(root,tmp_path);shared.public_context()
    stale=deepcopy(shared._completion_witness)
    goal=json.loads((root/'goal.json').read_bytes());goal['goal']=121;(root/'goal.json').write_bytes(protocol.encode(goal))
    completion=shared.check_completion()
    assert completion['observation_performed'] and shared.cli_processes==2
    assert completion['public_goal']==121 and completion['current_output']==116 and not completion['goal']
    assert stale['witness']['source_hashes']!=completion['source_hashes']


def test_same_source_bytes_in_another_root_require_current_root_witness(tmp_path):
    first=public_project(tmp_path,limit=16);old=tools(first,tmp_path);old.public_context()
    second=public_project(tmp_path,limit=16,name='projectB');current=tools(second,tmp_path)
    current._completion_witness=deepcopy(old._completion_witness)
    completion=current.check_completion()
    assert completion['goal'] and completion['observation_performed'] and current.cli_processes==1
    assert current._completion_witness['root']==str(second) and completion['root_alias']=='projectB'


@pytest.mark.parametrize('kind',['missing','stale'])
def test_no_observation_budget_reports_precise_incomplete_instead_of_trusting_notes(tmp_path,kind):
    root=public_project(tmp_path,limit=16);shared=tools(root,tmp_path)
    if kind=='stale':
        shared.public_context();value=json.loads((root/'goal.json').read_bytes());value['goal']=121
        (root/'goal.json').write_bytes(protocol.encode(value))
    calls=shared.cli_processes;completion=shared.check_completion(allow_observation=False)
    assert completion['status']=='INCOMPLETE_CURRENT_EVIDENCE_REQUIRED' and not completion['goal']
    assert completion['reason_codes']==['CURRENT_SOURCE_ROOT_BOUND_GOAL_WITNESS_REQUIRED']
    assert shared.cli_processes==calls and completion['evidence_sha256'] is None


@pytest.mark.parametrize('arm',['conventional','se6'])
def test_recorded_cold_finish_is_rejected_and_uses_remaining_original_turns(tmp_path,arm):
    root=public_project(tmp_path);before=checked_files(root)
    result,shared,gateway=execute(root,tmp_path,arm,[RECORDED_FINISH[arm],
        {'type':'inspect','target':'project'},RECORDED_FINISH[arm]])
    assert result['record_kind']=='SIMULATED_TEST_ONLY' and gateway.invocations==3
    assert result['status']=='INCOMPLETE' and result['completion_blocker']['reason']=='PILOT_COMPLETION_MODEL_TURNS_EXHAUSTED'
    assert result['independent_verdict']['actual_cli_goal'] is False
    assert result['action'] is None and result['native_receipts'] is None
    assert shared.act_proposals==0 and checked_files(root)==before
    rejection=json.loads(gateway.requests[1]['messages'][-1]['content'])
    assert rejection['completion_rejected'] and rejection['tool_observation']['current_output']==506
    assert rejection['tool_observation']['public_goal']==116 and rejection['turns_remaining']==2
    assert 'selected_action' not in json.dumps(rejection) and 'expected_patch' not in json.dumps(rejection)
    assert result['resources']['provider_calls_attempted']==3 and result['resources']['completion_checks']==2
    assert result['resources']['completion_observations']==0


@pytest.mark.parametrize('arm',['conventional','se6'])
def test_genuine_current_no_change_finish_succeeds_for_either_arm(tmp_path,arm):
    root=public_project(tmp_path,limit=16);before=checked_files(root)
    result,shared,gateway=execute(root,tmp_path,arm,[{'type':'finish','notes':'Current observed CLI already meets the public goal.'}])
    assert result['status']=='VERIFIED_SUCCESS' and result['independent_verdict']['goal'] is True
    assert gateway.invocations==1 and shared.act_proposals==0 and result['native_receipts'] is None
    assert result['completion_checks'][0]['goal'] and not result['completion_checks'][0]['observation_performed']
    assert shared.cli_processes==2  # Initial witness plus mandatory independent final grader; no duplicate inspection.
    assert checked_files(root)==before


@pytest.mark.parametrize('arm',['conventional','se6'])
def test_no_fourth_model_turn_or_effect_after_three_rejected_finishes(tmp_path,arm):
    root=public_project(tmp_path)
    result,shared,gateway=execute(root,tmp_path,arm,[RECORDED_FINISH[arm]]*3)
    assert gateway.invocations==3 and result['status']=='INCOMPLETE'
    assert result['completion_blocker']['reason']=='PILOT_COMPLETION_MODEL_TURNS_EXHAUSTED'
    assert len(result['completion_checks'])==3 and shared.act_proposals==0 and shared.cli_processes==2


@pytest.mark.parametrize('arm',['conventional','se6'])
def test_exhausted_time_reports_incomplete_without_new_model_request(tmp_path,arm,monkeypatch):
    root=public_project(tmp_path);monkeypatch.setitem(runner.LIMITS,'max_model_loop_seconds',0)
    result,shared,gateway=execute(root,tmp_path,arm,[])
    assert gateway.invocations==0 and result['status']=='INCOMPLETE'
    assert result['completion_blocker']['reason']=='PILOT_COMPLETION_TIME_BUDGET_EXHAUSTED'
    assert shared.act_proposals==0 and result['resources']['provider_calls_attempted']==0


def test_exhausted_tool_budget_does_not_reobserve_or_accept_missing_evidence(tmp_path,monkeypatch):
    root=public_project(tmp_path);shared=tools(root,tmp_path);original=shared.public_context
    def context_with_missing_witness():
        context=original();shared._completion_witness=None;return context
    monkeypatch.setattr(shared,'public_context',context_with_missing_witness)
    monkeypatch.setitem(runner.LIMITS,'max_tools_per_stage',0)
    gateway=RecordedDevelopmentGateway([RECORDED_FINISH['conventional']])
    result=runner.execute_stage(project_id='missing-evidence-development',stage=2,arm='conventional',
        tools=shared,notes={},output=tmp_path/'attempt',gateway=gateway,simulation=True)
    assert result['status']=='INCOMPLETE' and gateway.invocations==1
    assert result['completion_blocker']['reason']=='PILOT_COMPLETION_OBSERVATION_BUDGET_EXHAUSTED'
    assert result['resources']['completion_observations']==0 and shared.cli_processes==2
