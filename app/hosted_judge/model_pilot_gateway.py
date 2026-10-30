"""One source-bound model-workflow pilot; no spending or credentials on prepare.

Reuses the existing provider wire/parser and durable exclusive claim operations.
A prepared specification is not approval. Only the coordinator may install an
exact pinned owner decision after the human approves the declared batch.
"""
from pathlib import Path
from datetime import datetime,timezone
from decimal import Decimal
import hashlib,json,re,sys,time
from .v8_run_both import RunBothCoordinator,Blocked,require,encoded,digest,file_hash,read,exclusive,atomic

APP=Path(__file__).resolve().parents[1]
MODEL='nvidia/nemotron-3-super-120b-a12b'
ENDPOINT='https://api.tokenfactory.nebius.com/v1/chat/completions'
MAX_CALLS=36;MAX_OUTPUT=2048;MAX_WIRE_BYTES=24576;CONTEXT_UPPER=262144
PER_CALL_RESERVE=(Decimal(CONTEXT_UPPER)*Decimal('.30')+Decimal(MAX_OUTPUT)*Decimal('.90'))/Decimal(1000000)
TOTAL_RESERVE=PER_CALL_RESERVE*MAX_CALLS

def verified_usage(usage):
    require(isinstance(usage,dict) and all(type(usage.get(k)) is int and usage[k]>=0 for k in ('prompt_tokens','completion_tokens','total_tokens')),'Provider usage missing or invalid; stop without retry')
    require(usage['prompt_tokens']<=CONTEXT_UPPER and usage['completion_tokens']<=MAX_OUTPUT
            and usage['total_tokens']==usage['prompt_tokens']+usage['completion_tokens'],'Provider token bound or sum violated; stop without retry')
    return usage

class PilotGateway(RunBothCoordinator):
    def __init__(self,root,*,spec_path,spec_sha256,approval_path=None,approval_sha256=None,
                 live_enabled=False,transport_factory=None):
        super().__init__(root,approval_path=approval_path,approval_sha256=approval_sha256,
                         live_enabled=live_enabled,transport_factory=transport_factory,request_timeout_seconds=30)
        self.spec_path=Path(spec_path).resolve();self.spec_sha256=spec_sha256
        self._model_parts=None

    def specification(self):
        require(self.spec_path.is_file() and not self.spec_path.is_symlink() and file_hash(self.spec_path)==self.spec_sha256,'Frozen pilot specification changed')
        spec=read(self.spec_path)
        require(spec.get('schema')=='se6-model-workflow-batch-v1','Pilot specification schema')
        for key,expected in {'model':MODEL,'endpoint':ENDPOINT,'max_requests':MAX_CALLS,
              'max_output_tokens':MAX_OUTPUT,'max_wire_input_bytes':MAX_WIRE_BYTES,
              'model_context_token_upper_bound':CONTEXT_UPPER,'max_tool_turns_per_stage':3,
              'max_effects_per_stage':1,'usd_cap':'3.00'}.items():
            require(spec.get(key)==expected,'Frozen pilot cap mismatch: '+key)
        require(spec.get('tariff')=={'input_usd_per_million':'0.30','output_usd_per_million':'0.90'},'Pilot tariff mismatch')
        require(type(spec.get('allowed_projects')) is list and len(spec['allowed_projects'])==3 and len(set(spec['allowed_projects']))==3,'Exactly three projects required')
        require(spec.get('claim_store_sha256')==self.store_identity(),'Specification belongs to another durable claim store')
        require(TOTAL_RESERVE<=Decimal(spec['usd_cap']),'Whole context conservative reservation exceeds cap')
        return spec

    def _check_sources(self,spec):
        manifest=APP/'COMPLETE_SOURCE_MANIFEST_PRIVATE.json'
        require(file_hash(manifest)==spec['source_manifest_sha256'],'Pilot complete-source binding changed')
        files=read(manifest)['files']
        require('hosted_judge/model_pilot_gateway.py' in files,'Pilot gateway absent from frozen source')
        actual={p.relative_to(APP).as_posix() for p in APP.rglob('*') if p.is_file()}
        require(actual==set(files)|{manifest.name},'Pilot source inventory changed')
        for name,pin in files.items():
            path=APP/name
            require(not path.is_symlink() and path.resolve().is_relative_to(APP) and file_hash(path)==pin,'Pilot source member changed')

    def _parts(self):
        if self._model_parts is None:
            from .native_adapter import validate_bundle
            bundle=APP/'private-native';manifest=APP/'native-manifest.json'
            validate_bundle(bundle,manifest,file_hash(manifest));sys.path.insert(0,str(bundle))
            from src.workbench.runtime_revision import freeze_sources
            revision=freeze_sources(bundle)
            from .v8_run_both import dependencies
            model,router,pins=dependencies()
            require(router.NEBIUS_ENDPOINT==ENDPOINT,'Existing endpoint mismatch')
            self._model_parts=(model,router,pins,revision)
        return self._model_parts

    def prepare(self,request):
        spec=self.specification()
        require(type(request) is dict and set(request)=={'request_id','messages','project_id','stage','arm','turn'},'Pilot request fields')
        require(re.fullmatch('[0-9a-f]{32}',request['request_id'] or '') is not None,'Pilot request identity')
        require(request['project_id'] in spec['allowed_projects'] and type(request['stage']) is int and request['stage'] in (1,2)
                and request['arm'] in ('conventional','se6') and type(request['turn']) is int and 1<=request['turn']<=3,'Pilot cell bounds')
        messages=request['messages']
        require(type(messages) is list and 1<=len(messages)<=24 and all(type(r) is dict and set(r)=={'role','content'} and r['role'] in ('system','user','assistant') and type(r['content']) is str for r in messages),'Pilot message schema')
        model,router,pins,revision=self._parts()
        wire=router.payload_bytes(model,{'input':messages})
        require(len(wire)<=MAX_WIRE_BYTES,'Pilot wire-input capacity exceeded')
        require(revision.public()['disk_matches_loaded'],'Provider implementation changed')
        return {'request':request,'request_sha256':hashlib.sha256(wire).hexdigest(),
                'request_id':request['request_id'],'request_metadata':{'spec_sha256':self.spec_sha256,
                'source_contract':pins,'wire_bytes':len(wire),'max_output_tokens':MAX_OUTPUT,
                'input_billing_token_upper_bound':CONTEXT_UPPER,'reserve_usd':str(PER_CALL_RESERVE),
                'provider_calls':0,'status':'PREPARED_NOT_AUTHORIZED'}}

    def _approval(self,permit):
        require(self.live_enabled or self.simulated,'MODEL_COMPARISON: BLOCKED_PENDING_EXACT_BUDGET')
        require(self.approval_path and self.approval_sha256,'Exact pinned owner decision is missing')
        require(permit is None or isinstance(permit,(str,Path)) and Path(permit).resolve()==self.approval_path,'Caller approval object is not authority')
        require(not self.approval_path.is_symlink() and file_hash(self.approval_path)==self.approval_sha256,'Owner decision changed')
        value=read(self.approval_path)
        expected={'schema','permit_id','owner_identifier','decision','approved','spec_sha256','claim_store_sha256','expires_at_utc','max_requests','usd_cap','authorization_provenance'}
        require(set(value)==expected and value['schema']=='se6-model-workflow-owner-decision-v1','Purpose-specific owner decision required')
        require(value['owner_identifier']=='programmerONE' and value['decision']=='APPROVE_ONE_PAIRED_MODEL_WORKFLOW_PILOT' and value['approved'] is True,'Exact owner pilot approval required')
        require(re.fullmatch('[0-9a-f]{32}',value['permit_id'] or '') and value['spec_sha256']==self.spec_sha256 and value['claim_store_sha256']==self.store_identity(),'Approval source/store mismatch')
        require(value['max_requests']==MAX_CALLS and value['usd_cap']=='3.00' and type(value['authorization_provenance']) is dict and value['authorization_provenance'].get('kind')==('SIMULATED_TEST_ONLY' if self.simulated else 'EXPLICIT_HUMAN_DECISION_IN_CURRENT_CODEX_SESSION'),'Approval provenance/caps mismatch')
        expires=datetime.fromisoformat(value['expires_at_utc']);require(expires.tzinfo is not None and datetime.now(timezone.utc)<expires,'Owner decision expired')
        return value

    def require_admission(self,permit=None):
        self.specification();value=self._approval(permit)
        self._check_sources(self.specification())
        return {'status':'SIMULATED_TEST_ONLY' if self.simulated else 'EXACT_OWNER_PILOT_ADMITTED',
                'permit_id':value['permit_id'],'spec_sha256':self.spec_sha256,'max_effects':12,
                'scope':'DISPOSABLE_SOURCE_BOUND_DEVELOPMENT_ONLY_NOT_PRODUCTION_OR_NETWORK_AUTHORITY'}

    def invoke(self,prepared,permit=None):
        # No credential lookup, claims or provider operation before these guards.
        spec=self.specification();approval=self._approval(permit);self._check_sources(spec)
        require(prepared==self.prepare(prepared.get('request')),'Prepared request binding changed')
        model,router,pins,revision=self._parts()
        require(self.simulated or router.credential_status(model),'NEBIUS_CREDENTIAL_MISSING_NO_CALL')
        self.root.mkdir(parents=True,exist_ok=True)
        with self.lock('whole-model-workflow-pilot'):
            require(not self.path('STOP.json').exists(),'Prior provider outcome uncertain; no continuation or retry')
            for intent in self.root.glob('calls/*/intent.json'):
                require((intent.parent/'outcome.json').is_file(),'Unresolved provider intent; no automatic continuation')
                old=read(intent.parent/'outcome.json');expected_status='SIMULATED_TEST_ONLY' if self.simulated else 'PROVIDER_RETURNED_UNVERIFIED'
                require(old.get('status')==expected_status and old.get('request_sha256')==read(intent)['request_sha256'],'Prior provider outcome failed, corrupt or uncertain; no continuation')
            batch=self.path('batch-claim.json')
            if not batch.exists():
                spent=self.path('spent-permits',approval['permit_id']+'.json');spent.parent.mkdir(parents=True,exist_ok=True)
                exclusive(spent,{'spec_sha256':self.spec_sha256,'max_calls_reserved':MAX_CALLS,'reserve_usd':str(TOTAL_RESERVE),'scope':'NONREFUNDABLE_BATCH_NO_RETRY'})
                exclusive(batch,{'permit_id':approval['permit_id'],'spec_sha256':self.spec_sha256})
            require(read(batch)=={'permit_id':approval['permit_id'],'spec_sha256':self.spec_sha256},'Another batch already occupies this store')
            r=prepared['request'];cell=f"{r['project_id']}-{r['stage']}-{r['arm']}-{r['turn']}"
            directory=self.path('calls',cell);directory.mkdir(exist_ok=True,parents=True)
            require(not (directory/'intent.json').exists(),'Pilot cell already claimed; never retry')
            require(len(list(self.root.glob('calls/*/intent.json')))<MAX_CALLS,'Pilot call ceiling consumed')
            exclusive(directory/'intent.json',{'spec_sha256':self.spec_sha256,'request_sha256':prepared['request_sha256'],'request_id':r['request_id'],'at_utc':datetime.now(timezone.utc).isoformat(),'reserve_usd':str(PER_CALL_RESERVE)})
            exclusive(directory/'prepared.json',prepared)
            start=time.perf_counter()
            answer=None
            try:
                transport=self.transport_factory(model) if self.simulated else router.NebiusTransport(model)
                answer=transport.request({'input':r['messages']},directory,self.timeout)
                require(revision.public()['disk_matches_loaded'],'Provider loaded source changed after call')
                usage=answer.get('usage');estimate=None
                if not self.simulated:verified_usage(usage)
                if isinstance(usage,dict) and all(type(usage.get(k)) is int and usage[k]>=0 for k in ('prompt_tokens','completion_tokens')):
                    estimate=float((Decimal(usage['prompt_tokens'])*Decimal('.30')+Decimal(usage['completion_tokens'])*Decimal('.90'))/Decimal(1000000))
                outcome={'status':'SIMULATED_TEST_ONLY' if self.simulated else 'PROVIDER_RETURNED_UNVERIFIED',
                    'response':answer['text'],'usage':answer.get('usage'),'provider_request_id':answer.get('response_id'),
                    'returned_model':answer.get('model'),'wall_seconds':time.perf_counter()-start,
                    'estimated_cost_usd':estimate,'actual_billed_usd':None,'request_sha256':prepared['request_sha256'],'provider_calls':0 if self.simulated else 1}
                exclusive(directory/'outcome.json',outcome);return outcome
            except BaseException as error:
                failure={'status':'PROVIDER_FAILURE_OR_UNCERTAIN_NO_RETRY','error_type':type(error).__name__,
                    'wall_seconds':time.perf_counter()-start,'usage':answer.get('usage') if isinstance(answer,dict) else getattr(error,'usage',None),
                    'returned_model':answer.get('model') if isinstance(answer,dict) else getattr(error,'returned_model',None),
                    'partial_text':answer.get('text','') if isinstance(answer,dict) else getattr(error,'text',''),
                    'actual_billed_usd':None,'retry_allowed':False}
                exclusive(directory/'outcome.json',failure);exclusive(self.path('STOP.json'),failure)
                raise Blocked('Provider outcome failed or uncertain; evidence preserved; no retry') from None
