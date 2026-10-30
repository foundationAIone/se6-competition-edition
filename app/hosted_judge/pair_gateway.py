"""Trusted server configuration, fresh bounded pair worker; no credential read by browser/parent."""
from copy import deepcopy
import hashlib,json,multiprocessing,socket,sys,time,os,uuid
from pathlib import Path

HARD_PAIR_DEADLINE=75

def _worker_record(coordinator,values,kind,record):
    """Separate immutable PRIVATE sidecar; never extend a frozen provider archive."""
    path=coordinator.path('worker-attestations',values['task_id'],values['request_id'],uuid.uuid4().hex+'-'+kind+'.json')
    path.parent.mkdir(parents=True,exist_ok=True)
    raw=json.dumps(record,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    with path.open('xb') as stream:
        stream.write(raw);stream.flush();os.fsync(stream.fileno())
    return {'private_path':str(path),'sha256':hashlib.sha256(raw).hexdigest()}

def _pair_child(pipe,config,values):
    try:
        sys.dont_write_bytecode=True
        if config['simulated'] or config['prepare_only']:
            def denied(*a,**kw):raise ValueError('Offline pair work cannot access network')
            socket.socket.connect=denied;socket.create_connection=denied;socket.getaddrinfo=denied
            env_type=type(os.environ);prior_getitem=env_type.__getitem__;prior_get=env_type.get
            def getitem(env,key):
                if key in ('NEBIUS_API_KEY','OPENAI_API_KEY'):raise ValueError('Offline pair work cannot consult credentials')
                return prior_getitem(env,key)
            def get(env,key,default=None):
                if key in ('NEBIUS_API_KEY','OPENAI_API_KEY'):raise ValueError('Offline pair work cannot consult credentials')
                return prior_get(env,key,default)
            env_type.__getitem__=getitem;env_type.get=get
        from .native_adapter import validate_bundle
        validate_bundle(config['native_bundle'],config['native_manifest'],config['native_manifest_sha256'])
        # Admission must precede every import/compilation from the private bundle.
        sys.path.insert(0,config['native_bundle'])
        from src.workbench.runtime_revision import freeze_sources
        revision=freeze_sources(Path(config['native_bundle']))
        if config['simulated']:
            def denied(*a,**kw):raise ValueError('Simulation cannot access network')
            socket.socket.connect=denied;socket.create_connection=denied;socket.getaddrinfo=denied
            from .simulation import SimulatedNebiusTransport
            factory=SimulatedNebiusTransport
        else:factory=None
        from .v8_run_both import RunBothCoordinator
        from .common_pair_contract import PROTOCOL
        coordinator=RunBothCoordinator(config['storage_root'],approval_path=config['approval_path'],
            approval_sha256=config['approval_sha256'],live_enabled=config['live_enabled'],transport_factory=factory,answer_protocol=PROTOCOL)
        if config['prepare_only']:
            from .v8_run_both import prepare
            # Default offline preparation has no earlier model answers. Private
            # live histories are never accepted from HTTP clients.
            history_path=coordinator.path('histories',values['task_id']+'.json')
            histories=json.loads(history_path.read_bytes())['lanes'] if history_path.exists() else {'se6':[],'baseline':[]}
            packet=prepare(values['question'],values['native_context'],values['public_history'],histories,protocol=PROTOCOL)
            pipe.send({'ok':True,'prepared_only':True,'packet':packet,'provider_calls':0})
            return
        import re
        if not all(isinstance(values[k],str) and re.fullmatch('[0-9a-f]{32}',values[k]) for k in ('task_id','request_id')):
            raise ValueError('Trusted server identities required')
        before=revision.public()
        if not before['disk_matches_loaded']:raise ValueError('Provider source changed before execution')
        archive=coordinator.path('requests',values['task_id'],values['request_id'])
        intent='CACHED_RETRIEVAL' if (archive/'final-manifest.json').exists() else 'NEW_DISPATCH_REQUEST_NOT_YET_AUTHORIZED'
        preflight=_worker_record(coordinator,values,'preflight',{
            'schema':'se6-v8-private-worker-source-v1','phase':'BEFORE_COORDINATOR_RUN',
            'operation_intent':intent,
            'compiled_private_src':before,'native_manifest_sha256':config['native_manifest_sha256'],
            'hosted_disk_sources':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
                (Path(__file__),Path(__file__).with_name('v8_run_both.py'),Path(__file__).with_name('v8_scoring.py'),Path(__file__).with_name('common_pair_contract.py'),Path(__file__).with_name('common_answer_scoring.py'))},
            'scope':'Compiled provenance covers private src only. Hosted files are disk observations; no independent provider signature.',
            'provider_execution_proven':False})
        result=coordinator.run(**values)
        observed=revision.public()
        if not observed['disk_matches_loaded']:raise ValueError('Provider source changed during execution')
        result['attestation']['compiled_provider_source']=observed
        completion=_worker_record(coordinator,values,'completion',{
            'schema':'se6-v8-private-worker-completion-v1','source_preflight':preflight,
            'operation_intent':intent,
            'compiled_private_src_after':observed,
            'archive':result['attestation']['archive'],'freeze_sha256':result['attestation']['freeze_sha256'],
            'final_manifest_sha256':hashlib.sha256((Path(result['attestation']['archive'])/'final-manifest.json').read_bytes()).hexdigest(),
            'packet_sha256':result['attestation']['packet_sha256'],
            'scope':'Separate sidecar links source observations to the frozen archive; it does not change that archive or certify provider authenticity.'})
        result['attestation']['durable_worker_source']=completion
        pipe.send({'ok':True,'result':result})
    except Exception as error:
        # Never send exception text, an authorization file or credentials to the parent/UI.
        pipe.send({'ok':False,'error_type':type(error).__name__,'failure_observation':getattr(error,'public_failure',None)})
    finally:pipe.close()

def native_metrics(native_public):
    """Whole recursive wall/actions; total CPU unknown when reader CPU is missing."""
    recursive=(native_public.get('realization_loop') or {}).get('resources')
    if recursive is not None:
        return {'native_seconds':recursive['controller_wall_seconds'],
            'native_wall_seconds':recursive['controller_wall_seconds'],
            'native_cpu_seconds':None,'native_operations':recursive['native_actions'],
            'provider_calls':0,'provider_tokens':0,'provider_cost_usd':0,'local_monetary_cost_usd':None}
    resources=(native_public.get('canonical') or {}).get('resources',{})
    return {'native_seconds':native_public.get('native_seconds',0),
        'native_wall_seconds':resources.get('whole_execute_native_wall_seconds',0),
        'native_cpu_seconds':resources.get('whole_execute_native_cpu_seconds',0),
        'native_operations':native_public.get('native_receipt_count',0),
        'provider_calls':0,'provider_tokens':0,'provider_cost_usd':0,'local_monetary_cost_usd':None}

class PairGateway:
    def __init__(self,native_bundle,storage_root,*,native_manifest=None,native_manifest_sha256=None,approval_path=None,approval_sha256=None,live_enabled=False,simulated=False,deadline=HARD_PAIR_DEADLINE):
        self.config={'native_bundle':str(Path(native_bundle).resolve()),'storage_root':str(Path(storage_root).resolve()),
            'native_manifest':str(Path(native_manifest).resolve()),'native_manifest_sha256':native_manifest_sha256,
            'approval_path':str(Path(approval_path).resolve()) if approval_path else None,
            'approval_sha256':approval_sha256,'live_enabled':live_enabled is True,'simulated':simulated is True,'prepare_only':False}
        if live_enabled and simulated:raise ValueError('Simulation and live authorization are separate modes')
        if live_enabled and not(approval_path and approval_sha256):raise ValueError('Exact pinned new private allowance required')
        if type(deadline) not in (float,int) or not 0<deadline<=HARD_PAIR_DEADLINE:raise ValueError('Absolute pair deadline required')
        self.deadline=deadline;self.live_configured=live_enabled is True

    def status(self):
        return {'mode':'SIMULATED_TEST' if self.config['simulated'] else 'RUN_BOTH_GATED',
            'status':'SIMULATED_ONLY' if self.config['simulated'] else 'SERVER_ALLOWANCE_CONFIGURED_NOT_VERIFIED' if self.live_configured else 'NOT_AUTHORIZED',
            'provider_calls':0,'retries':0}

    def context(self,native_public,native_context):
        canonical=native_public.get('canonical') or {}
        # Faithful projection of ACTUAL verified native output, never evaluator truth.
        # Full provenance/operators/field/journals stay in the private archive and UI.
        views=native_public.get('business_views')
        arithmetic=(native_public.get('local_verification') or {}).get('host_arithmetic') or {}
        typed=native_public.get('typed_answer') or {}
        checks=typed.get('checks') or {}
        user_answer=typed.get('user_answer')
        if isinstance(user_answer,dict) and typed.get('origin') in ('NATIVE_DETERMINISTIC','HOST_DETERMINISTIC') and checks.get('schema') is True and checks.get('semantic') is True and checks.get('finish') is True and checks.get('evidence') is True:
            # This is a trusted server projection of native/HOST output, not public
            # evaluator truth. Never include internal scope, hashes or receipts.
            facts={'user_answer':deepcopy(user_answer),'origin':typed['origin']}
        elif views is not None and canonical.get('independent_checkpoint_replay') is True and arithmetic.get('passed') is True and arithmetic.get('current') is True:
            allowed={'allocations','revenue','materials_cost','gross_contribution','budget_variance','budget_exceeded'}
            facts={'business':{tag:{k:deepcopy(v) for k,v in view.items() if k in allowed} for tag,view in views.items()}}
        else:
            facts={'answer':native_context}
        return json.dumps({'verified_conditional_results':facts,'world_facts_verified':False,
            'scope':'Task-local native proofs/HOST arithmetic; no external fact or tool authority.'},ensure_ascii=False,sort_keys=True,separators=(',',':'))

    def run(self,*,task_id,request_id,question,native_context,native_public,public_history):
        model={'provider':'Nebius Token Factory','model':'nvidia/nemotron-3-super-120b-a12b','temperature':0,'max_output_tokens':2048,
            'reasoning_effort':'none','response_format':{'type':'json_object'},'retries':0}
        preparing=not self.live_configured and not self.config['simulated']
        metrics=native_metrics(native_public)
        values={'task_id':task_id,'request_id':request_id,'question':question,
            'native_context':self.context(native_public,native_context),'native_metrics':metrics,'public_history':deepcopy(public_history)}
        start=time.perf_counter();ctx=multiprocessing.get_context('spawn');read,write=ctx.Pipe(duplex=False)
        config={**self.config,'prepare_only':preparing}
        process=ctx.Process(target=_pair_child,args=(write,config,values),daemon=True);process.start();write.close()
        try:
            result=read.recv() if read.poll(self.deadline) else {'ok':False,'error_type':'HardDeadline'}
        finally:
            read.close();process.join(timeout=0.2)
            # Only this exact newly owned worker is supervised; no unknown process is touched.
            if process.is_alive():process.terminate();process.join(timeout=2)
            if process.is_alive():process.kill();process.join(timeout=2)
            process.close()
        if not result['ok']:
            uncertain=not preparing and result['error_type'] not in ('Blocked',)
            return {'public':{'mode':'OFFLINE_PREPARATION_FAILED' if preparing else 'SIMULATED_TEST' if self.config['simulated'] else 'LIVE_GATED',
                'baseline_status':'NOT_EXECUTED_OFFLINE_PREPARATION_FAILED' if preparing else 'UNKNOWN_OR_INCOMPLETE_SPENT' if uncertain else 'NOT_EXECUTED_ALLOWANCE_REFUSED',
                'authorization_status':'NOT_AUTHORIZED' if preparing else 'SIMULATED_ONLY' if self.config['simulated'] else 'CONFIGURED_SCOPE_NOT_COMPLETED',
                'provider_calls':0 if self.config['simulated'] or not uncertain else None,
                'simulated_calls':None if self.config['simulated'] and uncertain else 0,
                'reserved_call_ceiling':2,'retry_allowed':False,'baseline_answer':None,'assisted_answer':None,
                'matched_model':model,'score':{'status':'UNASSESSABLE','overall_winner':None},
                'failure_observation':result.get('failure_observation'),
                'scope':'No retry or winner. A request intent/reservation is not proof of actual provider execution.'},
                'attestation':{'failure_kind':result['error_type'],'pair_supervision_wall_seconds':time.perf_counter()-start}}
        if preparing:
            packet=result['packet']
            return {'public':{'mode':'OFFLINE_NATIVE_WITH_EXACT_PREPARED_PAIR','baseline_status':'NOT_EXECUTED_NOT_AUTHORIZED',
                'authorization_status':'NOT_AUTHORIZED','provider_calls':0,'simulated_calls':0,'matched_model':packet['model'],
                'baseline_answer':None,'assisted_answer':None,'score':{'status':'NOT_EXECUTED','overall_winner':None},
                'prepared_pair_sha256':packet['packet_sha256'],'prepared_input_bytes':packet['input_bytes'],
                'limits':{'calls':2,'completion_tokens_per_call':2048,'combined_input_bytes':49152,'retries':0,'authorized_paid_budget_usd':0},
                'scope':'Exact future wire packet prepared; no credential consulted, allowance acquired or provider request made.'},
                'attestation':{'prepared_pair':packet,'provider_calls':0}}
        public=result['result']['public'];lanes=public['lanes']
        return {'public':{**public,'mode':'SIMULATED_TEST' if self.config['simulated'] else 'LIVE_FROZEN',
            'baseline_status':'SIMULATED_TEST_NOT_MODEL_EVIDENCE' if self.config['simulated'] else 'FROZEN_PROVIDER_RESPONSE',
            'authorization_status':'SIMULATED_ONLY' if self.config['simulated'] else 'CAPPED_ALLOWANCE_SPENT',
            'matched_model':model,'assisted_answer':lanes['se6']['response'],'baseline_answer':lanes['baseline']['response'],
            'score':{'status':'ASSESSABLE' if all(v['assessment']['status']=='ASSESSABLE' for v in lanes.values()) else 'UNASSESSABLE','lanes':{k:v['assessment'] for k,v in lanes.items()},'arithmetic_winner':public['arithmetic_winner'],'common_user_answer_winner':public.get('common_user_answer_winner'),'answer_protocol':public.get('answer_protocol'),'overall_winner':None},
            'pair_supervision_wall_seconds':time.perf_counter()-start,
            'native_metrics_scope':'Recursive controller wall/actions when available; total CPU and local money unknown. Component CPU/proof/effect ledger remains in realization_loop.resources.'},'attestation':result['result']['attestation']}
