"""One frozen 3-project paired pilot. No gateway/approval means no execution."""
from copy import deepcopy
from datetime import UTC,datetime
from pathlib import Path
import json,time,tracemalloc,uuid,os,sys,subprocess,importlib
from .protocol import VERSION,LIMITS,MODEL_SETTINGS,PROTOCOL,SYSTEM_PROMPT,require,digest,encode,directive,validate_freeze
from .tasks import exclusive,install_initial_project,apply_stage2_change
from .tools import ProjectTools,checked_files
from .grader import grade_stage,public_verdict
from .control import ConventionalNotes


def admission(gateway,*,simulation=False):
    if gateway is None:return dict(status='BLOCKED_PENDING_EXACT_BUDGET',provider_calls=0)
    if simulation:
        require(getattr(gateway,'SIMULATED',getattr(gateway,'simulated',False)) is True,'PILOT_EXPLICIT_SIMULATED_GATEWAY')
    else:
        from hosted_judge.model_pilot_gateway import PilotGateway
        require(type(gateway) is PilotGateway and gateway.simulated is False,'PILOT_EXISTING_SOURCE_BOUND_GATEWAY_REQUIRED')
    return gateway.require_admission()


def _sum_known(rows,key):
    values=[row.get(key) for row in rows]
    return sum(values) if all(type(v) is int for v in values) else None


def execute_stage(*,project_id,stage,arm,tools,notes,output,gateway,native_dispatch=None,
        simulation=False,source_preflight=None,initialization_resources=None):
    """Same model/prompt/tools/bounds; SE6 only changes its actual Native path."""
    directory=Path(output);require(not directory.exists(),'PILOT_STAGE_ATTEMPT_ALREADY_EXISTS');directory.mkdir(parents=True)
    whole_wall,whole_cpu=time.perf_counter(),time.process_time();tracemalloc.start()
    result=dict(project_id=project_id,stage=stage,arm=arm,status='NOT_EXECUTED',
        record_kind='SIMULATED_TEST_ONLY' if simulation else 'ACTUAL_PAIRED_MODEL_STAGE',
        model_proposals=[],tool_events=[],selected_decision=None,action=None,native_receipts=None,
        independent_verdict=None,retention=None,resources={},responses_committed=False,stage_pid=os.getpid(),
        initialization_resources=initialization_resources)
    calls=[];public_context=None;proposal=None;native_result=None;before=None
    provider_attempts=0;provider_pending=False;native_pending=False
    finish_accepted=False;incomplete_reason=None
    try:
        permit=admission(gateway,simulation=simulation)
        if permit.get('status')=='BLOCKED_PENDING_EXACT_BUDGET':
            result['status']='BLOCKED_PENDING_EXACT_BUDGET';return result
        require(arm in {'conventional','se6'} and stage in (1,2),'PILOT_STAGE_SCOPE')
        public_context=tools.public_context();before=checked_files(tools.root)
        messages=[{'role':'system','content':SYSTEM_PROMPT},{'role':'user','content':json.dumps(
            {'public_task':public_context,'own_verified_notes':notes},sort_keys=True)}]
        exclusive(directory/'initial-public-input.json',dict(messages=messages,record_kind=result['record_kind']))
        for turn in range(1,LIMITS['max_model_turns_per_stage']+1):
            if time.perf_counter()-whole_wall>=LIMITS['max_model_loop_seconds']:
                incomplete_reason='PILOT_COMPLETION_TIME_BUDGET_EXHAUSTED';break
            if source_preflight is not None:source_preflight()
            request=dict(request_id=uuid.uuid4().hex,messages=deepcopy(messages),project_id=project_id,
                stage=stage,arm=arm,turn=turn)
            require(len(encode(request))<=LIMITS['max_request_wire_bytes'],'PILOT_REQUEST_WIRE_BOUND')
            prepared=gateway.prepare(request)
            exclusive(directory/f'request-{turn}.json',dict(request=request,prepared=prepared))
            provider_attempts+=1;provider_pending=True
            call=gateway.invoke(prepared,permit=None)
            provider_pending=False
            exclusive(directory/f'response-{turn}.json',call)
            calls.append(call);result['responses_committed']=True
            require(call.get('status')==('SIMULATED_TEST_ONLY' if simulation else 'PROVIDER_RETURNED_UNVERIFIED'),'PILOT_PROVIDER_RESULT_KIND')
            require(call.get('returned_model')==MODEL_SETTINGS['model'],'PILOT_RETURNED_MODEL_IDENTITY')
            raw=call['response'];require(type(raw) is str and len(raw.encode())<=16384,'PILOT_MODEL_RESPONSE_BOUND')
            proposal=directive(json.loads(raw))
            result['model_proposals'].append(dict(turn=turn,proposal=deepcopy(proposal),
                request_sha256=prepared['request_sha256'],provider_request_id=call.get('provider_request_id')))
            messages.append({'role':'assistant','content':raw})
            if proposal['type']=='act':
                if arm=='se6':
                    require(callable(native_dispatch),'PILOT_NATIVE_ACTUAL_STAGE_ADAPTER_REQUIRED')
                    native_pending=True
                    native_result=native_dispatch(proposal)
                    native_pending=False
                    result['selected_decision']=native_result.get('proposal_gate') or native_result.get('selection')
                    result['native_receipts']={key:native_result.get(key) for key in (
                        'native_receipt_hash','entity_receipt_id','renewal_receipt_sha256','retained_state_sha256')}
                    result['action']=native_result.get('selected_action')
                    result['native_result']=native_result
                    if native_result.get('status') in {'FAILED_CLOSED','INTERRUPTED'} or native_result.get('actual_effects') is None:
                        result['native_outcome']='UNKNOWN'
                        result['halt_batch']=True
                else:
                    result['selected_decision']=dict(status='MODEL_PROPOSED_VALIDATED_PUBLIC_ACTION',proposal=deepcopy(proposal))
                    result['action']=tools.apply_action(proposal)
                break
            if proposal['type']=='finish':
                # Exactly the same completion standard applies to both arms.
                # A model assertion or retained note is never current evidence.
                allow_read=(len(tools.events)<LIMITS['max_tools_per_stage'] and
                    time.perf_counter()-whole_wall<LIMITS['max_model_loop_seconds'])
                completion=tools.check_completion(allow_observation=allow_read)
                result.setdefault('completion_checks',[]).append(dict(turn=turn,**completion))
                result['tool_events']=deepcopy(tools.events)
                if completion['goal']:
                    finish_accepted=True;break
                if turn>=LIMITS['max_model_turns_per_stage']:
                    incomplete_reason='PILOT_COMPLETION_MODEL_TURNS_EXHAUSTED';break
                if time.perf_counter()-whole_wall>=LIMITS['max_model_loop_seconds']:
                    incomplete_reason='PILOT_COMPLETION_TIME_BUDGET_EXHAUSTED';break
                if completion['status']=='INCOMPLETE_CURRENT_EVIDENCE_REQUIRED':
                    incomplete_reason='PILOT_COMPLETION_OBSERVATION_BUDGET_EXHAUSTED';break
                messages.append({'role':'user','content':json.dumps(dict(completion_rejected=True,
                    tool_observation=completion,turns_remaining=LIMITS['max_model_turns_per_stage']-turn,
                    obligation='The current public goal is not reached. Investigate the current public evidence or propose a permitted action; no repair answer is supplied.'),sort_keys=True)})
                continue
            observation=tools.execute_non_effect(proposal)
            result['tool_events']=deepcopy(tools.events)
            require(len(tools.events)<=LIMITS['max_tools_per_stage'],'PILOT_TOOL_BUDGET')
            messages.append({'role':'user','content':json.dumps({'tool_observation':observation,'turns_remaining':3-turn},sort_keys=True)})
        result['tool_events']=deepcopy(tools.events)
        acted=proposal is not None and proposal['type']=='act'
        budget_exhausted=not acted and not finish_accepted
        verdict=grade_stage(tools.root,before,proposal,witness_runner=tools.readback,simulation=simulation)
        if result.get('native_outcome')=='UNKNOWN':
            original_verdict_sha256=verdict['verdict_sha256']
            verdict={**verdict,'status':'NOT_VERIFIED','goal':False,
                'assessment_status':'UNKNOWN',
                'native_cycle_status':'UNKNOWN_DESPITE_ANY_READ_ONLY_CLI_RESULT',
                'original_cli_verdict_sha256':original_verdict_sha256}
            verdict['verdict_sha256']=digest({k:v for k,v in verdict.items() if k!='verdict_sha256'})
            result['status']='INTERRUPTED_NATIVE_OUTCOME_UNKNOWN'
            result['independent_verdict']=public_verdict(verdict)
            result['retention']={'status':'NOT_VERIFIED_UNCERTAIN_NATIVE_CYCLE'}
            return result
        result['independent_verdict']=public_verdict(verdict)
        if native_result is not None and native_result.get('status')=='REFUSED_PROPOSAL':result['status']='REFUSED_PROPOSAL'
        elif incomplete_reason:
            result['status']='INCOMPLETE'
            result['completion_blocker']=dict(reason=incomplete_reason,
                unmet_obligation='CURRENT_SOURCE_ROOT_BOUND_GOAL_VERIFICATION_OR_PERMITTED_REPAIR',
                final_independent_goal=verdict['goal'])
        elif budget_exhausted:result['status']='BUDGET_EXHAUSTED_WITHOUT_ACTION'
        else:result['status']='VERIFIED_SUCCESS' if verdict['goal'] else 'VERIFIED_FAILURE'
        if arm=='conventional':
            keeper=ConventionalNotes(directory.parent/'ordinary-notes',project_id)
            result['retention']=keeper.retain(stage=stage,public_observation=dict(context=public_context,
                tool_events=result['tool_events']),proposal=proposal,independent_verdict=result['independent_verdict'])
        else:
            result['retention']=dict(status='VERIFIED_NATIVE_RENEWAL' if verdict['goal'] and native_result and native_result.get('renewal_receipt_sha256') else 'NOT_VERIFIED',
                cold_continuation=bool(native_result and native_result.get('cold_restored')),
                verified_prior_memory_available=bool(native_result and native_result.get('verified_prior_memory_available',native_result.get('cold_restored'))),
                maintained_edges_consumed=native_result.get('maintained_edges_consumed',[]) if native_result else [],
                retained_state_sha256=native_result.get('retained_state_sha256') if native_result else None)
    except Exception as error:
        result['status']='FAILED_CLOSED'
        text=str(error)
        result['failure']=dict(error_type=type(error).__name__,
            code=getattr(error,'code',None) or (text if text.startswith('PILOT_') else 'PILOT_OPERATION_FAILED_NO_RETRY'))
        # A provider call may be uncertain even if no complete response was
        # returned. The source-bound gateway preserves its claim independently.
        result['provider_outcome']='UNKNOWN_CHECK_GATEWAY_CLAIM' if provider_pending else 'SEE_IMMUTABLE_RESPONSES_AND_GATEWAY_CLAIMS'
        if native_pending:
            result['native_outcome']='UNKNOWN';result['halt_batch']=True
        if arm=='conventional' and tools.effect_attempt_state!='NOT_ATTEMPTED':
            result['effect_outcome']='UNKNOWN';result['halt_batch']=True
        if before is not None and not provider_pending and not native_pending and not result.get('halt_batch'):
            try:
                result['independent_verdict']=public_verdict(grade_stage(tools.root,before,None,
                    witness_runner=tools.readback,simulation=simulation))
            except Exception:
                result['independent_verdict']=dict(status='NOT_VERIFIED',assessment_status='UNKNOWN',goal=None)
    finally:
        usages=[]
        for call in calls:
            usage=call.get('usage') or {}
            usages.append(dict(input_tokens=usage.get('prompt_tokens',usage.get('input_tokens')),
                output_tokens=usage.get('completion_tokens',usage.get('output_tokens'))))
        input_tokens=_sum_known(usages,'input_tokens');output_tokens=_sum_known(usages,'output_tokens')
        if provider_pending or provider_attempts!=len(calls):input_tokens=output_tokens=None
        result['resources']=dict(completed_model_responses=len(calls),provider_calls_attempted=provider_attempts,
            input_tokens=input_tokens,output_tokens=output_tokens,
            tariff_estimate_usd=(input_tokens*.30+output_tokens*.90)/1_000_000 if input_tokens is not None and output_tokens is not None else None,
            actual_invoice_usd=None,whole_host_cpu_seconds=time.process_time()-whole_cpu,
            whole_wall_seconds=time.perf_counter()-whole_wall,peak_host_traced_python_bytes=tracemalloc.get_traced_memory()[1],
            child_cpu_seconds=None,total_cpu_seconds=None,
            native_worker_cpu_seconds=native_result.get('worker_cpu_seconds') if native_result else None,
            native_worker_wall_seconds=native_result.get('worker_wall_seconds') if native_result else None,
            tool_calls=len(tools.events),repeated_inspections=len(tools.inspected)-len(set(tools.inspected)),
            model_directed_tools=sum(p['proposal']['type']!='finish' for p in result['model_proposals']),
            common_cli_processes=tools.cli_processes,
            native_observed_cli_processes=native_result.get('observed_cli_processes') if native_result else 0,
            effect_attempts=tools.act_proposals if arm=='conventional' else native_result.get('actual_effects') if native_result else 0,
            model_act_proposals=int(proposal is not None and proposal.get('type')=='act'),
            completion_checks=len(result.get('completion_checks',[])),
            completion_observations=sum(bool(x.get('observation_performed')) for x in result.get('completion_checks',[])),
            scope='Whole stage includes public observations, controller, verification and retention; initialization reported separately. Host CPU excludes children; total CPU UNKNOWN.')
        exclusive(directory/'result.json',result)
    return result


def run_pilot(*,case_directory,freeze,source_root,output,gateway=None,root_factory=None,
        stage_launcher=None,native_api=None,effect_admission=None,simulation=False):
    """Coordinator invokes only after exact gateway approval and source freeze."""
    freeze_hash=validate_freeze(freeze,source_root)
    if gateway is None:return dict(status='BLOCKED_PENDING_EXACT_BUDGET',record_kind='NOT_EXECUTED',projects=[],aggregate=None)
    admission(gateway,simulation=simulation)  # before task setup or first call
    require(callable(root_factory) and callable(stage_launcher),'PILOT_REGISTERED_ROOT_AND_COLD_STAGE_LAUNCHER_REQUIRED')
    output=Path(output);require(not output.exists(),'PILOT_BATCH_ATTEMPT_ALREADY_EXISTS');output.mkdir(parents=True)
    exclusive(output/'source-freeze.json',freeze)
    private=Path(case_directory)/'EVALUATOR_ONLY';generation=json.loads((private/'generation.json').read_bytes())
    require(not private.resolve().is_relative_to(Path(source_root).resolve()),'PILOT_PRIVATE_CASES_OUTSIDE_SOLVER_SOURCE')
    require(generation['freeze_sha256']==freeze_hash and generation['protocol_sha256']==digest(PROTOCOL),'PILOT_CASE_GENERATION_BINDING')
    projects=[];halt=False
    for index,entry in enumerate(generation['private_cases'],start=1):
        case=json.loads((private/(entry['project_id']+'.json')).read_bytes())
        require(digest(case)==entry['case_sha256'],'PILOT_CASE_PIN')
        project=dict(project_id=case['project_id'],change_kind=case['change_kind'],stages=[dict(stage=s,change_kind='INITIAL' if s==1 else case['change_kind'],arms={}) for s in (1,2)])
        order=('conventional','se6') if index%2 else ('se6','conventional')
        for arm in order:
            if halt:
                for staged in project['stages']:staged['arms'][arm]={'status':'NOT_EXECUTED_AFTER_UNCERTAIN_FAILURE'}
                continue
            init_wall,init_cpu=time.perf_counter(),time.process_time()
            root=Path(root_factory(arm,case['project_id'])).resolve(strict=True)
            require(not private.resolve().is_relative_to(root),'PILOT_EVALUATOR_NOT_IN_REGISTERED_SOLVER_ROOT')
            initialization=dict(host_cpu_seconds=time.process_time()-init_cpu,wall_seconds=time.perf_counter()-init_wall,
                child_cpu_seconds=None,scope='Actual arm root/state initialization, including Native/Entity construction when used')
            world='projectA';install_initial_project(case,root/world)
            for stage in (1,2):
                if halt:project['stages'][stage-1]['arms'][arm]={'status':'NOT_EXECUTED_AFTER_UNCERTAIN_FAILURE'};continue
                if stage==2:
                    new_world=case['stage2_change']['root_alias'];apply_stage2_change(case,root/world,root/new_world);world=new_world
                stage_id=f"{case['project_id']}-{arm}-stage{stage}"
                validate_freeze(freeze,source_root)
                descriptor=dict(project_id=case['project_id'],stage=stage,arm=arm,root=str(root),world=world,
                    output=str(output/case['project_id']/arm/f'stage{stage}'),
                    notes_directory=str(output/case['project_id']/arm/'ordinary-notes'),
                    source_root=str(Path(source_root).resolve()),freeze_path=str((output/'source-freeze.json').resolve()),
                    initialization_resources=initialization if stage==1 else None)
                try:record=stage_launcher(descriptor)
                except Exception as error:
                    record=dict(status='FAILED_CLOSED',stage_pid=None,halt_batch=True,
                        provider_outcome='UNKNOWN_CHECK_GATEWAY_CLAIM',native_outcome='UNKNOWN',
                        error_code='PILOT_COLD_STAGE_FAILED_NO_RETRY',error_type=type(error).__name__)
                if not record.get('halt_batch'):
                    require(type(record.get('stage_pid')) is int and record['stage_pid']!=os.getpid(),'PILOT_COLD_INTERPRETER_REQUIRED')
                project['stages'][stage-1]['arms'][arm]=record
                if record.get('halt_batch') or record.get('provider_outcome')=='UNKNOWN_CHECK_GATEWAY_CLAIM':halt=True
        projects.append(project)
    result=public_projection(projects,freeze_hash,source_manifest_sha256=freeze.get('source_manifest_sha256'),simulation=simulation)
    exclusive(output/'PUBLIC_RESULT.json',result)
    return result


def _install_read_boundary(descriptor):
    """Audit the actual model-agent interpreter, not just folder separation."""
    from urllib.parse import urlsplit,unquote
    source=Path(descriptor['source_root']).resolve(strict=True)
    root=Path(descriptor['root']).resolve(strict=True)
    output=Path(descriptor['output']).resolve(strict=False)
    gateway=descriptor['gateway_config']
    writable=[root,output,Path(descriptor['notes_directory']).resolve(strict=False),Path(gateway['root']).resolve(strict=False)]
    readable=[source,output.parent,Path(sys.base_prefix).resolve(),Path(sys.prefix).resolve()]
    exact={Path(descriptor['freeze_path']).resolve(strict=True),Path(gateway['spec_path']).resolve(strict=True)}
    if gateway.get('approval_path'):exact.add(Path(gateway['approval_path']).resolve(strict=True))
    def permitted(path,write=False):
        path=Path(path).resolve(strict=False)
        return any(path==r or path.is_relative_to(r) for r in writable) or (not write and (path in exact or any(path==r or path.is_relative_to(r) for r in readable)))
    def audit(event,args):
        if event=='open' and isinstance(args[0],(str,bytes,os.PathLike)):
            mode=str(args[1] or '');flags=args[2] if len(args)>2 and type(args[2]) is int else 0
            write=any(c in mode for c in 'wax+') or bool(flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))
            require(permitted(os.fsdecode(args[0]),write),'PILOT_SOLVER_FILE_SCOPE_DENIED')
        if event=='sqlite3.connect':
            address=str(args[0]);parsed=unquote(urlsplit(address).path) if address.startswith('file:') else address
            if os.name=='nt' and parsed.startswith('/') and len(parsed)>2 and parsed[2]==':':parsed=parsed[1:]
            require(permitted(parsed,True),'PILOT_SOLVER_DATABASE_SCOPE_DENIED')
        if event=='subprocess.Popen':
            raw=args[1]
            # Only fixed, frozen Python source entrypoints can launch. There
            # is no shell/-c/model-code tool. CLI bytes are checked separately.
            words=raw if isinstance(raw,(list,tuple)) else __import__('shlex').split(raw,posix=False)
            words=[str(w).strip('"') for w in words]
            require(words and Path(words[0]).resolve()==Path(sys.executable).resolve()
                and not any(w in {'-c','-m'} for w in words),'PILOT_SOLVER_SUBPROCESS_SCOPE_DENIED')
            scripts=[Path(w).resolve(strict=False) for w in words[1:] if w.endswith('.py')]
            require(len(scripts)==1 and (scripts[0]==root/descriptor['world']/'workload.py'
                or scripts[0].is_relative_to(source)),'PILOT_SOLVER_SUBPROCESS_SOURCE_DENIED')
    sys.addaudithook(audit)
    # This path is deliberately outside every solver allowlist. It need not
    # exist: audit denial occurs before an operating-system file read.
    forbidden=root.parent/'EVALUATOR_ONLY'/'independent-read-boundary-probe.json'
    try:forbidden.read_bytes()
    except ValueError as error:require(str(error)=='PILOT_SOLVER_FILE_SCOPE_DENIED','PILOT_READ_BOUNDARY_PROBE')
    else:raise ValueError('PILOT_EVALUATOR_READ_WAS_NOT_DENIED')
    return dict(status='AUDIT_READ_BOUNDARY_VERIFIED',private_probe='DENIED',public_tool_paths='EXACT_VALIDATED_PROJECT_FILE_SET')


def stage_main(descriptor_path,factory='hosted_judge.model_workflow_runtime:stage_runtime'):
    """Fresh interpreter entrypoint; descriptor has no case/evaluator answers."""
    start,cpu=time.perf_counter(),time.process_time()
    require(factory=='hosted_judge.model_workflow_runtime:stage_runtime','PILOT_SOURCE_BOUND_RUNTIME_FACTORY')
    descriptor=json.loads(Path(descriptor_path).read_bytes())
    expected={'project_id','stage','arm','root','world','output','notes_directory','gateway_config','freeze_path','source_root','initialization_resources'}
    require(set(descriptor)==expected and descriptor['arm'] in {'conventional','se6'} and descriptor['stage'] in (1,2)
        and descriptor['world'] in {'projectA','projectB'},'PILOT_PUBLIC_STAGE_DESCRIPTOR')
    output=Path(descriptor['output']).resolve(strict=False)
    require(output.name=='stage'+str(descriptor['stage']) and output.parent.name==descriptor['arm']
        and output.parent.parent.name==descriptor['project_id']
        and Path(descriptor['notes_directory']).resolve(strict=False)==output.parent/'ordinary-notes',
        'PILOT_OWN_ARM_OUTPUT_AND_NOTES_SCOPE')
    boundary=_install_read_boundary(descriptor)
    module,name=factory.split(':');runtime=getattr(importlib.import_module(module),name)(descriptor)
    require(type(runtime) is dict and set(runtime)=={'gateway','tools','notes','native_dispatch','source_preflight'},'PILOT_RUNTIME_FACTORY_FIELDS')
    setup=dict(cpu_seconds=time.process_time()-cpu,wall_seconds=time.perf_counter()-start,
        scope='Fresh interpreter runtime construction/imports; process startup measured by parent')
    result=execute_stage(project_id=descriptor['project_id'],stage=descriptor['stage'],arm=descriptor['arm'],
        output=descriptor['output'],initialization_resources=descriptor['initialization_resources'],**runtime)
    final=dict(stage_pid=os.getpid(),record_sha256=digest(result),stage_setup_resources=setup,
        solver_read_boundary=boundary,process_cpu_seconds=time.process_time(),retry_allowed=False)
    exclusive(Path(descriptor['output'])/'cold-process-receipt.json',final)
    return result


def process_stage(descriptor_path,*,factory='hosted_judge.model_workflow_runtime:stage_runtime',timeout=360):
    """Parent calls once. A timed-out child is uncertain and never relaunched."""
    path=Path(descriptor_path).resolve(strict=True);descriptor=json.loads(path.read_bytes())
    source=Path(descriptor['source_root']).resolve(strict=True)
    start=time.perf_counter()
    output=Path(descriptor['output'])
    logs=output.parent/(output.name+'-private-transport');logs.mkdir(parents=True,exist_ok=False)
    try:
        child=subprocess.run([sys.executable,'-B','-m','paired_workflow.runner','--stage',str(path),'--factory',factory],
            cwd=source,capture_output=True,text=True,timeout=timeout,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
    except subprocess.TimeoutExpired as error:
        exclusive(logs/'failure.json',dict(status='INTERRUPTED',provider_outcome='UNKNOWN_CHECK_GATEWAY_CLAIM',native_outcome='UNKNOWN',retry_allowed=False))
        exclusive(logs/'stdout.txt',(error.stdout or b'') if isinstance(error.stdout,bytes) else (error.stdout or '').encode())
        exclusive(logs/'stderr.txt',(error.stderr or b'') if isinstance(error.stderr,bytes) else (error.stderr or '').encode())
        return dict(status='INTERRUPTED',stage_pid=None,halt_batch=True,provider_outcome='UNKNOWN_CHECK_GATEWAY_CLAIM',native_outcome='UNKNOWN',retry_permitted=False)
    exclusive(logs/'stdout.txt',child.stdout.encode());exclusive(logs/'stderr.txt',child.stderr.encode())
    exclusive(logs/'transport.json',dict(returncode=child.returncode,wall_seconds=time.perf_counter()-start,retry_allowed=False))
    require(child.returncode==0 and (output/'result.json').is_file(),'PILOT_COLD_STAGE_FAILED_NO_RETRY')
    result=json.loads((output/'result.json').read_bytes())
    receipt=json.loads((output/'cold-process-receipt.json').read_bytes())
    require(result['stage_pid']!=os.getpid() and result['stage_pid']==receipt['stage_pid']
        and receipt['record_sha256']==digest(result),'PILOT_COLD_STAGE_RECEIPT')
    exclusive(output/'parent-process-receipt.json',dict(parent_pid=os.getpid(),stage_pid=result['stage_pid'],
        child_process_wall_seconds=time.perf_counter()-start,descriptor_sha256=digest(descriptor),retry_allowed=False))
    return {**result,'cold_process_receipt':receipt,'parent_process_receipt':dict(
        child_process_wall_seconds=time.perf_counter()-start,parent_pid=os.getpid(),stage_pid=result['stage_pid'])}


def independently_assessed(cell):
    return (cell.get('independent_verdict') or {}).get('assessment_status')=='INDEPENDENTLY_ASSESSED'


def public_projection(projects,freeze_hash,*,source_manifest_sha256=None,simulation=False):
    completed=[cell for project in projects for stage in project['stages'] for cell in stage['arms'].values()]
    simulation=simulation or any(cell.get('record_kind')=='SIMULATED_TEST_ONLY' for cell in completed)
    responses=any(cell.get('responses_committed') for cell in completed)
    aggregate=None
    def success(cell):
        verdict=cell.get('independent_verdict') or {}
        return cell.get('status')=='VERIFIED_SUCCESS' and verdict.get('status')=='INDEPENDENTLY_VERIFIED' and verdict.get('goal') is True
    if responses:
        arms={}
        for arm in ('conventional','se6'):
            cells=[stage['arms'].get(arm,{}) for project in projects for stage in project['stages']]
            resources=[cell.get('resources',{}) for cell in cells]
            def known(key):
                values=[row.get(key) for row in resources]
                return sum(values) if len(values)==6 and all(type(v) in (int,float) for v in values) else None
            wrong=[(cell.get('independent_verdict') or {}).get('wrong_target_edits') for cell in cells]
            arms[arm]=dict(successful_stages=sum(success(c) for c in cells),stages=6,
                attempted_stages=sum(type((c.get('resources') or {}).get('provider_calls_attempted')) is int
                    and c['resources']['provider_calls_attempted']>0 for c in cells),
                independently_assessed_stages=sum(independently_assessed(c) for c in cells),
                statuses=[c.get('status','NOT_EXECUTED') for c in cells],
                completed_projects=sum(all(success(s['arms'].get(arm,{})) for s in p['stages']) for p in projects),
                wrong_target_edits=sum(wrong) if len(wrong)==6 and all(type(v) is int for v in wrong) else None,
                model_calls=known('provider_calls_attempted'),input_tokens=known('input_tokens'),output_tokens=known('output_tokens'),
                model_directed_tools=known('model_directed_tools'),common_cli_processes=known('common_cli_processes'),
                native_observed_cli_processes=known('native_observed_cli_processes'),
                repeated_inspections=known('repeated_inspections'),stage_host_cpu_seconds=known('whole_host_cpu_seconds'),
                stage_wall_seconds=known('whole_wall_seconds'),native_worker_cpu_seconds=known('native_worker_cpu_seconds'),
                initialization_resources=[c.get('initialization_resources') for c in cells if c.get('initialization_resources')],
                cold_process_resources=[c.get('cold_process_receipt') for c in cells],
                total_cpu_seconds=None,child_cpu_seconds=None,tariff_estimate_usd=known('tariff_estimate_usd'),actual_billed_usd=None,
                interventions=0,scope='Model-directed tools, common CLI and observed Native CLI counts have distinct scopes; total child CPU is UNKNOWN. All initialization/cold-process components retained.')
        all_assessed=all(arms[a]['independently_assessed_stages']==6 for a in arms)
        difference=arms['se6']['successful_stages']-arms['conventional']['successful_stages'] if all_assessed else None
        aggregate=dict(per_arm=arms,comparative_result=('TIE_ON_PRIMARY_SUCCESS' if difference==0 else
            'OBSERVED_SMALL_PILOT_PRIMARY_DIFFERENCE' if difference is not None else 'INCOMPLETE_NOT_ASSESSABLE'),
            successful_stage_difference_se6_minus_control=difference,general_superiority='NOT_ESTABLISHED',
            independent_units=3,stages_per_arm=6,story_project='project-001')
    if simulation:
        return dict(schema='se6-model-workflow-simulated-test-v1',status='SIMULATED_TEST_ONLY',record_kind='SIMULATED_TEST_ONLY',
            responses_committed=False,protocol_sha256=digest(PROTOCOL),aggregate=None,projects=[],
            scope=['Injected unit transport is not real model evidence and cannot be served as a recorded comparison.'])
    complete=len(completed)==12 and all(c.get('responses_committed') and
        independently_assessed(c)
        and (c.get('cold_process_receipt') or {}).get('stage_pid')==c.get('stage_pid')
        and (c.get('parent_process_receipt') or {}).get('stage_pid')==c.get('stage_pid')
        and type(c.get('stage_pid')) is int for c in completed)
    def safe(value):
        import re
        if isinstance(value,str) and (re.search(r'[A-Za-z]:[\\/]',value) or value.startswith(('/', '\\\\'))):
            return 'PRIVATE_PATH_REDACTED:'+digest(value)
        if isinstance(value,dict):return {k:safe(v) for k,v in value.items()}
        if isinstance(value,list):return [safe(v) for v in value]
        return value
    public_projects=[]
    allowed={'status','model_proposals','tool_events','native_receipts','action','independent_verdict',
        'retention','cold_continuation','resources','stage_pid','initialization_resources','cold_process_receipt',
        'parent_process_receipt','native_outcome','effect_outcome','failure'}
    for project in projects:
        stages=[]
        for staged in project['stages']:
            arms={}
            for name,cell in staged['arms'].items():
                arms[name]={**{k:safe(v) for k,v in cell.items() if k in allowed},
                    'native_or_control_decision':safe(cell.get('selected_decision'))}
            stages.append(dict(stage=staged['stage'],change_kind=staged.get('change_kind'),arms=arms))
        public_projects.append(dict(project_id=project['project_id'],change_kind=project.get('change_kind'),stages=stages))
    return dict(schema='se6-model-workflow-view-v1',status=('COMPLETE' if complete else 'INCOMPLETE') if responses else 'BLOCKED_PENDING_EXACT_BUDGET',
        record_kind='RECORDED' if responses else 'PREPARED',responses_committed=responses,
        protocol_sha256=digest(PROTOCOL),source_manifest_sha256=source_manifest_sha256,
        model={'provider':'Nebius','identifier':MODEL_SETTINGS['model'],'settings':deepcopy(MODEL_SETTINGS)},
        limits=dict(max_requests=36,input_tokens=None,model_context_token_upper_bound=262144,wire_input_bytes=24576,
            output_tokens=2048,tool_turns=3,usd_cap='3.00',max_effects=12,max_stage_seconds=360),
        scope=['Three independent project sequences; two dependent cold stages per arm.','Actual source freeze: '+freeze_hash,
            'Native deterministically solves the public affine subset; computation is measured, not attributed to model reasoning.'],
        aggregate=safe(aggregate),projects=public_projects if responses else [],full_canonical=False,
        limitations=['Three project sequences are independent units; stages are dependent.','Native deterministically solves the declared affine subset; model proposes/control, not mathematical necessity.','Actual invoice and unmeasured child CPU remain UNKNOWN.','A simulated transport never establishes a real comparison.'])


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description='Source-bound cold paired-model stage; no implicit provider approval')
    parser.add_argument('--stage',required=True);parser.add_argument('--factory',default='hosted_judge.model_workflow_runtime:stage_runtime')
    arguments=parser.parse_args()
    saved=stage_main(arguments.stage,arguments.factory)
    print(json.dumps({'status':saved['status'],'stage_pid':saved['stage_pid'],'result_sha256':digest(saved)}))
