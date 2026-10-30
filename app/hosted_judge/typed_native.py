"""Bounded lossless intake and typed presentation over existing V11 tools.

No canonical solver rebuilt. Parent holds scope/state; native solver still
creates/replays actual receipts. Graph reachability is explicitly HOST work.
"""
from copy import deepcopy
import hashlib,json,re
from .answer_contract import encode,digest,make_envelope,verify_user_answer,rational,rational_rank
from .benchmark_scoring import parse_linear_answer,solve_affine,reachable

SCHEMA='se6-typed-native-answer-state-v1'
NAME=r'[A-Za-z][A-Za-z0-9_]{0,31}'

def sealed(v):return {**v,'sha256':digest(v)}
def checked(v):
    if not isinstance(v,dict) or v.get('sha256')!=digest({k:x for k,x in v.items() if k!='sha256'}) or len(encode(v))>65536:raise ValueError('TYPED_STATE_SEAL')
    return v

def _literal(row):
    row=row.strip();return row[:-1].rstrip() if row.endswith('.') else row

def _linear(row):
    # Reuse already-approved bounded AST parser, never eval or a new solver.
    row=_literal(row).replace('\u2212','-')
    if re.search(r'(?<![A-Za-z0-9_])\d+(?:\.\d+)?[eE][+-]?\d+',row):raise ValueError('SCIENTIFIC_LITERAL_UNSUPPORTED')
    row=re.sub(r'(?<![A-Za-z0-9_])(\d+(?:\.\d+)?(?:/\d+)?)([A-Za-z_])',r'\1*\2',row)
    return parse_linear_answer(row)

def prepare(question,prior_state=None):
    if not isinstance(question,str) or not 0<len(question.encode())<=4096:raise ValueError('QUESTION_BOUND')
    prior=checked(prior_state) if prior_state is not None else None
    original_sha=hashlib.sha256(question.encode()).hexdigest();normalized=question.strip();facts={};kind='unsupported';changes=[]
    boundary=None
    if re.search(r'\bDerive\b',question,re.I):
        kind='affine';split=re.split(r'\bDerive\b',question,maxsplit=1,flags=re.I);body,request=split[0].strip(),'Derive'+split[1]
        match=re.fullmatch(r'Derive (?:a |the )?(?:relation|relationship) (?:involving|between|among) (.+?)\.?',request.strip(),re.I)
        if not match:raise ValueError('REQUEST_UNSUPPORTED')
        targets=[v.strip() for v in re.sub(r'\s+and\s+',',',match[1].rstrip('.')).split(',')]
        if not 1<=len(targets)<=6 or len(set(targets))!=len(targets) or any(not re.fullmatch(NAME,v) for v in targets):raise ValueError('TARGET_BOUND')
        domain_matches=list(re.finditer(r'Variables are integers (?:between (-?\d+) and (-?\d+)|in \[(-?\d+),\s*(-?\d+)\])\.?',body,re.I))
        if len(domain_matches)>1:raise ValueError('PUBLIC_DOMAIN_DUPLICATE')
        domain=deepcopy((prior or {}).get('public_integer_domain'))
        domain_text=None
        if domain_matches:
            d=domain_matches[0];proposed=[int(d[1] or d[3]),int(d[2] or d[4])]
            if not -10000<=proposed[0]<=proposed[1]<=10000 or proposed[1]-proposed[0]>=128:raise ValueError('PUBLIC_DOMAIN_BOUND')
            if domain is not None and proposed!=domain:raise ValueError('PUBLIC_DOMAIN_CHANGE')
            domain=proposed;domain_text=d[0];body=(body[:d.start()]+body[d.end():]).strip()
        equations=deepcopy((prior or {}).get('equations',{}));correction=re.fullmatch(r'Correct\s+('+NAME+r')\s*(?::|\bto\b)\s*(.+)',body,re.I|re.S)
        if correction:
            label,literal=correction.groups()
            if not equations or label not in equations:raise ValueError('CORRECTION_WITHOUT_PRIOR')
            literal=_literal(literal)
            if _linear(literal)==equations[label]['row']:raise ValueError('UNCHANGED_CORRECTION')
            equations[label]={'literal':literal,'row':_linear(literal),'source_question_sha256':original_sha}
            normalized=f'Correct {label} to {literal}.\n'+request.strip()
            changes=['EXPLICIT_CORRECTION_DELIMITER','SENTENCE_PUNCTUATION_ONLY']
        elif body:
            if equations:raise ValueError('EXPLICIT_CORRECTION_REQUIRED')
            body=re.sub(r'^Given(?: (?:the |these )?(?:linear )?equations)?\s*:\s*','',body,flags=re.I)
            parts=[p.strip() for p in re.split(r'[\n;]',body) if p.strip()]
            if not 1<=len(parts)<=4:raise ValueError('EQUATION_BOUND')
            for index,part in enumerate(parts):
                m=re.fullmatch(r'('+NAME+r'):\s*(.+)',part);label,literal=m.groups() if m else (f'E{index+1}',part)
                if label in equations:raise ValueError('DUPLICATE_EQUATION')
                literal=_literal(literal);equations[label]={'literal':literal,'row':_linear(literal),'source_question_sha256':original_sha}
            normalized='Given equations:\n'+'\n'.join(k+': '+v['literal'] for k,v in equations.items())+'\n'+request.strip()
            changes=['SENTENCE_PUNCTUATION_ONLY']
        elif not equations:raise ValueError('NO_RETAINED_PREMISES')
        variables=sorted({n for e in equations.values() for n in e['row']['coefficients']})
        if len(variables)>6 or not set(targets)<=set(variables):raise ValueError('UNKNOWN_TARGET')
        if domain_text:normalized=normalized.replace('\nDerive','\n'+domain_text+'\nDerive',1)
        facts={'premises':[e['row'] for e in equations.values()],'requested_variables':targets}
        if domain is not None:facts['public_integer_domain']=domain
        diagnostic=solve_affine(variables,[(e['coefficients'],e['rhs']) for e in facts['premises']])
        if diagnostic['status']=='INFEASIBLE':boundary='INFEASIBLE'
        elif len(targets)==1 and domain is None:
            rows=[[rational(e['coefficients'].get(v,0)) for v in variables] for e in facts['premises']]
            unit=[int(v==targets[0]) for v in variables]
            if rational_rank(rows+[unit])!=rational_rank(rows):boundary='UNDERDETERMINED'
        # Rank deficiency does not forbid an entailed multi-variable relation.
    elif re.search(r'RELATES_TO',question):
        kind='graph';edges=deepcopy((prior or {}).get('graph_edges',[]))
        found=[list(x) for x in re.findall(r'('+NAME+r') RELATES_TO ('+NAME+r')',question)]
        if question.strip().startswith('Remove the directed edge'):
            if len(found)!=1 or found[0] not in edges:raise ValueError('EDGE_REMOVAL_WITHOUT_PRIOR')
            edges.remove(found[0]);changes=['EXPLICIT_EDGE_REMOVAL']
        else:
            if edges:raise ValueError('GRAPH_REPLACEMENT_REQUIRES_EXPLICIT_NEW_TASK')
            edges=found
        if len(edges)>12 or len({tuple(e) for e in edges})!=len(edges):raise ValueError('GRAPH_BOUND')
        query=re.search(r'Can ('+NAME+r') (?:still )?be reached from ('+NAME+r')',question)
        if not query:raise ValueError('GRAPH_QUERY')
        target,start=query.groups();facts={'edges':edges,'start':start,'target':target};normalized=None
    else:
        # Lexical routing only. HOSTbook supplies all business values later.
        rates=list(re.finditer(r'^('+NAME+r'):\s*(\d+(?:/\d+|\.\d+)?)\s+technician-hours,\s*\$(\d+(?:/\d+|\.\d+)?)\s+materials cost,\s*\$(\d+(?:/\d+|\.\d+)?)\s+customer revenue\.',question,re.M))
        scalar_patterns=[r'completed (\d+) jobs',r'original \w+ recorded (\d+(?:/\d+|\.\d+)?) technician-hours',r'materials budget is \$(\d+(?:/\d+|\.\d+)?)']
        for pattern in scalar_patterns:
            matches=re.findall(pattern,question,re.I)
            if len({rational(v) for v in matches})>1:raise ValueError('BUSINESS_PUBLIC_SCALAR_AMBIGUITY')
        jobs=re.search(r'completed (\d+) jobs',question,re.I);hours=re.search(r'original \w+ recorded (\d+(?:/\d+|\.\d+)?) technician-hours',question,re.I);budget=re.search(r'materials budget is \$(\d+(?:/\d+|\.\d+)?)',question,re.I)
        if len(rates)==2 and jobs and hours and budget:
            kind='business';classes=[m[1].lower() for m in rates]
            if len(set(classes))!=2:raise ValueError('BUSINESS_CLASSES')
            facts={'classes':classes,'hours_per_job':{m[1].lower():m[2] for m in rates},'materials_per_job':{m[1].lower():m[3] for m in rates},'revenue_per_job':{m[1].lower():m[4] for m in rates},'total_jobs':jobs[1],'total_hours':hours[1],'budget':budget[1]}
            normalized=re.sub(r'\s+(Calculate\b)',r'\n\1',question,flags=re.I);changes=['REQUEST_LINE_BOUNDARY_ONLY']
        elif prior and prior.get('task_type')=='business' and re.match(r'\s*Correct(?: the)? technician-hours to ',question,re.I):
            correction=re.fullmatch(r'\s*Correct(?: the)? technician-hours to (\d+(?:/\d+|\.\d+)?)(?:\.)?\s*(.*?)\s*',question,re.I|re.S)
            if correction is None:raise ValueError('BUSINESS_CORRECTION_REQUEST_UNSUPPORTED')
            value,suffix=correction.groups()
            if suffix:
                request=re.fullmatch(r'Calculate (.+?)\.?',suffix,re.I)
                allowed={'allocations','revenue','materials','materials cost','contribution','gross contribution','budget variance'}
                items=[x.strip().lower() for x in re.split(r',\s*|\s+and\s+',request[1])] if request else []
                if not items or any(x not in allowed for x in items):raise ValueError('BUSINESS_CORRECTION_REQUEST_UNSUPPORTED')
                normalized=f'Correct technician-hours to {value}.'
                changes=['DECLARED_FINANCIAL_REQUEST_TO_EXISTING_CORRECTION_GRAMMAR']
            kind='business';facts=deepcopy(prior['public_facts']);facts['total_hours']=value
        else:
            boundary='UNVERIFIED' if re.search(r'(?:no|missing|without) (?:a )?(?:signature|provenance)',question,re.I) else 'UNSUPPORTED'
    if kind=='business':
        classes=facts['classes']
        diagnosed=solve_affine(classes,[({c:'1' for c in classes},str(rational(facts['total_jobs']))),
            ({c:str(rational(facts['hours_per_job'][c])) for c in classes},str(rational(facts['total_hours'])))])
        if diagnosed['status']=='INFEASIBLE' or diagnosed['status']=='UNIQUE' and any(rational(v)<0 or rational(v).denominator!=1 for v in diagnosed['values'].values()):boundary='INFEASIBLE'
    if boundary:facts['boundary_status']=boundary
    state_data={'equations':equations,'public_integer_domain':domain} if kind=='affine' else {'graph_edges':edges} if kind=='graph' else {}
    return sealed({'schema':SCHEMA,'task_type':kind,'original_question_sha256':original_sha,
        'original_question':question,'native_question':normalized,
        'native_question_sha256':hashlib.sha256(normalized.encode()).hexdigest() if normalized is not None else None,
        'normalization':changes,'public_facts':facts,'state_data':state_data,
        'prior_state_sha256':prior['sha256'] if prior else None})

def finalize(prepared,native_result,*,task_id,cycle,verified_context=None):
    """Trusted caller must pass source-bound proof context, never HTTP flags.

    This layer checks exact retained checkpoint/out/answer bindings itself.
    It cannot authenticate an arbitrary caller's source context as world truth.
    """
    checked(prepared);kind=prepared['task_type'];payload=None;origin='NATIVE_DETERMINISTIC';evidence={'verified':False,'kind':'NOT_EXECUTED'}
    if kind=='graph':
        payload={'reachable':reachable([tuple(e) for e in prepared['public_facts']['edges']],prepared['public_facts']['start'],prepared['public_facts']['target'])}
        origin='HOST_DETERMINISTIC';evidence={'verified':True,'kind':'HOST_DIRECTED_GRAPH_COMPUTATION','public_facts_sha256':digest(prepared['public_facts']),'canonical_receipts':[],'scope':'Existing approved reachability algorithm + independent fixed-point check; no canonical inference or physical adjacency'}
    elif prepared['public_facts'].get('boundary_status'):
        payload={'status':prepared['public_facts']['boundary_status']};origin='HOST_DETERMINISTIC';evidence={'verified':True,'kind':'PUBLIC_PREMISE_BOUNDARY_DIAGNOSTIC','canonical_receipts':[]}
    elif native_result is not None and verified_context:
        out=native_result['attestation']['raw_execution_out'];cp=native_result['attestation'].get('primary_native_checkpoint') or native_result['checkpoint']
        if verified_context.get('checkpoint_sha256')!=digest(cp) or verified_context.get('raw_out_sha256')!=digest(out) or verified_context.get('native_question_sha256')!=prepared['native_question_sha256'] or out.get('question_sha256')!=prepared['native_question_sha256'] or verified_context.get('bundle_manifest_sha256')!=native_result['attestation']['bundle_manifest_sha256']:raise ValueError('VERIFIED_NATIVE_CONTEXT_BINDING')
        evidence={'verified':True,'kind':'SOURCE_BOUND_NATIVE_CHECKPOINT_PROOF','checkpoint_sha256':digest(cp),
            'source_manifest_sha256':native_result['attestation']['bundle_manifest_sha256'],
            'receipt_hashes':[r['receipt_hash'] for r in out['receipts']],'scope':'Native conditional proof + independently admitted HOST records; no verified external facts'}
        if verified_context.get('verified') is not True:
            envelope=make_envelope(prepared,{'status':'BLOCKED'},task_id=task_id,cycle=cycle,origin='HOST_DETERMINISTIC',evidence={'verified':False,'kind':'NATIVE_PROOF_NOT_ADMITTED'})
            envelope['checks']['semantic']=None;envelope['checks']['reason']='NO_VERIFIED_NATIVE_VALUE'
            return {'envelope':envelope,'next_state':None,'prepared':prepared}
        if kind=='business':
            views=(out.get('business') or {}).get('views');public=native_result['public']
            audit=(public.get('local_verification') or {}).get('host_arithmetic') or {}
            if not views or audit.get('passed') is not True or audit.get('current') is not True:raise ValueError('HOST_ARITHMETIC_NOT_VERIFIED')
            payload=deepcopy(views.get('corrected') or views.get('original'))
        elif kind=='affine':
            math_cp=((cp.get('auto_checkpoint') or {}).get('math') or {})
            journal=json.loads(math_cp['journal'])
            relations=list({digest(r):r for r in journal['state']['deduction_history']}.values())
            targets=set(prepared['public_facts']['requested_variables'])
            nodes=[n['result'] for n in out.get('nodes',[]) if n.get('status')=='COMPLETE' and n.get('knowledge_status')=='CURRENT' and n.get('route')=='LINEAR_DERIVATION']
            pairs=[(r,n) for n in nodes for r in relations if n.get('head')==math_cp['head'] and n.get('deduction_reference')=='math-deduction:'+digest(r) and set(dict(r['equation']['coefficients']))==targets and r['verification'].get('passed') is True and digest(r['proof'])==digest(n.get('proof')) and digest(r['verification'])==digest(n.get('verification'))]
            if len(pairs)!=1:raise ValueError('NO_UNIQUE_CURRENT_TYPED_DEDUCTION')
            selected,node=pairs[0]
            equation=selected['equation'];payload={'relation':{'coefficients':{k:str(v) for k,v in equation['coefficients']},'rhs':str(equation['rhs'])}}
            evidence['deduction_reference']=node['deduction_reference'];evidence['native_head']=math_cp['head']

    if payload is None:
        envelope=make_envelope(prepared,{'status':'BLOCKED'},task_id=task_id,cycle=cycle,origin='HOST_DETERMINISTIC',evidence=evidence)
        envelope['checks']['semantic']=None
        envelope['checks']['reason']='NO_VERIFIED_NATIVE_VALUE'
        return {'envelope':envelope,'next_state':None,'prepared':prepared}
    validation=verify_user_answer(kind,payload,prepared['public_facts'])
    if validation['semantic'] is not True:raise ValueError('NATIVE_TYPED_ANSWER_SEMANTIC_MISMATCH')
    envelope=make_envelope(prepared,payload,task_id=task_id,cycle=cycle,origin=origin,evidence=evidence)
    next_state=sealed({'schema':SCHEMA,'task_type':kind,'public_facts':deepcopy(prepared['public_facts']),
        **deepcopy(prepared['state_data']),'prior_state_sha256':prepared['prior_state_sha256'],
        'question_sha256':prepared['original_question_sha256'],'native_question_sha256':prepared['native_question_sha256'],
        'verified_answer_sha256':digest(payload),'checkpoint_sha256':digest(native_result['checkpoint']) if native_result is not None else None})
    return {'envelope':envelope,'next_state':None if 'status' in payload else next_state,'prepared':prepared}
