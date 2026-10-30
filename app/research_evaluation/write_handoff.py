"""Write bounded Worker B handoff from existing execution evidence only."""
from pathlib import Path
from datetime import datetime,timezone
import difflib,hashlib,json

APP=Path(__file__).resolve().parents[1]
MISSION=APP.parents[2]
OUT=MISSION/'outputs/research-evaluation-20261028/worker-b'
def pin(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):
    with Path(path).open('x',encoding='utf-8') as file:json.dump(value,file,indent=2);file.write('\n')
def main():
    scope=OUT/'os-scope-attempt-1'
    osresult=json.loads((scope/'RESULT.json').read_bytes())
    reader=json.loads((scope/'READER_INPUT_EVIDENCE.json').read_bytes())
    inserted=json.loads((scope/'se6-insert.json').read_bytes())
    cold=json.loads((scope/'se6-query.json').read_bytes())
    assert inserted['diagnostic']['entity_id']==cold['trace']['entity_id']
    assert inserted['diagnostic']['entity_state_id']==cold['trace']['entity_state_id']
    assert inserted['pid']!=cold['pid'] and cold['trace']['consumed']
    owned=sorted(p for folder in ['research_controls','research_evaluation'] for p in (APP/folder).rglob('*')
        if p.is_file() and '__pycache__' not in p.parts and '.pytest_cache' not in p.parts)
    hashes={p.relative_to(APP).as_posix():pin(p) for p in owned}
    write(OUT/'SOURCE_HASHES.json',hashes)
    diff=''.join(''.join(difflib.unified_diff([],p.read_text(encoding='utf-8').splitlines(True),
        fromfile='/dev/null',tofile=p.relative_to(APP).as_posix())) for p in owned if p.suffix in {'.py','.md'})
    (OUT/'SOURCE_CHANGES.diff').write_text(diff,encoding='utf-8')
    review=dict(status='INDEPENDENTLY_SUPPORTED_BOUNDED_SOURCE_AND_COLD_MEMORY_CONNECTION',
        reviewer='WorkerB/evaluation_finish, separate from adapter author',
        adapter_sha256=pin(APP/'research_memory/adapter.py'),
        inspected_sources={str(p.relative_to(APP)):pin(p) for p in [APP/'research_memory/adapter.py',APP/'research_memory/entity.py',APP/'research_memory/format.py']},
        evidence=dict(scope_result_sha256=pin(scope/'RESULT.json'),reader_input_sha256=pin(scope/'READER_INPUT_EVIDENCE.json'),
            same_entity=True,same_committed_state=True,distinct_cold_pids=[inserted['pid'],cold['pid']],
            cold_entity_version=cold['trace']['entity_version'],cold_entity_state_id=cold['trace']['entity_state_id'],
            source_memory_records_consumed=len(cold['trace']['consumed'])),
        supported=['Actual LocalEntityRuntime ingress/transaction/SQLite memory path, not a JSON simulated store.',
            'MemoryPayload.CANDIDATE is retained PROVISIONAL/REPORTED with source events, exact reconstructed source hashes and lifecycle active_at consumption.',
            'Source records, entity identity and state survive distinct process restoration; cold query uses retained actual Entity memory.',
            'Prepared same-reader payload contains the exact returned context with matching question/settings and saved content-reference hashes.',
            'No VerificationPayload, Native witness, World outcome, verified capability or model answer is fabricated.'],
        limitations=['Only the declared synthetic text developer history was executed; no actual benchmark question was evaluated.',
            'The exact reader input is prepared, not dispatched; no answering model consumed it and no correctness or benefit is established.',
            'Optional official Memory registry is unexecuted because unmodified official imports require unavailable httpx; direct JSON/custom interface is what ran.',
            'Current input and record capacity cannot claim the official 100-trajectory haystack.',
            'Adapter storage checks can overshoot by one atomic commit; this is not a hard total-filesystem quota.',
            'The bounded contract does not establish full canonical mathematical realization or general learned capability.'])
    write(OUT/'INDEPENDENT_ADAPTER_REVIEW.json',review)
    resolved=dict(status='FOUR_SOURCE_REVIEW_FINDINGS_RESOLVED_OR_QUALIFIED',
        originating_review_sha256=pin(OUT.parent/'worker-a/CONTROL_REVIEW.json'),
        findings=dict(CONTROL_CONTEXT_ALLOCATION_LOSS='Fixed: exact allocated slices retained through chronological ordering; focused regression passed.',
            EAGER_SE6_IMPORT_COST_IN_CONTROL='Coordinator lazy package export; fresh conventional insert subprocess confirms no SE6 or pydantic import.',
            IMAGE_EMPTY_STRING_ASYMMETRY='Fixed: query_image must be exactly None for both control and worker, including empty-string refusal checks.',
            NOTES_COMPLETENESS_WORDING='Qualified: complete source chunks plus short verbatim notes; no complete-notes claim.'))
    write(OUT/'CONTROL_REVIEW_RESOLUTION.json',resolved)
    result=dict(status='LOCAL_MEMORY_CONTROL_ISOLATION_AND_PROTOCOL_PREPARATION_COMPLETE_EXTERNAL_RUN_BLOCKED',
        completed_at_utc=datetime.now(timezone.utc).isoformat(),provider_calls=0,embedding_calls=0,judge_calls=0,
        World_effects=0,production_changes=False,alpha_changes=False,
        tests=dict(result='14 passed in 0.15s',command='environment/Scripts/python.exe -B -m pytest -q -p no:cacheprovider research_evaluation/tests/test_preparation.py',
            output_sha256=pin(OUT/'TEST_OUTPUT.txt'),scope='New control/protocol/formatter isolation/official rubric/prepared reader input only; prior historical suites not repeated.'),
        executed=dict(os_scope='os-scope-attempt-1/RESULT.json',four_distinct_processes=True,
            real_os_filesystem_boundary='VERIFIED',cold_real_entity_memory='VERIFIED',
            prepared_exact_reader_input='VERIFIED_NOT_INFERENCE',reader_invocations=0,
            measured_own_process_resources=osresult['rows']),
        current_external_blockers=['No defensible full-evidence text-only eligibility for screenshot-bearing histories has been established.',
            'The inspected official record is 1344890 bytes, beyond the actual adapter 524288-byte cap and prospective 262144-byte protocol cap; no truncation occurred.',
            'The small tier has two shared history components; prospective disjoint development/evaluation split has only one evaluation unit.',
            'Prospective candidates remain BLOCKED_NOT_A_FROZEN_RUN; no pristine final held-out cases or actual capacity proof exists.'],
        inspected_record_scope='SCHEMA_CAPACITY_INSPECTION_ONLY: no semantic development, learning, question gold or scored answer inspected. Future semantic use must quarantine its history before a final split.',
        paid_proposal=dict(status='DRAFT_BLOCKED_NOT_OWNER_ADMISSION',runner='research_evaluation/paid_runner.py',
            max_calls=48,max_reader_calls=24,max_judge_calls=24,max_tokens_per_response=2048,
            max_wire_input_bytes_per_call=24576,timeout_seconds_per_call=30,hard_cap_usd='4.00',
            conservative_tariff_upper_usd='3.8633472',retries=0,
            paid_execution='NO_PROVIDER_ENTRYPOINT_WHILE_ACTUAL_DATA_CONTRACT_BLOCKED',
            freeze_required='Coordinator must run prepare with final complete-source manifest and exact official evaluator/OS proof pins.',
            next_after_data_admission='Bind a genuinely new-purpose execution gateway and fresh exact owner admission; old V2 gateway/approvals remain inapplicable.'),
        outcome='No benchmark accuracy result, validated model judgment, superiority, paid action or Alpha increase exists.',
        source_hashes_file='SOURCE_HASHES.json',source_diff_file='SOURCE_CHANGES.diff',independent_review='INDEPENDENT_ADAPTER_REVIEW.json')
    write(OUT/'RESULT.json',result)
    write(OUT/'EVIDENCE_HASHES.json',{p.relative_to(OUT).as_posix():pin(p) for p in OUT.rglob('*')
        if p.is_file() and p.name!='EVIDENCE_HASHES.json' and not any(part.startswith('SE6-MEMORY-') for part in p.parts)})
    print(json.dumps(dict(status=result['status'],result_sha256=pin(OUT/'RESULT.json'),source_manifest_sha256=pin(OUT/'SOURCE_HASHES.json'))))
if __name__=='__main__':main()
