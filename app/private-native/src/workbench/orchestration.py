"""Bounded host composition of the existing registry and canonical adapters.

This is not an SE engine, model interpreter, calculator or tool authority.
Unparsed text is retained as a model-only subproblem, never silently dropped.
"""
from copy import deepcopy
import hashlib
import json
import re
import time

from .auto_intake import MAX_ACTIONS, MAX_CONTEXT_BYTES, NATIVE_ROUTES, digest, question, registry
from .config import Settings
from .core_revisions import SOURCE_HASHES, load_core, verify_traces
from .linear_admission import equation
from . import business_arithmetic as business

CONTRACT = 'se6-unified-orchestration-v1'
MAX_NODES = 12
ROUTES = {'LINEAR_MATH': 'linear_math', 'LINEAR_DERIVATION': 'linear_math',
          'RELATIONAL': 'relational', 'VERIFIED_MIRROR': 'verified_mirror',
          'NATIVE_MATH_FIXTURE': 'native_math_fixture', 'EVIDENCE_PROJECTION': 'evidence_projection',
          'DIRECT_MODEL': 'direct_model', 'HOST_BUSINESS':'business_arithmetic', 'HOST_BUDGET':'business_arithmetic'}


def request(text):
    # Wording normalization only. Candidate mathematics still comes exclusively
    # from validated public equalities and the existing coefficient search.
    text = re.sub(r'^Derive and verify\s+', 'Derive ', text.strip(), flags=re.I)
    text = re.sub(r'^Find\s+(?=(?:a |the )?(?:linear |mathematical )?(?:relation|relationship))',
                  'Derive ', text, flags=re.I)
    return text


def allocation(text):
    """Bounded two-class count/resource prose -> public affine premises.

    No amounts or answers are fixture-specific. This does not implement money,
    recommendations, signature verification or code execution.
    """
    rates=list(re.finditer(r'^([A-Za-z][A-Za-z0-9_]{0,31}):\s*(\d+(?:\.\d+)?)\s+([A-Za-z]+-hours)\b.*$',text,re.M))
    total=re.search(r'\bcompleted (\d+) jobs\b',text,re.I)
    original=re.search(r'\boriginal \w+ recorded (\d+(?:\.\d+)?) ([A-Za-z]+-hours)\b',text,re.I)
    correction=re.search(r'\bcorrection showing (\d+(?:\.\d+)?) ([A-Za-z]+-hours)\b',text,re.I)
    if len(rates)!=2 or not total or not original:
        return None
    names=[m[1].lower() for m in rates]
    if len(set(names))!=2 or not 0<int(total[1])<128 or any(m[3].lower()!=original[2].lower() for m in rates):
        return None
    spans=[[m.start(),m.end()] for m in (*rates,total,original)]
    a,b=names
    equations=f'E1: {a}+{b}={total[1]}\nE2: {rates[0][2]}{a}+{rates[1][2]}{b}={original[1]}\nVariables are integers between 0 and {total[1]}.'
    result=[{'input':equations+f'\nDerive a relation involving {a}.','source_spans':spans,'route':'PENDING_MATH'},
            {'input':f'Derive a relation involving {b}.','source_spans':spans,'route':'PENDING_MATH'}]
    if correction:
        if correction[2].lower()!=original[2].lower():
            return None
        refs=spans+[[correction.start(),correction.end()]]
        result.extend([{'input':f'Correct E2 to {rates[0][2]}{a}+{rates[1][2]}{b}={correction[1]}.\nDerive a relation involving {a}.',
                        'source_spans':refs,'route':'PENDING_MATH'},
                       {'input':f'Derive a relation involving {b}.','source_spans':refs,'route':'PENDING_MATH'}])
    # Full residual remains available only to an authorized model; financial,
    # business and code work is not silently claimed by this affine mapping.
    count=len(result)
    # These nodes disclose missing contracts; no new finance/recommendation or
    # executable-code engine is registered under a native label.
    requests=[('financial_calculations',r'^(?:\d+\. )?Calculate .*$',None,
               'No registered native financial calculation/verification adapter.'),
              ('budget_comparison',r'^(?:\d+\. )?Determine whether .*budget.*$','financial_calculations',
               'Budget decision depends on verified financial calculations.'),
              ('business_recommendation',r'^(?:\d+\. )?Recommend .*$','budget_comparison',
               'Recommendations require judgment; model output is UNVERIFIED.'),
              ('code_generation_validation',r'^(?:\d+\. )?Provide .*Python.*$','financial_calculations',
               'No registered authorized code execution adapter; code must not be reported executed.')]
    identified={}
    for purpose,pattern,predecessor,limit in requests:
        match=re.search(pattern,text,re.M|re.I)
        if not match:
            continue  # Optional business/code work cannot gate count mathematics.
        deps=[identified[predecessor]] if predecessor in identified else list(range(1,count+1))
        identified[purpose]=len(result)+1
        result.append({'input':match[0],'source_spans':[[match.start(),match.end()]],
                       'route':'DIRECT_MODEL','purpose':purpose,'requires_nodes':deps,'native_limit':limit})
    if not identified:
        result.append({'input':text,'source_spans':[[0,len(text)]],'route':'DIRECT_MODEL',
                       'purpose':'unparsed_remainder','native_limit':'Only bounded count/resource premises were mapped; remaining prose has no general native interpretation contract.'})
    return result


class Orchestrator:
    def __init__(self, auto):
        self.auto = auto

    def _restore(self, checkpoint, task_id=None):
        if checkpoint is None:
            return None
        if (checkpoint.get('schema') != CONTRACT or checkpoint.get('source_hashes') != SOURCE_HASHES
                or checkpoint.get('checkpoint_hash') != digest({k:v for k,v in checkpoint.items() if k != 'checkpoint_hash'})
                or (task_id and checkpoint.get('task_id') != task_id)):
            raise ValueError('Orchestration checkpoint identity/source/content mismatch')
        return checkpoint.get('auto_checkpoint')

    def decompose(self, text, checkpoint=None):
        question(text)
        old = self._restore(checkpoint)
        whole = self.auto.classify(text, old)
        if whole['route'] in ROUTES and whole['route'] != 'DIRECT_MODEL':
            return [{'input':text, 'source_spans':[[0,len(text)]], 'route':whole['route']}]
        previous=(checkpoint or {}).get('business')
        try:
            parsed_business=business.parse(text,previous)
            business_error=None
        except ValueError as exc:
            parsed_business=None;business_error=str(exc)
        if parsed_business and parsed_business['mode']!='INITIAL':
            parts=[]
            if parsed_business['mode']=='HOURS_CORRECTION':
                names=parsed_business['classes']
                equality='+'.join(parsed_business['hours_per_job'][n]+'*'+n for n in names)+'='+parsed_business['hours']['corrected']
                parts=[{'input':'Correct E2 to '+equality+'.\nDerive a relation involving '+names[0]+'.',
                        'source_spans':[[0,len(text)]],'route':'PENDING_MATH'},
                       {'input':'Derive a relation involving '+names[1]+'.','source_spans':[[0,len(text)]],'route':'PENDING_MATH'}]
            dependencies=list(range(1,len(parts)+1))
            parts.append({'input':text,'source_spans':[[0,len(text)]],'route':'HOST_BUSINESS',
                'purpose':'financial_calculations','business_inputs':parsed_business,'requires_nodes':dependencies})
            parts.append({'input':text,'source_spans':[[0,len(text)]],'route':'HOST_BUDGET',
                'purpose':'budget_comparison','requires_nodes':[len(parts)]})
            return parts
        mapped=allocation(text)
        if mapped:
            for part in mapped:
                if part.get('purpose') in ('financial_calculations','budget_comparison'):
                    if parsed_business:
                        part['route']='HOST_BUSINESS' if part['purpose']=='financial_calculations' else 'HOST_BUDGET'
                        part['business_inputs']=parsed_business
                        part.pop('native_limit',None)
                    elif business_error:
                        part['native_limit']='Monetary admission rejected: '+business_error
            return mapped
        # Preserve exact source offsets. Only bounded equality/request/relational
        # lines are mapped. Every other nonempty span remains explicit.
        parts, residual, block, spans = [], [], [], []
        def flush():
            if not block:
                return
            body = '\n'.join(block)
            if not any(re.match(r'Derive\b', row, re.I) for row in block):
                names = set()
                try:
                    for row in block:
                        if '=' in row:
                            eq, _ = equation(re.sub(r'^\w+:\s*', '', row), load_core())
                            names.update(dict(eq.coefficients))
                except ValueError:
                    names = set()
                # An assignment is requested only as a candidate singleton row
                # consequence. There is no general solver or inferred answer.
                if names:
                    for i, name in enumerate(sorted(names)):
                        parts.append({'input': (body+'\n' if i == 0 else '')+
                            'Derive a relation involving '+name+'.',
                            'source_spans':deepcopy(spans), 'route':'PENDING_MATH'})
                else:
                    residual.extend(spans)
            else:
                parts.append({'input':body, 'source_spans':deepcopy(spans), 'route':'PENDING_MATH'})
            block.clear(); spans.clear()
        offset = 0
        for line in text.splitlines(keepends=True):
            row = line.strip(); span = [offset, offset+len(line)]; offset += len(line)
            normalized = request(row)
            if re.match(r'Correct \w+ to ', row, re.I):
                flush(); block.append(row); spans.append(span)
            elif '=' in row and not re.search(r'[;`{}]', row):
                if block and any(re.match(r'Derive\b', r, re.I) for r in block):
                    flush()
                block.append(row); spans.append(span)
            elif re.match(r'Derive\b', normalized, re.I):
                block.append(normalized); spans.append(span); flush()
            elif re.fullmatch(r'Given(?:(?: the| these)?(?: linear)? equations)?\s*:', row, re.I) or re.match(r'Variables are integers ',row,re.I):
                block.append(row); spans.append(span)
            elif row and self.auto.classify(row, old)['route'] == 'RELATIONAL':
                flush(); parts.append({'input':row, 'source_spans':[span], 'route':'RELATIONAL'})
            elif row:
                residual.append(span)
        flush()
        if residual:
            parts.append({'input':''.join(text[a:b] for a,b in residual), 'source_spans':residual,
                          'route':'DIRECT_MODEL'})
        return parts or [{'input':text,'source_spans':[[0,len(text)]],'route':'DIRECT_MODEL'}]

    def plan(self, text, settings, records, credentials, checkpoint=None):
        base = self.auto.plan(text, settings, records, credentials)
        capabilities = registry(self.auto.integrations)  # The existing registry only.
        available = {row['id']:row for row in capabilities}
        parts = self.decompose(text, checkpoint)
        if len(parts) > MAX_NODES:
            raise ValueError('Bounded subproblem limit exceeded; no execution or escalation')
        nodes, last_math, last_relation = [], None, None
        old = self._restore(checkpoint)
        for part in parts:
            ident = 'n'+str(len(nodes)+1)
            selected = {'route':part['route'],'limitations':['Deterministic HOST arithmetic, not a canonical SE operator.']} if part['route'].startswith('HOST_') else self.auto.classify(part['input'], old)
            deferred = part['route'] == 'PENDING_MATH' and last_math is not None
            route = 'LINEAR_DERIVATION' if deferred else selected['route']
            capability = ROUTES.get(route)
            deps = [last_math] if route in NATIVE_ROUTES and last_math else []
            if part.get('requires_nodes'):
                deps=['n'+str(i) for i in part['requires_nodes']]
            if route == 'RELATIONAL' and last_relation:
                deps = [last_relation]
            nodes.append({**part, 'id':ident, 'route':route, 'depends_on':deps,
                'capability':capability, 'admission':'AFTER_PREDECESSOR' if deferred else 'VALIDATED',
                'connected':bool(capability and available[capability]['connected']),
                'limitations': selected.get('limitations',[]), 'blocker':selected.get('blocker')})
            if route in NATIVE_ROUTES:
                last_math = ident
            if route == 'RELATIONAL':
                last_relation = ident
        value = {'schema':CONTRACT, 'original_question':text, 'question_sha256':hashlib.sha256(text.encode()).hexdigest(),
            'nodes':nodes, 'capabilities':capabilities, 'settings':base['settings'], 'source_hashes':dict(SOURCE_HASHES),
            'provider_profile':base['provider_profile'], 'provider_ready':base['provider_profile']['status']=='VERIFIED_COMPLETION_PROFILE',
            'resources':base['resources'], 'previous_checkpoint_hash':(checkpoint or {}).get('checkpoint_hash'),
            'plan_only':True, 'provider_calls':0, 'output_tokens_reserved':0,
            'model_interpretation':'Not implemented; unparsed text remains model-only. No generated task schema is trusted.',
            'authority':'Explicit RUN permits bounded task-local registered operations only; provider pair needs existing readiness and quotas.'}
        value['plan_sha256'] = digest(value)
        return value

    def advance(self, task_id, round_id, text, checkpoint, plan):
        started = time.perf_counter()
        if (plan.get('schema') != CONTRACT or plan.get('original_question') != text
                or plan.get('plan_sha256') != digest({k:v for k,v in plan.items() if k!='plan_sha256'})
                or plan.get('source_hashes') != SOURCE_HASHES
                or plan.get('previous_checkpoint_hash') != (checkpoint or {}).get('checkpoint_hash')):
            raise ValueError('Orchestration plan/question/source/ancestry binding mismatch')
        # Reconstruct decomposition to reject forged node schemas/inputs even
        # if an untrusted caller recomputed a content hash.
        if [dict(input=n['input'],source_spans=n['source_spans']) for n in plan['nodes']] != [
                dict(input=n['input'],source_spans=n['source_spans']) for n in self.decompose(text,checkpoint)]:
            raise ValueError('Subproblem provenance mismatch')
        rebuilt=self.plan(text,Settings.parse(plan['settings']),[],False,checkpoint)
        if plan['nodes'] != rebuilt['nodes']:
            raise ValueError('Subproblem graph/capability/admission mismatch')
        cp = deepcopy(self._restore(checkpoint,task_id))
        book=deepcopy((checkpoint or {}).get('business'));business_projection=None;host_seconds=0.0
        outcomes, receipts, traces, contexts = [], [], [], []
        completed = set()
        for node in plan['nodes']:
            result = {'id':node['id'], 'route':node['route'], 'depends_on':node['depends_on'],
                      'source_spans':node['source_spans'], 'purpose':node.get('purpose'), 'status':'BLOCKED', 'result':None}
            if any(d not in completed for d in node['depends_on']):
                result['blocker'] = 'Required predecessor did not verify; independent subproblems may continue.'
            elif not node['connected'] or node['route'] == 'UNSUPPORTED':
                result['blocker'] = node.get('blocker') or 'Capability unavailable; no fabricated operation.'
            elif node['route'] == 'DIRECT_MODEL':
                result['blocker'] = (node.get('native_limit','No native contract for this subproblem.')+' '+
                    (plan['provider_profile']['blocker'] or 'Requires the matched authorized provider pair; model output remains UNVERIFIED.'))
            elif node['route'] in ('HOST_BUSINESS','HOST_BUDGET'):
                host_started=time.perf_counter()
                try:
                    if node['route']=='HOST_BUSINESS':
                        inputs=node['business_inputs']
                        bindings=business.canonical_bindings(inputs,cp,outcomes,book)
                        book,shown=business.execute(inputs,bindings,book,auto_checkpoint=cp)
                        business.verify_host_book(book,cp)
                        business_projection=shown
                    else:
                        if book is None:raise ValueError('No verified financial result for budget comparison')
                        audit=business.verify_host_book(book,cp)
                        shown={'kind':'DETERMINISTIC_HOST_CALCULATION','canonical_receipts_created':0,
                            'verification':audit,'book_hash':book['book_hash'],
                            'answer':'Budget comparison verified: '+', '.join(s+' '+('OVER' if v['budget_exceeded']['value'] else 'WITHIN')+' budget' for s,v in book['views'].items())}
                    result.update(status='COMPLETE',result=shown,blocker=None)
                    completed.add(node['id'])
                    contexts.append({'node':node['id'],'answer':shown['answer'],'evidence':shown,'original_question_sha256':plan['question_sha256']})
                except ValueError as exc:
                    result['blocker']='Deterministic arithmetic failed closed: '+str(exc)
                host_seconds+=time.perf_counter()-host_started
            else:
                try:
                    selection = self.auto.classify(node['input'],cp)
                    if selection['route'] != node['route']:
                        raise ValueError('Native admission unavailable: '+'; '.join(selection.get('limitations',[])))
                    next_cp, detail = self.auto.advance(task_id,round_id,node['input'],cp,selection)
                    if selection['route'] in NATIVE_ROUTES:
                        shown = self.auto.native_result(selection,detail,next_cp)
                        answer = shown['answer']
                    else:
                        shown = {'scope':'Actual registered result; not model-generated world truth.', 'context':detail['context'],
                                 'receipt_hashes':[r['receipt_hash'] for r in detail['receipts']]}
                        answer = detail['context']
                    cp = next_cp
                    result.update(status='COMPLETE',result=shown,blocker=None)
                    completed.add(node['id']); receipts.extend(detail['receipts']); traces.extend(detail['realization_traces'])
                    contexts.append({'node':node['id'], 'answer':answer, 'evidence':shown, 'original_question_sha256':plan['question_sha256']})
                except ValueError as exc:
                    result['blocker'] = str(exc)  # No local retry or assertion promotion.
            outcomes.append(result)
        material = {'schema':CONTRACT,'task_id':task_id,'source_hashes':dict(SOURCE_HASHES),
                    'auto_checkpoint':cp,'previous_checkpoint_hash':(checkpoint or {}).get('checkpoint_hash')}
        book=business.invalidate_stale(book,cp)
        if book:material['business']=book
        if book and book.get('current_status')!='COMPLETE':business_projection=None
        material['checkpoint_hash'] = digest(material)
        change=None
        if cp and cp.get('math'):
            api=load_core(); retained=cp['math']
            state=api.SE.restore(retained['journal'],expected_head=retained['head']).state
            active={d.reference for d in state.active_deductions}
            for node in outcomes:
                if node['result'] and node['result'].get('deduction_reference'):
                    node['knowledge_status']='CURRENT' if node['result']['deduction_reference'] in active else 'SUPERSEDED'
            statuses={n['id']:n.get('knowledge_status') for n in outcomes}
            contexts=[{**c,'knowledge_status':statuses[c['node']]} for c in contexts
                      if statuses[c['node']] != 'SUPERSEDED']
            change={'current_constraints':[{'label':c.label,'reference':c.reference,
                    'previous_ref':c.previous_ref,'equation':c.equation.display()} for c in state.current_constraints],
                'constraint_history_count':len(state.constraint_history),
                'invalidated_deductions':[d.reference for d in state.invalidated_deductions],
                'active_deductions':[d.reference for d in state.active_deductions],
                'supplied_signature_verified':False,'scope':'Conditional supplied premises; canonical correction history is append-only.'}
        context = json.dumps({'scope':'Executed bounded native results; unsupported parts are unresolved. Tooling advantage, not intrinsic reasoning.',
            'results':contexts, 'unresolved':[{'id':n['id'],'blocker':n['blocker']} for n in outcomes if n['status']!='COMPLETE']},ensure_ascii=False)
        if len(context.encode()) > MAX_CONTEXT_BYTES:
            raise ValueError('Composition context cap exceeded; no truncation, commit or provider request')
        summary = {'route':'ORCHESTRATED','nodes':outcomes,'receipts':receipts,'realization_traces':traces,
            'operators_executed':[{'stage':s['name'],'operator':s['operator'],'outcome':s['outcome'],'stage_id':s['stage_id']} for t in traces for s in t['stages']],
            'context':context,'context_bytes':len(context.encode()),'context_sha256':hashlib.sha256(context.encode()).hexdigest(),
            'local_seconds':time.perf_counter()-started,'source_hashes':dict(SOURCE_HASHES),
            'checkpoint_hash':material['checkpoint_hash'],'question_sha256':plan['question_sha256'],
            'limitations':[n['blocker'] for n in outcomes if n['status']!='COMPLETE'],
            'production_connected':False,'model_output_ingested':False,
            'local_actions_charged':sum(r.get('action') is not None for r in receipts),
            'local_operations':len(receipts),'correction_state':change,
            'business':business_projection,'native_business_complete':bool(business_projection),
            'host_calculation_seconds':host_seconds,
            'host_calculations_created':len(business_projection['new_records']) if business_projection else 0}
        answer = '\n\n'.join(n['id']+(' [HISTORICAL — SUPERSEDED]' if n.get('knowledge_status')=='SUPERSEDED' else '')+': '+ (n['result'].get('answer',n['result'].get('context','')) if n['status']=='COMPLETE'
                               else 'UNRESOLVED — '+n['blocker']) for n in outcomes)
        if business_projection:
            answer=business_projection['answer']+'\nCanonical SE6 receipts: '+str(len(receipts))+'. Host financial records: '+str(len(book['records']))+'.'
        return material, summary, answer

    def score_local(self, task):
        row = task['rounds'][-1]
        if hashlib.sha256(row['lanes']['se6']['response'].encode()).hexdigest() != row['lanes']['se6']['response_sha256']:
            raise ValueError('Local raw output was not frozen intact before scoring')
        checkpoint = task['orchestration_checkpoint']
        cp = self._restore(checkpoint,task['id'])
        if cp and cp.get('math'):
            api=load_core(); retained=cp['math']
            engine=api.SE.restore(retained['journal'],expected_head=retained['head'])
            verify_traces(api,engine,retained['traces'])
        host_audit=business.verify_host_book(checkpoint['business'],cp) if checkpoint.get('business') else None
        return {'host_arithmetic':host_audit,'status':'LOCAL_CERTIFICATES_REPLAYED','native_nodes_verified':sum(n['status']=='COMPLETE' and bool(n['result'].get('receipt_hashes')) for n in row['auto_execution']['nodes']),
                'unresolved_nodes':sum(n['status']!='COMPLETE' for n in row['auto_execution']['nodes']),
                'provider_answer_quality':'UNASSESSED','unsupported_claims':None,'winner':None,
                'scope':'Canonical proof/state replay, not a general prose, business or model-reasoning judge.'}
