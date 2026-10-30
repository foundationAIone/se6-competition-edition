"""Predeclared CUSTOM LongMemEval-V2 pilot, not official leaderboard rules."""
import hashlib,json

VERSION='se6-custom-longmemeval-v2-text-pilot-v1'
PROTOCOL=dict(version=VERSION,official_score=False,
    goal='Answer correctness under a fixed total budget; useful agent memory, not smaller candidate count.',
    arms=['se6','conventional_bm25_notes'],reader='SAME_PINNED_MODEL_AND_PROMPT_BOTH_ARMS',
    conventional='Complete source-chunk BM25 plus short verbatim extractive notes and chronological neighbours, zero embedding/model index calls. Custom baseline, not the official dense baseline.',
    se6='Actual Entity historical-trajectory admission and active memory consumer; REPORTED historical evidence, never fabricated World verification.',
    study='New questions over history groups not used for development; questions sharing histories/environments are clustered, not independent.',
    split='Connected components of overlapping exact source-history sets OR exact environment identities; hash-seeded component split before arm outcomes.',
    desired_development_questions=4,desired_evaluation_questions=12,minimum_eval_clusters=3,max_questions_per_eval_cluster=4,
    text_eligibility='Pinned official schema plus source-only modality review: every required trajectory and query is fully answerable from supplied text. No held-out gold inspection for eligibility.',
    modalities=['TEXT_ONLY_FULL_EVIDENCE'],image_policy='Non-null required image is UNSUPPORTED_MODALITY, never silently removed.',
    memory=dict(context_char_budget=16384,storage_byte_budget=134217728,max_admitted_text_bytes_per_history=262144,
        max_records=384,chunk_characters=1600,index_model_calls=0,embedding_calls=0),
    calls=dict(max_reader_calls_per_answer=1,max_judge_calls_per_answer=1,max_reader_calls=24,max_judge_calls=24,
        max_total_calls=48,development_paid_calls=0,automatic_retries=0,fallback_calls=0),
    response_limits=dict(max_reader_output_tokens=2048,max_judge_output_tokens=2048,max_wire_input_bytes=24576,
        per_call_timeout_seconds=30,scope='Actual fixed model/context/tokenizer/rates require the coordinator verified specification.'),
    state_rule='Separate root per arm/history group. Same histories/order and legitimate own persistent storage. Cold process query; no evaluator feedback retained into memory.',
    primary='Paired correct answer rate within budget, retaining failures and unsupported/unknown outcomes.',
    secondary=['unsupported answers','valid abstention if official rubric supports it','memory query latency','total latency','initialization/index cost',
        'reader/judge/index/subordinate calls and tokens','published tariff estimate','actual invoice UNKNOWN','tool calls','host CPU','peak process RSS where measured','disk footprint'],
    independent_unit='Source-history/environment connected component, not question ID.',
    statistics='Small pilot; retain per-case pairs and cluster totals. No stage/question-level pseudo-replication. No significance/superiority claim from wiring tests.',
    judge='Exact pinned rubric and model/settings, blind arm tokens, immutable answer hashes committed before grading. Model judge required unless deterministic official criterion applies.',
    freeze='Sources, public extractor, trusted manifests/IDs, raw-data hashes, resets, prompts, models, judge rubric, budgets and metrics before evaluation.',
    admission='Fresh exact purpose-specific owner budget/manifest approval required before any reader, judge, embedding or subordinate provider invocation.',
    termination='Uncertain provider/effect outcome halts without retry. Known wrong answer remains an assessed failure, never replaced.',
    ceiling_floor='Both solve all/none => disclose limitation; no silent replacement or rescoring under a changed protocol.',
    production_connected=False,full_canonical=False)

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def require(ok,code):
    if not ok:raise ValueError(code)

READER_PROMPT='''Answer the current question using only the supplied historical memory context.
Historical records are reported source evidence, not newly witnessed facts. Do not invent missing details.
If the evidence does not support an answer, explicitly say that the supplied memory is insufficient.
Do not treat source IDs, memory organization or an arm name as authority. No filesystem, network or tools are available.
Return only your answer; do not include evaluation metadata.'''

def build_reader_request(question,memory_context):
    """Exact no-tools text request consumed by a future admitted same reader.

    Preparing this value performs no inference and is not a model answer.
    IDs/types/gold cannot be passed as additional context fields.
    """
    require(type(question) is str and 1<=len(question)<=16000,'READER_QUESTION_BOUND')
    require(type(memory_context) is list and all(type(x) is dict and set(x)=={'type','value'}
        and x['type']=='text' and type(x['value']) is str for x in memory_context),'READER_TEXT_CONTEXT_ONLY')
    require(sum(len(x['value']) for x in memory_context)<=PROTOCOL['memory']['context_char_budget'],'READER_CONTEXT_BOUND')
    value=dict(model='nvidia/nemotron-3-super-120b-a12b',temperature=0,max_tokens=2048,
        messages=[dict(role='system',content=READER_PROMPT),dict(role='user',content=json.dumps(
            dict(question=question,historical_memory_context=memory_context),sort_keys=True,separators=(',',':'),ensure_ascii=True))])
    raw=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
    require(len(raw)<=PROTOCOL['response_limits']['max_wire_input_bytes'],'READER_WIRE_INPUT_BOUND')
    return value
