"""Attach exact prepared reader inputs to the EXISTING cold-query trace.

No namespace, memory, World or provider operation is repeated.
"""
from pathlib import Path
import argparse,hashlib,json
from .protocol import build_reader_request,digest,require,READER_PROMPT

def run(scope_path):
    root=Path(scope_path).resolve(strict=True)
    result=json.loads((root/'RESULT.json').read_bytes())
    require(result['status']=='VERIFIED_SYNTHETIC_CONTRACT_AND_REAL_OS_BOUNDARY','EXISTING_OS_SCOPE_PROOF_REQUIRED')
    question='Which tab contains the Export PDF button?'
    rows=[]
    for arm in ['conventional','se6']:
        cold=json.loads((root/(arm+'-query.json')).read_bytes())
        context=cold['context'];payload=build_reader_request(question,context)
        decoded=json.loads(payload['messages'][1]['content'])
        require(decoded['historical_memory_context']==context and decoded['question']==question,'EXACT_COLD_CONTEXT_CONSUMPTION')
        if arm=='se6':require(cold['trace']['query_sha256']==digest(question),'ACTUAL_SE6_QUERY_BINDING')
        body=root/(arm+'-prepared-reader-input.json')
        with body.open('x',encoding='utf-8') as file:json.dump(payload,file,indent=2);file.write('\n')
        rows.append(dict(arm=arm,cold_pid=cold['pid'],cold_record_sha256=hashlib.sha256((root/(arm+'-query.json')).read_bytes()).hexdigest(),
            cold_context_sha256=digest(context),prepared_payload_sha256=digest(payload),saved_body_sha256=hashlib.sha256(body.read_bytes()).hexdigest(),
            consumed_memory_refs=cold['trace'].get('source_refs',cold['trace'].get('consumed',[])),
            exact_context_reused=True,settings={k:payload[k] for k in ['model','temperature','max_tokens']},
            question_sha256=digest(question),system_prompt_sha256=digest(READER_PROMPT)))
    require(rows[0]['settings']==rows[1]['settings'] and rows[0]['question_sha256']==rows[1]['question_sha256']
        and rows[0]['system_prompt_sha256']==rows[1]['system_prompt_sha256'],'PAIRED_READER_SETTINGS_IDENTICAL')
    out=dict(status='VERIFIED_EXACT_PREPARED_READER_INPUT_NOT_INFERENCE',scope_result_sha256=hashlib.sha256((root/'RESULT.json').read_bytes()).hexdigest(),
        provider_calls=0,reader_invocations=0,model_answers='NOT_EXECUTED',benchmark_score='NONE',rows=rows,
        limitation='A prepared answer-agent input proves context wiring, not that a model consumed it or answered correctly.')
    with (root/'READER_INPUT_EVIDENCE.json').open('x',encoding='utf-8') as file:json.dump(out,file,indent=2);file.write('\n')
    print(json.dumps(dict(status=out['status'],provider_calls=0,rows=len(rows))))
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--scope',required=True);args=parser.parse_args();run(args.scope)
