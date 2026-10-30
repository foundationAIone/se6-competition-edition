"""Nonexecuting, source-bound proposal/preflight for the custom memory pilot.

There is intentionally no credential lookup, network transport or approval
writer here. The real external ingestion prerequisites are presently blocked;
this preparation command must never turn an arbitrary approval JSON into spend.
"""
from pathlib import Path
from decimal import Decimal
import argparse,hashlib,json
from .protocol import PROTOCOL,READER_PROMPT,digest,require

MODEL='nvidia/nemotron-3-super-120b-a12b'
ENDPOINT='https://api.tokenfactory.nebius.com/v1/chat/completions'
MAX_CALLS=48;INPUT_UPPER=262144;OUTPUT_UPPER=2048
RATE_IN=Decimal('.30');RATE_OUT=Decimal('.90');CAP=Decimal('4.00')
TARIFF_BOUND=MAX_CALLS*(INPUT_UPPER*RATE_IN+OUTPUT_UPPER*RATE_OUT)/Decimal(1000000)

def file_sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def preparation(readiness,*,source_manifest_path=None,official_evaluator_path=None,os_scope_path=None):
    require(type(readiness) is dict,'READINESS_OBJECT_REQUIRED')
    blockers=[]
    if readiness.get('status')!='READY_FOR_FROZEN_CUSTOM_EVALUATION':blockers.append('ACTUAL_EXTERNAL_CASE_MANIFEST_NOT_ADMITTED')
    if readiness.get('modality_eligibility')!='TEXT_ONLY_FULL_EVIDENCE_CERTIFIED':blockers.append('TEXT_SUFFICIENCY_UNESTABLISHED_NO_IMAGE_STRIPPING')
    if readiness.get('evaluation_independent_units',0)<PROTOCOL['minimum_eval_clusters']:blockers.append('INSUFFICIENT_INDEPENDENT_EVALUATION_HISTORY_CLUSTERS')
    if readiness.get('source_capacity_verified') is not True:blockers.append('ACTUAL_SOURCE_AND_HAYSTACK_CAPACITY_NOT_VERIFIED')
    pins={}
    if source_manifest_path:
        pins['source_manifest_sha256']=file_sha(source_manifest_path)
    else:blockers.append('FINAL_COMPLETE_SOURCE_MANIFEST_REQUIRED')
    if official_evaluator_path:pins['official_evaluator_sha256']=file_sha(official_evaluator_path)
    else:blockers.append('OFFICIAL_EVALUATOR_PIN_REQUIRED')
    if os_scope_path:
        scope=json.loads(Path(os_scope_path).read_bytes())
        require(scope.get('status')=='VERIFIED_SYNTHETIC_CONTRACT_AND_REAL_OS_BOUNDARY'
            and len(scope.get('rows',[]))==4 and all(r.get('os_sandbox',{}).get('kernel_boundary')=='VERIFIED' for r in scope['rows']),
            'OS_SCOPE_EVIDENCE_REQUIRED')
        pins['os_scope_sha256']=file_sha(os_scope_path)
    else:blockers.append('EXECUTED_OS_SCOPE_RECEIPT_REQUIRED')
    require(TARIFF_BOUND<=CAP,'CONSERVATIVE_TARIFF_BOUND_EXCEEDS_CAP')
    quote=dict(schema='se6-custom-memory-paid-proposal-v1',status='BLOCKED_NOT_AN_APPROVAL' if blockers else 'PREPARED_REQUIRES_FRESH_PURPOSE_ADMISSION',
        blockers=blockers,custom_not_official=True,protocol_sha256=digest(PROTOCOL),reader_prompt_sha256=digest(READER_PROMPT),
        reader=dict(model=MODEL,endpoint=ENDPOINT,temperature=0,max_output_tokens=OUTPUT_UPPER),
        judge=dict(model=MODEL,endpoint=ENDPOINT,temperature=0,max_output_tokens=OUTPUT_UPPER,
            rubric='Exact pinned official gotchas/abstention prompt and deterministic checkers; custom model/transport, blind per-answer labels.',
            model_judgment_validated=False),
        calls=dict(reader=24,judge=24,total=MAX_CALLS,indexing=0,embedding=0,simulator=0,subordinate=0,development_paid=0),
        budgets=dict(wire_input_bytes_per_call=24576,conservative_input_token_reserve_per_call=INPUT_UPPER,
            output_tokens_per_call=OUTPUT_UPPER,output_tokens_total=MAX_CALLS*OUTPUT_UPPER,
            per_call_timeout_seconds=30,whole_batch_timeout_seconds=1800,context_characters_per_arm=16384,
            persistent_bytes_per_arm=134217728,local_worker_cpu_seconds=120,local_worker_wall_timeout_seconds=150,
            local_worker_address_space_bytes=1073741824,local_worker_parallelism=1,
            scope='Whole-batch deadline includes indexing, cold queries and provider/judge work; reaching it leaves an incomplete result, never replacement cases.'),
        tariff=dict(input_usd_per_million=str(RATE_IN),output_usd_per_million=str(RATE_OUT),
            conservative_upper_usd=str(TARIFF_BOUND),hard_cap_usd=str(CAP),invoice='UNKNOWN',
            primary_source='https://nebius.com/services/token-factory/models/nvidia-nemotron-models-inference',
            freshness='Recheck exact rates and model bounds before future purpose-specific admission.'),
        data_sent='Only declared public synthetic benchmark historical context/question to reader; question/reference/committed answer to isolated judge. No production, credentials, private evaluator IDs/types or hidden rubrics to contestants.',
        termination='Count timed-out/ambiguous requests at full reserved cost and stop; no retry, replacement, fallback or automatic additional batch. Wrong answers remain failures.',
        error_policy='No credential lookup or dispatch before exact data/source/purpose/OS admission. Preserve incomplete results; never claim missing usage is zero.',
        disclosure='Small clustered pilot only; no superiority or official score from offline wiring. All answer hashes committed before blind grading; no feedback assimilated into held-out memory.',
        approval='NOT_REQUESTED; no approval artifact created. Prior V2 permits remain spent and inapplicable.',
        execution_transport='NO_PROVIDER_ENTRYPOINT_WHILE_EXTERNAL_INPUT_CONTRACT_BLOCKED',
        required_next_connection='Resolve faithful admitted multimodal/text-sufficiency and source-capacity scope, freeze actual disjoint manifests, then source-bind a new-purpose gateway and fresh exact owner admission.',
        production_connected=False,alpha_changed=False,provider_calls=0,evidence_pins=pins)
    return {**quote,'proposal_sha256':digest(quote)}

def preflight(quote):
    require(quote.get('schema')=='se6-custom-memory-paid-proposal-v1','PAID_PROPOSAL_SCHEMA')
    body={k:v for k,v in quote.items() if k!='proposal_sha256'}
    require(quote.get('proposal_sha256')==digest(body),'PAID_PROPOSAL_HASH')
    require(not quote.get('blockers'),'EXTERNAL_DATA_CONTRACT_BLOCKED_BEFORE_CREDENTIALS_OR_NETWORK')
    raise ValueError('FRESH_PURPOSE_SPECIFIC_GATEWAY_AND_OWNER_ADMISSION_REQUIRED')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=['prepare','preflight'])
    parser.add_argument('--readiness',type=Path);parser.add_argument('--source-manifest',type=Path)
    parser.add_argument('--official-evaluator',type=Path);parser.add_argument('--os-scope',type=Path)
    parser.add_argument('--proposal',type=Path);parser.add_argument('--out',type=Path)
    args=parser.parse_args()
    if args.operation=='prepare':
        require(args.readiness is not None and args.out is not None,'PREPARATION_INPUTS_REQUIRED')
        value=preparation(json.loads(args.readiness.read_bytes()),source_manifest_path=args.source_manifest,
            official_evaluator_path=args.official_evaluator,os_scope_path=args.os_scope)
        args.out.parent.mkdir(parents=True,exist_ok=True)
        with args.out.open('x',encoding='utf-8') as file:json.dump(value,file,indent=2);file.write('\n')
        print(json.dumps(dict(status=value['status'],blockers=value['blockers'],proposal_sha256=value['proposal_sha256'],provider_calls=0)))
    else:
        require(args.proposal is not None,'PROPOSAL_REQUIRED')
        try:preflight(json.loads(args.proposal.read_bytes()))
        except ValueError as error:
            print(json.dumps(dict(status='BLOCKED',reason=str(error),provider_calls=0,credential_lookups=0)))
            raise SystemExit(2)
if __name__=='__main__':main()
