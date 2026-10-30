"""Untrusted model proposal -> source-bound Native validation and lifecycle.

The model proposes; it is not an authority or an independent witness. The
existing affine Native operator can already compute this bounded task. Its
role here is an independent validator/selector, never a silent repair fallback.
No provider client or model call exists in this module.
"""
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
import hashlib,json,os,re,subprocess,sys,tempfile,uuid

APP=Path(__file__).resolve().parents[1]
VERSION='se6-model-native-proposal-port-v1'
ROOT_REGISTRATION='.SE6_MODEL_TRANSPORT_ROOT.json'
ROOT_REGISTRATION_VERSION='se6-model-native-transport-root-v2'


def require(value,code):
    if not value: raise ValueError(code)


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def validate_proposal(proposal):
    require(type(proposal) is dict and set(proposal)=={'type','path','field','value','prediction'},'MODEL_ACTION_FIELDS')
    require(proposal['type']=='act' and proposal['field']=='limit','MODEL_ACTION_PRIMITIVE')
    require(type(proposal['path']) is str and re.fullmatch(r'[A-Za-z0-9_-]{1,80}\.json',proposal['path'])
        and proposal['path'] not in {'manifest.json','goal.json'},'MODEL_ACTION_RELATIVE_TARGET')
    require(type(proposal['value']) is int and 0<=proposal['value']<=100,'MODEL_ACTION_INTEGER_BOUND')
    require(type(proposal['prediction']) is dict and set(proposal['prediction'])=={'expected_output'}
        and type(proposal['prediction']['expected_output']) is int,'MODEL_ACTION_PREDICTION')
    return deepcopy(proposal)


def proposal_gate(proposal,observation,prepared,consumer,boundary,actions):
    """Consume actual prepare_native_input output and the original Core Boundary.

    A wrong model proposal is rejected before select can create a pending
    action. The full permitted candidate catalog remains available; this gate
    does not invent a new solver or modify a proposed value to fit the answer.
    """
    proposal=validate_proposal(proposal)
    require(observation['context']['cwd']==observation['context']['observed_root'],'MODEL_CURRENT_ROOT_BINDING')
    require(prepared['operating_context']==observation['context'] and
        prepared['binding']['entity_id']==consumer.engine.state.identity and
        prepared['binding']['entity_state']==consumer.engine.state.state_hash,'MODEL_NATIVE_FRAME_BINDING')
    action=next((a for a in actions if a['payload']['path']==proposal['path']),None)
    action_id=action['id'] if action is not None else 'MODEL_UNADMITTED:'+digest(proposal)
    predicted=next((row for row in prepared['predictions'] if row['continuation']==[action_id]),None)
    matching=(action is not None and action_id in boundary['permissions'] and predicted is not None and
        predicted['status']=='KNOWN' and predicted['outcomes'][-1][1] is True and
        predicted.get('derived_values',{}).get(action['id'])==proposal['value'] and
        proposal['prediction']['expected_output']==observation['schema']['goal'])
    core=consumer.c.core;state=consumer.engine.state
    sensed=core.SEObservation('UNTRUSTED_MODEL_PROPOSAL',state.identity,digest(proposal),
        source=prepared['binding']['source'],evidence_refs=(prepared['certificate_sha256'],))
    native_action=core.SEAction(action_id,json.dumps(dict(op='SET_INTEGER',path=proposal['path'],
        field='limit',value=proposal['value']),sort_keys=True))
    candidate=core.SECandidateTransition(state.state_hash,sensed.observation_id,None,(),False,native_action,
        json.dumps(proposal['prediction'],sort_keys=True))
    context=core._context(dict(identity=boundary['identity'],authorized=boundary['authorized'],
        permissions=boundary['permissions'],integrity_valid=True,evidence_valid=matching,
        max_actions=boundary['max_native_actions'],risk=0,max_risk=0,sensitive=False,human_approval_for=None))
    decision=core._bound(state,sensed,candidate,context)
    return dict(version=VERSION,allowed=decision.outcome=='ALLOW',boundary=asdict(decision),
        proposal_sha256=digest(proposal),native_prepared_sha256=digest(prepared),
        native_state_hash=state.state_hash,source_frame=dict(source=prepared['binding']['source'],
            epoch=prepared['binding']['epoch'],root_sha256=digest(observation['context']['cwd'])),
        fallback_used=False,model_role='UNTRUSTED_REPAIR_PROPOSER',
        native_role='SOURCE_BOUND_VALIDATOR_AND_SELECTOR',world_effects=0)


def require_exact_selected_action(proposal,selected):
    proposal=validate_proposal(proposal)
    require(selected['payload']==dict(op='SET_INTEGER',path=proposal['path'],field='limit',value=proposal['value']),
        'MODEL_PROPOSAL_NATIVE_SELECTION_MISMATCH_NO_FALLBACK')


def _linked(path):
    return path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction())


def _checked_transport_root(root):
    raw=Path(root)
    require(raw.is_absolute() and not any(_linked(p) for p in (raw,*raw.parents)),
        'MODEL_LOG_REGISTERED_ROOT')
    root=raw.resolve(strict=True)
    require(root.is_dir() and root.name.startswith('SE6-NATIVE-QPRE-'),'MODEL_LOG_REGISTERED_ROOT')
    marker=root/'.SE6_NATIVE_QPRE_DISPOSABLE'
    require(marker.is_file() and not _linked(marker)
        and marker.read_text()=='explicit-simulated-development-only-v1','MODEL_LOG_REGISTERED_MARKER')
    return root,marker


def _register_native_root(root):
    """Record the original selected temp parent before installing solver audit.

    This grants no Native, model, filesystem-tool or World authority. The exact
    original Native check_root and all independent source/effect checks remain
    mandatory in the child. Existing roots are never migrated or overwritten.
    """
    root,marker=_checked_transport_root(root)
    parent=Path(tempfile.gettempdir()).resolve(strict=True)
    require(root.parent==parent,'MODEL_LOG_REGISTERED_TEMP_PARENT')
    record=dict(version=ROOT_REGISTRATION_VERSION,purpose='NON_AUTHORIZING_TRANSPORT_ROOT',
        root=str(root),temp_parent=str(parent),marker_sha256=hashlib.sha256(marker.read_bytes()).hexdigest(),
        bridge_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    with (root/ROOT_REGISTRATION).open('xb') as stream:
        stream.write(json.dumps(record,sort_keys=True,separators=(',',':')).encode());stream.flush();os.fsync(stream.fileno())
    return root


def _read_registered_native_root(root):
    root,marker=_checked_transport_root(root)
    registration=root/ROOT_REGISTRATION
    require(registration.is_file() and not _linked(registration),'MODEL_LOG_REGISTRATION_REQUIRED')
    require(registration.stat().st_size<=4096,'MODEL_LOG_REGISTRATION_BOUND')
    record=json.loads(registration.read_bytes())
    expected=dict(version=ROOT_REGISTRATION_VERSION,purpose='NON_AUTHORIZING_TRANSPORT_ROOT',
        root=str(root),temp_parent=str(root.parent),marker_sha256=hashlib.sha256(marker.read_bytes()).hexdigest(),
        bridge_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    require(record==expected,'MODEL_LOG_REGISTRATION_MISMATCH')
    return root


def _private_stage_log(root,operation,world,phase,proposal,outcome,stdout,stderr):
    """Keep child evidence inside its previously registered disposable root.

    No temp discovery occurs here: an uncached gettempdir performs probe writes
    outside the solver boundary. Read the exact pre-audit host registration;
    never relax that boundary or infer Native authority from this transport file.
    No captured bytes or private paths are included in the returned public row.
    """
    if root is None:return None
    root=_read_registered_native_root(root)
    directory=root/'model-stage-logs';require(not _linked(directory),'MODEL_LOG_NO_LINK')
    directory.mkdir(exist_ok=True)
    def raw(value):return value if isinstance(value,bytes) else (value or '').encode('utf-8',errors='surrogatepass')
    stdout,stderr=raw(stdout),raw(stderr);attempt=uuid.uuid4().hex
    for suffix,value in (('stdout',stdout),('stderr',stderr)):
        with (directory/(attempt+'.'+suffix)).open('xb') as stream:
            stream.write(value);stream.flush();os.fsync(stream.fileno())
    record=dict(operation=operation,world=world,phase=phase,outcome=outcome,
        proposal_sha256=None if proposal is None else digest(proposal),
        stdout_sha256=hashlib.sha256(stdout).hexdigest(),stderr_sha256=hashlib.sha256(stderr).hexdigest(),
        stdout_bytes=len(stdout),stderr_bytes=len(stderr),retry_permitted=False,
        evidence_scope='PRIVATE_CHILD_TRANSPORT_EVIDENCE_NOT_MODEL_INPUT')
    with (directory/(attempt+'.json')).open('xb') as stream:
        stream.write(json.dumps(record,sort_keys=True,separators=(',',':')).encode());stream.flush();os.fsync(stream.fileno())
    return digest(record)


def _command(operation,*,root=None,world=None,phase=None,proposal=None,deadline_seconds=120):
    require(type(deadline_seconds) in (int,float) and 0<deadline_seconds<=120,'MODEL_NATIVE_DEADLINE')
    command=[sys.executable,'-B',str(APP/'tools/run_model_native_stage.py'),'--operation',operation]
    if root is not None: command+=['--root',str(root)]
    if world is not None: command+=['--world',world]
    if phase is not None: command+=['--phase',str(phase)]
    environment={key:value for key,value in os.environ.items() if key.upper() in {
        'PATH','PATHEXT','SYSTEMROOT','WINDIR','COMSPEC','TEMP','TMP','LOCALAPPDATA','APPDATA','USERPROFILE'}}
    environment.update(PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1')
    try:
        result=subprocess.run(command,input=json.dumps({'proposal':proposal}) if proposal is not None else '',
            cwd=APP,capture_output=True,text=True,timeout=deadline_seconds,env=environment)
    except subprocess.TimeoutExpired as error:
        evidence=_private_stage_log(root,operation,world,phase,proposal,dict(status='TIMEOUT',returncode=None),
            error.stdout,error.stderr)
        return dict(status='INTERRUPTED',goal=False,error_code='MODEL_NATIVE_UNCERTAIN_NO_RETRY',
            actual_effects=None,retry_permitted=False,private_evidence_sha256=evidence)
    evidence=_private_stage_log(root,operation,world,phase,proposal,dict(status='EXITED',returncode=result.returncode),
        result.stdout,result.stderr)
    if result.returncode!=0:
        return dict(status='FAILED_CLOSED',goal=False,error_code='MODEL_NATIVE_STAGE_FAILED_NO_RETRY',
            actual_effects=None,retry_permitted=False,private_evidence_sha256=evidence)
    require(len(result.stdout)<=2*1024*1024,'MODEL_NATIVE_RESULT_BOUND')
    value=json.loads(result.stdout)
    if evidence is not None:value['private_evidence_sha256']=evidence
    return value


def initialize_native_instance():
    """Actual disposable Entity/genesis only; no project action or model call."""
    result=_command('initialize')
    require(result['status']=='INITIALIZED_DISPOSABLE_NATIVE','MODEL_NATIVE_INITIALIZATION')
    return _register_native_root(result['root'])


def run_native_stage(root,world,phase,proposal,*,deadline_seconds=120):
    require(world in ('projectA','projectB') and type(phase) is int and phase in (1,2),'MODEL_NATIVE_STAGE_SCOPE')
    proposal=validate_proposal(proposal)
    return _command('run',root=root,world=world,phase=phase,proposal=proposal,deadline_seconds=deadline_seconds)
