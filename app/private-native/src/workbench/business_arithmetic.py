"""Exact, dimension-checked HOST arithmetic over canonical quantity evidence.

No SE operators or receipts, solver, provider, tool execution or production DB.
Inputs remain OWNER_SUPPLIED. Results verify arithmetic conditional on inputs,
not authenticity of bills, timesheets, signatures or a business recommendation.
"""
from copy import deepcopy
from dataclasses import asdict
from fractions import Fraction
import hashlib
import math
import re

from .auto_intake import digest
from .core_revisions import load_core, verify_traces
from .linear_admission import equation

CONTRACT = 'se6-deterministic-business-arithmetic-v1'
MAX_RECORDS = 512
MAX_ITEMS = 8
NUMBER = r'\d+(?:\.\d+|/\d+)?'
MONEY = rf'([$€£]|USD|EUR|GBP)\s*({NUMBER})'
CURRENCIES = {'$':'USD','€':'EUR','£':'GBP','USD':'USD','EUR':'EUR','GBP':'GBP'}


def exact(value):
    if not isinstance(value,str) or len(value)>40 or not re.fullmatch(r'-?\d+(?:\.\d+|/\d+)?',value):
        raise ValueError('Exact bounded decimal/rational string required; floats, NaN and code are forbidden')
    try:
        result=Fraction(value)
    except (ValueError,ZeroDivisionError) as exc:
        raise ValueError('Invalid rational amount') from exc
    if abs(result.numerator)>10**18 or result.denominator>10**9:
        raise ValueError('Exact arithmetic resource bound exceeded')
    return result


def money_text(value,currency):
    value=exact(value);d=value.denominator;twos=fives=0
    while d%2==0:d//=2;twos+=1
    while d%5==0:d//=5;fives+=1
    if d!=1:return currency+' '+str(value)
    digits=max(2,twos,fives);scaled=abs(value.numerator)*10**digits//value.denominator
    whole,tail=divmod(scaled,10**digits)
    return ('-' if value<0 else '')+{'USD':'$','EUR':'€','GBP':'£'}[currency]+str(whole)+'.'+str(tail).zfill(digits)


def fact(name,value,unit,text,span,previous_ref=None):
    row={'kind':'OWNER_SUPPLIED_FACT','name':name,'value':str(exact(value)),'unit':unit,
         'source_sha256':hashlib.sha256(text.encode()).hexdigest(),'source_span':span,
         'source_text':text[span[0]:span[1]],'previous_ref':previous_ref}
    row['reference']='fact:'+digest(row)
    return row


def parse(text,previous=None):
    """Bounded monetary intake; no calculations, mutations or credential lookup."""
    if previous:
        validate_book(previous)
        hours=re.fullmatch(r'\s*Correct(?: the)? ([A-Za-z]+-hours) to ('+NUMBER+r')(?:\s+([A-Za-z]+-hours))?\.?\s*',text,re.I)
        if hours:
            data=deepcopy(previous['inputs'])
            if hours[1].lower()!=data['hour_unit'].lower() or (hours[3] and hours[3].lower()!=data['hour_unit'].lower()):
                raise ValueError('Resource-hour dimensions mismatch')
            if exact(hours[2])<=0 or str(exact(hours[2]))==data['hours'].get('corrected',data['hours']['original']):
                raise ValueError('Hours correction must change a positive supplied total')
            data['hours']['corrected']=str(exact(hours[2]));data['mode']='HOURS_CORRECTION'
            data['question_sha256']=hashlib.sha256(text.encode()).hexdigest()
            return data
        update=re.fullmatch(r'\s*Correct (?:([A-Za-z][A-Za-z0-9_]{0,31}) (materials cost|unit cost|customer revenue)|(?:materials )?budget) to '+MONEY+r'\.?(?:\s+Verify(?: it)?\.?)?\s*',text,re.I)
        if update:
            name,column,symbol,amount=update.groups()
            data=deepcopy(previous['inputs']);currency=CURRENCIES[symbol.upper() if symbol.isalpha() else symbol]
            if currency!=data['currency'] or exact(amount)<0:
                raise ValueError('Currency/dimension mismatch or negative monetary input')
            key='budget' if name is None else name.lower()+':'+('revenue' if column.lower()=='customer revenue' else 'expense')
            if key not in data['facts']:raise ValueError('Correction names an unknown supplied fact')
            old=data['facts'][key];incoming=fact(key,amount,old['unit'],text,[0,len(text)],old['reference'])
            if incoming['value']==old['value']:raise ValueError('Correction must change a supplied monetary value')
            data['facts'][key]=incoming;data['mode']='MONETARY_CORRECTION'
            data['question_sha256']=hashlib.sha256(text.encode()).hexdigest()
            return data
    rates=list(re.finditer(r'^([A-Za-z][A-Za-z0-9_]{0,31}):\s*('+NUMBER+r')\s+([A-Za-z]+-hours)\b.*$',text,re.M))
    if not rates:return None
    total=re.search(r'\bcompleted (\d+) jobs\b',text,re.I)
    original=re.search(r'\boriginal \w+ recorded ('+NUMBER+r') ([A-Za-z]+-hours)\b',text,re.I)
    corrected=re.search(r'\bcorrection showing ('+NUMBER+r') ([A-Za-z]+-hours)\b',text,re.I)
    budget=list(re.finditer(r'\b(?:materials|expense) budget is '+MONEY,text,re.I))
    if not total or not original or not budget:return None
    if len(rates)!=2 or len(budget)!=1:raise ValueError('Ambiguous bounded job classes or budget')
    facts={};classes=[];currency=None
    for row in rates:
        name=row[1].lower()
        if name in classes:raise ValueError('Duplicate job class')
        classes.append(name)
        for column,pattern in (('expense',MONEY+r'\s+(?:materials|unit|expenses?) cost\b'),('revenue',MONEY+r'\s+customer revenue\b')):
            values=list(re.finditer(pattern,row[0],re.I))
            if len(values)!=1:raise ValueError('Exactly one supplied unit cost and revenue per job class required')
            found=values[0];symbol,amount=found.groups();cur=CURRENCIES[symbol.upper() if symbol.isalpha() else symbol]
            if currency is not None and cur!=currency:raise ValueError('Mixed currencies require an unavailable conversion contract')
            currency=cur
            if exact(amount)<0:raise ValueError('Negative unit cost/revenue unsupported')
            start=row.start()+found.start();end=row.start()+found.end()
            facts[name+':'+column]=fact(name+':'+column,amount,cur+'/job',text,[start,end])
    found=budget[0];symbol,amount=found.groups();cur=CURRENCIES[symbol.upper() if symbol.isalpha() else symbol]
    if cur!=currency or exact(amount)<0:raise ValueError('Budget currency/dimension mismatch')
    facts['budget']=fact('budget',amount,cur,text,[found.start(),found.end()])
    if any(row[3].lower()!=original[2].lower() for row in rates) or (corrected and corrected[2].lower()!=original[2].lower()):
        raise ValueError('Technician-hour dimensions do not agree')
    return {'contract':CONTRACT,'mode':'INITIAL','currency':currency,'classes':classes,'facts':facts,
            'hour_unit':original[2],
            'total_jobs':int(total[1]),'hours_per_job':{row[1].lower():str(exact(row[2])) for row in rates},
            'hours':{'original':str(exact(original[1])),**({'corrected':str(exact(corrected[1]))} if corrected else {})},
            'question_sha256':hashlib.sha256(text.encode()).hexdigest(),
            'scope':'Conditional owner-supplied unit prices, count semantics and hours. No labour, taxes or overhead inferred.'}


def canonical_bindings(inputs,auto_checkpoint,outcomes,previous=None):
    """Read quantities from verified canonical equations, never answer strings."""
    retained=(auto_checkpoint or {}).get('math')
    if not retained:raise ValueError('Verified canonical quantity state required')
    api=load_core();engine=api.SE.restore(retained['journal'],expected_head=retained['head'])
    verify_traces(api,engine,retained['traces'])
    if engine.state.identity!='competition-auto-math:'+auto_checkpoint['task_id']:raise ValueError('Financial quantity state belongs to another task')
    receipts={r.receipt_hash:r for r in engine.receipts}
    rows=[n['result'] for n in outcomes if n['status']=='COMPLETE' and n['result'].get('deduction_reference')]
    bindings=deepcopy(previous['bindings']) if previous else {}
    if rows:
        scenarios=['corrected'] if inputs['mode']=='HOURS_CORRECTION' else list(inputs['hours'])
        if len(rows)!=len(inputs['classes'])*len(scenarios):raise ValueError('Complete original/corrected quantity proofs required')
        for i,shown in enumerate(rows):
            scenario=scenarios[i//len(inputs['classes'])]
            receipt=receipts.get(shown['head'])
            if receipt is None or not receipt.verification.passed:raise ValueError('Quantity receipt binding mismatch')
            d=next((d for d in receipt.state_after.active_deductions if d.reference==shown['deduction_reference']),None)
            if d is None or asdict(d.proof)!=shown['proof']:raise ValueError('Quantity proof/reference mismatch')
            if len(d.equation.coefficients)!=1:raise ValueError('Singleton quantity deduction required')
            name,coefficient=d.equation.coefficients[0];amount=Fraction(d.equation.rhs,coefficient)
            if name not in inputs['classes'] or amount.denominator!=1 or not 0<=amount<=inputs['total_jobs']:
                raise ValueError('Invalid canonical job quantity')
            binding={'kind':'CANONICAL_QUANTITY_BINDING','name':name,'value':str(amount),'unit':'job',
                     'deduction_reference':d.reference,'receipt_hash':receipt.receipt_hash,'scenario':scenario}
            binding['reference']='quantity:'+digest(binding)
            bindings.setdefault(scenario,{})[name]=binding
    verify_bindings(inputs,bindings,engine,receipts)
    current=bindings['corrected' if 'corrected' in bindings else 'original']
    if not {q['deduction_reference'] for q in current.values()}<={d.reference for d in engine.state.active_deductions}:
        raise ValueError('Financial quantities are superseded; complete current allocation proofs required')
    return bindings


def verify_bindings(inputs,bindings,engine,receipts=None):
    receipts=receipts or {r.receipt_hash:r for r in engine.receipts};api=load_core()
    if set(bindings)!=set(inputs['hours']):raise ValueError('Missing quantity scenario')
    for scenario,quantities in bindings.items():
        if set(quantities)!=set(inputs['classes']):raise ValueError('Incomplete job allocation')
        assignment={}
        for name,b in quantities.items():
            if b['reference']!='quantity:'+digest({k:v for k,v in b.items() if k!='reference'}) or b['unit']!='job' or b['name']!=name or b['scenario']!=scenario:
                raise ValueError('Quantity content/dimension binding mismatch')
            r=receipts.get(b['receipt_hash']);d=next((d for d in r.state_after.active_deductions if d.reference==b['deduction_reference']),None) if r else None
            if not d or not r.verification.passed or len(d.equation.coefficients)!=1 or d.equation.coefficients[0][0]!=name:
                raise ValueError('Canonical quantity evidence unavailable')
            actual=Fraction(d.equation.rhs,d.equation.coefficients[0][1])
            if actual!=exact(b['value']) or actual.denominator!=1 or actual<0:raise ValueError('Quantity value contradicts canonical proof')
            current={c.label:c.equation for c in r.state_after.current_constraints}
            names=inputs['classes'];e1,_=equation('+'.join(names)+'='+str(inputs['total_jobs']),api)
            e2,_=equation('+'.join(inputs['hours_per_job'][n]+'*'+n for n in names)+'='+inputs['hours'][scenario],api)
            if current.get('E1')!=e1 or current.get('E2')!=e2:raise ValueError('Quantity proofs belong to different source premises')
            assignment[name]=actual
        if sum(assignment.values())!=inputs['total_jobs'] or sum(exact(inputs['hours_per_job'][n])*v for n,v in assignment.items())!=exact(inputs['hours'][scenario]):
            raise ValueError('Allocation source equations do not hold')


def calculate(operation,operands):
    """Bounded producer using Fraction; no executable expressions."""
    if not isinstance(operands,list) or not 1<=len(operands)<=MAX_ITEMS:raise ValueError('Bounded operands required')
    if any(not isinstance(x,dict) or not {'value','unit'}<=set(x) or not isinstance(x['unit'],str) for x in operands):
        raise ValueError('Typed value/dimension operands required')
    values=[exact(x['value']) for x in operands];units=[x['unit'] for x in operands]
    if operation=='UNIT_PRODUCT':
        if len(values)!=2 or '/' not in units[0] or units[0].split('/')[1]!=units[1]:raise ValueError('Unit price × quantity dimension mismatch')
        currency=units[0].split('/')[0]
        if currency not in CURRENCIES.values() or values[1]<0 or values[0]<0:raise ValueError('Unsupported monetary product')
        return str(values[0]*values[1]),currency
    if len(set(units))!=1 or units[0] not in CURRENCIES.values():raise ValueError('Matching monetary dimensions required')
    if operation=='SUM':return str(sum(values,Fraction(0))),units[0]
    if operation=='SUBTRACT' and len(values)==2:return str(values[0]-values[1]),units[0]
    if operation=='EXCEEDS_ZERO' and len(values)==1:return values[0]>0,'boolean'
    raise ValueError('Unsupported deterministic arithmetic operation')


def independent_check(record,available):
    """Independent integer numerator/denominator checker; never calls calculate."""
    args=[available[r] for r in record['dependencies']]
    def pair(value):
        if not isinstance(value,str) or not re.fullmatch(r'-?\d+(?:/\d+)?',value):raise ValueError('Normalized rational required')
        a,_,b=value.partition('/');n,d=int(a),int(b or '1')
        if d<=0:raise ValueError('Invalid denominator')
        return n,d
    def add(a,b):
        n=a[0]*b[1]+b[0]*a[1];d=a[1]*b[1];g=math.gcd(n,d);return n//g,d//g
    pairs=[pair(x['value']) for x in args];op=record['operation'];unit=None
    if op=='UNIT_PRODUCT' and len(args)==2:
        rate= args[0]['unit'].split('/')
        if len(rate)!=2 or rate[1]!=args[1]['unit'] or rate[0] not in CURRENCIES.values():raise ValueError('Independent product dimensions failed')
        if pairs[0][0]<0 or pairs[1][0]<0:raise ValueError('Negative input product')
        expected=(pairs[0][0]*pairs[1][0],pairs[0][1]*pairs[1][1]);unit=rate[0]
    elif op in ('SUM','SUBTRACT','EXCEEDS_ZERO'):
        if not args or len({x['unit'] for x in args})!=1 or args[0]['unit'] not in CURRENCIES.values():raise ValueError('Independent monetary dimensions failed')
        unit=args[0]['unit'];expected=(0,1)
        if op=='SUM':
            for item in pairs:expected=add(expected,item)
        elif op=='SUBTRACT' and len(args)==2:expected=add(pairs[0],(-pairs[1][0],pairs[1][1]))
        elif op=='EXCEEDS_ZERO' and len(args)==1:
            if type(record['value']) is not bool or record['value']!=(pairs[0][0]>0) or record['unit']!='boolean':raise ValueError('Independent budget comparison failed')
            return True
        else:raise ValueError('Invalid operator arity')
    else:raise ValueError('Unsupported host operation')
    actual=pair(record['value'])
    if actual[0]*expected[1]!=expected[0]*actual[1] or record['unit']!=unit:raise ValueError('Independent arithmetic result mismatch')
    return True


def validate_book(book):
    if book.get('contract')!=CONTRACT or book.get('book_hash')!=digest({k:v for k,v in book.items() if k!='book_hash'}):raise ValueError('Host calculation book hash mismatch')
    if len(book['records'])>MAX_RECORDS:raise ValueError('Host calculation history bound exceeded')
    available={}
    for f in book['facts']:
        if f['kind']!='OWNER_SUPPLIED_FACT' or f['reference']!='fact:'+digest({k:v for k,v in f.items() if k!='reference'}):raise ValueError('Source fact content/class mismatch')
        available[f['reference']]=f
    for qs in book['bindings_history']:
        if qs['reference']!='quantity:'+digest({k:v for k,v in qs.items() if k!='reference'}):raise ValueError('Quantity reference tampered')
        available[qs['reference']]=qs
    for record in book['records']:
        if (record['kind']!='DETERMINISTIC_HOST_CALCULATION' or record['reference']!='calculation:'+digest({k:v for k,v in record.items() if k!='reference'}) or record.get('canonical_receipt') is not None):
            raise ValueError('Host record class/hash mismatch; canonical receipt fabrication forbidden')
        if any(r not in available for r in record['dependencies']):raise ValueError('Missing or forward arithmetic dependency')
        independent_check(record,available);available[record['reference']]=record
    return available


def execute(inputs,bindings,previous=None,*,auto_checkpoint=None):
    """Append exact host records; reuse unaffected dependencies; preserve history."""
    if auto_checkpoint is None:raise ValueError('Canonical quantity evidence required; caller/model assertions cannot certify themselves')
    canonical_bindings(inputs,auto_checkpoint,[],{'bindings':bindings})
    if previous:validate_book(previous)
    book=deepcopy(previous) if previous else {'contract':CONTRACT,'facts':[],'bindings_history':[],
        'records':[],'views_history':[],'invalidations':[],'active':[]}
    book.pop('book_hash',None);book['inputs']=deepcopy(inputs);book['bindings']=deepcopy(bindings)
    available={r['reference']:r for r in (*book['facts'],*book['bindings_history'],*book['records'])}
    added=[];reused=[];views={}
    for f in inputs['facts'].values():
        if exact(f['value'])<0:raise ValueError('Negative supplied monetary input')
        if f['reference'] not in available:book['facts'].append(deepcopy(f));available[f['reference']]=f
    for quantities in bindings.values():
        for q in quantities.values():
            if q['reference'] not in available:book['bindings_history'].append(deepcopy(q));available[q['reference']]=q
    def run(op,args):
        dependencies=[a['reference'] for a in args]
        prior=next((r for r in book['records'] if r['operation']==op and r['dependencies']==dependencies),None)
        if prior is not None:
            independent_check(prior,available)
            reused.append(prior['reference'])
            return prior  # Do not regenerate unaffected conclusions.
        value,unit=calculate(op,args)
        record={'kind':'DETERMINISTIC_HOST_CALCULATION','operation':op,'dependencies':dependencies,
                'value':value,'unit':unit,'canonical_receipt':None,'verification':'INDEPENDENT_EXACT_ARITHMETIC',
                'scope':'Arithmetic conditional on supplied facts and canonical quantity proofs; not world verification.'}
        record['reference']='calculation:'+digest(record)
        independent_check(record,available)
        if record['reference'] not in available:
            book['records'].append(record);available[record['reference']]=record;added.append(record['reference'])
        else:reused.append(record['reference'])
        return record
    for scenario,quantities in bindings.items():
        terms={}
        for column in ('revenue','expense'):
            terms[column]=[run('UNIT_PRODUCT',[inputs['facts'][name+':'+column],quantities[name]]) for name in inputs['classes']]
        revenue=run('SUM',terms['revenue']);cost=run('SUM',terms['expense'])
        gross=run('SUBTRACT',[revenue,cost]);variance=run('SUBTRACT',[cost,inputs['facts']['budget']]);over=run('EXCEEDS_ZERO',[variance])
        view={'scenario':scenario,'allocations':{n:q['value'] for n,q in quantities.items()},
              'revenue':revenue,'materials_cost':cost,'gross_contribution':gross,'budget_variance':variance,'budget_exceeded':over,
              'quantity_references':[q['reference'] for q in quantities.values()],
              'active_references':[r['reference'] for r in (*terms['revenue'],*terms['expense'],revenue,cost,gross,variance,over)]}
        view['view_hash']=digest(view)
        if not any(v['view_hash']==view['view_hash'] for v in book['views_history']):book['views_history'].append(deepcopy(view))
        views[scenario]=view
    final_view=views['corrected' if 'corrected' in views else 'original']
    prior_active=set(previous['active']) if previous else set(views['original']['active_references'])
    for ref in sorted(prior_active-set(final_view['active_references'])):
        event={'reference':ref,'replaced_by_view':final_view['view_hash'],'reason':'DEPENDENCY_SUPERSEDED; historical conditional result retained'}
        if event not in book['invalidations']:book['invalidations'].append(event)
    book['active']=final_view['active_references'];book['current_status']='COMPLETE'
    book['previous_book_hash']=previous['book_hash'] if previous else None
    book['views']=views
    if len(book['records'])>MAX_RECORDS:raise ValueError('Host arithmetic record allowance exhausted; no purge or automatic increase')
    book['book_hash']=digest(book);validate_book(book)
    projection={'contract':CONTRACT,'kind':'DETERMINISTIC_HOST_CALCULATION','canonical_receipts_created':0,
        'currency':inputs['currency'],'views':{s:{k:(v[k]['value'] if k not in ('allocations',) else v[k]) for k in
        ('allocations','revenue','materials_cost','gross_contribution','budget_variance','budget_exceeded')} for s,v in views.items()},
        'record_references':{s:[v[k]['reference'] for k in ('revenue','materials_cost','gross_contribution','budget_variance','budget_exceeded')] for s,v in views.items()},
        'book_hash':book['book_hash'],'new_records':added,'reused_records':reused,
        'verification':'INDEPENDENT_EXACT_ARITHMETIC','scope':inputs['scope'],
        'source_facts_class':'OWNER_SUPPLIED','signature_authenticity':'UNVERIFIED',
        'changed':([key for key,f in inputs['facts'].items() if previous and f['reference']!=previous['inputs']['facts'][key]['reference']]+['dependent monetary conclusions']) if inputs['mode']=='MONETARY_CORRECTION' else
            (['technician-hour premise','job allocations','dependent financial conclusions'] if 'corrected' in inputs['hours'] else []),
        'unchanged':['job total','unit technician-hours','unit costs','unit revenues','budget'] if inputs['mode'] in ('INITIAL','HOURS_CORRECTION') else ['canonical quantity proofs','other monetary inputs'],
        'limitations':['Recommendation pending approved provider.','Python generation/execution pending; no authorized code tool.','Gross contribution excludes unspecified labour, overhead and taxes.']}
    lines=['VERIFIED NATIVE BUSINESS RESULT — conditional on supplied facts',
           'Financial operations: deterministic HOST calculations; no new SE6 receipts.',
           'Source facts: OWNER_SUPPLIED. Record/signature authenticity: UNVERIFIED.']
    for s,v in projection['views'].items():
        lines.append(s.upper()+' RECORD: '+', '.join(n.upper()+' '+a for n,a in v['allocations'].items()))
        for key,label in (('revenue','Revenue'),('materials_cost','Materials cost'),('gross_contribution','Gross contribution'),('budget_variance','Materials minus budget')):
            lines.append(label+': '+money_text(v[key],inputs['currency']))
        lines.append('Budget exceeded: '+('YES' if v['budget_exceeded'] else 'NO'))
    lines.extend(['Changed: '+', '.join(projection['changed'])+'.','Unchanged: '+', '.join(projection['unchanged'])+'.',
                  'Canonical quantity proofs + exact dimension-checked arithmetic independently verified.',
                  'Recommendations and Python: PENDING; no model or code execution. Baseline: NOT RUN; no comparison winner.'])
    projection['answer']='\n'.join(lines)
    return book,projection


def verify_host_book(book,auto_checkpoint):
    validate_book(book)
    retained=auto_checkpoint['math'];api=load_core()
    engine=api.SE.restore(retained['journal'],expected_head=retained['head']);verify_traces(api,engine,retained['traces'])
    for q in book['bindings_history']:
        r=next((r for r in engine.receipts if r.receipt_hash==q['receipt_hash']),None)
        d=next((d for d in r.state_after.active_deductions if d.reference==q['deduction_reference']),None) if r else None
        if (not d or not r.verification.passed or len(d.equation.coefficients)!=1 or d.equation.coefficients[0][0]!=q['name']
            or q['unit']!='job' or Fraction(d.equation.rhs,d.equation.coefficients[0][1])!=exact(q['value'])):
            raise ValueError('Historical quantity record is not supported by canonical evidence')
    verify_bindings(book['inputs'],book['bindings'],engine)
    latest=book['bindings']['corrected' if 'corrected' in book['bindings'] else 'original']
    active={d.reference for d in engine.state.active_deductions}
    current={q['deduction_reference'] for q in latest.values()}<=active
    if book.get('current_status')=='COMPLETE' and not current:raise ValueError('Stale financial result cannot be reported current')
    return {'passed':True,'current':current,'host_records':len(book['records']),'canonical_receipts_created':0}


def dependent_references(records,changed):
    """Transitive closure in the already-validated topological record order."""
    affected=set(changed)
    for record in records:
        if any(ref in affected for ref in record['dependencies']):affected.add(record['reference'])
    return affected


def invalidate_stale(book,auto_checkpoint):
    if not book or not auto_checkpoint or not auto_checkpoint.get('math'):return book
    api=load_core();state=api.SE.restore(auto_checkpoint['math']['journal'],expected_head=auto_checkpoint['math']['head']).state
    latest=book['bindings']['corrected' if 'corrected' in book['bindings'] else 'original']
    active={d.reference for d in state.active_deductions}
    stale={q['reference'] for q in latest.values() if q['deduction_reference'] not in active}
    if not stale:return book
    affected=dependent_references(book['records'],stale)
    updated=deepcopy(book);updated.pop('book_hash')
    for ref in set(updated['active']) & affected:
        updated['invalidations'].append({'reference':ref,'reason':'CANONICAL_QUANTITY_SUPERSEDED; recomputation pending'})
    updated['active']=[ref for ref in updated['active'] if ref not in affected]
    updated['current_status']='PENDING_RECOMPUTATION';updated['previous_book_hash']=book['book_hash']
    updated['book_hash']=digest(updated)
    return updated
