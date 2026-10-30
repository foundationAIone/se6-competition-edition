"""Server-only one-pair guard, using existing Nebius wire parser/serializer.

Default BLOCKED. No CLI, credential reads, model calls or authority on import.
SIMULATED transport must explicitly declare SIMULATED=True and uses its own root.
"""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime,timezone
import hashlib,json,math,os,re,tempfile,time
from pathlib import Path
try:
    from .v8_scoring import PUBLIC_CONTRACT,public_output_shape,score_pair,rational,derived_question,unique_object
except ImportError:
    from v8_scoring import PUBLIC_CONTRACT,public_output_shape,score_pair,rational,derived_question,unique_object

from . import common_pair_contract as common
LEGACY_PROTOCOL='SE6_LEGACY_V8_ANSWER_V1'

MODEL='nvidia/nemotron-3-super-120b-a12b'
MAX_OUTPUT=2048;INPUT_CAP=49152;CONTEXT_CAP=262144
# Dated existing official-source provenance, not a current invoice guarantee.
TARIFF={'input_usd_per_million':'0.30','output_usd_per_million':'0.90','verified_date':'2026-10-11',
 'source':'https://nebius.com/services/token-factory/models/nvidia-nemotron-models-inference'}
SPENT={'mission-v11-dashboard-pair-v1','mission-v11-dashboard-pair-v2','mission-v11-heldout-pilot-v1','mission-successor-v2','mission-successor-v1','LINEAR_EVAL_V1','mission-first-scored-linear-v1','mission-first-linear-v1'}

class Blocked(ValueError):pass
class Pending(ValueError):
    def __init__(self,message,public_failure=None):
        super().__init__(message);self.public_failure=public_failure
def require(ok,reason):
    if not ok:raise Blocked(reason)
def encoded(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(v):return hashlib.sha256(encoded(v)).hexdigest()
def file_hash(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def utc():return datetime.now(timezone.utc)
def exclusive(p,v):
    with p.open('xb') as f:f.write(encoded(v));f.flush();os.fsync(f.fileno())
def atomic(p,v):
    fd,temporary=tempfile.mkstemp(dir=p.parent,prefix='.v8-')
    try:
        with os.fdopen(fd,'wb') as f:f.write(encoded(v));f.flush();os.fsync(f.fileno())
        os.replace(temporary,p)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)

def dependencies():
    from src.workbench.models import ModelSettings
    from src.workbench import provider_router,transport,provider_reasoning_control,response_policy
    model=ModelSettings(model=MODEL,temperature=0,max_output_tokens=MAX_OUTPUT,
        provider_reasoning_control=provider_reasoning_control.COMPLETE_PAIR)
    modules=[provider_router,transport,provider_reasoning_control,response_policy]
    pins={m.__name__:file_hash(Path(m.__file__)) for m in modules}
    pins['models']=file_hash(Path(__import__('src.workbench.models',fromlist=['ModelSettings']).__file__))
    pins['coordinator']=file_hash(Path(__file__))
    pins['scorer']=file_hash(Path(__file__).with_name('v8_scoring.py'))
    pins['common_contract']=file_hash(Path(__file__).with_name('common_pair_contract.py'))
    pins['common_scorer']=file_hash(Path(__file__).with_name('common_answer_scoring.py'))
    pins['context_gateway']=file_hash(Path(__file__).with_name('pair_gateway.py'))
    complete=Path(__file__).resolve().parents[1]/'COMPLETE_SOURCE_MANIFEST_PRIVATE.json'
    if complete.is_file():pins['complete_source_manifest']=file_hash(complete)
    return model,provider_router,pins

def prepare(question,native_context,public_history,own_histories,*,protocol=LEGACY_PROTOCOL):
    require(protocol in (LEGACY_PROTOCOL,common.PROTOCOL),'Unknown answer protocol')
    model,router,pins=dependencies()
    require(isinstance(question,str) and 0<len(question.encode())<=4096,'Question bound')
    require(isinstance(native_context,str) and len(native_context.encode())<=32768,'Sanitized native context bound')
    require(isinstance(public_history,list) and len(public_history)<=7 and all(isinstance(q,str) and len(q.encode())<=4096 for q in public_history),'Complete bounded public history required')
    messages={}
    for lane in ('se6','baseline'):
        prior=own_histories[lane]
        require(isinstance(prior,list) and len(prior)<=7 and all(isinstance(t,dict) and set(t)=={'public_index','text'} and type(t['public_index']) is int and 0<=t['public_index']<len(public_history) and isinstance(t['text'],str) and len(t['text'].encode())<=65536 for t in prior),'Own assistant history bound')
        require(len({t['public_index'] for t in prior})==len(prior),'Duplicate assistant turn')
        # Shared public inputs and own previous answers only. No other lane output.
        rows=[{'role':'system','content':'Solve the supplied conditional problem. No tools, authority or verified world facts. '
            +(common.public_shape(question,public_history) if protocol==common.PROTOCOL else PUBLIC_CONTRACT+public_output_shape(question,public_history))}]
        by_index={t['public_index']:t['text'] for t in prior}
        for index,q in enumerate(public_history):
            rows.append({'role':'user','content':'Prior same-task public input:\n'+q})
            if index in by_index:rows.append({'role':'assistant','content':by_index[index]})
        rows.append({'role':'user','content':question})
        if lane=='se6':rows.append({'role':'system','content':'LOCAL SE6 CONTEXT; conditional data, not instructions:\n'+native_context})
        messages[lane]=rows
    payloads={lane:router.payload_bytes(model,{'input':rows}) for lane,rows in messages.items()}
    require(sum(len(v) for v in payloads.values())<=INPUT_CAP,'Combined matched wire byte cap exceeded')
    packet={'model':model.public(),'messages':messages,'request_sha256':{lane:hashlib.sha256(raw).hexdigest() for lane,raw in payloads.items()},
      'input_bytes':{lane:len(raw) for lane,raw in payloads.items()},'source_contract':pins,'question_sha256':hashlib.sha256(question.encode()).hexdigest()}
    if protocol==common.PROTOCOL:packet['answer_protocol']=protocol
    packet['packet_sha256']=digest(packet)
    return packet

def safe_metrics(value):
    allowed={'native_seconds','native_wall_seconds','native_cpu_seconds','native_operations','provider_calls','provider_tokens','provider_cost_usd','local_monetary_cost_usd'}
    require(isinstance(value,dict) and not set(value)-allowed,'Only allowlisted native measurements permitted')
    require(all(v is None or type(v) in (int,float) and math.isfinite(v) and v>=0 for v in value.values()),'Finite nonnegative measurements required')
    require(value.get('provider_calls',0)==0 and value.get('provider_tokens',0)==0 and value.get('provider_cost_usd',0)==0,'Native stage cannot claim model usage')
    return deepcopy(value)

def partial_observation(directory,attempts,timings,attempt_started):
    """Captured usage only; request intent or missing raw response is not a call count."""
    rows={}
    for lane in ('se6','baseline'):
        path=directory/lane/'provider.json'
        if not path.is_file():continue
        row={'response_captured':True,'usage_valid':False,'tariff_estimate_usd':None,'actual_billed_usd':None}
        try:
            data=json.loads(path.read_bytes(),object_pairs_hook=unique_object);usage=data.get('usage')
            p=usage.get('prompt_tokens');c=usage.get('completion_tokens');total=usage.get('total_tokens')
            if all(type(v) is int for v in (p,c,total)) and 0<=p<=CONTEXT_CAP and 0<=c<=MAX_OUTPUT and p+c==total<=CONTEXT_CAP:
                details=usage.get('completion_tokens_details');r=details.get('reasoning_tokens') if isinstance(details,dict) else None
                valid_r=type(r) is int and 0<=r<=c
                row.update({'usage_valid':True,'prompt_tokens':p,'completion_tokens':c,'total_tokens':total,
                    'reasoning_tokens':r if valid_r else None,'non_reasoning_completion_tokens':c-r if valid_r else None,
                    'tariff_estimate_usd':float((p*rational(TARIFF['input_usd_per_million'])+c*rational(TARIFF['output_usd_per_million']))/1000000)})
            finish=data['choices'][0].get('finish_reason')
            row['finish_reason']=finish if finish in ('stop','length','tool_calls','content_filter') else 'UNKNOWN'
        except (ValueError,TypeError,KeyError,AttributeError,IndexError):pass
        if lane in timings:row['completed_transport_seconds']=timings[lane]['transport_seconds']
        rows[lane]=row
    return {'status':'INCOMPLETE_SPENT_NO_RETRY','dispatch_intents':attempts,'captured_provider_responses':len(rows),
        'actual_provider_calls':None,'reserved_calls':2,'lanes':rows,
        'last_attempt_window_seconds':time.perf_counter()-attempt_started if attempt_started is not None else None,
        'timing_scope':'Attempt window includes transport/parser/validation; no isolated network latency on exception.',
        'retry_allowed':False,'winner':None,'scope':'Raw response/usage observations only; no complete paired score or billing proof.'}

class RunBothCoordinator:
    def __init__(self,storage_root,*,approval_path=None,approval_sha256=None,live_enabled=False,
                 credential_probe=None,transport_factory=None,clock=utc,request_timeout_seconds=20,answer_protocol=LEGACY_PROTOCOL):
        require(answer_protocol in (LEGACY_PROTOCOL,common.PROTOCOL),'Unknown answer protocol')
        self.answer_protocol=answer_protocol
        self.simulated=transport_factory is not None and getattr(transport_factory,'SIMULATED',False) is True
        require(transport_factory is None or self.simulated,'Only explicitly SIMULATED injectable transports permitted')
        self.root=Path(storage_root).resolve()/('SIMULATED' if self.simulated else 'LIVE')
        self.approval_path=Path(approval_path).resolve() if approval_path else None
        self.approval_sha256=approval_sha256;self.live_enabled=live_enabled is True
        self.credential_probe=credential_probe;self.transport_factory=transport_factory;self.clock=clock
        require(type(request_timeout_seconds) in (int,float) and 0<request_timeout_seconds<=30,'Bounded transport timeout required')
        self.timeout=request_timeout_seconds

    def status(self):
        # No approval/key read. Configured status is not spendable authority.
        return {'mode':'SIMULATED' if self.simulated else 'LIVE','status':'SIMULATED_ONLY' if self.simulated else
                'BLOCKED' if not(self.live_enabled and self.approval_path and self.approval_sha256) else 'SERVER_ALLOWANCE_CONFIGURED_NOT_VERIFIED',
                'provider_calls':0,'maximum_calls_per_question':2,'retries':0,'credentials_consulted':False}

    def path(self,*parts):
        p=self.root.joinpath(*parts)
        require(p.resolve().is_relative_to(self.root),'Storage path escaped private root')
        require(not any(x.is_symlink() for x in [p,*p.parents] if x!=self.root.parent),'Linked claim/cache paths refused')
        return p

    @contextmanager
    def lock(self,task):
        p=self.path('locks',task+'.lock');p.parent.mkdir(parents=True,exist_ok=True)
        try:fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        except FileExistsError:raise Pending('Task job active or interrupted; no retry/lock stealing')
        owned=os.fstat(fd)
        try:yield
        finally:
            os.close(fd)
            if p.exists() and p.stat().st_ino==owned.st_ino:p.unlink()

    def allowance(self,packet):
        if self.simulated:return None
        require(self.live_enabled and self.approval_path and self.approval_sha256,'Live allowance absent; no credential lookup')
        require(file_hash(self.approval_path)==self.approval_sha256,'Pinned private allowance changed')
        value=read(self.approval_path)
        expected={'schema','permit_id','campaign_id','approved','purpose','expires_at_utc','allowed_question_hashes','packet_sha256','model_settings','source_contract','claim_store_sha256','max_pairs','max_calls','max_output_tokens','max_input_bytes','usd_cap','tariff'}
        require(set(value)==expected and value['schema']=='se6-v8-one-pair-allowance-v1','Exact new one-pair allowance required')
        require(value['approved'] is True and value['purpose']=='ONE_MATCHED_NEMOTRON_PAIR' and value['campaign_id'] not in SPENT,'New explicit approval required; prior campaigns exhausted')
        require(isinstance(value['campaign_id'],str) and re.fullmatch('[a-z0-9][a-z0-9-]{0,63}',value['campaign_id']) is not None,'Named fresh campaign required')
        require(re.fullmatch('[0-9a-f]{32}',value['permit_id']) is not None,'Permit identity required')
        require(value['allowed_question_hashes']==[packet['question_sha256']] and value['packet_sha256']==packet['packet_sha256'],'Exact approved question and private wire packet required')
        require(value['source_contract']==packet['source_contract'] and value['model_settings']==packet['model'],'Approved source/settings mismatch')
        require(value['claim_store_sha256']==self.store_identity(),'Allowance is bound to a different persistent claim store')
        require(value['max_pairs']==1 and type(value['max_pairs']) is int and value['max_calls']==2 and type(value['max_calls']) is int and value['max_output_tokens']==MAX_OUTPUT and value['max_input_bytes']==INPUT_CAP,'Exact caps required')
        now=self.clock();require(now.tzinfo is not None,'Server UTC clock required');now=now.astimezone(timezone.utc)
        expires=datetime.fromisoformat(value['expires_at_utc']);require(expires.tzinfo is not None and now<expires,'Allowance expired')
        tariff=value['tariff']
        if self.answer_protocol==common.PROTOCOL:
            require(type(tariff) is dict and set(tariff)==set(TARIFF) and all(tariff[k]==TARIFF[k] for k in TARIFF if k!='verified_date') and tariff['verified_date']==now.date().isoformat(),'Exact approved current-day published tariff required')
        else:
            require(tariff==TARIFF and TARIFF['verified_date']==now.date().isoformat(),'Pricing provenance stale; reverify before any live readiness')
        bound=(2*CONTEXT_CAP*rational(tariff['input_usd_per_million'])+2*MAX_OUTPUT*rational(tariff['output_usd_per_million']))/1000000
        require(bound<=rational(value['usd_cap'])<=rational('0.20'),'Conservative two-call tariff bound exceeds approval')
        return value

    def store_identity(self):
        # Private pinned approval binds the stable resolved claim directory, so
        # copying the permit into a new output/store cannot reset paid reservations.
        path=str(self.root)
        if os.name=='nt':path=os.path.normcase(path)
        return hashlib.sha256(path.encode()).hexdigest()

    def run(self,task_id,request_id,question,native_context,native_metrics,public_history,lane_histories=None):
        require(all(isinstance(v,str) and re.fullmatch('[0-9a-f]{32}',v) for v in (task_id,request_id)),'Server task/request identities required')
        # Block before importing provider dependencies, credential lookup or writes.
        if not self.simulated:require(self.live_enabled and self.approval_path and self.approval_sha256,'Live run blocked before credential lookup')
        native_metrics=safe_metrics(native_metrics)
        self.root.mkdir(parents=True,exist_ok=True)
        fingerprint=digest({'task':task_id,'request':request_id,'question':question,'native_context':native_context,'public_history':public_history})
        directory=self.path('requests',task_id,request_id)
        with self.lock(task_id):
            if (directory/'reservation.json').exists():
                require(read(directory/'reservation.json')['fingerprint']==fingerprint,'Request id reused for different public problem')
                if not(directory/'summary.json').exists() or not(directory/'final-manifest.json').exists():raise Pending('Reserved job uncertain/incomplete; allowance never refunded or retried')
                result=self.replay(directory)
                self.restore_history(task_id,read(directory/'next-history.json'))
                return result
            history_path=self.path('histories',task_id+'.json');history_path.parent.mkdir(parents=True,exist_ok=True)
            state=read(history_path) if history_path.exists() else {'public_history':[],'lanes':{'se6':[],'baseline':[]}}
            require(public_history[:len(state['public_history'])]==state['public_history'],'Public history lineage differs')
            require(lane_histories is None or lane_histories==state['lanes'],'Caller cannot inject assistant histories')
            packet=prepare(question,native_context,public_history,state['lanes'],protocol=self.answer_protocol);permit=self.allowance(packet)
            # Known exhausted claims fail before credential lookup. Atomic claims
            # below still prevent races between independently submitted tasks.
            require(not self.path('spent-questions',packet['question_sha256']+'.json').exists(),'Question already claimed globally; no dispatch')
            if permit:
                require(not self.path('spent-permits',permit['permit_id']+'.json').exists(),'Allowance already spent; no dispatch')
            tariff=permit['tariff'] if permit else TARIFF
            try:scoring_question=common.derive_public_spec(question,public_history) if self.answer_protocol==common.PROTOCOL else derived_question(question,public_history)
            except (ValueError,TypeError,KeyError,ZeroDivisionError):scoring_question=None
            model,router,pins=dependencies()
            if not self.simulated:
                try:available=(self.credential_probe or router.credential_status)(model) is True
                except Exception:raise Blocked('Credential unavailable; no paid claim or call') from None
                require(available,'Credential unavailable; no paid claim or call')
            directory.mkdir(parents=True,exist_ok=False)
            # Both calls are reserved before dispatch. Partial/uncertain work is spent.
            reservation={'fingerprint':fingerprint,'mode':'SIMULATED' if self.simulated else 'LIVE','reserved_calls':2,'request_id':request_id}
            exclusive(directory/'reservation.json',reservation)
            spent=self.path('spent-questions',packet['question_sha256']+'.json');spent.parent.mkdir(parents=True,exist_ok=True)
            try:exclusive(spent,{'reserved':2,'fingerprint':fingerprint})
            except FileExistsError:raise Blocked('Question already claimed globally; no dispatch')
            if permit:
                claim=self.path('spent-permits',permit['permit_id']+'.json');claim.parent.mkdir(parents=True,exist_ok=True)
                try:exclusive(claim,{'reserved':2,'fingerprint':fingerprint})
                except FileExistsError:raise Blocked('Allowance already spent; no dispatch')
                allowance_raw=self.approval_path.read_bytes()
                require(hashlib.sha256(allowance_raw).hexdigest()==self.approval_sha256,'Allowance changed after reservation')
                with (directory/'private-allowance.json').open('xb') as f:f.write(allowance_raw)
            exclusive(directory/'prepared.json',packet);exclusive(directory/'public-question.json',{'question':question});exclusive(directory/'native-metrics.json',native_metrics)
            exclusive(directory/'preparation-input.json',{'native_context':native_context,'public_history':public_history,'own_histories':state['lanes'],**({'answer_protocol':self.answer_protocol} if self.answer_protocol==common.PROTOCOL else {})})
            exclusive(directory/'public-derived-truth.json',{'scoring_question':scoring_question,'public_history':public_history,'scope':'Derived public facts only; never sent to provider as hidden truth'})
            captures={};timings={};attempts=0;start=time.perf_counter();attempt_started=None
            try:
                for lane in ('se6','baseline'):
                    require(time.perf_counter()-start<65,'Pair deadline expired; no further request')
                    if permit:self.allowance(packet)
                    raw=directory/lane;raw.mkdir()
                    factory=self.transport_factory or router.NebiusTransport
                    attempts+=1;exclusive(directory/f'attempt-{attempts}.json',{'lane':lane,'attempt':attempts,'reserved_calls_remaining':2-attempts})
                    tick=time.perf_counter();attempt_started=tick
                    transport=factory(model)
                    if self.simulated:transport.answer_protocol=self.answer_protocol
                    result=transport.request({'input':packet['messages'][lane]},raw,self.timeout);elapsed=time.perf_counter()-tick
                    # Verify retained exact wire and raw parsed response, not callback flags.
                    require((raw/'request.json').read_bytes()==router.payload_bytes(model,{'input':packet['messages'][lane]}),'Wire differs from reservation')
                    provider_raw=(raw/'provider.json').read_bytes();require(len(provider_raw)<=4194304,'Provider response size bound')
                    json.loads(provider_raw,object_pairs_hook=unique_object)
                    parsed=router.parse_nebius_completion(provider_raw,MODEL,provider_reasoning_control=model.provider_reasoning_control)
                    require(time.perf_counter()-start<=65,'Absolute pair allowance elapsed; no score or further request')
                    require(parsed==result and (raw/'returned-text.txt').read_bytes()==parsed['text'].encode(),'Raw provider capture differs')
                    usage=parsed['usage'];require(isinstance(usage,dict),'Missing usage; stop remaining call')
                    p=usage.get('prompt_tokens');c=usage.get('completion_tokens');total=usage.get('total_tokens')
                    require(type(p) is int and type(c) is int and type(total) is int and 0<=p<=CONTEXT_CAP and 0<=c<=MAX_OUTPUT and total==p+c and total<=CONTEXT_CAP,'Usage/model contract anomaly; stop remaining call')
                    account=parsed['completion_accounting']
                    if self.answer_protocol==common.PROTOCOL:
                        require(type(account.get('reasoning_tokens')) is int and account['reasoning_tokens']==0,'Current NONE contract requires explicitly reported zero reasoning tokens; stop remaining call')
                    captures[lane]=parsed;timings[lane]={'origin':'SIMULATED' if self.simulated else 'NEBIUS_TRANSPORT_CAPTURE','transport_seconds':elapsed,'prompt_tokens':p,'completion_tokens':c,'total_tokens':total,
                        'reasoning_tokens':account['reasoning_tokens'],'non_reasoning_completion_tokens':account['reported_non_reasoning_completion_tokens'],
                        'tariff_estimate_usd':float((p*rational(tariff['input_usd_per_million'])+c*rational(tariff['output_usd_per_million']))/1000000),'actual_billed_usd':None}
                require(dependencies()[2]==pins,'Loaded source observation changed; no score')
                exclusive(directory/'captures.json',captures);exclusive(directory/'measurements.json',timings)
                manifest={p.relative_to(directory).as_posix():file_hash(p) for p in directory.rglob('*') if p.is_file()}
                exclusive(directory/'freeze.json',manifest) # Both lanes frozen before truth/scorer intake.
                score=common.score_pair(scoring_question,captures,self.simulated) if self.answer_protocol==common.PROTOCOL else score_pair(scoring_question or 'UNSUPPORTED_PUBLIC_TRUTH',captures,self.simulated)
                summary={'status':'SIMULATED_FROZEN' if self.simulated else 'LIVE_FROZEN','origin':'SIMULATED' if self.simulated else 'NEBIUS_TRANSPORT_CAPTURE',
                    'provider_calls':0 if self.simulated else attempts,'simulated_calls':attempts if self.simulated else 0,
                    'lanes':{lane:{'response':captures[lane]['text'],'assessment':score['lanes'][lane]} for lane in captures},
                    'arithmetic_winner':score['arithmetic_winner'],**({'answer_protocol':self.answer_protocol,'common_user_answer_winner':score['common_user_answer_winner']} if self.answer_protocol==common.PROTOCOL else {}),'overall_winner':None,'native_metrics':native_metrics,
                    'measurements':timings,'tariff_estimate_usd':0 if self.simulated else sum(v['tariff_estimate_usd'] for v in timings.values()),
                    'simulated_tariff_estimate_usd':sum(v['tariff_estimate_usd'] for v in timings.values()) if self.simulated else 0,'actual_billed_usd':None,
                    'scope':'SIMULATED fixture answers; not model evidence or a live win' if self.simulated else score['scope']}
                exclusive(directory/'summary.json',summary)
                state={'public_history':public_history+[question],'lanes':{lane:state['lanes'][lane]+[{'public_index':len(public_history),'text':captures[lane]['text']}] for lane in ('se6','baseline')}}
                exclusive(directory/'next-history.json',state)
                exclusive(directory/'final-manifest.json',{p.relative_to(directory).as_posix():file_hash(p) for p in directory.rglob('*') if p.is_file()})
                atomic(history_path,state)
                return {'public':summary,'attestation':{'archive':str(directory),'freeze_sha256':file_hash(directory/'freeze.json'),'packet_sha256':packet['packet_sha256']}}
            except Exception as error:
                exclusive(directory/'failure.json',{'status':'UNKNOWN_OR_INCOMPLETE_SPENT','error_type':type(error).__name__,'attempts':attempts,'reserved_calls':2,'retry_allowed':False})
                observed=partial_observation(directory,attempts,timings,attempt_started)
                observed['mode']='SIMULATED_TEST' if self.simulated else 'LIVE_CAPTURE_OBSERVATION'
                exclusive(directory/'failure-observation.json',observed)
                raise Pending('Pair incomplete or uncertain; private capture retained, no retry or winner',observed) from None

    def restore_history(self,task_id,next_state):
        path=self.path('histories',task_id+'.json');path.parent.mkdir(parents=True,exist_ok=True)
        current=read(path) if path.exists() else {'public_history':[],'lanes':{'se6':[],'baseline':[]}}
        if len(current['public_history'])<len(next_state['public_history']):
            require(next_state['public_history'][:len(current['public_history'])]==current['public_history'],'Cached history lineage differs')
            atomic(path,next_state)
        else:require(current['public_history'][:len(next_state['public_history'])]==next_state['public_history'],'Cached history fork refused')

    def replay(self,directory):
        final=read(directory/'final-manifest.json')
        actual={p.relative_to(directory).as_posix() for p in directory.rglob('*') if p.is_file()}-{'final-manifest.json'}
        require(set(final)==actual and all(file_hash(directory/name)==wanted for name,wanted in final.items()),'Final cached archive changed')
        manifest=read(directory/'freeze.json')
        require(all(file_hash(directory/name)==wanted for name,wanted in manifest.items()),'Frozen pair changed')
        summary=read(directory/'summary.json');packet=read(directory/'prepared.json');question=read(directory/'public-question.json')['question']
        inputs=read(directory/'preparation-input.json')
        require(packet==prepare(question,inputs['native_context'],inputs['public_history'],inputs['own_histories'],protocol=self.answer_protocol),'Replayed lane messages/isolation differ')
        if not self.simulated:
            require(self.approval_sha256 and file_hash(directory/'private-allowance.json')==self.approval_sha256,'Original pinned allowance archive differs')
            approved=read(directory/'private-allowance.json')
            require(approved['packet_sha256']==packet['packet_sha256'] and approved['claim_store_sha256']==self.store_identity(),'Archived allowance packet/store binding differs')
        require(packet['source_contract']==dependencies()[2],'Replay requires exact same reviewed source')
        model,router,pins=dependencies();captures={}
        for lane in ('se6','baseline'):
            raw=directory/lane
            require((raw/'request.json').read_bytes()==router.payload_bytes(model,{'input':packet['messages'][lane]}),'Frozen wire changed')
            provider_raw=(raw/'provider.json').read_bytes();require(len(provider_raw)<=4194304,'Frozen provider size bound')
            json.loads(provider_raw,object_pairs_hook=unique_object)
            captures[lane]=router.parse_nebius_completion(provider_raw,MODEL,provider_reasoning_control=model.provider_reasoning_control)
            if self.answer_protocol==common.PROTOCOL:
                account=captures[lane]['completion_accounting']
                require(type(account.get('reasoning_tokens')) is int and account['reasoning_tokens']==0,'Frozen current NONE reasoning accounting unverifiable')
        truth=read(directory/'public-derived-truth.json')
        tariff=TARIFF if self.simulated else approved['tariff']
        try:recomputed=common.derive_public_spec(question,truth['public_history']) if self.answer_protocol==common.PROTOCOL else derived_question(question,truth['public_history'])
        except (ValueError,TypeError,KeyError,ZeroDivisionError):recomputed=None
        require(recomputed==truth['scoring_question'],'Derived public truth changed')
        score=common.score_pair(recomputed,captures,self.simulated) if self.answer_protocol==common.PROTOCOL else score_pair(recomputed or 'UNSUPPORTED_PUBLIC_TRUTH',captures,self.simulated)
        require(summary['origin']==('SIMULATED' if self.simulated else 'NEBIUS_TRANSPORT_CAPTURE') and summary['status']==('SIMULATED_FROZEN' if self.simulated else 'LIVE_FROZEN'),'Cached origin mismatch')
        require(summary['provider_calls']==(0 if self.simulated else 2) and summary['simulated_calls']==(2 if self.simulated else 0) and summary['overall_winner'] is None,'Cached call/scoring scope differs')
        require(summary['native_metrics']==safe_metrics(read(directory/'native-metrics.json')),'Cached native measurements differ')
        require(summary['measurements']==read(directory/'measurements.json'),'Cached latency/cost differs')
        for lane,result in captures.items():
            usage=result['usage'];v=summary['measurements'][lane]
            require(v['prompt_tokens']==usage['prompt_tokens'] and v['completion_tokens']==usage['completion_tokens'] and v['total_tokens']==usage['total_tokens'],'Cached usage differs')
            account=result['completion_accounting']
            require(v['reasoning_tokens']==account['reasoning_tokens'] and v['non_reasoning_completion_tokens']==account['reported_non_reasoning_completion_tokens'],'Cached reasoning/final usage differs')
            cost=float((usage['prompt_tokens']*rational(tariff['input_usd_per_million'])+usage['completion_tokens']*rational(tariff['output_usd_per_million']))/1000000)
            require(v['tariff_estimate_usd']==cost and v['actual_billed_usd'] is None and type(v['transport_seconds']) in (float,int) and math.isfinite(v['transport_seconds']) and v['transport_seconds']>=0,'Cached tariff/latency scope differs')
        expected_next={'public_history':inputs['public_history']+[question],'lanes':{lane:inputs['own_histories'][lane]+[{'public_index':len(inputs['public_history']),'text':captures[lane]['text']}] for lane in ('se6','baseline')}}
        require(read(directory/'next-history.json')==expected_next,'Cached next history differs from own captures')
        if self.answer_protocol==common.PROTOCOL:require(summary['answer_protocol']==common.PROTOCOL and summary['common_user_answer_winner']==score['common_user_answer_winner'],'Cached common protocol/score differs')
        require(summary['arithmetic_winner']==score['arithmetic_winner'] and all(summary['lanes'][lane]['assessment']==score['lanes'][lane] and summary['lanes'][lane]['response']==captures[lane]['text'] for lane in captures),'Cached independent score changed')
        return {'public':summary,'attestation':{'archive':str(directory),'freeze_sha256':file_hash(directory/'freeze.json'),'packet_sha256':packet['packet_sha256']}}
