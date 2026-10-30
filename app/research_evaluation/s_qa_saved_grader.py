"""Thirty fixed saved outputs -> independent blinded semantic grading only.

New authority, store and source binding. Never generates or regenerates reader
answers. Preparation/recovery are local; execute requires fresh owner approval.
"""
from pathlib import Path
from datetime import datetime,timezone
from decimal import Decimal
import argparse,hashlib,json,os,re,subprocess,sys,time
from hosted_judge.v8_run_both import RunBothCoordinator,exclusive,read,file_hash,digest,require,Blocked
from .s_qa_gateway import model_parts,official_judge_prompt
from .s_qa_recovery import classify,binary_judge_result,ResponseJournal,MODEL,ENDPOINT

APP=Path(__file__).resolve().parents[1]
CAP='2.40';MAX_ITEMS=30;OUTPUT=512
RESERVE=(Decimal(262144)*Decimal('.30')+Decimal(OUTPUT)*Decimal('.90'))/Decimal(1000000)
TOTAL=MAX_ITEMS*RESERVE

class SavedGrader(RunBothCoordinator):
    def __init__(self,root,*,spec_path,spec_pin,approval_path=None,approval_pin=None,live=False,transport_factory=None,source_root=None):
        super().__init__(root,approval_path=approval_path,approval_sha256=approval_pin,live_enabled=live,
            transport_factory=transport_factory,request_timeout_seconds=30)
        self.spec_path=Path(spec_path).resolve();self.spec_pin=spec_pin;self.source_root=Path(source_root or APP).resolve()
        require(self.simulated or self.source_root==APP,'Fixed source required for live saved grading')
    def spec(self):
        require(not self.spec_path.is_symlink() and file_hash(self.spec_path)==self.spec_pin,'Saved-grader specification changed')
        value=read(self.spec_path)
        for key,expected in {'schema':'se6-saved-answers-grader-only-v1','model':MODEL,'endpoint':ENDPOINT,
            'max_calls':30,'max_output_tokens':512,'max_wire_bytes':24576,'input_token_reserve_per_call':262144,'timeout_seconds':30,'usd_cap':CAP}.items():
            require(value.get(key)==expected,'Fixed grader-only purpose/cap mismatch: '+key)
        require(value['claim_store_sha256']==self.store_identity(),'Saved-grader store mismatch')
        require(len(value['items'])==30 and len({i['blind_id'] for i in value['items']})==30,'Exactly30frozen saved outputs required')
        require(any(m['path']==value['private_mapping_path'] for m in value['evidence_files']),'Private evaluator mapping must be source-bound')
        require(TOTAL<=Decimal(CAP),'Conservative grader reserve exceeds cap')
        return value
    def sources(self,spec):
        manifest=Path(spec['source_manifest_path'])
        require(manifest.resolve()==self.source_root/'COMPLETE_SOURCE_MANIFEST_PRIVATE.json'
            and file_hash(manifest)==spec['source_manifest_sha256'],'Saved-grader source manifest changed')
        files=read(manifest)['files']
        require(self.simulated or all(n in files for n in ['research_evaluation/s_qa_saved_grader.py','research_evaluation/s_qa_recovery.py']),
            'Saved-grader executing source absent from freeze')
        for name,pin in files.items():
            path=self.source_root/name
            require(not path.is_symlink() and path.resolve().is_relative_to(self.source_root) and file_hash(path)==pin,'Saved-grader source member changed')
        for member in spec['evidence_files']:
            path=Path(member['path']);require(not path.is_symlink() and file_hash(path)==member['sha256'],'Saved-grader input evidence changed')
    def approval(self):
        require(self.simulated or self.live_enabled,'Saved-grader live authority absent; no credential lookup')
        require(self.approval_path and self.approval_sha256 and file_hash(self.approval_path)==self.approval_sha256,'Fresh exact saved-grader owner decision required')
        value=read(self.approval_path)
        require(value.get('schema')=='se6-saved-answer-grader-owner-decision-v1' and value.get('owner_identifier')=='programmerONE'
            and value.get('decision')=='APPROVE_ONE_SAVED_LONGMEMEVAL_S_GRADER_ONLY_RECOVERY' and value.get('approved') is True,
            'Old reader/pilot permission is not grader-only authority')
        require(re.fullmatch('[0-9a-f]{32}',value.get('permit_id','')) is not None and value['spec_sha256']==self.spec_pin
            and value['claim_store_sha256']==self.store_identity() and value['max_calls']==30 and value['usd_cap']==CAP,
            'Saved-grader owner binding/caps changed')
        require(isinstance(value.get('authorization_provenance'),dict) and value['authorization_provenance'].get('kind')==('SIMULATED_TEST_ONLY' if self.simulated else 'EXPLICIT_HUMAN_DECISION_IN_CURRENT_CODEX_SESSION'),
            'Actual new owner decision required')
        expiry=datetime.fromisoformat(value['expires_at_utc']);require(expiry.tzinfo is not None and datetime.now(timezone.utc)<expiry,'Saved-grader owner decision expired')
        return value
    def admit(self):
        spec=self.spec();decision=self.approval();self.sources(spec);return spec,decision
    def prepare(self,blind_id):
        spec=self.spec();items=[i for i in spec['items'] if i['blind_id']==blind_id];require(len(items)==1,'Saved output not in approved grading set')
        item=items[0];path=Path(item['packet_path']);require(file_hash(path)==item['packet_sha256'],'Blinded grader packet changed')
        packet=read(path);require(set(packet)=={'blind_id','messages','saved_answer_sha256','rubric_source_sha256'},'Only declared blinded grader fields allowed')
        settings,router=model_parts('judge');wire=router.payload_bytes(settings,{'input':packet['messages']})
        require(len(wire)<=24576,'Grader packet wire cap')
        return dict(blind_id=blind_id,messages=packet['messages'],wire_sha256=hashlib.sha256(wire).hexdigest(),
            wire_bytes=len(wire),spec_sha256=self.spec_pin)
    def invoke(self,blind_id):
        spec,decision=self.admit();prepared=self.prepare(blind_id);settings,router=model_parts('judge')
        self.root.mkdir(parents=True,exist_ok=True)
        with self.lock('saved-answer-grader-only'):
            self.approval()
            require(not self.path('STOP.json').exists(),'Saved-grader globally stopped; no retry')
            directory=self.path('calls',blind_id);journal=ResponseJournal(directory,max_output_tokens=OUTPUT)
            if (directory/'intent.json').exists():return self.recover(blind_id)
            intents=list(self.root.glob('calls/*/intent.json'));require(len(intents)<30,'Saved-grader call ceiling consumed')
            for intent in intents:
                previous=ResponseJournal(intent.parent,max_output_tokens=OUTPUT).recover()
                require(previous['status']!='GLOBAL_STOP','Unresolved existing inference; no retry/continuation')
            require(self.simulated or router.credential_status(settings),'NEBIUS_CREDENTIAL_MISSING_NO_CALL')
            batch=self.path('batch-claim.json')
            if not batch.exists():
                spent=self.path('spent-permits',decision['permit_id']+'.json');spent.parent.mkdir(parents=True,exist_ok=True)
                exclusive(spent,dict(spec_sha256=self.spec_pin,max_calls_reserved=30,reserved_usd=str(TOTAL)))
                exclusive(batch,dict(permit_id=decision['permit_id'],spec_sha256=self.spec_pin,started_at_utc=datetime.now(timezone.utc).isoformat()))
            batch_value=read(batch)
            require(batch_value.get('permit_id')==decision['permit_id'] and batch_value.get('spec_sha256')==self.spec_pin,'Another saved-grader batch occupies store')
            require((datetime.now(timezone.utc)-datetime.fromisoformat(batch_value['started_at_utc'])).total_seconds()<1770,'Saved-grader persistent batch deadline; no new call')
            journal.reserve(prepared['wire_sha256']);exclusive(directory/'prepared.json',prepared)
            if self.simulated:
                try:self.transport_factory(settings).request({'input':prepared['messages']},directory,30)
                except Exception:pass  # classify captured raw bytes; no retry
            else:
                command=[sys.executable,'-B','-m','research_evaluation.s_qa_saved_grader','transport-child','--spec',str(self.spec_path),
                    '--spec-pin',self.spec_pin,'--store',str(self.root.parent),'--approval',str(self.approval_path),
                    '--approval-pin',self.approval_sha256,'--blind-id',blind_id]
                try:
                    child=subprocess.run(command,cwd=APP,capture_output=True,text=True,encoding='utf-8',timeout=30)
                    (directory/'child.stdout').write_text(child.stdout,encoding='utf-8');(directory/'child.stderr').write_text(child.stderr,encoding='utf-8')
                except subprocess.TimeoutExpired:pass  # captured body may still permit local recovery
            result=self.recover(blind_id)
            if result['status']=='GLOBAL_STOP':
                exclusive(self.path('STOP.json'),dict(reason=result['reason'],blind_id=blind_id,retry_permitted=False))
            return result
    def recover(self,blind_id):
        prepared=self.prepare(blind_id);directory=self.path('calls',blind_id)
        intent=read(directory/'intent.json');require(intent['request_sha256']==prepared['wire_sha256'],'Recovered request binding changed')
        result=ResponseJournal(directory,max_output_tokens=OUTPUT).recover()
        result['judge_result']=binary_judge_result(result)
        return result

def transport_child(gateway,blind_id):
    spec,decision=gateway.admit();prepared=gateway.prepare(blind_id);directory=gateway.path('calls',blind_id)
    require(read(directory/'prepared.json')==prepared and read(directory/'intent.json')['request_sha256']==prepared['wire_sha256'],
        'Transport requires an exact existing new-purpose claim')
    batch=read(gateway.path('batch-claim.json'))
    require(batch.get('permit_id')==decision['permit_id'] and batch.get('spec_sha256')==gateway.spec_pin,
        'Transport batch binding mismatch')
    require((datetime.now(timezone.utc)-datetime.fromisoformat(batch['started_at_utc'])).total_seconds()<1770,'Saved-grader persistent child deadline')
    exclusive(directory/'transport-child-claim.json',dict(pid=os.getpid(),wire_sha256=prepared['wire_sha256']))
    gateway.approval();settings,router=model_parts('judge')
    require(router.credential_status(settings),'NEBIUS_CREDENTIAL_MISSING_NO_CALL')
    try:router.NebiusTransport(settings).request({'input':prepared['messages']},directory,25)
    except Exception:
        if not (directory/'provider.json').is_file():raise
    return gateway.recover(blind_id)

def prepare_packets(old_root,inventory_path,out,store):
    old=Path(old_root).resolve();inventory_path=Path(inventory_path);inventory=read(inventory_path)
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    old_spec_path=old/'qa-prepared/QA_SPEC.json';old_spec=read(old_spec_path)
    official=old_spec['official_judge_source'];evidence={str(inventory_path):file_hash(inventory_path),str(old_spec_path):file_hash(old_spec_path),
        official['path']:official['sha256']};items=[];mapping=[]
    complete=[r for r in inventory['items'] if r['status']=='COMPLETE'];require(len(complete)==30,'Exactly30saved complete outputs expected')
    cases={c['case_id']:c for c in old_spec['cases']}
    for row in complete:
        case=cases[row['case_id']];public=read(Path(case['public_path']));labels=read(Path(case['private_path']))
        for kind in ['public','private']:
            path=Path(case[kind+'_path']);require(file_hash(path)==case[kind+'_sha256'],'Original question/reference binding changed');evidence[str(path)]=file_hash(path)
        directory=Path(row['source_directory'])
        for name,pin in row['source_files'].items():require(file_hash(directory/name)==pin,'Saved source capture changed');evidence[str(directory/name)]=pin
        answer=row['classification']['final_text'];require(hashlib.sha256(answer.encode()).hexdigest()==row['output_sha256'],'Saved answer text binding changed')
        prompt=official_judge_prompt(official['path'],official['sha256'],task=labels['question_type'],question=public['question'],
            answer=labels['answer'],response=answer,abstention=False)
        blind='saved-'+hashlib.sha256(('se6-grader-recovery-v1:'+row['cell']+':'+row['output_sha256']).encode()).hexdigest()[:24]
        packet=dict(blind_id=blind,messages=[dict(role='user',content=prompt)],saved_answer_sha256=row['output_sha256'],rubric_source_sha256=official['sha256'])
        packet_path=out/(blind+'.json');exclusive(packet_path,packet);evidence[str(packet_path)]=file_hash(packet_path)
        settings,router=model_parts('judge');wire=router.payload_bytes(settings,{'input':packet['messages']});require(len(wire)<=24576,'Saved grader packet exceeds wire cap')
        items.append(dict(blind_id=blind,packet_path=str(packet_path),packet_sha256=file_hash(packet_path),wire_bytes=len(wire)))
        mapping.append(dict(blind_id=blind,case_id=row['case_id'],arm=row['arm'],original_cell=row['cell'],input_sha256=row['input_sha256'],output_sha256=row['output_sha256']))
    # Fixed blind order and two first items are completion-only calibration;
    # no selection depends on correctness or either method's apparent quality.
    items.sort(key=lambda item:item['blind_id'])
    mapping_path=out/'PRIVATE_BLIND_MAPPING.json';exclusive(mapping_path,mapping);evidence[str(mapping_path)]=file_hash(mapping_path)
    spec_path=out/'GRADER_SPEC.json';placeholder=SavedGrader(store,spec_path=spec_path,spec_pin='0'*64)
    manifest=APP/'COMPLETE_SOURCE_MANIFEST_PRIVATE.json'
    spec=dict(schema='se6-saved-answers-grader-only-v1',model=MODEL,endpoint=ENDPOINT,max_calls=30,max_output_tokens=512,max_wire_bytes=24576,
        input_token_reserve_per_call=262144,timeout_seconds=30,usd_cap=CAP,conservative_total_usd=str(TOTAL),tariff=dict(input_usd_per_million='0.30',output_usd_per_million='0.90'),
        claim_store_sha256=placeholder.store_identity(),source_manifest_path=str(manifest),source_manifest_sha256=file_hash(manifest),
        items=items,evidence_files=[dict(path=p,sha256=h) for p,h in sorted(evidence.items())],private_mapping_path=str(mapping_path),
        protocol=dict(reader_calls=0,judge_calls=30,indexing_calls=0,embedding_calls=0,calibration_calls_extra=0,
            calibration='First2fixedblinditems count within30; stop as systemic completion failure if both fail to yield a complete binary judge output.',
            grading='Verbatim original LongMemEval semantic rubric/reference; model judged, not answer/reference exact matching or Codex grading.',
            parser='Only complete yes/no decisions are scored; optional final period accepted. Invalid/truncated/empty judgments remain unmeasured, with usage charged.',
            incomplete_policy='Known valid item incomplete may continue within fixed calls. Authority/source/cost/transport ambiguity stops globally; never reissue any existing intent.',
            coverage='30savedcompleteanswers,15pairedcases; one truncated and9unattempted reader items excluded from recovered partial semantic result, not converted to successes.',
            output_justification='Retains the original512-token binary judge ceiling rather than silently increasing reader budgets. Separate reasoning may consume it; no guarantee of completion.',
            reasoning_controls='UNKNOWN for this exact Nebius deployment; no unsupported NVIDIA NIM/chat-template controls emitted.',
            disclosure='Question, reference/rubric and saved final answer only; no reasoning traces, credentials, production data or arm labels in model messages.',
            retries=0,fallbacks=0,replacement_runs=0,batch_timeout_seconds=1800,production_connected=False,alpha_changed=False),
        authority='NOT_APPROVED: fresh source/store/purpose-specific owner decision required; old31-call STOP and spent permission are immutable.')
    exclusive(spec_path,spec);return preflight(spec_path,file_hash(spec_path),store)

def preflight(spec_path,pin,store):
    gateway=SavedGrader(store,spec_path=spec_path,spec_pin=pin);spec=gateway.spec();gateway.sources(spec)
    packets=[gateway.prepare(i['blind_id']) for i in spec['items']]
    return dict(status='GRADER_ONLY_EXECUTABLE_PENDING_FRESH_OWNER_AUTHORITY',spec_sha256=pin,source_manifest_sha256=spec['source_manifest_sha256'],
        packets=30,maximum_wire_bytes=max(p['wire_bytes'] for p in packets),max_calls=30,reader_calls=0,max_output_tokens=512,input_token_reserve_per_call=262144,
        conservative_total_usd=str(TOTAL),hard_cap_usd=CAP,provider_calls=0,credential_lookups=0,semantic_grades='NONE')

def joined_summary(spec,rows):
    mapping_bytes=Path(spec['private_mapping_path']).read_bytes()
    require(any(m['path']==spec['private_mapping_path'] and m['sha256']==hashlib.sha256(mapping_bytes).hexdigest() for m in spec['evidence_files']),'Evaluator mapping changed before report')
    mapping=json.loads(mapping_bytes);by_id={m['blind_id']:m for m in mapping}
    require(len(mapping)==30 and len(by_id)==30 and set(by_id)=={i['blind_id'] for i in spec['items']},'Evaluator mapping does not cover exactly30fixed items')
    require(all(m['arm'] in {'se6','bm25'} for m in mapping),'Unknown evaluator arm')
    pairs={}
    for member in mapping:
        pair=pairs.setdefault(member['case_id'],{});require(member['arm'] not in pair,'Duplicate mapped case/arm');pair[member['arm']]=member['blind_id']
    require(len(pairs)==15 and all(set(p)=={'se6','bm25'} for p in pairs.values()),'Expected15complete saved-reader pairs')
    by_result={r['blind_id']:r for r in rows};arms={};paired=[]
    for arm in ['se6','bm25']:
        ids=[m['blind_id'] for m in mapping if m['arm']==arm]
        grades=[by_result[i]['judge']['label'] for i in ids if i in by_result and by_result[i]['judge']['status']=='GRADED']
        arms[arm]=dict(saved_answers=15,graded=len(grades),correct=sum(grades),unmeasured=15-len(grades),
            accuracy_on_graded_saved_answers=sum(grades)/len(grades) if grades else None,accuracy_denominator=len(grades),
            original_planned_readers=20,excluded_not_complete_saved_readers=5)
    for case,ids in sorted(pairs.items()):
        grades={arm:by_result.get(bid,{}).get('judge',dict(status='UNATTEMPTED',label=None)) for arm,bid in ids.items()}
        paired.append(dict(case_id=case,judgments=grades,jointly_graded=all(g['status']=='GRADED' for g in grades.values())))
    joint=[p for p in paired if p['jointly_graded']]
    known=[r for r in rows if r.get('tariff_estimate_usd') is not None]
    unknown=[r for r in rows if r.get('tariff_estimate_usd') is None]
    resources=dict(attempted_claims=len(rows),known_usage_items=len(known),unknown_usage_items=len(unknown),
        known_input_tokens=sum(r['usage']['prompt_tokens'] for r in known),known_completion_tokens=sum(r['usage']['completion_tokens'] for r in known),
        known_reported_reasoning_tokens=sum(r.get('reported_reasoning_tokens') or 0 for r in known),
        items_with_unknown_reasoning_token_split=sum(r.get('reported_reasoning_tokens') is None for r in known),
        known_usage_tariff_estimate_usd=str(sum((Decimal(r['tariff_estimate_usd']) for r in known),Decimal(0))),
        unknown_usage_full_reservation_usd=str(len(unknown)*RESERVE),reserved_input_tokens_per_call=262144,
        conservative_all30_reservation_usd=str(TOTAL),actual_invoice_usd=None,actual_invoice_status='UNKNOWN')
    return dict(per_arm=arms,paired_coverage=paired,jointly_graded_pairs=len(joint),unmeasured_pairs=15-len(joint),
        paired_accuracy={a:dict(correct=sum(p['judgments'][a]['label'] for p in joint),denominator=len(joint),
            accuracy=sum(p['judgments'][a]['label'] for p in joint)/len(joint) if joint else None) for a in ['se6','bm25']},
        resources=resources,scope='Model semantic grades only on actual saved-output subset; incomplete/missing judgments remain unmeasured. Original20case accuracy remains UNMEASURED.')

def execute(gateway):
    spec,_=gateway.admit();start=time.monotonic();rows=[]
    for index,item in enumerate(spec['items']):
        require(time.monotonic()-start<1770,'Saved-grader batch deadline before another call')
        result=gateway.invoke(item['blind_id']);rows.append(dict(blind_id=item['blind_id'],status=result['status'],judge=result['judge_result'],
            usage=result.get('usage'),tariff_estimate_usd=result.get('tariff_estimate_usd'),reported_reasoning_tokens=result.get('reported_reasoning_tokens')))
        if result['status']=='GLOBAL_STOP':break
        if index==1 and all(r['judge']['status']!='GRADED' for r in rows):
            exclusive(gateway.path('STOP.json'),dict(reason='SYSTEMIC_COMPLETION_CALIBRATION_FAILED_FIRST_TWO',retry_permitted=False));break
    report=dict(status='RECOVERED_PARTIAL_SEMANTIC_GRADING_COMPLETE' if len(rows)==30 and all(r['judge']['status']=='GRADED' for r in rows)
        else 'PARTIAL_OR_SYSTEMICALLY_STOPPED_NO_RETRY',results=rows,reader_calls=0,provider_calls=0 if gateway.simulated else len(list(gateway.root.glob('calls/*/intent.json'))),
        simulated=gateway.simulated,original20case_accuracy='UNMEASURED: only saved-output subset recovery is in scope.',measurement=joined_summary(spec,rows),production_connected=False,alpha_changed=False)
    path=gateway.path('RECOVERY_RESULT-'+hashlib.sha256(json.dumps(report,sort_keys=True).encode()).hexdigest()[:16]+'.json')
    if not path.exists():exclusive(path,report)
    return report

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('operation',choices=['prepare','preflight','admit','execute','transport-child'])
    for flag in ['old-root','inventory','out','store','spec','approval']:parser.add_argument('--'+flag,type=Path)
    parser.add_argument('--spec-pin');parser.add_argument('--approval-pin');parser.add_argument('--blind-id');parser.add_argument('--live',action='store_true')
    args=parser.parse_args()
    if args.operation=='prepare':result=prepare_packets(args.old_root,args.inventory,args.out,args.store)
    elif args.operation=='preflight':result=preflight(args.spec,args.spec_pin,args.store)
    else:
        gateway=SavedGrader(args.store,spec_path=args.spec,spec_pin=args.spec_pin,approval_path=args.approval,approval_pin=args.approval_pin,live=args.live or args.operation in {'admit','transport-child'})
        if args.operation=='admit':gateway.admit();result=dict(status='FRESH_GRADER_ONLY_ADMISSION_VERIFIED',provider_calls=0,credential_lookups=0)
        elif args.operation=='transport-child':result=transport_child(gateway,args.blind_id)
        else:result=execute(gateway)
    print(json.dumps(result,ensure_ascii=True))
if __name__=='__main__':main()
