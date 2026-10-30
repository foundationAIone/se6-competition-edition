"""Prepare/preflight/execute the matched final-answer continuation.

Prepare and preflight make zero provider/credential calls. Execute requires a
fresh exact source-bound owner decision and a process-only Nebius credential.
The existing masked key-entry mechanism can launch this executable CLI.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,time
from decimal import Decimal
from .s_qa_gateway import MemoryQAGateway,model_parts,MODEL,ENDPOINT,TOTAL_RESERVE,CAP,official_judge_prompt
from .s_public import score_case,sha,require
from .s_batch import file_sha,write
from research_memory.sessions_format import render_session

APP=Path(__file__).resolve().parents[1];LANE=APP.parent
SYSTEM='''Answer the question from the supplied historical conversations and their dates.
These are source-backed historical reports, not fresh verified World facts.
Use only the provided evidence; do not invent missing details. If it is insufficient,
say that the provided history is insufficient. You have no tools or filesystem access.
Evidence may be explicitly truncated under a fixed equal byte budget. Return your answer.'''

def reader_messages(public,retrieval):
    sessions=retrieval.get('sessions',[]) if isinstance(retrieval,dict) else []
    remaining=16384;pieces=[];trace=[]
    for rank,session in enumerate(sessions):
        text='Historical session; source '+session['source_ref']+'\n'+render_session(session)+'\n'
        raw=text.encode('utf-8');selected=raw[:remaining].decode('utf-8',errors='ignore')
        used=len(selected.encode('utf-8'))
        if used:
            pieces.append(selected);remaining-=used
            trace.append(dict(session_id=session['session_id'],source_ref=session['source_ref'],
                full_session_sha256=session['content_sha256'],retrieval_rank=rank+1,reader_bytes=used,
                reader_text_sha256=hashlib.sha256(selected.encode()).hexdigest(),truncated=used<len(raw)))
        if remaining<=0:break
    content=dict(question=public['question'],question_date=public['question_date'],
        historical_evidence=''.join(pieces),evidence_truncated=any(t['truncated'] for t in trace),
        evidence_absent=not pieces)
    messages=[dict(role='system',content=SYSTEM),dict(role='user',content=json.dumps(content,ensure_ascii=False,separators=(',',':')))]
    settings,router=model_parts('reader');wire=router.payload_bytes(settings,{'input':messages})
    require(len(wire)<=24576,'QA_READER_WIRE_BOUND_BEFORE_APPROVAL')
    return messages,dict(context_bytes=16384-remaining,context_limit_bytes=16384,selected_sources=trace,
        serialized_wire_bytes=len(wire),wire_sha256=hashlib.sha256(wire).hexdigest(),reader_invoked=False)

def prepare(manifest_path,retrieval_root,claim_store,out):
    start=time.perf_counter();cpu=time.process_time()
    manifest_path=Path(manifest_path).resolve(strict=True);manifest=json.loads(manifest_path.read_bytes())
    retrieval_root=Path(retrieval_root).resolve(strict=True);batch=json.loads((retrieval_root/'RESULT.json').read_bytes())
    require(batch['partition']=='evaluation' and batch['cases_selected']==20 and batch['cases_attempted']==20,'QA_REQUIRES_COMPLETED_SELECTED_RETRIEVAL_PASS')
    cases=[c for c in manifest['cases'] if c['partition']=='evaluation'];require(len(cases)==20,'QA_EXACT_SELECTED_CASES')
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    evidence={str(manifest_path):file_sha(manifest_path),str(retrieval_root/'RESULT.json'):file_sha(retrieval_root/'RESULT.json')}
    prepared_cases=[]
    for case in cases:
        cid=case['case_id'];public_path=Path(case['public_path']);private_path=Path(case['private_path'])
        require(file_sha(public_path)==case['public_sha256'] and file_sha(private_path)==case['private_sha256'],'QA_DATA_BINDING_CHANGED')
        public=json.loads(public_path.read_bytes());labels=json.loads(private_path.read_bytes())
        evidence[str(public_path)]=file_sha(public_path);evidence[str(private_path)]=file_sha(private_path)
        result_path=retrieval_root/cid/'RESULT.json';row=json.loads(result_path.read_bytes());evidence[str(result_path)]=file_sha(result_path)
        readers={}
        for arm in ['se6','bm25']:
            actual=row['arms'][arm]
            verification=score_case(public,labels['required_session_ids'],actual.get('result'),failure=actual.get('failure'))
            require(not verification['invalid_evidence'],'QA_RETRIEVAL_PROVENANCE_INVALID')
            retrieved=actual.get('result') if actual.get('failure') is None else None
            messages,trace=reader_messages(public,retrieved)
            path=out/(cid+'-'+arm+'-reader.json');write(path,dict(messages=messages,trace=trace))
            readers[arm]=dict(path=str(path),sha256=file_sha(path));evidence[str(path)]=file_sha(path)
        prepared_cases.append(dict(case_id=cid,public_path=str(public_path),public_sha256=file_sha(public_path),
            private_path=str(private_path),private_sha256=file_sha(private_path),readers=readers,abstention=False))
    official=LANE/'external/longmemeval/src/evaluation/evaluate_qa.py'
    evidence[str(official)]=file_sha(official)
    spec_path=out/'QA_SPEC.json'
    gateway=MemoryQAGateway(claim_store,spec_path=spec_path,spec_sha256='0'*64)
    source=APP/'COMPLETE_SOURCE_MANIFEST_PRIVATE.json'
    spec=dict(schema='se6-longmemeval-s-final-answer-v1',model=MODEL,endpoint=ENDPOINT,
        max_requests=80,max_reader_calls=40,max_judge_calls=40,max_reader_output_tokens=2048,max_judge_output_tokens=512,
        max_wire_input_bytes=24576,input_token_reserve_per_call=262144,timeout_seconds=30,batch_timeout_seconds=1800,usd_cap=CAP,
        tariff=dict(input_usd_per_million='0.30',output_usd_per_million='0.90'),
        conservative_total_reserve_usd=str(TOTAL_RESERVE),claim_store_sha256=gateway.store_identity(),
        source_manifest_path=str(source),source_manifest_sha256=file_sha(source),
        dataset_revision=manifest.get('dataset_revision'),dataset_sha256=manifest.get('dataset_sha256'),
        retrieval_selection_manifest_sha256=file_sha(manifest_path),retrieval_result_sha256=file_sha(retrieval_root/'RESULT.json'),
        cases=prepared_cases,evidence_files=[dict(path=p,sha256=h) for p,h in sorted(evidence.items())],
        official_judge_source=dict(path=str(official),sha256=file_sha(official)),
        protocol=dict(label='Custom LongMemEval-S final-answer continuation on the same 20 retrieval cases; not a fresh independent generalization set.',
            reader='Same Nemotron model/system prompt and 16384-byte UTF8 evidence cap in both arms. Retrieval ranking order; prefix truncation only for reader context, full source intake unchanged.',
            grader='Same Nemotron judge, original get_anscheck_prompt source verbatim; original yes-substring decision semantics. Blind separate API calls with no arm labels in messages.',
            reasoning='Provider default reasoning, within combined output caps; no guarantee that final-answer tokens remain.',
            answer_commit='All forty reader answers committed before any judging begins.',
            methods_retuned_after_retrieval=False,cases_reused_from_retrieval=True,
            retries=0,fallback_calls=0,replacement_runs=0,indexing_calls=0,embedding_calls=0,summarization_calls=0,subordinate_model_calls=0,
            disclosure='Reader receives only question/date and its own exact retrieved source excerpts. Judge receives question, reference, task rubric and one committed answer; no production data.',
            stop='Any failed/ambiguous call stops without retry. Unknown usage reserves full call cost; original partial outputs preserved. Batch deadline1800seconds.',
            authority='No prior approval applies. Fresh exact programmerONE purpose/spec/store-bound approval and private process credential required.',
            production_connected=False,alpha_changed=False),
        preparation_resources=dict(wall_seconds=time.perf_counter()-start,parent_cpu_seconds=time.process_time()-cpu,provider_calls=0,
            scope='Reads frozen local retrieval/source evidence and constructs all reader packets; no inference or credential setup.'))
    write(spec_path,spec)
    result=preflight(spec_path,file_sha(spec_path),claim_store)
    write(out/'QA_PREFLIGHT.json',result)
    return result

def preflight(spec_path,spec_pin,store):
    gateway=MemoryQAGateway(store,spec_path=spec_path,spec_sha256=spec_pin)
    spec=gateway.specification();gateway._sources(spec)
    wires=[];judge_templates=[]
    for case in spec['cases']:
        for arm in ['se6','bm25']:wires.append(gateway.prepare_cell('reader',case['case_id'],arm))
        # Validate every actual selected rubric/type now, before any paid
        # readers can run. Placeholder responses remain trusted-side only.
        labels=json.loads(Path(case['private_path']).read_bytes());public=json.loads(Path(case['public_path']).read_bytes())
        template=official_judge_prompt(spec['official_judge_source']['path'],spec['official_judge_source']['sha256'],
            task=labels['question_type'],question=public['question'],answer=labels['answer'],
            response='UNSCORED_OFFLINE_RESPONSE_PLACEHOLDER',abstention=case.get('abstention',False))
        settings,router=model_parts('judge');raw=router.payload_bytes(settings,{'input':[dict(role='user',content=template)]})
        require(len(raw)<=24576,'QA_JUDGE_TEMPLATE_ALREADY_EXCEEDS_WIRE_CAP')
        judge_templates.append(dict(sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw)))
    return dict(status='EXECUTABLE_READY_REQUIRES_FRESH_OWNER_SPENDING_AUTHORITY',spec_sha256=spec_pin,
        source_manifest_sha256=spec['source_manifest_sha256'],reader_packets=len(wires),maximum_reader_wire_bytes=max(w['wire_bytes'] for w in wires),
        judge_rubric_templates_validated=len(judge_templates),maximum_base_judge_wire_bytes=max(j['bytes'] for j in judge_templates),
        maximum_provider_calls=80,max_reader_calls=40,max_judge_calls=40,conservative_tariff_upper_usd=str(TOTAL_RESERVE),
        hard_cap_usd=CAP,provider_calls=0,credential_lookups=0,approval_created=False,
        scope='All local preparation and executable transport/admission path ready; no reader or model judge has executed.')

def execute(spec_path,spec_pin,store,approval_path,approval_pin,*,live=False,transport_factory=None,source_root=None):
    gateway=MemoryQAGateway(store,spec_path=spec_path,spec_sha256=spec_pin,approval_path=approval_path,
        approval_sha256=approval_pin,live_enabled=live,transport_factory=transport_factory,source_root=source_root)
    spec,_=gateway.admit();start=time.monotonic();cpu=time.process_time();rows=[]
    for kind in ['reader','judge']:
        for case in spec['cases']:
            for arm in ['se6','bm25']:
                require(time.monotonic()-start<1800,'QA_BATCH_DEADLINE_STOP_NO_RETRY')
                outcome=gateway.invoke_cell(kind,case['case_id'],arm)
                if kind=='judge':rows.append(dict(case_id=case['case_id'],arm=arm,
                    judge_response=outcome['response'],correct=('yes' in outcome['response'].lower()),
                    outcome_sha256=file_sha(gateway.path('calls',case['case_id']+'-judge-'+arm,'outcome.json'))))
    aggregate={arm:sum(r['correct'] for r in rows if r['arm']==arm)/20 for arm in ['se6','bm25']}
    outcomes=[json.loads(p.read_bytes()) for p in gateway.root.glob('calls/*/outcome.json')]
    costs=dict(input_tokens=sum(o['usage']['prompt_tokens'] for o in outcomes),
        output_tokens=sum(o['usage']['completion_tokens'] for o in outcomes),
        tariff_estimate_usd=str(sum((Decimal(o['tariff_estimate_usd']) for o in outcomes),Decimal(0))),
        actual_invoice_usd=None,parent_cpu_seconds=time.process_time()-cpu,
        transport_child_cpu_seconds=sum(o['transport_child_resources']['host_cpu_seconds'] for o in outcomes if o.get('transport_child_resources')),
        transport_child_peak_rss_bytes=max((o['transport_child_resources']['peak_process_rss_bytes'] or 0 for o in outcomes if o.get('transport_child_resources')),default=None),
        preparation_resources=spec.get('preparation_resources','UNKNOWN_NOT_ZERO'),
        scope='Provider-reported usage and tariff estimate, not invoice. Parent plus individually metered helpers; engineering/Codex/total OS cost remains UNKNOWN.')
    result=dict(status='COMPLETED_CUSTOM_MODEL_FINAL_ANSWER_COMPARISON' if not gateway.simulated else 'SIMULATED_TEST_ONLY',
        cases=20,model=MODEL,reader_calls=40,judge_calls=40,provider_calls=0 if gateway.simulated else 80,
        accuracy=aggregate,results=rows,source_manifest_sha256=spec['source_manifest_sha256'],spec_sha256=spec_pin,
        scope='Same previously retrieved cases and frozen methods; custom Nemotron judge, not official full benchmark or broad superiority.',
        actual_invoice_usd=None,elapsed_seconds=time.monotonic()-start,resources=costs,production_connected=False,alpha_changed=False)
    exclusive=gateway.path('FINAL_RESULT.json');write(exclusive,result);return result

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('operation',choices=['prepare','preflight','admit','execute'])
    for flag in ['manifest','retrieval-root','out','spec','store','approval']:parser.add_argument('--'+flag,type=Path)
    parser.add_argument('--spec-pin');parser.add_argument('--approval-pin');parser.add_argument('--live',action='store_true')
    args=parser.parse_args()
    if args.operation=='prepare':result=prepare(args.manifest,args.retrieval_root,args.store,args.out)
    elif args.operation=='preflight':result=preflight(args.spec,args.spec_pin,args.store)
    elif args.operation=='admit':
        gateway=MemoryQAGateway(args.store,spec_path=args.spec,spec_sha256=args.spec_pin,
            approval_path=args.approval,approval_sha256=args.approval_pin,live_enabled=True)
        gateway.admit()
        result=dict(status='EXACT_MEMORY_QA_OWNER_ADMISSION_VERIFIED_NO_DISPATCH',provider_calls=0,credential_lookups=0)
    else:result=execute(args.spec,args.spec_pin,args.store,args.approval,args.approval_pin,live=args.live)
    print(json.dumps(result,ensure_ascii=True))
if __name__=='__main__':main()
