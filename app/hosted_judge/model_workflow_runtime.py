"""Trusted isolated-stage host wiring, separate from model output and World trust."""
from pathlib import Path
import hashlib,json,os
from .model_pilot_gateway import PilotGateway
from . import model_native_workflow as native
from paired_workflow.protocol import digest,require,validate_freeze
from paired_workflow.tools import ProjectTools,checked_files
from paired_workflow.control import ConventionalNotes,native_model_notes

APP=Path(__file__).resolve().parents[1]

def stage_runtime(descriptor):
    require(Path(descriptor['source_root']).resolve()==APP,'PILOT_RUNTIME_SOURCE_ROOT')
    config=descriptor['gateway_config'];gateway=PilotGateway(**config)
    admitted=gateway.require_admission();spec=gateway.specification()
    root=Path(descriptor['root']).resolve(strict=True)
    temporary=Path(os.environ.get('TEMP') or os.environ['TMP']).resolve(strict=True)
    require(root.parent==temporary and root.name.startswith('SE6-NATIVE-QPRE-')
            and not root.is_symlink() and (root/'.SE6_NATIVE_QPRE_DISPOSABLE').is_file(),'PILOT_REGISTERED_DISPOSABLE_ROOT')
    authority_path=root/'pilot-authority.json';require(not authority_path.is_symlink(),'PILOT_AUTHORITY_LINK')
    authority=json.loads(authority_path.read_bytes())
    require(authority==dict(schema='se6-paired-disposable-root-v1',spec_sha256=gateway.spec_sha256,
        project_id=descriptor['project_id'],arm=descriptor['arm'],root_sha256=digest(str(root)),
        max_stages=2,max_effects_per_stage=1,scope='DISPOSABLE_LOCAL_ONLY_NO_PRODUCTION_PROVIDER_OR_NETWORK_AUTHORITY'),
        'PILOT_REGISTERED_AUTHORITY_BINDING')
    world=root/descriptor['world'];require(world.parent==root and descriptor['world'] in {'projectA','projectB'},'PILOT_WORLD_SCOPE')
    output=Path(descriptor['output']).resolve();notes_directory=Path(descriptor['notes_directory']).resolve()
    run_output=Path(spec['run_output']).resolve()
    require(output.is_relative_to(run_output) and notes_directory.is_relative_to(run_output),'PILOT_OUTPUT_SCOPE')
    freeze=json.loads(Path(descriptor['freeze_path']).read_bytes())
    def preflight():
        require(validate_freeze(freeze,APP)==spec['freeze_sha256'],'PILOT_RUNTIME_FREEZE_BINDING')
        gateway.require_admission()
    preflight()
    stage_id=f"{descriptor['project_id']}-{descriptor['arm']}-stage{descriptor['stage']}"
    def effect_admission(request):
        preflight()
        require(json.loads(authority_path.read_bytes())==authority,'PILOT_CURRENT_AUTHORITY_CHANGED')
        require(request['stage_id']==stage_id and request['root']==str(world.resolve()),'PILOT_EFFECT_FRAME')
        files=checked_files(world)
        require(request['source_hashes']=={n:hashlib.sha256(v).hexdigest() for n,v in files.items()},'PILOT_EFFECT_CURRENT_BYTES')
        return dict(status='ADMITTED',stage_id=stage_id,max_effects=1,root_sha256=digest(str(world.resolve())),
            authority_source='CURRENT_REGISTERED_DISPOSABLE_ROOT_AND_EXACT_PILOT_ADMISSION',
            spec_sha256=gateway.spec_sha256,world_scope='DISPOSABLE_LOCAL_PROJECT_ONLY')
    tools=ProjectTools(world,root_alias=descriptor['world'],state_root=root/'paired-tool-state',
        stage_id=stage_id,effect_admission=effect_admission)
    if descriptor['arm']=='conventional':
        notes=ConventionalNotes(notes_directory,descriptor['project_id']).load(stage=descriptor['stage'])
        dispatch=None
    else:
        notes=native_model_notes(notes_directory,descriptor['project_id'],stage=descriptor['stage'])
        if descriptor['stage']==2 and (root/'retained-1.json').exists():
            state=json.loads((root/'retained-1.json').read_bytes());renewal=json.loads((root/'renewal-1.json').read_bytes())
            result=json.loads((root/'result-1.json').read_bytes())
            require(digest(state)==renewal['state_sha256'] and result['goal'] is True
                    and hashlib.sha256((root/'retained-1.json').read_bytes()).hexdigest()==result['retained_state_sha256'],
                    'PILOT_NATIVE_NOTE_DURABLE_LINEAGE')
            obs=state['certificate']['observation']
            notes=dict(status='COLD_OWN_VERIFIED_NATIVE_AND_MODEL_EVIDENCE',verified_observations=notes['verified_observations']+[dict(
                manifest=obs['manifest'],goal=obs['schema'],configs=obs['configs'],root_alias='projectA',
                actual_prior_action=result['selected_action'],independent_goal=True,
                retained_state_sha256=result['retained_state_sha256'],native_receipt_hash=result['native_receipt_hash'])])
        def dispatch(proposal):
            preflight()
            return native.run_native_stage(root,descriptor['world'],descriptor['stage'],proposal)
    return dict(gateway=gateway,tools=tools,notes=notes,native_dispatch=dispatch,source_preflight=preflight)
