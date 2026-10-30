"""Versioned transport-outcome recovery; no inference and no semantic grading.

Historical old STOP/outcome files are read-only inputs. Separate reasoning is
accounted/digested, never substituted for the final answer or reprinted.
"""
from pathlib import Path
from datetime import datetime,timezone
from decimal import Decimal
import hashlib,json,os
from hosted_judge.v8_run_both import exclusive,encoded,file_hash,read,require

MODEL='nvidia/nemotron-3-super-120b-a12b'
ENDPOINT='https://api.tokenfactory.nebius.com/v1/chat/completions'
POLICY='se6-item-aware-saved-provider-outcomes-v2'

def strict_json(raw):
    def unique(rows):
        result={}
        for key,value in rows:
            if key in result:raise ValueError('DUPLICATE_PROVIDER_JSON_FIELD')
            result[key]=value
        return result
    return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('NONFINITE_PROVIDER_JSON')))

def classify(raw,*,expected_model=MODEL,max_output_tokens=2048):
    raw=raw.encode() if isinstance(raw,str) else raw
    base=dict(policy=POLICY,provider_raw_sha256=hashlib.sha256(raw).hexdigest(),final_text='',reasoning_fields={},
        usage=None,finish_reason=None,semantic_correctness='UNMEASURED',retry_permitted=False)
    try:
        value=strict_json(raw)
        require(type(value) is dict and type(value.get('choices')) is list and len(value['choices'])==1,'PROVIDER_CAPTURE_SCHEMA')
        require(value.get('model')==expected_model,'PROVIDER_MODEL_IDENTITY_MISMATCH')
        choice=value['choices'][0];message=choice['message'];require(type(message) is dict,'PROVIDER_MESSAGE_SCHEMA')
        usage=value.get('usage');base['usage']=usage
        require(type(usage) is dict and all(type(usage.get(k)) is int and usage[k]>=0 for k in ['prompt_tokens','completion_tokens','total_tokens']),
            'PROVIDER_USAGE_UNKNOWN_OR_INVALID')
        require(usage['prompt_tokens']<=262144 and usage['completion_tokens']<=max_output_tokens
            and usage['total_tokens']==usage['prompt_tokens']+usage['completion_tokens'],'PROVIDER_USAGE_OUTSIDE_RESERVED_CAP')
        details=usage.get('completion_tokens_details')
        require(details is None or type(details) is dict,'PROVIDER_REASONING_ACCOUNTING_INVALID')
        reasoning=details.get('reasoning_tokens') if isinstance(details,dict) else None
        require(reasoning is None or type(reasoning) is int and 0<=reasoning<=usage['completion_tokens'],'PROVIDER_REASONING_ACCOUNTING_INVALID')
        text=message.get('content')
        require(text is None or type(text) is str,'PROVIDER_FINAL_CONTENT_SCHEMA')
        base['final_text']=text or '';base['final_text_sha256']=hashlib.sha256((text or '').encode()).hexdigest()
        base['final_content_characters']=len(text or '')
        for name in ['reasoning','reasoning_content']:
            content=message.get(name)
            if isinstance(content,str) and content:
                base['reasoning_fields'][name]=dict(characters=len(content),sha256=hashlib.sha256(content.encode()).hexdigest())
        finish=choice.get('finish_reason');base['finish_reason']=finish
        base['reported_reasoning_tokens']=reasoning
        base['reported_non_reasoning_completion_tokens']=usage['completion_tokens']-reasoning if reasoning is not None else None
        base['tariff_estimate_usd']=str((Decimal(usage['prompt_tokens'])*Decimal('.30')+Decimal(usage['completion_tokens'])*Decimal('.90'))/Decimal(1000000))
        base['actual_invoice_usd']=None
        if finish=='length':status,code='ITEM_INCOMPLETE','LENGTH_CAP_REACHED'
        elif message.get('tool_calls') or message.get('function_call'):status,code='ITEM_INCOMPLETE','UNSUPPORTED_TOOL_RESPONSE_NO_TOOL_EXECUTED'
        elif message.get('refusal') or finish=='content_filter':status,code='ITEM_INCOMPLETE','PROVIDER_REFUSAL'
        elif finish!='stop':status,code='GLOBAL_STOP','UNRESOLVED_OR_NONTERMINAL_PROVIDER_COMPLETION'
        elif not (text or '').strip():status,code='ITEM_INCOMPLETE','EMPTY_FINAL_CONTENT_REASONING_NOT_AN_ANSWER'
        else:status,code='COMPLETE','KNOWN_TERMINAL_FINAL_CONTENT'
        return {**base,'status':status,'reason':code,'eligible_for_saved_answer_grading':status=='COMPLETE'}
    except (ValueError,KeyError,TypeError,IndexError) as error:
        code=str(error) if str(error).isupper() and len(str(error))<160 else 'MALFORMED_OR_AMBIGUOUS_PROVIDER_CAPTURE'
        return {**base,'status':'GLOBAL_STOP','reason':code,'eligible_for_saved_answer_grading':False,
            'cost_policy':'Unknown/invalid usage is not zero; reserve the entire attempted call.'}

def binary_judge_result(classified):
    if classified['status']!='COMPLETE':return dict(status=classified['status'],label=None,reason=classified['reason'])
    text=classified['final_text'].strip().casefold()
    if text in {'yes','yes.'}:return dict(status='GRADED',label=True,reason='SEMANTIC_MODEL_JUDGE_YES')
    if text in {'no','no.'}:return dict(status='GRADED',label=False,reason='SEMANTIC_MODEL_JUDGE_NO')
    return dict(status='ITEM_INCOMPLETE',label=None,reason='JUDGE_DID_NOT_RETURN_UNAMBIGUOUS_BINARY_DECISION')

class ResponseJournal:
    """Intent/raw/outcome ledger. Any existing intent forbids duplicate inference."""
    def __init__(self,root,*,max_output_tokens):self.root=Path(root);self.max_output_tokens=max_output_tokens
    def reserve(self,request_sha256):
        self.root.mkdir(parents=True,exist_ok=True)
        exclusive(self.root/'intent.json',dict(policy=POLICY,request_sha256=request_sha256,max_output_tokens=self.max_output_tokens))
    def inference_allowed(self):return not (self.root/'intent.json').exists()
    def capture(self,raw):
        require((self.root/'intent.json').is_file(),'RESPONSE_WITHOUT_REGISTERED_INTENT')
        with (self.root/'provider.json').open('xb') as file:file.write(raw);file.flush();os.fsync(file.fileno())
    def recover(self):
        require((self.root/'intent.json').is_file(),'NO_PRIOR_INFERENCE_INTENT')
        raw=self.root/'provider.json'
        if not raw.is_file():return dict(status='GLOBAL_STOP',reason='INTENT_WITHOUT_CAPTURE_UNCERTAIN_NO_RETRY',retry_permitted=False)
        result=classify(raw.read_bytes(),max_output_tokens=self.max_output_tokens)
        result['request_sha256']=read(self.root/'intent.json')['request_sha256']
        path=self.root/'outcome-v2.json'
        if path.exists():require(read(path)==result,'RECOVERED_OUTCOME_INTEGRITY_MISMATCH')
        else:exclusive(path,result)
        return result

def inventory(old_root,out):
    old=Path(old_root).resolve(strict=True);out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    spec_path=old/'qa-prepared/QA_SPEC.json';spec=read(spec_path)
    require(spec['model']==MODEL and spec['endpoint']==ENDPOINT,'HISTORICAL_MODEL_ENDPOINT_BINDING')
    claim=old/'qa-provider-claims/LIVE';all_rows=[];attempted=[]
    for case in spec['cases']:
        for arm in ['se6','bm25']:
            cell=case['case_id']+'-reader-'+arm;directory=claim/'calls'/cell
            row=dict(cell=cell,case_id=case['case_id'],arm=arm,kind='reader',status='UNATTEMPTED',source_files={})
            if (directory/'intent.json').is_file():
                intent=read(directory/'intent.json');raw=(directory/'provider.json').read_bytes()
                request_path=directory/'request.json';request=strict_json(request_path.read_bytes())
                prepared=read(directory/'prepared.json');historical=read(directory/'outcome.json')
                require(file_hash(request_path)==intent['wire_sha256']==prepared['wire_sha256'],'HISTORICAL_WIRE_HASH_MISMATCH')
                require(request.get('model')==MODEL and request.get('max_tokens')==2048 and request.get('temperature')==0
                    and request.get('stream') is False,'HISTORICAL_REQUEST_SETTINGS_CHANGED')
                classification=classify(raw,max_output_tokens=request['max_tokens'])
                expected=historical.get('response',historical.get('partial_text',''))
                require(expected==classification['final_text'],'HISTORICAL_FINAL_OUTPUT_CAPTURE_MISMATCH')
                row.update(status=classification['status'],classification=classification,at_utc=intent['at_utc'],
                    endpoint=spec['endpoint'],request_settings={k:v for k,v in request.items() if k!='messages'},
                    absent_request_controls=[k for k in ['stop','response_format','reasoning_effort','chat_template_kwargs','nvext'] if k not in request],
                    historical_outcome_status=historical['status'],input_sha256=file_hash(request_path),
                    output_sha256=classification['final_text_sha256'],provider_raw_sha256=file_hash(directory/'provider.json'),
                    source_directory=str(directory),source_files={name:file_hash(directory/name) for name in
                        ['intent.json','prepared.json','request.json','provider.json','outcome.json']})
                attempted.append(row)
            all_rows.append(row)
    ordered=sorted(attempted,key=lambda r:datetime.fromisoformat(r['at_utc']))
    for i,row in enumerate(ordered,1):row['actual_request_number']=i
    paired=[]
    for case in spec['cases']:
        rows=[r for r in all_rows if r['case_id']==case['case_id']]
        paired.append(dict(case_id=case['case_id'],statuses={r['arm']:r['status'] for r in rows},
            complete_pair=all(r['status']=='COMPLETE' for r in rows)))
    summary=dict(policy=POLICY,status='HISTORICAL_READERS_INVENTORIED_NOT_GRADED',source_spec_sha256=file_hash(spec_path),
        planned_readers=len(all_rows),attempted_readers=len(attempted),complete=sum(r['status']=='COMPLETE' for r in all_rows),
        incomplete=sum(r['status']=='ITEM_INCOMPLETE' for r in all_rows),unattempted=sum(r['status']=='UNATTEMPTED' for r in all_rows),
        complete_pairs=sum(p['complete_pair'] for p in paired),paired_coverage=paired,
        actual_grader_intents=len(list((claim/'calls').glob('*-judge-*/intent.json'))),
        historical_stop_preserved=True,historical_stop_sha256=file_hash(claim/'STOP.json'),
        request31=next((r for r in ordered if r['actual_request_number']==31),None),
        historical_usage=dict(prompt_tokens=sum(r['classification']['usage']['prompt_tokens'] for r in attempted),
            completion_tokens=sum(r['classification']['usage']['completion_tokens'] for r in attempted),
            tariff_estimate_usd=str(sum((Decimal(r['classification']['tariff_estimate_usd']) for r in attempted),Decimal(0))),
            incomplete_usage_counted=True,actual_invoice_usd=None),
        new_provider_calls=0,semantic_grades='NONE; correctness cannot be inferred from completion, source overlap or Codex assessment.',
        old_stop_analysis='Approved strict parser rejected length completion; approved global40-reader barrier and STOP then prevented any grading. This history is unchanged.',
        new_policy='Known item incompleteness is separated from global authority, source integrity, unknown cost or unresolved transport failure. Recovery never reissues a claimed inference.')
    exclusive(out/'INVENTORY_PRIVATE.json',dict(summary=summary,items=all_rows))
    public={k:v for k,v in summary.items() if k not in {'request31','paired_coverage'}}
    public['request31']={k:v for k,v in summary['request31'].items() if k not in {'classification','source_directory','source_files'}}
    public['request31']['outcome']={k:v for k,v in summary['request31']['classification'].items()
        if k not in {'final_text','reasoning_fields'}}
    exclusive(out/'INVENTORY_SUMMARY.json',public)
    print(json.dumps({k:public[k] for k in ['complete','incomplete','unattempted','complete_pairs','actual_grader_intents','new_provider_calls']}))
    return summary
