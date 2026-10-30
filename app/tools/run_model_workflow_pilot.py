"""Source-freeze preparation and one explicitly admitted paired pilot.

prepare makes no provider request and no repair effects. execute requires a new
exact pinned owner decision; no key test, fallback, or automatic retry exists.
"""
from pathlib import Path
import argparse,datetime,hashlib,json,os,sys,uuid
APP=Path(__file__).resolve().parents[1];sys.path.insert(0,str(APP));sys.dont_write_bytecode=True
from paired_workflow.protocol import PROTOCOL,SYSTEM_PROMPT,MODEL_SETTINGS,digest,sha,encode,validate_freeze,require
from paired_workflow.tasks import exclusive,generate_scored_cases,install_initial_project
from paired_workflow.tools import ProjectTools
from paired_workflow.runner import run_pilot,process_stage
from hosted_judge.model_pilot_gateway import PilotGateway,MODEL,ENDPOINT,TOTAL_RESERVE
from hosted_judge.model_native_workflow import initialize_native_instance

def source_freeze():
    manifest=APP/'COMPLETE_SOURCE_MANIFEST_PRIVATE.json';files=json.loads(manifest.read_bytes())['files']
    actual={p.relative_to(APP).as_posix() for p in APP.rglob('*') if p.is_file()}
    require(actual==set(files)|{manifest.name},'PILOT_EXACT_SOURCE_INVENTORY')
    for name,pin in files.items():require(sha(APP/name)==pin,'PILOT_SOURCE_PIN_CHANGED')
    sources={**files,manifest.name:sha(manifest)}
    return dict(status='SOURCE_FROZEN',source_manifest_sha256=sha(manifest),protocol_sha256=digest(PROTOCOL),
        sources=sources,native_source_paths=[name for name in sources if name.startswith('awareness_native/')],
        frozen_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())

def gateway_at(out,*,approval=None,approval_sha=None,enabled=False):
    spec=out/'BATCH_SPEC.json'
    return PilotGateway(out/'provider-claims',spec_path=spec,spec_sha256=sha(spec),
        approval_path=approval,approval_sha256=approval_sha,live_enabled=enabled)

def prepare(out):
    require(out.is_dir(),'PILOT_OUTPUT_DIRECTORY_REQUIRED')
    require(not (out/'BATCH_SPEC.json').exists(),'PILOT_ALREADY_PREPARED_NO_REGENERATION')
    freeze=source_freeze();exclusive(out/'SOURCE_FREEZE.json',freeze)
    generation=generate_scored_cases(out/'scored-cases',freeze,APP)
    proto=PilotGateway(out/'provider-claims',spec_path=out/'BATCH_SPEC.json',spec_sha256='0'*64)
    spec=dict(schema='se6-model-workflow-batch-v1',model=MODEL,endpoint=ENDPOINT,
        max_requests=36,max_output_tokens=2048,max_wire_input_bytes=24576,
        model_context_token_upper_bound=262144,max_tool_turns_per_stage=3,max_effects_per_stage=1,
        usd_cap='3.00',tariff={'input_usd_per_million':'0.30','output_usd_per_million':'0.90'},
        allowed_projects=generation['project_ids'],claim_store_sha256=proto.store_identity(),
        source_manifest_sha256=freeze['source_manifest_sha256'],freeze_sha256=digest(freeze),
        protocol_sha256=digest(PROTOCOL),case_generation_receipt_sha256=generation['generation_receipt_sha256'],
        run_output=str(out/'actual-pilot'),case_directory=str(out/'scored-cases'),
        scope='ONE_SYNTHETIC_DEVELOPER_PILOT_THREE_PROJECTS_TWO_COLD_STAGES_TWO_ARMS',
        max_disposable_effects=12,provider_timeout_seconds=30,stage_timeout_seconds=360,
        automatic_retries=0,fallback_calls=0,development_provider_calls=0,
        story_rule='LOWEST_NUMERIC_PROJECT_ID_REGARDLESS_OF_OUTCOME')
    exclusive(out/'BATCH_SPEC.json',spec)
    gateway=gateway_at(out);gateway._check_sources(spec)
    # Construct first-turn messages using actual failing read-only public copies.
    # Future tool turns and cold notes depend on committed model/work outcomes;
    # their exact source-bound construction and ceiling are frozen, not invented.
    private=out/'scored-cases/EVALUATOR_ONLY';catalog=json.loads((private/'generation.json').read_bytes())
    prepared=[]
    for entry in catalog['private_cases']:
        case=json.loads((private/(entry['project_id']+'.json')).read_bytes())
        public=out/'prepared-inputs'/entry['project_id']/'projectA';install_initial_project(case,public)
        tools=ProjectTools(public,root_alias='projectA',state_root=out/'prepared-tool-state',stage_id='prepare-'+entry['project_id'],effect_admission=None)
        context=tools.public_context()
        for arm in ('conventional','se6'):
            request=dict(request_id=uuid.uuid4().hex,project_id=entry['project_id'],stage=1,arm=arm,turn=1,
                messages=[dict(role='system',content=SYSTEM_PROMPT),dict(role='user',content=json.dumps(dict(public_task=context,own_verified_notes={'status':'NO_PRIOR_NOTES','verified_observations':[]}),sort_keys=True))])
            packet=gateway.prepare(request);name=entry['project_id']+'-'+arm+'.json';exclusive(out/'prepared-first-requests'/name,packet)
            prepared.append(dict(file=name,request_sha256=packet['request_sha256'],wire_bytes=packet['request_metadata']['wire_bytes']))
    exclusive(out/'PREPARATION_RESULT.json',dict(status='OFFLINE_PREPARATION_COMPLETE',model_comparison='BLOCKED_PENDING_EXACT_BUDGET',
        spec_sha256=sha(out/'BATCH_SPEC.json'),source_manifest_sha256=freeze['source_manifest_sha256'],
        source_frozen_before_scored_generation=True,projects=3,stages_per_arm=6,prepared_first_requests=prepared,
        adaptive_requests='Only allowed public tool results and each arm own verified notes; future tool-turn and cold-stage messages cannot be invented before outcomes.',
        conservative_estimate_upper_usd=str(TOTAL_RESERVE),hard_published_tariff_cap_usd='3.00',actual_invoice=None,
        provider_calls=0,repair_effects=0,credential_status='PRESENT' if bool(os.environ.get('NEBIUS_API_KEY')) else 'MISSING'))
    print(json.dumps(dict(status='OFFLINE_PREPARATION_COMPLETE',spec_sha256=sha(out/'BATCH_SPEC.json'),model_comparison='BLOCKED_PENDING_EXACT_BUDGET',provider_calls=0)))

def execute(out,approval,approval_sha):
    require(approval and approval_sha,'PILOT_EXACT_PINNED_OWNER_APPROVAL_REQUIRED')
    gateway=gateway_at(out,approval=approval,approval_sha=approval_sha,enabled=True)
    gateway.require_admission();spec=gateway.specification()
    freeze=json.loads((out/'SOURCE_FREEZE.json').read_bytes());validate_freeze(freeze,APP)
    require(digest(freeze)==spec['freeze_sha256'],'PILOT_APPROVED_FREEZE')
    generation=json.loads((out/'scored-cases/EVALUATOR_ONLY/generation.json').read_bytes())
    require(digest(generation)==spec['case_generation_receipt_sha256'],'PILOT_APPROVED_CASE_SET_CHANGED')
    exclusive(out/'RUN_STARTED.json',dict(spec_sha256=gateway.spec_sha256,started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),provider_calls=0,status='ADMITTED_NOT_YET_DISPATCHED'))
    roots={}
    def root_factory(arm,project):
        if arm=='se6':root=initialize_native_instance()
        else:
            core=APP/'awareness_native/work/qpre-calibration-integration-20261026/dev';sys.path.insert(0,str(core))
            from scripts.run_native_qpre_learning import new_root
            root=new_root()
        record=dict(schema='se6-paired-disposable-root-v1',spec_sha256=gateway.spec_sha256,
            project_id=project,arm=arm,root_sha256=digest(str(root)),max_stages=2,max_effects_per_stage=1,
            scope='DISPOSABLE_LOCAL_ONLY_NO_PRODUCTION_PROVIDER_OR_NETWORK_AUTHORITY')
        exclusive(root/'pilot-authority.json',record);roots[(project,arm)]=str(root)
        return root
    def stage_launcher(descriptor):
        descriptor['gateway_config']=dict(root=str(out/'provider-claims'),spec_path=str(out/'BATCH_SPEC.json'),
            spec_sha256=gateway.spec_sha256,approval_path=str(Path(approval).resolve()),approval_sha256=approval_sha,live_enabled=True)
        name=f"{descriptor['project_id']}-{descriptor['arm']}-{descriptor['stage']}.json"
        path=out/'actual-pilot/stage-descriptors'/name;exclusive(path,descriptor)
        try:
            record=process_stage(path,timeout=360)
            checkpoint=dict(spec_sha256=gateway.spec_sha256,latest_project=descriptor['project_id'],stage=descriptor['stage'],arm=descriptor['arm'],status=record.get('status'),stage_pid=record.get('stage_pid'),updated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),continuous_monitor=False)
            target=out/'CURRENT_RUN_CHECKPOINT.json';temporary=out/'CURRENT_RUN_CHECKPOINT.tmp'
            temporary.write_bytes(encode(checkpoint));os.replace(temporary,target)
            return record
        except BaseException as error:
            failure=dict(status='FAILED_CLOSED',stage_pid=None,provider_outcome='UNKNOWN_CHECK_GATEWAY_CLAIM',
                effect_outcome='UNKNOWN',retry_allowed=False,error_type=type(error).__name__)
            exclusive(out/'actual-pilot/stage-descriptors'/(name+'.failure.json'),failure)
            gateway.root.mkdir(parents=True,exist_ok=True)
            if not gateway.path('STOP.json').exists():exclusive(gateway.path('STOP.json'),failure)
            return failure
    result=run_pilot(case_directory=out/'scored-cases',freeze=freeze,source_root=APP,
        output=out/'actual-pilot',gateway=gateway,root_factory=root_factory,stage_launcher=stage_launcher)
    exclusive(out/'ACTUAL_ROOTS_PRIVATE.json',{'roots':[{'project':p,'arm':a,'root':r} for (p,a),r in roots.items()]})
    print(json.dumps(dict(status=result['status'],result=str(out/'actual-pilot/PUBLIC_RESULT.json'))))

def preflight(out):
    gateway=gateway_at(out);spec=gateway.specification();gateway._check_sources(spec)
    freeze=json.loads((out/'SOURCE_FREEZE.json').read_bytes());require(validate_freeze(freeze,APP)==spec['freeze_sha256'],'PILOT_PREFLIGHT_FREEZE')
    generation=json.loads((out/'scored-cases/EVALUATOR_ONLY/generation.json').read_bytes())
    require(digest(generation)==spec['case_generation_receipt_sha256'],'PILOT_PREFLIGHT_CASE_SET')
    checked=0
    for path in sorted((out/'prepared-first-requests').glob('*.json')):
        packet=json.loads(path.read_bytes());require(gateway.prepare(packet['request'])==packet,'PILOT_PREFLIGHT_REQUEST_CHANGED');checked+=1
    require(checked==6,'PILOT_PREFLIGHT_REQUEST_COUNT')
    from hosted_judge.model_pilot_gateway import Blocked
    try:gateway.require_admission()
    except Blocked as error:require('BLOCKED_PENDING_EXACT_BUDGET' in str(error),'PILOT_PREFLIGHT_UNEXPECTED_REFUSAL')
    else:raise ValueError('PILOT_PREFLIGHT_MISSING_BUDGET_DID_NOT_REFUSE')
    require(not gateway.root.exists(),'PILOT_PREFLIGHT_CREATED_PAID_CLAIMS')
    record=dict(status='PASS_EFFECT_FREE_ADMISSION_PREFLIGHT',spec_sha256=gateway.spec_sha256,
        source_pins=len(freeze['sources']),first_requests_reconstructed=checked,unapproved_dispatch='REFUSED',
        provider_calls=0,effects=0,paid_claims_created=0,credential_values_saved=False)
    exclusive(out/'EFFECT_FREE_PREFLIGHT.json',record);print(json.dumps(record))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','preflight','execute']);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--owner-approval',type=Path);p.add_argument('--owner-approval-sha256');args=p.parse_args()
    out=args.output.resolve(strict=True)
    if args.mode=='prepare':prepare(out)
    elif args.mode=='preflight':preflight(out)
    else:execute(out,args.owner_approval,args.owner_approval_sha256)
