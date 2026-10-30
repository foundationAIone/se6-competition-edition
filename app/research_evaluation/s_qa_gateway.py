"""Fresh-purpose final-answer gateway; existing wire/parser and durable claims.

No authority or credential lookup on import/prepare. A new exact owner decision
is required. Old V2 pilot approvals cannot match this schema or purpose.
"""
from pathlib import Path
from datetime import datetime,timezone
from decimal import Decimal
import ast,hashlib,json,re,subprocess,sys,time
from hosted_judge.v8_run_both import RunBothCoordinator,Blocked,require,encoded,digest,file_hash,read,exclusive

APP=Path(__file__).resolve().parents[1]
MODEL='nvidia/nemotron-3-super-120b-a12b'
ENDPOINT='https://api.tokenfactory.nebius.com/v1/chat/completions'
CAP='6.50';MAX_CALLS=80;INPUT_UPPER=262144;MAX_WIRE=24576
OUTPUT={'reader':2048,'judge':512}
RESERVE={kind:(Decimal(INPUT_UPPER)*Decimal('.30')+Decimal(tokens)*Decimal('.90'))/Decimal(1000000) for kind,tokens in OUTPUT.items()}
TOTAL_RESERVE=40*RESERVE['reader']+40*RESERVE['judge']

def model_parts(kind):
    require(kind in OUTPUT,'Memory QA call purpose')
    bundle=APP/'private-native'
    if str(bundle) not in sys.path:sys.path.insert(0,str(bundle))
    from src.workbench.models import ModelSettings
    from src.workbench import provider_router
    settings=ModelSettings(model=MODEL,temperature=0,max_output_tokens=OUTPUT[kind],provider_reasoning_control=None)
    require(provider_router.NEBIUS_ENDPOINT==ENDPOINT,'Existing provider endpoint changed')
    return settings,provider_router

def official_judge_prompt(path,pin,*,task,question,answer,response,abstention=False):
    path=Path(path);require(file_hash(path)==pin,'Official answer rubric source changed')
    tree=ast.parse(path.read_text(encoding='utf-8'))
    function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='get_anscheck_prompt')
    scope={};exec(compile(ast.Module(body=[function],type_ignores=[]),str(path),'exec'),scope)
    return scope['get_anscheck_prompt'](task,question,answer,response,abstention=abstention)

def checked_usage(usage,kind):
    require(type(usage) is dict and all(type(usage.get(k)) is int and usage[k]>=0 for k in ['prompt_tokens','completion_tokens','total_tokens']),
        'Usage missing or invalid; charged at full reserve and stop')
    require(usage['prompt_tokens']<=INPUT_UPPER and usage['completion_tokens']<=OUTPUT[kind]
        and usage['total_tokens']==usage['prompt_tokens']+usage['completion_tokens'],'Usage outside frozen reservation')
    return usage

class MemoryQAGateway(RunBothCoordinator):
    def __init__(self,root,*,spec_path,spec_sha256,approval_path=None,approval_sha256=None,live_enabled=False,
                 transport_factory=None,source_root=None):
        super().__init__(root,approval_path=approval_path,approval_sha256=approval_sha256,live_enabled=live_enabled,
            transport_factory=transport_factory,request_timeout_seconds=30)
        self.spec_path=Path(spec_path).resolve();self.spec_sha256=spec_sha256
        self.source_root=Path(source_root or APP).resolve()
        require(self.simulated or self.source_root==APP,'Live memory QA uses the actual fixed application source')

    def specification(self):
        require(not self.spec_path.is_symlink() and file_hash(self.spec_path)==self.spec_sha256,'Exact memory QA specification changed')
        value=read(self.spec_path)
        require(value.get('schema')=='se6-longmemeval-s-final-answer-v1','New memory QA purpose specification required')
        expected={'model':MODEL,'endpoint':ENDPOINT,'max_requests':80,'max_reader_calls':40,'max_judge_calls':40,
            'max_reader_output_tokens':2048,'max_judge_output_tokens':512,'max_wire_input_bytes':24576,
            'input_token_reserve_per_call':262144,'timeout_seconds':30,'batch_timeout_seconds':1800,'usd_cap':CAP}
        for key,want in expected.items():require(value.get(key)==want,'Frozen memory QA cap changed: '+key)
        require(value.get('tariff')=={'input_usd_per_million':'0.30','output_usd_per_million':'0.90'},'Memory QA tariff changed')
        require(value.get('claim_store_sha256')==self.store_identity(),'Memory QA claim store changed')
        require(type(value.get('cases')) is list and len(value['cases'])==20 and len({c['case_id'] for c in value['cases']})==20,
            'Exactly twenty source-bound QA cases required')
        require(TOTAL_RESERVE<=Decimal(CAP),'Memory QA reserve exceeds cap')
        return value

    def _sources(self,spec):
        path=Path(spec['source_manifest_path']).resolve()
        require(path==self.source_root/'COMPLETE_SOURCE_MANIFEST_PRIVATE.json' and file_hash(path)==spec['source_manifest_sha256'],
            'Memory QA complete source binding changed')
        source_manifest=read(path)
        require(self.simulated or all(name in source_manifest['files'] for name in
            ['research_evaluation/s_qa_gateway.py','research_evaluation/s_qa.py','research_evaluation/s_qa_transport_child.py']),
            'QA execution is absent from the source freeze; primary-only closure is not paid authority')
        for name,pin in source_manifest['files'].items():
            member=self.source_root/name
            require(not member.is_symlink() and member.resolve().is_relative_to(self.source_root)
                and member.is_file() and file_hash(member)==pin,'Memory QA source member changed')
        for member in spec['evidence_files']:
            path=Path(member['path']);require(not path.is_symlink() and file_hash(path)==member['sha256'],'QA data or retrieval evidence changed')

    def _approval(self):
        require(self.simulated or self.live_enabled,'Memory QA is not live-enabled; no credential lookup')
        require(self.approval_path and self.approval_sha256 and not self.approval_path.is_symlink()
            and file_hash(self.approval_path)==self.approval_sha256,'Exact new memory QA owner decision required')
        value=read(self.approval_path)
        required={'schema','permit_id','owner_identifier','decision','approved','spec_sha256','claim_store_sha256',
            'expires_at_utc','max_requests','usd_cap','authorization_provenance'}
        require(set(value)==required and value['schema']=='se6-longmemeval-s-answer-owner-decision-v1','Old or unrelated approval is not memory QA authority')
        require(value['owner_identifier']=='programmerONE' and value['decision']=='APPROVE_ONE_CUSTOM_LONGMEMEVAL_S_FINAL_ANSWER_BATCH'
            and value['approved'] is True,'Exact programmerONE memory QA decision required')
        require(re.fullmatch('[0-9a-f]{32}',value['permit_id'] or '') is not None and value['spec_sha256']==self.spec_sha256
            and value['claim_store_sha256']==self.store_identity(),'Owner decision specification/store binding changed')
        require(value['max_requests']==80 and value['usd_cap']==CAP,'Owner decision caps differ')
        require(type(value['authorization_provenance']) is dict and value['authorization_provenance'].get('kind')==('SIMULATED_TEST_ONLY' if self.simulated else 'EXPLICIT_HUMAN_DECISION_IN_CURRENT_CODEX_SESSION'),
            'Genuine current-session decision provenance required')
        expires=datetime.fromisoformat(value['expires_at_utc'])
        require(expires.tzinfo is not None and datetime.now(timezone.utc)<expires,'Owner decision expired')
        return value

    def admit(self):
        spec=self.specification();approval=self._approval();self._sources(spec)
        return spec,approval

    def _case(self,spec,case_id):
        matches=[c for c in spec['cases'] if c['case_id']==case_id]
        require(len(matches)==1,'Case not in exact approved QA set');return matches[0]

    def prepare_cell(self,kind,case_id,arm):
        spec=self.specification();require(kind in OUTPUT and arm in {'se6','bm25'},'Memory QA cell shape')
        case=self._case(spec,case_id)
        if kind=='reader':
            source=case['readers'][arm];path=Path(source['path'])
            require(file_hash(path)==source['sha256'],'Frozen reader input changed')
            messages=read(path)['messages']
        else:
            # Every answer is durably committed before opening any judge call.
            for row in spec['cases']:
                for lane in ['se6','bm25']:
                    outcome=self.path('calls',row['case_id']+'-reader-'+lane,'outcome.json')
                    require(outcome.is_file() and read(outcome).get('status')==('SIMULATED_TEST_ONLY' if self.simulated else 'PROVIDER_RETURNED_UNVERIFIED'),
                        'All forty reader answers must be committed before grading')
            source=Path(case['private_path']);require(file_hash(source)==case['private_sha256'],'Trusted QA labels changed')
            labels=read(source);public=read(Path(case['public_path']))
            answer=read(self.path('calls',case_id+'-reader-'+arm,'outcome.json'))['response']
            prompt=official_judge_prompt(spec['official_judge_source']['path'],spec['official_judge_source']['sha256'],
                task=labels['question_type'],question=public['question'],answer=labels['answer'],response=answer,
                abstention=case.get('abstention',False))
            messages=[{'role':'user','content':prompt}]
        require(type(messages) is list and all(type(m) is dict and set(m)=={'role','content'}
            and m['role'] in {'system','user'} and type(m['content']) is str for m in messages),'Memory QA isolated messages required')
        settings,router=model_parts(kind);raw=router.payload_bytes(settings,{'input':messages})
        require(len(raw)<=MAX_WIRE,'Memory QA actual wire input exceeds cap; no call')
        return dict(kind=kind,case_id=case_id,arm=arm,messages=messages,wire_sha256=hashlib.sha256(raw).hexdigest(),
            wire_bytes=len(raw),response_tokens=OUTPUT[kind])

    def invoke_cell(self,kind,case_id,arm):
        # No environment/credential access before genuine source/purpose admission.
        spec,approval=self.admit();prepared=self.prepare_cell(kind,case_id,arm)
        settings,router=model_parts(kind)
        require(self.simulated or router.credential_status(settings),'NEBIUS_CREDENTIAL_MISSING_NO_CALL')
        self.root.mkdir(parents=True,exist_ok=True)
        with self.lock('whole-memory-qa-batch'):
            # Final authority/expiry check at the exclusive intent boundary.
            approval=self._approval()
            require(not self.path('STOP.json').exists(),'Memory QA stopped; no retry or continuation')
            intents=list(self.root.glob('calls/*/intent.json'))
            for old in intents:
                outcome=old.parent/'outcome.json'
                require(outcome.is_file() and read(outcome).get('status')==('SIMULATED_TEST_ONLY' if self.simulated else 'PROVIDER_RETURNED_UNVERIFIED'),
                    'Unresolved prior memory QA call; no retry')
            batch=self.path('batch-claim.json')
            if not batch.exists():
                spent=self.path('spent-permits',approval['permit_id']+'.json');spent.parent.mkdir(parents=True,exist_ok=True)
                exclusive(spent,dict(spec_sha256=self.spec_sha256,max_calls_reserved=80,reserve_usd=str(TOTAL_RESERVE),scope='NONREFUNDABLE_SOURCE_BOUND_BATCH_NO_RETRY'))
                exclusive(batch,dict(permit_id=approval['permit_id'],spec_sha256=self.spec_sha256))
            require(read(batch)==dict(permit_id=approval['permit_id'],spec_sha256=self.spec_sha256),'Another memory QA batch occupies store')
            cell=case_id+'-'+kind+'-'+arm;directory=self.path('calls',cell);directory.mkdir(parents=True,exist_ok=True)
            require(not (directory/'intent.json').exists(),'Memory QA cell already claimed; no retry')
            require(len(intents)<80 and sum(read(p)['kind']==kind for p in intents)<40,'Memory QA call cap consumed')
            exclusive(directory/'intent.json',dict(kind=kind,wire_sha256=prepared['wire_sha256'],spec_sha256=self.spec_sha256,
                at_utc=datetime.now(timezone.utc).isoformat(),reserve_usd=str(RESERVE[kind])))
            exclusive(directory/'prepared.json',prepared);start=time.perf_counter();answer=None
            try:
                if self.simulated:
                    answer=self.transport_factory(settings).request({'input':prepared['messages']},directory,30)
                else:
                    # A separate owned helper gives an absolute client deadline,
                    # rather than relying only on urllib's per-socket timeout.
                    command=[sys.executable,'-B','-m','research_evaluation.s_qa_transport_child',
                        '--store',str(self.root.parent),'--spec',str(self.spec_path),'--spec-pin',self.spec_sha256,
                        '--approval',str(self.approval_path),'--approval-pin',self.approval_sha256,
                        '--kind',kind,'--case-id',case_id,'--arm',arm]
                    try:
                        completed=subprocess.run(command,cwd=APP,capture_output=True,text=True,encoding='utf-8',timeout=30)
                        (directory/'transport-child.stdout').write_text(completed.stdout,encoding='utf-8')
                        (directory/'transport-child.stderr').write_text(completed.stderr,encoding='utf-8')
                        if completed.returncode!=0 and (directory/'transport-failure.json').is_file():
                            answer=read(directory/'transport-failure.json')
                        require(completed.returncode==0 and (directory/'transport-response.json').is_file(),
                            'Owned provider helper failed; no retry')
                        answer=read(directory/'transport-response.json')
                    except subprocess.TimeoutExpired:
                        # subprocess.run terminates only this owned helper. The
                        # remote outcome remains uncertain and fully reserved.
                        raise Blocked('Absolute provider helper deadline; uncertain outcome, no retry') from None
                require(self.simulated or file_hash(directory/'request.json')==prepared['wire_sha256'],'Actual provider wire differs from approved prepared input')
                self._sources(spec);usage=checked_usage(answer.get('usage'),kind)
                estimate=(Decimal(usage['prompt_tokens'])*Decimal('.30')+Decimal(usage['completion_tokens'])*Decimal('.90'))/Decimal(1000000)
                outcome=dict(status='SIMULATED_TEST_ONLY' if self.simulated else 'PROVIDER_RETURNED_UNVERIFIED',response=answer['text'],
                    usage=usage,returned_model=answer.get('model'),provider_request_id=answer.get('response_id'),wall_seconds=time.perf_counter()-start,
                    tariff_estimate_usd=str(estimate),actual_billed_usd=None,wire_sha256=prepared['wire_sha256'],provider_calls=0 if self.simulated else 1,
                    transport_child_resources=answer.get('transport_child_resources'))
                exclusive(directory/'outcome.json',outcome);return outcome
            except BaseException as error:
                failure=dict(status='PROVIDER_FAILURE_OR_UNCERTAIN_NO_RETRY',error_type=type(error).__name__,
                    wall_seconds=time.perf_counter()-start,usage=answer.get('usage') if isinstance(answer,dict) else getattr(error,'usage',None),
                    partial_text=answer.get('text','') if isinstance(answer,dict) else getattr(error,'text',''),
                    actual_billed_usd=None,reserved_cost_usd=str(RESERVE[kind]),retry_allowed=False)
                exclusive(directory/'outcome.json',failure);exclusive(self.path('STOP.json'),failure)
                raise Blocked('Memory QA outcome failed or uncertain; preserved and stopped without retry') from None
