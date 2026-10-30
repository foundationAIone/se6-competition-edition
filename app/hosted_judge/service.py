"""Anonymous bounded sessions + exact-origin HTTP; no campaign dispatch API."""
from copy import deepcopy
from dataclasses import dataclass,field
import hashlib
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import multiprocessing
import os
from datetime import datetime,timezone
from pathlib import Path
import re
import secrets
import threading
import time
from urllib.parse import urlsplit
from .native_adapter import execute_native,encode,validate_bundle
from .paired_review import with_public_history

SESSION_TTL=600;MAX_SESSIONS=16;MAX_ROUNDS=4;MAX_ACTIONS=20
MAX_ATTEMPTS=8
MAX_BODY=8192;MAX_QUESTION=4096;MAX_ACTIVE_WORKERS=2;WORKER_DEADLINE=20


class LimitError(ValueError):pass
class UnavailableError(ValueError):pass

class NativeExecutionError(ValueError):
    def __init__(self,code):
        self.error_code=code
        super().__init__('Bounded native execution failed')

SAFE_CODES={'NATIVE_TIMEOUT','NATIVE_VERIFICATION_REJECTED','NATIVE_EXECUTION_REJECTED',
    'SESSION_EXPIRED','ACTION_ALLOWANCE','RESOURCE_LIMIT','NATIVE_UNAVAILABLE','EXECUTION_FAILED'}
VERIFICATION_MESSAGES={'AUTO checkpoint hash mismatch','Prior AUTO checkpoint identity/hash mismatch',
    'Claimed native receipt differs from replayed consequence','Claimed receipts must be the exact new journal delta',
    'Current node order and exact new journal receipts disagree','Hosted native boundary violation',
    'Independent native checkpoint replay failed','Actual consequence did not pass local proof replay','Duplicate consequence receipt','Native node receipt coverage malformed','Native task/source identity mismatch','Prior AUTO checkpoint identity/hash mismatch','Prior journal belongs to another task',
    'Native history was replaced instead of appended','Previously retained independent journal was removed'}

def failure_code(error):
    if isinstance(error,NativeExecutionError) and error.error_code in SAFE_CODES:return error.error_code
    if isinstance(error,LimitError):
        text=str(error)
        if text=='Native time allowance exceeded; prior state preserved':return 'NATIVE_TIMEOUT'
        if text=='Session expired during computation; result discarded':return 'SESSION_EXPIRED'
        if text=='Native action allowance exceeded; prior state preserved':return 'ACTION_ALLOWANCE'
        return 'RESOURCE_LIMIT'
    if isinstance(error,UnavailableError):return 'NATIVE_UNAVAILABLE'
    if type(error) is ValueError and (str(error) in VERIFICATION_MESSAGES or str(error).startswith('PRESENTATION_')):return 'NATIVE_VERIFICATION_REJECTED'
    return 'EXECUTION_FAILED'


def _child(pipe,values):
    try:pipe.send({'ok':True,'result':execute_native(*values)})
    except Exception as error:
        code=failure_code(error)
        if code=='EXECUTION_FAILED':code='NATIVE_EXECUTION_REJECTED'
        pipe.send({'ok':False,'error_code':code})
    finally:pipe.close()


def disposable_native(values,deadline=WORKER_DEADLINE):
    ctx=multiprocessing.get_context('spawn');read,write=ctx.Pipe(duplex=False)
    process=ctx.Process(target=_child,args=(write,values),daemon=True);process.start();write.close()
    try:
        if not read.poll(deadline):raise LimitError('Native time allowance exceeded; prior state preserved')
        result=read.recv()
        if not result['ok']:raise NativeExecutionError(result.get('error_code','NATIVE_EXECUTION_REJECTED'))
        return result['result']
    finally:
        read.close();process.join(timeout=0.2)
        # This is the exact child owned above, never an unknown process.
        if process.is_alive():process.terminate();process.join(timeout=2)
        if process.is_alive():process.kill();process.join(timeout=2)
        process.close()


@dataclass
class Session:
    csrf:str
    expires:float
    task_id:str
    checkpoint:object=None
    field_checkpoint:object=None
    realization_state:object=None
    rounds:int=0
    actions:int=0
    attempts:int=0
    attestation:object=None
    busy:bool=False
    requests:dict=field(default_factory=dict)
    request_times:list=field(default_factory=list)
    public_questions:list=field(default_factory=list)
    queued_id:object=None
    failure_info:dict=field(default_factory=dict)
    benchmark_jobs:set=field(default_factory=set)
    typed_task_state:object=None


class JudgeService:
    def __init__(self,bundle,manifest,digest,*,clock=time.monotonic,executor=disposable_native,review=None,dynamic=None,canonical=None,current_coverage=None,field_controls=None,replays=None,pair_gateway=None,asynchronous=False,realization_root=None,benchmark=None):
        self.bundle,self.manifest,self.digest=str(bundle),str(manifest),digest
        self.native_available=False
        if bundle is not None and manifest is not None and digest is not None:
            validate_bundle(bundle,manifest,digest);self.native_available=True
        self.clock,self.executor=clock,executor
        self.sessions={};self.lock=threading.RLock();self.workers=threading.BoundedSemaphore(MAX_ACTIVE_WORKERS)
        self.dynamic=deepcopy(dynamic or {'name':'Dynamic evidence not configured','scenarios':[]})
        self.canonical=deepcopy(canonical or {'name':'Canonical evidence not configured','cases':[]})
        self.canonical['current_operators']=deepcopy(current_coverage or [])
        self.canonical['field_controls']=deepcopy(field_controls or {})
        self.replays=deepcopy(replays or {'schema':'se6-frozen-offline-replays-v8','cases':[]})
        self.benchmark=deepcopy(benchmark or {'schema':'se6-v11-benchmark-view-v1','status':'NOT_CONFIGURED','tasks':[],'provider_calls':0})
        self.benchmark_runner=None
        self.pair_gateway=pair_gateway;self.asynchronous=asynchronous
        self.awareness=None
        self.model_workflow_evidence=None
        self.agent_realization_evidence=None
        self.model_integration_evidence=None
        self.realization_root=None;self.durable=None
        if realization_root is not None:
            if not self.native_available or executor is not disposable_native:raise ValueError('Recursive execution requires actual reviewed native workers')
            from .realization_loop import root_path
            from .durable_sessions import DurableSessions
            self.realization_root=root_path(realization_root)
            if self.realization_root.is_relative_to(Path(bundle).parent.resolve()):raise ValueError('Recursive private store cannot enter source')
            self.durable=DurableSessions(self.realization_root/'sessions',digest)
        self.research_preparation_evidence=None
        self.review=deepcopy(review or {'schema':'se6-public-frozen-score-review-v1','records':[]})

    def execution_status(self):
        mode=self.pair_gateway.status() if self.pair_gateway else {'mode':'NATIVE_ONLY','status':'BLOCKED'}
        return {'execution_mode':mode['mode'],'baseline_authorization_status':mode['status']}

    def submit(self,token,csrf,value):
        if not isinstance(value,dict) or set(value)!={'question','request_id'}:raise ValueError('Provide question and request_id only')
        question,request_id=value['question'],value['request_id']
        if not isinstance(question,str) or not question.strip() or len(question)>4000 or len(question.encode())>MAX_QUESTION:raise ValueError('Question bound')
        if not isinstance(request_id,str) or not re.fullmatch('[0-9a-f]{32}',request_id):raise ValueError('Request identity required')
        identity=hashlib.sha256(encode(value)).hexdigest()
        with self.lock:
            s=self.session(token)
            if not isinstance(csrf,str) or not secrets.compare_digest(csrf,s.csrf):raise PermissionError('Session CSRF required')
            if not self.native_available:raise UnavailableError('Native execution unavailable')
            if request_id in s.requests:
                old,output=s.requests[request_id]
                if old!=identity:raise ValueError('Request identity reused with different input')
                return deepcopy(output)
            if s.busy or s.queued_id is not None:raise LimitError('A RUN BOTH job is already active')
            if s.rounds>=MAX_ROUNDS or s.actions>=MAX_ACTIONS or s.attempts>=MAX_ATTEMPTS:raise LimitError('Session computation allowance exhausted')
            if self.realization_root and (s.realization_state or {}).get('step',0)>=4:raise LimitError('Four private realization cycles exhausted; reset the isolated problem')
            s.queued_id=request_id
            s.requests[request_id]=(identity,{'status':'RUNNING','request_id':request_id,'scope':'One queued bounded job; polling cannot dispatch another call'})
            worker=threading.Thread(target=self._execute_job,args=(token,csrf,deepcopy(value),identity,s),daemon=True)
            worker.start()
            return deepcopy(s.requests[request_id][1])

    def _record_failure(self,s,request_id,error,context):
        code=failure_code(error);stage=context['stage']
        unknown=stage=='provider_phase'
        row={'schema':'se6-private-job-failure-v1','error_code':code,'stage':stage,
            'at_utc':datetime.now(timezone.utc).isoformat(),
            'elapsed_wall_seconds':max(0,time.perf_counter()-context['wall_start']),
            'elapsed_cpu_seconds':max(0,time.process_time()-context['cpu_start']),
            'worker_deadline_seconds':WORKER_DEADLINE,'provider_calls':None if unknown else 0,
            'paid_outcome':'UNKNOWN' if unknown else 'NOT_DISPATCHED',
            'native_state_committed':context['committed'],
            'prior_native_state_sha256':context['prior_native_hash'],
            'current_native_state_sha256':hashlib.sha256(encode(s.checkpoint)).hexdigest(),
            'prior_field_state_sha256':context['prior_field_hash'],
            'current_field_state_sha256':hashlib.sha256(encode(s.field_checkpoint)).hexdigest(),
            'completed_rounds':s.rounds,'completed_actions':s.actions,'attempts':s.attempts,
            'private_realization_outcome':'UNKNOWN_INSPECT_PRIVATE_LEDGER_NO_RETRY' if self.realization_root and stage in ('realization_phase','commit_validation') else 'NOT_DISPATCHED_OR_ALREADY_COMMITTED'}
        saved=False
        # Only admitted attempts may consume bounded private receipt storage.
        if self.pair_gateway is not None and stage in ('native_phase','realization_phase','commit_validation','provider_phase'):
            try:
                if not re.fullmatch('[0-9a-f]{32}',s.task_id) or not re.fullmatch('[0-9a-f]{32}',request_id):raise ValueError('Receipt identity')
                path=Path(self.pair_gateway.config['storage_root'])/'job-failures'/s.task_id/(request_id+'.json')
                if any(p.is_symlink() for p in (path,*path.parents)):raise ValueError('Linked private store')
                path.parent.mkdir(parents=True,exist_ok=True)
                raw=encode(row)
                if len(raw)>4096:raise ValueError('Failure receipt bound')
                with path.open('xb') as stream:
                    stream.write(raw);stream.flush();os.fsync(stream.fileno())
                saved=True
            except Exception:
                # Receipt failure is itself reported honestly, without its unsafe details.
                saved=False
        info={'status':'FAILED_CLOSED','request_id':request_id,'error_code':code,'stage':stage,
            'error':'RUN BOTH failed closed. No automatic retry.',
            'failure_receipt_saved':saved,'provider_calls':None if unknown else 0,
            'paid_outcome':'UNKNOWN' if unknown else 'NOT_DISPATCHED'}
        with self.lock:s.failure_info[request_id]=info
        return info

    def _execute_job(self,token,csrf,value,identity,s):
        context={'stage':'admission','committed':False,'wall_start':time.perf_counter(),'cpu_start':time.process_time(),
            'prior_native_hash':hashlib.sha256(encode(s.checkpoint)).hexdigest(),
            'prior_field_hash':hashlib.sha256(encode(s.field_checkpoint)).hexdigest()}
        try:self._run_sync(token,csrf,value,_job_id=value['request_id'])
        except Exception as error:
            info=s.failure_info.get(value['request_id'])
            if info is None:info=self._record_failure(s,value['request_id'],error,context)
            with self.lock:
                s.requests[value['request_id']]=(identity,deepcopy(info))
        finally:
            with self.lock:
                if s.queued_id==value['request_id']:s.queued_id=None

    def run(self,token,csrf,value):
        return self.submit(token,csrf,value) if self.asynchronous else self._run_sync(token,csrf,value)

    def new_session(self):
        with self.lock:
            now=self.clock()
            self.sessions={k:s for k,s in self.sessions.items() if s.expires>now or s.busy}
            if len(self.sessions)>=MAX_SESSIONS:raise LimitError('Anonymous session capacity reached; try later')
            token=secrets.token_hex(32);csrf=secrets.token_hex(32)
            self.sessions[token]=Session(csrf,now+SESSION_TTL,secrets.token_hex(16))
            if self.durable:self.durable.save(token,self.sessions[token],self.clock)
            return token,{'csrf_token':csrf,'expires_in_seconds':SESSION_TTL,'maximum_rounds':MAX_ROUNDS,
                **({'maximum_realization_cycles':4,'remaining_realization_cycles':4} if self.realization_root else {}),
                'provider_calls':0,'mode':'HOSTED_NATIVE_ONLY',
                'native_available':self.native_available,**self.execution_status()}

    def reset(self,token,csrf):
        with self.lock:
            s=self.session(token)
            if not isinstance(csrf,str) or not secrets.compare_digest(csrf,s.csrf):raise PermissionError('This session CSRF token is required')
            if s.busy or s.queued_id is not None:raise LimitError('A RUN BOTH job is still running; session cannot be reset')
            now=self.clock();times=[t for t in s.request_times if now-t<60]
            if len(times)>=8:raise LimitError('Session request rate exceeded')
            del self.sessions[token]
            fresh=secrets.token_hex(32);new=Session(secrets.token_hex(32),s.expires,secrets.token_hex(16),
                actions=s.actions,attempts=s.attempts,request_times=times+[now])
            self.sessions[fresh]=new
            if self.durable:
                # The retired cookie cannot regain its old task after restart.
                s.expires=now;self.durable.save(token,s,self.clock)
                self.durable.save(fresh,new,self.clock)
            return fresh,{'csrf_token':new.csrf,'expires_in_seconds':max(0,int(new.expires-now)),
                **({'maximum_realization_cycles':4,'remaining_realization_cycles':4} if self.realization_root else {}),
                'maximum_rounds':MAX_ROUNDS,'rounds':0,'session_actions':new.actions,'remaining_actions':MAX_ACTIONS-new.actions,
                'remaining_attempts':MAX_ATTEMPTS-new.attempts,
                'provider_calls':0,'mode':'HOSTED_NATIVE_ONLY',
                'native_available':self.native_available,**self.execution_status()}

    def session(self,token):
        # GET restoration is real proof work: serialize a cookie restore and
        # use the same bounded computation semaphore as RUN BOTH.
        with self.lock:return self._session_locked(token)

    def read_agent_realization_evidence(self,token):
        """Authenticated saved development projection; no work is submitted."""
        with self.lock:
            self.session(token)
            if self.agent_realization_evidence is None:
                raise UnavailableError('Agent realization development evidence is not configured')
            return deepcopy(self.agent_realization_evidence)

    def read_research_preparation_evidence(self,token):
        """Authenticated preparation only; no provider or execution port."""
        with self.lock:
            self.session(token)
            if self.research_preparation_evidence is None:
                raise UnavailableError('Research preparation is not configured')
            return deepcopy(self.research_preparation_evidence)

    def _session_locked(self,token):
        s=self.sessions.get(token)
        if s is None and self.durable and isinstance(token,str):
            s=self.durable.restore(token,self.clock)
            if s is not None:
                from .recursive_controller import restore
                if not self.workers.acquire(blocking=False):raise LimitError('Native worker capacity reached during state restoration')
                try:restored=restore(self.realization_root/'tasks'/s.task_id,self.bundle,self.manifest,self.digest,s.task_id)
                finally:self.workers.release()
                if restored is not None and (s.checkpoint!=restored['checkpoint'] or s.field_checkpoint!=restored['field_checkpoint'] or s.realization_state!=restored['state']):
                    raise ValueError('Restored session and verified recursive state differ')
                if restored is None and (s.realization_state is not None or s.checkpoint is not None):raise ValueError('Restored native session lacks verified realization companion')
                if s.typed_task_state is not None:
                    from .typed_answer_state import verify_retained
                    verify_retained(self.realization_root,s.task_id,s.typed_task_state,s.checkpoint)
                self.sessions[token]=s
                s.restored_from_disk=restored is not None
        if not s or s.expires<=self.clock():raise PermissionError('Session expired; start a new isolated session')
        return s

    def _run_sync(self,token,csrf,value,*,_job_id=None):
        job_start=time.perf_counter()
        context={'stage':'admission','committed':False,'wall_start':job_start,'cpu_start':time.process_time(),
            'prior_native_hash':None,'prior_field_hash':None}
        if not isinstance(value,dict) or set(value)!={'question','request_id'}:raise ValueError('Provide question and request_id only')
        question,request_id=value['question'],value['request_id']
        if not isinstance(question,str) or not question.strip() or len(question)>4000 or len(question.encode())>MAX_QUESTION:raise ValueError('Provide a nonempty question of at most 4000 characters and 4096 UTF-8 bytes')
        if not isinstance(request_id,str) or not re.fullmatch('[0-9a-f]{32}',request_id):raise ValueError('Invalid request_id')
        identity=hashlib.sha256(encode(value)).hexdigest()
        with self.lock:
            s=self.session(token)
            if not isinstance(csrf,str) or not secrets.compare_digest(csrf,s.csrf):raise PermissionError('This session CSRF token is required')
            if not self.native_available:raise UnavailableError('Native execution unavailable in this deployment; frozen results remain reviewable')
            if request_id in s.requests and request_id!=_job_id:
                old,output=s.requests[request_id]
                if old!=identity:raise ValueError('Request identity reused with different input')
                return deepcopy(output)
            if s.busy:raise LimitError('A native operation is already running for this session')
            if s.rounds>=MAX_ROUNDS or s.actions>=MAX_ACTIONS:raise LimitError('Session native allowance exhausted; start a new isolated session')
            if self.realization_root and (s.realization_state or {}).get('step',0)>=4:raise LimitError('Four private realization cycles exhausted; reset the isolated problem')
            if s.attempts>=MAX_ATTEMPTS:raise LimitError('Ten-minute computation attempt allowance exhausted; wait for session expiry')
            now=self.clock();s.request_times=[t for t in s.request_times if now-t<60]
            if len(s.request_times)>=8:raise LimitError('Session request rate exceeded')
            if not self.workers.acquire(blocking=False):raise LimitError('Native worker capacity reached; no queue or provider fallback')
            s.busy=True;s.request_times.append(now);s.attempts+=1
            before=deepcopy(s.checkpoint)
            context['prior_native_hash']=hashlib.sha256(encode(before)).hexdigest()
            context['prior_field_hash']=hashlib.sha256(encode(s.field_checkpoint)).hexdigest()
        try:
            # Persistence failure must still release the admitted worker.
            if self.durable:self.durable.save(token,s,self.clock)
            from .typed_native import prepare as prepare_typed,finalize as finalize_typed
            from .answer_contract import digest as typed_digest
            typed_prepared=None;typed_preparation_error=None
            try:
                prepared=prepare_typed(question,deepcopy(s.typed_task_state)) if self.executor is disposable_native else None
                if prepared is not None and prepared['task_type']!='unsupported':typed_prepared=prepared
                if typed_prepared and typed_prepared['task_type']=='business' and re.search(r'(?:original\s+and\s+corrected|Later a correction)',question,re.I):
                    typed_prepared=None;typed_preparation_error='MULTIVIEW_TYPED_CONTRACT_NOT_SUPPORTED_LEGACY_OUTPUT_PRESERVED'
            except ValueError as error:
                # A unsupported bounded intake cannot fabricate a typed answer.
                # Existing native routing still reports its own real boundary.
                typed_preparation_error=str(error).splitlines()[0][:80]
            native_question=(typed_prepared or {}).get('native_question') or question
            if typed_prepared and typed_prepared['task_type']=='graph':
                from .typed_controls import native_input
                native_question=native_input(typed_prepared)
            values=(self.bundle,self.manifest,self.digest,native_question,before,s.task_id,request_id)
            if self.executor is disposable_native:values=(*values,deepcopy(s.field_checkpoint))
            context['stage']='native_phase'
            typed_boundary=bool(typed_prepared and typed_prepared['public_facts'].get('boundary_status'))
            if typed_preparation_error=='BUSINESS_PUBLIC_SCALAR_AMBIGUITY':
                result={'checkpoint':before,'field_checkpoint':deepcopy(s.field_checkpoint),
                    'realization_state':deepcopy(s.realization_state),'operations':0,'attestation':{},
                    'public':{'answer':'BLOCKED: conflicting public business totals require clarification.',
                        'provider_calls':0,'native_receipt_count':0,'receipts':[],
                        'scope':'HOST intake ambiguity; no native effects or claimed mathematical infeasibility'}}
            elif typed_boundary:
                # A contradictory request is rejected before actual effects;
                # the previously verified native/typed state remains intact.
                result={'checkpoint':before,'field_checkpoint':deepcopy(s.field_checkpoint),
                    'realization_state':deepcopy(s.realization_state),'operations':0,'attestation':{},
                    'public':{'answer':typed_prepared['public_facts']['boundary_status'],
                        'provider_calls':0,'native_receipt_count':0,'receipts':[],
                        'scope':'HOST exact public-premise boundary; native state unchanged, no native operation claimed'}}
            elif self.realization_root is not None:
                from .recursive_controller import execute as execute_recursive
                def pre_effect_gate(operations):
                    with self.lock:
                        if self.clock()>=s.expires or s.actions+operations>MAX_ACTIONS:return False
                        return self.sessions.get(token) is s and s.busy
                context['stage']='realization_phase'
                result=execute_recursive(values,self.realization_root/'tasks'/s.task_id,
                    prior=deepcopy(s.realization_state),remaining_native=MAX_ACTIONS-s.actions,pre_effect_gate=pre_effect_gate)
            else:result=self.executor(values)
            typed_final=None;typed_receipt=None
            if typed_prepared is not None:
                att=result.get('attestation') or {};out=att.get('raw_execution_out');primary_cp=att.get('primary_native_checkpoint') or result['checkpoint']
                proof_ok=bool((result['public'].get('canonical') or {}).get('independent_checkpoint_replay'))
                verified_context={'verified':proof_ok,'checkpoint_sha256':typed_digest(primary_cp),
                    'raw_out_sha256':typed_digest(out),'native_question_sha256':typed_prepared['native_question_sha256'],
                    'bundle_manifest_sha256':att.get('bundle_manifest_sha256')}
                typed_final=finalize_typed(typed_prepared,result,task_id=s.task_id,cycle=s.rounds+1,
                    verified_context=verified_context if out is not None else None)
                if self.realization_root is not None:
                    from .typed_answer_state import append as append_typed
                    typed_receipt=append_typed(self.realization_root,s.task_id,request_id,typed_prepared,typed_final,
                        deepcopy(s.typed_task_state),native_checkpoint=result['checkpoint'])
                result['public']['typed_answer']=typed_final['envelope']
                result['public']['typed_answer']['intake']={'normalization':typed_prepared['normalization'],
                    'native_input_differs':native_question!=question,
                    'scope':'Explicit lossless equation/request adapter; graph assertions bind supplied inputs while reachability remains HOST computation'}
                if typed_receipt:result['public']['typed_answer']['delivery_receipt']={k:v for k,v in typed_receipt.items() if k not in ('state','relative_receipt')}
            elif typed_preparation_error:
                result['public']['typed_contract_status']={'status':'BLOCKED','reason':typed_preparation_error,
                    'scope':'No typed answer accepted; existing native output separately scoped'}
            context['stage']='commit_validation'
            with self.lock:
                if self.clock()>=s.expires:raise LimitError('Session expired during computation; result discarded')
                if s.actions+result['operations']>MAX_ACTIONS:raise LimitError('Native action allowance exceeded; prior state preserved')
                prepared=(result.get('attestation') or {}).get('prepared_pair')
                if prepared is not None:
                    prepared,pair_public=with_public_history(prepared,s.public_questions)
                    result['attestation']['prepared_pair']=prepared
                    result['public']['comparison']=pair_public
                prior_public_history=list(s.public_questions)
                attestation=result.get('attestation')
                field_checkpoint=result.get('field_checkpoint')
                if field_checkpoint is not None and self.pair_gateway is not None:
                    # Private append-only task field journal; never part of public source/evidence.
                    record=Path(self.pair_gateway.config['storage_root'])/'native-field'/s.task_id/(request_id+'.json')
                    if any(p.is_symlink() for p in (record,*record.parents)):raise ValueError('Linked field store refused')
                    record.parent.mkdir(parents=True,exist_ok=True)
                    raw=encode({'schema':'se6-v11-private-field-journal' if self.realization_root else 'se6-v8-private-field-journal','previous':s.field_checkpoint,'next':field_checkpoint,
                        'observation':((attestation or {}).get('canonical') or {}).get('field_candidate'),
                        'toroidal_realization':((attestation or {}).get('canonical') or {}).get('toroidal_realization'),
                        'relational_realization':((attestation or {}).get('canonical') or {}).get('field_realization'),
                        **({'recursive_scope':'Primary canonical snapshot; final field/native state independently bound in per-cycle native companions',
                            'recursive_private':(attestation or {}).get('recursive_private')} if self.realization_root else {})})
                    with record.open('xb') as stream:
                        stream.write(raw);stream.flush()
                        import os
                        os.fsync(stream.fileno())
                    attestation['field_journal']={'private_path':str(record),'sha256':hashlib.sha256(raw).hexdigest()}
                s.checkpoint=result['checkpoint'];s.rounds+=1;s.actions+=result['operations']
                s.public_questions.append(question);s.attestation=attestation
                s.field_checkpoint=deepcopy(field_checkpoint)
                if self.realization_root is not None:s.realization_state=deepcopy(result.get('realization_state'))
                if typed_final is not None and typed_final['envelope']['status']=='COMPLETE':s.typed_task_state=deepcopy(typed_final['next_state'])
                context['committed']=True
                output={**result['public'],'round':s.rounds,'maximum_rounds':MAX_ROUNDS,'session_actions':s.actions,
                    **({'maximum_realization_cycles':4,'remaining_realization_cycles':4-(s.realization_state or {}).get('step',0)} if self.realization_root else {}),
                    'remaining_attempts':MAX_ATTEMPTS-s.attempts}
            if self.pair_gateway is not None:
                context['stage']='provider_phase'
                pair=self.pair_gateway.run(task_id=s.task_id,request_id=request_id,question=question,
                    native_context=result['public']['answer'],native_public=result['public'],public_history=prior_public_history)
                output['comparison']=pair['public'];output['provider_calls']=pair['public']['provider_calls']
                if s.attestation is not None:s.attestation['matched_pair']=pair.get('attestation')
            output['job_wall_seconds']=time.perf_counter()-job_start
            with self.lock:
                s.requests[request_id]=(identity,deepcopy(output))
                if self.durable:
                    self.durable.save(token,s,self.clock,terminal=True)
            return output
        except Exception as error:
            info=self._record_failure(s,request_id,error,context)
            with self.lock:
                s.requests[request_id]=(identity,deepcopy(info))
                if self.durable:
                    try:self.durable.save(token,s,self.clock,terminal=True)
                    except Exception:pass  # The original failure stays authoritative.
            raise
        finally:
            with self.lock:s.busy=False
            self.workers.release()


def public_origin(value,*,loopback_development=False,port=None):
    parsed=urlsplit(value)
    if loopback_development:
        if parsed.scheme!='http' or parsed.hostname!='127.0.0.1' or parsed.port!=port or parsed.username or parsed.password or parsed.path not in ('','/') or parsed.query or parsed.fragment:
            raise ValueError('Development transport is exact HTTP127.0.0.1 and matching owned port only')
        return 'http://127.0.0.1:'+str(port),'127.0.0.1:'+str(port)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ('','/') or parsed.query or parsed.fragment:
        raise ValueError('Configure one exact public HTTPS origin without path/credentials')
    if parsed.port not in (None,443):raise ValueError('Hosted origin uses HTTPS port443')
    return 'https://'+parsed.netloc.lower().rstrip('/'),parsed.netloc.lower()


def make_server(service,origin,static_root,port=8080,*,loopback_development=False):
    origin,host=public_origin(origin,loopback_development=loopback_development,port=port);static_root=Path(static_root)
    cookie_name='se6_judge_session' if loopback_development else '__Host-se6_judge_session'
    assets={path:(static_root/name).read_bytes() for path,name in {'/':'index.html','/app.js':'app.js','/benchmark.js':'benchmark.js','/style.css':'style.css','/dynamic':'dynamic.html','/dynamic.js':'dynamic.js','/dynamic.css':'dynamic.css','/canonical':'canonical.html','/canonical.js':'canonical.js','/canonical.css':'canonical.css'}.items()}
    assets.update({'/demo/comparison/':assets['/'],'/demo/comparison/index.html':assets['/'],'/demo/comparison/app.js':assets['/app.js'],'/demo/comparison/style.css':assets['/style.css']})
    repair_asset=static_root/'repair-evidence.js'
    if repair_asset.is_file():assets['/repair-evidence.js']=repair_asset.read_bytes()
    for name in ('awareness.js','awareness.css','model-workflow.js','model-workflow.css','agent-realization.js','research-preparation.js'):
        path=static_root/name
        if path.is_file():assets['/'+name]=path.read_bytes()
    kinds={path:('text/html; charset=utf-8' if path in ('/','/dynamic','/canonical','/demo/comparison/','/demo/comparison/index.html') else 'text/javascript; charset=utf-8' if path.endswith('.js') else 'text/css; charset=utf-8') for path in assets}
    class Handler(BaseHTTPRequestHandler):
        protocol_version='HTTP/1.1'
        def setup(self):
            super().setup();self.connection.settimeout(5)
            self.deadline_timer=threading.Timer(25,self.close_stalled)
            self.deadline_timer.daemon=True;self.deadline_timer.start()
        def close_stalled(self):
            import socket
            try:self.connection.shutdown(socket.SHUT_RDWR)
            except (OSError,AttributeError):pass
        def finish(self):
            self.deadline_timer.cancel();super().finish()
        def handle_expect_100(self):
            self.respond(417,{'error':'Expect framing is unavailable'});return False
        def log_message(self,*args):pass
        def authorized_host(self):
            root_nav=self.command=='GET' and self.path in ('/','/dynamic','/canonical') and self.headers.get('Origin') is None and self.headers.get('Sec-Fetch-Mode')=='navigate' and self.headers.get('Sec-Fetch-Dest')=='document'
            return len(self.headers.get_all('Host',[]))==1 and len(self.headers.get_all('Origin',[]))<=1 and self.headers.get('Host')==host and self.headers.get('Origin') in (None,origin) and (self.headers.get('Sec-Fetch-Site')!='cross-site' or root_nav)
        def token(self):
            raw=self.headers.get('Cookie','')
            names=[piece.partition('=')[0].strip() for piece in raw.split(';') if '=' in piece]
            if names.count(cookie_name)>1 or len(self.headers.get_all('Cookie',[]))>1:
                raise PermissionError('Ambiguous session cookies rejected')
            cookie=SimpleCookie();cookie.load(raw)
            value=cookie.get(cookie_name);return value.value if value else None
        def respond(self,status,value,kind='application/json; charset=utf-8',cookie=None):
            raw=value if isinstance(value,bytes) else encode(value)
            self.send_response(status)
            headers={'Content-Type':kind,'Content-Length':str(len(raw)),'Connection':'close','Cache-Control':'no-store',
                'X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','Cross-Origin-Resource-Policy':'same-origin',
                'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'; form-action 'self'"}
            if cookie:headers['Set-Cookie']=cookie
            for key,val in headers.items():self.send_header(key,val)
            self.end_headers();self.close_connection=True
            try:self.wfile.write(raw)
            except OSError:pass
        def do_GET(self):
            # Public liveness only, usable by platform probes with an internal Host.
            # Never create a session, disclose source/state or invoke native work.
            if self.path=='/healthz':
                return self.respond(200,{'status':'ok','scope':'HOSTED_NATIVE_ONLY','provider_calls':0})
            if not self.authorized_host():return self.respond(403,{'error':'Exact configured judge origin required'})
            try:
                if self.path in assets:return self.respond(200,assets[self.path],kinds[self.path])
                if self.path=='/api/session':
                    with service.lock:
                        token=self.token()
                        try:s=service.session(token);data={'csrf_token':s.csrf,'expires_in_seconds':max(0,int(s.expires-service.clock())),
                            'maximum_rounds':MAX_ROUNDS,'provider_calls':0,'mode':'HOSTED_NATIVE_ONLY'}
                        except PermissionError:token,data=service.new_session()
                    data.update(service.execution_status())
                    data['native_available']=service.native_available
                    data['loopback_development']=loopback_development
                    data['rounds']=service.sessions[token].rounds
                    data['remaining_actions']=MAX_ACTIONS-service.sessions[token].actions
                    data['remaining_attempts']=MAX_ATTEMPTS-service.sessions[token].attempts
                    if service.realization_root:
                        data['maximum_realization_cycles']=4
                        data['remaining_realization_cycles']=4-(service.sessions[token].realization_state or {}).get('step',0)
                        data['state_restored_from_disk']=bool(getattr(service.sessions[token],'restored_from_disk',False))
                    return self.respond(200,data,cookie=f'{cookie_name}={token}; Path=/; HttpOnly; '+('' if loopback_development else 'Secure; ')+'SameSite=Strict')
                if self.path=='/api/model-workflow/evidence':
                    with service.lock:service.session(self.token())
                    if service.model_workflow_evidence is None:raise UnavailableError('Model workflow evidence is not configured')
                    return self.respond(200,deepcopy(service.model_workflow_evidence))
                if self.path=='/api/research-preparation/evidence':
                    return self.respond(200,service.read_research_preparation_evidence(self.token()))
                if self.path=='/api/agent-realization/evidence':
                    return self.respond(200,service.read_agent_realization_evidence(self.token()))
                if self.path=='/api/awareness/evidence':
                    with service.lock:service.session(self.token())
                    if service.awareness is None:raise UnavailableError('Awareness capability is not configured')
                    return self.respond(200,{'awareness':service.awareness.evidence(),
                        'model_integration':deepcopy(service.model_integration_evidence)})
                awareness_match=re.fullmatch('/api/awareness/(result|export)/([0-9a-f]{32})',self.path)
                if awareness_match:
                    with service.lock:service.session(self.token())
                    if service.awareness is None:raise UnavailableError('Awareness capability is not configured')
                    method=service.awareness.export if awareness_match[1]=='export' else service.awareness.get
                    record=method(self.token(),awareness_match[2])
                    return self.respond(202 if record.get('status')=='RUNNING' else 200,record)
                if self.path=='/api/dynamic':return self.respond(200,service.dynamic)
                if self.path=='/api/canonical':return self.respond(200,service.canonical)
                if self.path=='/api/review':return self.respond(200,service.review)
                if self.path=='/api/replays':return self.respond(200,service.replays)
                if self.path=='/api/benchmark':return self.respond(200,service.benchmark)
                match=re.fullmatch('/api/benchmark/result/([0-9a-f]{32})',self.path)
                if match:
                    with service.lock:s=service.session(self.token())
                    if service.benchmark_runner is None:return self.respond(503,{'error':'Native repeat is not configured'})
                    return self.respond(200,service.benchmark_runner.get(s.task_id,match[1]))
                match=re.fullmatch('/api/result/([0-9a-f]{32})',self.path)
                if match:
                    with service.lock:
                        s=service.session(self.token());saved=s.requests.get(match[1])
                        if not saved:return self.respond(404,{'error':'No committed result for that request; no automatic retry'})
                        return self.respond(202 if saved[1].get('status')=='RUNNING' else 200,deepcopy(saved[1]))
                return self.respond(404,{'error':'No such judge route'})
            except LimitError as error:return self.respond(429,{'error':str(error)})
            except PermissionError as error:return self.respond(403,{'error':str(error)})
            except Exception:return self.respond(503,{'error':'Judge service unavailable; execution status is not established'})
        def do_POST(self):
            if not self.authorized_host() or self.headers.get('Origin')!=origin:return self.respond(403,{'error':'Exact HTTPS origin required'})
            if self.path not in ('/api/run','/api/reset','/api/benchmark/run','/api/awareness/run'):return self.respond(404,{'error':'No campaign/provider/action route'})
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':return self.respond(415,{'error':'JSON required'})
            try:
                lengths=self.headers.get_all('Content-Length',[])
                if self.headers.get('Transfer-Encoding') or self.headers.get('Expect') or len(lengths)!=1 or not re.fullmatch('[0-9]{1,5}',lengths[0]) or not 0<int(lengths[0])<=MAX_BODY:
                    raise ValueError('Bounded unambiguous Content-Length required')
                remaining=int(lengths[0]);pieces=[];deadline=time.monotonic()+3
                while remaining:
                    available=deadline-time.monotonic()
                    if available<=0:raise ValueError('Body read deadline exceeded')
                    self.connection.settimeout(available)
                    part=self.rfile.read1(remaining)
                    if not part:break
                    pieces.append(part);remaining-=len(part)
                raw=b''.join(pieces)
                if len(raw)!=int(lengths[0]):raise ValueError('Incomplete request')
                def unique(pairs):
                    result={}
                    for key,value in pairs:
                        if key in result:raise ValueError('Duplicate JSON field')
                        result[key]=value
                    return result
                value=json.loads(raw,object_pairs_hook=unique,parse_constant=lambda value:(_ for _ in ()).throw(ValueError('Nonfinite JSON')))
                if self.path=='/api/awareness/run':
                    with service.lock:
                        token=self.token();s=service.session(token)
                        if not secrets.compare_digest(self.headers.get('X-Judge-CSRF',''),s.csrf):raise PermissionError('Session CSRF required')
                        if service.awareness is None:raise UnavailableError('Awareness capability is not configured')
                        if s.busy or s.queued_id is not None:raise LimitError('An existing Native job is active')
                        if s.expires-service.clock()<330:raise LimitError('Session needs a fresh isolated problem before this bounded workflow')
                        record=service.awareness.submit(token,value)
                    return self.respond(202 if record.get('status')=='RUNNING' else 200,record)
                if service.awareness is not None and service.awareness.active(self.token()):
                    raise LimitError('Configuration awareness is active; wait for its saved result')
                if self.path=='/api/benchmark/run':
                    with service.lock:
                        s=service.session(self.token())
                        if not secrets.compare_digest(self.headers.get('X-Judge-CSRF',''),s.csrf):raise PermissionError('Session CSRF required')
                        if service.benchmark_runner is None:raise UnavailableError('Offline native repeat unavailable')
                        if not isinstance(value,dict) or not isinstance(value.get('request_id'),str):raise ValueError('Repeat identity')
                        if value['request_id'] not in s.benchmark_jobs and len(s.benchmark_jobs)>=2:raise LimitError('Two offline repeats per isolated session')
                        result=service.benchmark_runner.submit(s.task_id,value);s.benchmark_jobs.add(value['request_id'])
                    return self.respond(202 if result.get('status')=='RUNNING' else 200,result)
                if self.path=='/api/reset':
                    if value!={}:raise ValueError('Session reset requires empty JSON object')
                    token,data=service.reset(self.token(),self.headers.get('X-Judge-CSRF',''))
                    return self.respond(200,data,cookie=f'{cookie_name}={token}; Path=/; HttpOnly; '+('' if loopback_development else 'Secure; ')+'SameSite=Strict')
                result=service.run(self.token(),self.headers.get('X-Judge-CSRF',''),value)
                return self.respond(202 if result.get('status')=='RUNNING' else 200,result)
            except PermissionError as error:return self.respond(403,{'error':str(error)})
            except UnavailableError as error:return self.respond(503,{'error':str(error)})
            except LimitError as error:return self.respond(429,{'error':str(error)})
            except (ValueError,TypeError,UnicodeError):return self.respond(400,{'error':'Question request rejected; no automatic retry'})
            except Exception:return self.respond(503,{'error':'Operation failed closed; no automatic retry'})
    class BoundedServer(ThreadingHTTPServer):
        daemon_threads=True;request_queue_size=8
        def __init__(self,*args):self.slots=threading.BoundedSemaphore(8);super().__init__(*args)
        def process_request(self,request,address):
            if not self.slots.acquire(blocking=False):self.shutdown_request(request);return
            try:super().process_request(request,address)
            except Exception:self.slots.release();raise
        def process_request_thread(self,request,address):
            try:super().process_request_thread(request,address)
            finally:self.slots.release()
    server=BoundedServer(('127.0.0.1' if loopback_development else '0.0.0.0',port),Handler)
    if loopback_development:
        origin='http://127.0.0.1:'+str(server.server_port);host='127.0.0.1:'+str(server.server_port)
    server.public_origin=origin
    return server
