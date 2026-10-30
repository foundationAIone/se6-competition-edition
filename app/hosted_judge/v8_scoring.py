"""Bounded independent public-premise scoring; no native engine, key or provider."""
import json,re
from fractions import Fraction

PUBLIC_CONTRACT=('For a supported labelled affine derivation return JSON with relation '
 '{coefficients:{variable:rational_string},rhs:rational_string}, certificate '
 '{public_equation_label:rational_weight}, world_facts_verified:false, execution_receipts:[]. '
 'For the supported two-class job business format return JSON with business views keyed '
 'original/corrected, each containing allocations by class, revenue, materials_cost, '
 'gross_contribution, budget_variance, budget_exceeded; also world_facts_verified:false '
 'and execution_receipts:[]. For other work explain unsupported scope; no automatic '
 'prose correctness or winner will be assigned. Only an explicit Correct E# instruction '
 'replaces an earlier labelled equation; an unannounced conflicting equation is not '
 'assimilated. Business views use current explicitly corrected unit prices/budget. '
 'All values are conditional supplied facts.')

def public_output_shape(question,public_history):
    """Public key/type instructions only; no solved values or evaluator truth."""
    try:
        normalized=derived_question(question,public_history)
        facts=public_business(normalized)
        if facts:
            view={'allocations':{name:'RATIONAL' for name in facts['classes']},
                'revenue':'RATIONAL','materials_cost':'RATIONAL','gross_contribution':'RATIONAL',
                'budget_variance':'RATIONAL','budget_exceeded':'BOOLEAN'}
            shape={'business':{tag:view for tag in facts['hours']},
                'world_facts_verified':False,'execution_receipts':[]}
            return (' Return only one JSON object, no markdown or prose. Exact keys and lowercase class names: '
                +json.dumps(shape,separators=(',',':'))
                +'. Replace RATIONAL with your calculated rational string and BOOLEAN with a JSON boolean. '
                'The top-level key is business, never business views. These placeholders contain no solution.')
    except (ValueError,TypeError,KeyError,ZeroDivisionError):pass
    return ' Return only one complete JSON object, no markdown, reasoning or prose outside the object.'

def rational(value):
    if type(value) is int:value=str(value)
    if not isinstance(value,str) or len(value)>64 or not re.fullmatch(r'[+-]?[0-9]{1,24}(?:/[1-9][0-9]{0,23}|\.[0-9]{1,12})?',value):raise ValueError('Bounded rational required')
    return Fraction(value)

def unique_object(pairs):
    result={}
    for k,v in pairs:
        if k in result:raise ValueError('Duplicate JSON key')
        result[k]=v
    return result

def decoded(text):
    if not isinstance(text,str) or len(text.encode())>65536:raise ValueError('Output bound')
    return json.loads(text,object_pairs_hook=unique_object,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('Nonfinite')))

def affine(raw):
    if len(raw)>512:raise ValueError('Expression bound')
    raw=re.sub(r'\s+','',raw);terms=re.findall(r'[+-]?[^+-]+',raw)
    if not terms or ''.join(terms)!=raw:raise ValueError('Affine grammar')
    coefficients={};constant=Fraction(0)
    for term in terms:
        sign=-1 if term.startswith('-') else 1;body=term[1:] if term[:1] in '+-' else term
        match=re.fullmatch(r'(?:(\d+(?:/\d+|\.\d+)?)\*?)?([A-Za-z][A-Za-z0-9_]{0,31})',body)
        if match:coefficients[match[2]]=coefficients.get(match[2],0)+sign*rational(match[1] or '1')
        else:constant+=sign*rational(body)
    return {k:v for k,v in coefficients.items() if v},constant

def public_linear(question):
    equations={}
    for line in question.splitlines():
        match=re.fullmatch(r'\s*(E[1-4]):\s*([^=]+)=([^=]+)\s*',line)
        if not match:continue
        if match[1] in equations:raise ValueError('Duplicate public equation label')
        lhs,a=affine(match[2]);rhs,b=affine(match[3]);co={k:lhs.get(k,0)-rhs.get(k,0) for k in set(lhs)|set(rhs)}
        equations[match[1]]=({k:v for k,v in co.items() if v},b-a)
    targets=re.findall(r'Derive (?:a |the )?relation (?:involving|between|among) ([A-Za-z0-9_, ]+)\.?',question,re.I)
    if not equations or len(targets)!=1:return None
    target=set(re.split(r'\s*(?:,|\band\b)\s*',targets[0].strip()))
    names=set().union(*(set(co) for co,rhs in equations.values()))
    if not target or not target<=names or len(names)>6:raise ValueError('Target or variable bound')
    return equations,target

def in_span(rows,wanted):
    def rank(matrix):
        matrix=[list(row) for row in matrix];pivot=0
        for c in range(len(wanted)):
            at=next((i for i in range(pivot,len(matrix)) if matrix[i][c]),None)
            if at is None:continue
            matrix[pivot],matrix[at]=matrix[at],matrix[pivot];scale=matrix[pivot][c];matrix[pivot]=[v/scale for v in matrix[pivot]]
            for i in range(len(matrix)):
                if i!=pivot:
                    scale=matrix[i][c];matrix[i]=[x-scale*y for x,y in zip(matrix[i],matrix[pivot])]
            pivot+=1
        return pivot
    return rank(rows)==rank(rows+[wanted])

def linear(value,truth):
    equations,target=truth
    if set(value)!={'relation','certificate','world_facts_verified','execution_receipts'}:raise ValueError('Exact linear schema required')
    rel=value['relation'];cert=value['certificate']
    if set(rel)!={'coefficients','rhs'} or not isinstance(rel['coefficients'],dict) or not isinstance(cert,dict) or len(cert)>4:raise ValueError('Relation/certificate schema')
    co={k:rational(v) for k,v in rel['coefficients'].items()};rhs=rational(rel['rhs']);names=sorted(set().union(*(set(x[0]) for x in equations.values())))
    if set(co)-set(names) or set(cert)-set(equations):raise ValueError('Unknown public variable or label')
    rows=[[terms.get(k,0) for k in names]+[r] for terms,r in equations.values()]
    # Inconsistent public premises do not make arbitrary answers assessable.
    if in_span(rows,[Fraction(0)]*len(names)+[Fraction(1)]):raise ValueError('Inconsistent public premise set')
    wanted=[co.get(k,0) for k in names]+[rhs]
    correct=bool(co) and {k for k,v in co.items() if v}==target and in_span(rows,wanted)
    weights={k:rational(v) for k,v in cert.items()};sum_co={k:sum(weights.get(label,0)*terms.get(k,0) for label,(terms,r) in equations.items()) for k in names};sum_rhs=sum(weights.get(label,0)*r for label,(terms,r) in equations.items())
    proof=any(weights.values()) and all(sum_co[k]==co.get(k,0) for k in names) and sum_rhs==rhs
    discipline=value['world_facts_verified'] is False and value['execution_receipts']==[]
    return {'status':'ASSESSABLE','score':int(correct)+int(proof)+int(discipline),'maximum':3,'checks':{'entailed_requested_relation':correct,'public_certificate':proof,'conditional_scope':discipline},'scope':'Exact conditional affine/certificate subset; additional prose unscored'}

def public_business(question):
    """Independent bounded two-class public fact parser; no native imports."""
    number=r'\d+(?:/\d+|\.\d+)?';money=r'(\$|USD)\s*('+number+r')'
    rates=list(re.finditer(r'^([A-Za-z][A-Za-z0-9_]{0,31}):\s*('+number+r')\s+([A-Za-z]+-hours)\b[^\n]*',question,re.M))
    total=re.search(r'\bcompleted (\d+) jobs\b',question,re.I);hours=re.search(r'\boriginal \w+ recorded ('+number+r') ([A-Za-z]+-hours)\b',question,re.I)
    budgets=list(re.finditer(r'\bmaterials budget is '+money,question,re.I))
    if not rates:return None
    if len(rates)!=2 or not total or not hours or len(budgets)!=1:raise ValueError('Complete unique public business inputs required')
    classes=[r[1].lower() for r in rates]
    if len(set(classes))!=2 or any(r[3].lower()!=hours[2].lower() for r in rates):raise ValueError('Business dimensions differ')
    facts={}
    for row,name in zip(rates,classes):
        for column,word in [('expense','materials cost'),('revenue','customer revenue')]:
            found=list(re.finditer(money+r'\s+'+word+r'\b',row[0],re.I))
            if len(found)!=1:raise ValueError('Unique public cost/revenue required')
            amount=rational(found[0][2])
            if amount<0:raise ValueError('Nonnegative business amount required')
            facts[name+':'+column]={'value':str(amount)}
    facts['budget']={'value':str(rational(budgets[0][2]))}
    possibilities={'original':str(rational(hours[1]))}
    corrected=re.search(r'\bcorrection showing ('+number+r') '+re.escape(hours[2])+r'\b',question,re.I)
    if corrected:possibilities['corrected']=str(rational(corrected[1]))
    return {'mode':'INITIAL','classes':classes,'total_jobs':int(total[1]),'hours_per_job':{row[1].lower():str(rational(row[2])) for row in rates},'hours':possibilities,'facts':facts,'hour_unit':hours[2]}

def derived_question(question,public_history):
    """Normalize only PUBLIC labelled facts; never native output or model answers."""
    equations={};conflicts=set();business_state=None
    for text in [*public_history,question]:
        parsed_business=public_business(text)
        if parsed_business is not None:
            if business_state is not None and parsed_business!=business_state:raise ValueError('Unannounced business replacement')
            business_state=parsed_business
        if business_state is not None:
            update=re.fullmatch(r'\s*Correct (?:(\w+) (materials cost|customer revenue)|materials budget) to (?:\$|USD)\s*(\d+(?:\.\d+)?)\.?(?:\s+Verify(?: it)?\.?)?\s*',text,re.I)
            if update:
                name,column,amount=update.groups();key='budget' if name is None else name.lower()+':'+('expense' if column.lower()=='materials cost' else 'revenue')
                if key not in business_state['facts']:raise ValueError('Unknown corrected business fact')
                business_state['facts'][key]={'value':str(rational(amount))}
            corrected=re.fullmatch(r'\s*Correct (?:the recorded hours|recorded hours) to (\d+(?:\.\d+)?) '+re.escape(business_state['hour_unit'])+r'\.?(?:\s+Verify(?: it)?\.?)?\s*',text,re.I)
            if corrected:business_state['hours']['corrected']=str(rational(corrected[1]))
        for line in text.splitlines():
            correction=re.fullmatch(r'\s*Correct (E[1-4]) to ([^=]+=[^=]+)\.?(?:\s*Verify(?: it)?\.?)?\s*',line,re.I)
            ordinary=re.fullmatch(r'\s*(E[1-4]):\s*([^=]+=[^=]+)\s*',line)
            if correction:
                label=correction[1].upper();row=correction[2].rstrip('.')
                if label not in equations:raise ValueError('Correction has no public predecessor')
                equations[label]=row;conflicts.discard(label)
            elif ordinary:
                label,row=ordinary.groups()
                if label in equations and equations[label]!=row:conflicts.add(label)
                else:equations[label]=row
    if conflicts:raise ValueError('Unannounced public contradiction unresolved')
    target_lines=[line.strip() for line in question.splitlines() if re.match(r'Derive\b',line.strip(),re.I)]
    if equations and len(target_lines)==1:return '\n'.join(k+': '+v for k,v in equations.items())+'\n'+target_lines[0]
    if business_state:
        a,b=business_state['classes'];pieces=[f"We completed {business_state['total_jobs']} jobs. The original log recorded {business_state['hours']['original']} {business_state['hour_unit']}."]
        if 'corrected' in business_state['hours']:pieces.append('The correction showing '+business_state['hours']['corrected']+' '+business_state['hour_unit']+'.')
        for name in [a,b]:pieces.append(f"{name}: {business_state['hours_per_job'][name]} {business_state['hour_unit']}, USD {business_state['facts'][name+':expense']['value']} materials cost, USD {business_state['facts'][name+':revenue']['value']} customer revenue")
        pieces.append('The materials budget is USD '+business_state['facts']['budget']['value']+'.')
        return '\n'.join(pieces)
    return question

def business(value,question):
    facts=public_business(question)
    if facts is None:return None
    if set(value)!={'business','world_facts_verified','execution_receipts'} or set(value['business'])!=set(facts['hours']):raise ValueError('Business output schema')
    a,b=facts['classes'];ha=rational(facts['hours_per_job'][a]);hb=rational(facts['hours_per_job'][b]);jobs=facts['total_jobs']
    if type(jobs) is not int or not 0<jobs<128 or ha==hb:raise ValueError('Unique bounded allocation required')
    checks={}
    for scenario,hours in facts['hours'].items():
        qb=(rational(hours)-ha*jobs)/(hb-ha);qa=jobs-qb
        if min(qa,qb)<0 or qa.denominator!=1 or qb.denominator!=1:raise ValueError('No bounded integer allocation')
        revenue=sum(q*rational(facts['facts'][n+':revenue']['value']) for n,q in [(a,qa),(b,qb)]);cost=sum(q*rational(facts['facts'][n+':expense']['value']) for n,q in [(a,qa),(b,qb)]);budget=rational(facts['facts']['budget']['value']);view=value['business'][scenario]
        if set(view)!={'allocations','revenue','materials_cost','gross_contribution','budget_variance','budget_exceeded'} or set(view['allocations'])!={a,b}:raise ValueError('Exact business view required')
        for name,truth in {'revenue':revenue,'materials_cost':cost,'gross_contribution':revenue-cost,'budget_variance':cost-budget}.items():checks[scenario+':'+name]=rational(view[name])==truth
        checks[scenario+':allocation']=rational(view['allocations'][a])==qa and rational(view['allocations'][b])==qb
        checks[scenario+':budget_exceeded']=view['budget_exceeded'] is (cost>budget)
    checks['conditional_scope']=value['world_facts_verified'] is False and value['execution_receipts']==[]
    return {'status':'ASSESSABLE','score':sum(checks.values()),'maximum':len(checks),'checks':checks,'scope':'Exact supplied allocation/money subset; recommendations/signatures/code/prose unscored'}

def assess(question,text):
    try:
        value=decoded(text)
        if not isinstance(value,dict):raise ValueError('Object required')
        truth=public_linear(question)
        if truth:return linear(value,truth)
        result=business(value,question)
        if result:return result
    except (ValueError,TypeError,KeyError,ZeroDivisionError,OverflowError,RecursionError):pass
    return {'status':'UNASSESSABLE','score':None,'scope':'No supported public exact truth/output schema; arbitrary prose has no automatic winner'}

def score_pair(question,captures,simulated=False):
    lanes={lane:assess(question,captures[lane]['text']) for lane in ('se6','baseline')};winner=None
    if not simulated and all(x['status']=='ASSESSABLE' for x in lanes.values()):winner='TIE' if lanes['se6']['score']==lanes['baseline']['score'] else max(lanes,key=lambda k:lanes[k]['score'])
    return {'lanes':lanes,'arithmetic_winner':winner,'overall_winner':None,'origin':'SIMULATED' if simulated else 'FROZEN_PROVIDER_CAPTURE','scope':'Subset arithmetic/certificates only; no general-purpose/model superiority inference'}
