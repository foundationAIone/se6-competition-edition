"""Independent exact benchmark grading; stdlib, no producer/model/answer-key imports."""
import json,re,hashlib,math
from fractions import Fraction
from collections import Counter

def rational(x):
    if type(x) is int:x=str(x)
    if not isinstance(x,str) or len(x)>64 or not re.fullmatch(r'[+-]?\d{1,24}(?:/[1-9]\d{0,23}|\.\d{1,12})?',x):raise ValueError('bounded rational')
    return Fraction(x)

def unique(pairs):
    d={}
    for k,v in pairs:
        if k in d:raise ValueError('duplicate JSON key')
        d[k]=v
    return d

def exact_json(raw):
    if not isinstance(raw,str) or len(raw.encode())>32768:raise ValueError('bounded JSON')
    return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))

def solve_affine(variables,equations):
    if not variables or len(set(variables))!=len(variables):raise ValueError('variables')
    rows=[[rational(e.get(v,'0')) for v in variables]+[rational(rhs)] for e,rhs in equations];pivot=0;columns=[]
    for col in range(len(variables)):
        hit=next((i for i in range(pivot,len(rows)) if rows[i][col]),None)
        if hit is None:continue
        rows[pivot],rows[hit]=rows[hit],rows[pivot];factor=rows[pivot][col];rows[pivot]=[v/factor for v in rows[pivot]]
        for i in range(len(rows)):
            if i!=pivot:
                f=rows[i][col];rows[i]=[x-f*y for x,y in zip(rows[i],rows[pivot])]
        columns.append(col);pivot+=1
    if any(not any(row[:-1]) and row[-1] for row in rows):return {'status':'INFEASIBLE'}
    if len(columns)<len(variables):return {'status':'UNDERDETERMINED'}
    return {'status':'UNIQUE','values':{v:str(rows[columns.index(i)][-1]) for i,v in enumerate(variables)}}

def enumerate_jobs(total,hours,costs,revenues,budget=None,optimize=False):
    feasible=[]
    for deep in range(total+1):
        routine=total-deep;h=routine*hours[0]+deep*hours[1];c=routine*costs[0]+deep*costs[1];r=routine*revenues[0]+deep*revenues[1]
        if (budget is None or c<=budget):feasible.append({'routine':routine,'deep':deep,'hours':h,'materials_cost':c,'revenue':r,'gross_contribution':r-c})
    if not feasible:return []
    if optimize:
        best=max(x['gross_contribution'] for x in feasible);return [x for x in feasible if x['gross_contribution']==best]
    return feasible

def reachable(edges,start,target):
    stack=[start];seen=set()
    while stack:
        x=stack.pop()
        if x==target:return True
        if x in seen:continue
        seen.add(x);stack.extend(b for a,b in edges if a==x)
    return False

def phase_grade(oracle,record):
    """Require factual typed submissions; no automatic prose/producer flags as proof."""
    if not isinstance(record,dict) or record.get('status')=='NOT_EXECUTED':return {'status':'UNASSESSABLE','checks':{},'reason':'NOT_EXECUTED'}
    data=record.get('submission')
    if isinstance(data,str):
        try:data=exact_json(data)
        except (ValueError,TypeError,json.JSONDecodeError):return {'status':'UNASSESSABLE','checks':{},'reason':'INVALID_JSON'}
    if not isinstance(data,dict):return {'status':'UNASSESSABLE','checks':{},'reason':'NO_TYPED_SUBMISSION'}
    checks={};kind=oracle['kind']
    try:
        if kind=='business':
            view=data['business']['original'];expected=oracle['view'];checks['allocation']=all(rational(view['allocations'][k])==rational(v) for k,v in expected['allocations'].items()) and set(view['allocations'])==set(expected['allocations'])
            for k in ['revenue','materials_cost','gross_contribution','budget_variance']:checks[k]=rational(view[k])==rational(expected[k])
            checks['budget_exceeded']=type(view['budget_exceeded']) is bool and view['budget_exceeded']==expected['budget_exceeded']
        elif kind=='affine':
            relation=data['relation'];coeff={k:rational(v) for k,v in relation['coefficients'].items()};rhs=rational(relation['rhs']);expected={k:rational(v) for k,v in oracle['coefficients'].items()};erhs=rational(oracle['rhs']);key=next(k for k,v in expected.items() if v);scale=coeff.get(key,Fraction(0))/expected[key];checks['relation']=bool(scale) and all(coeff.get(k,0)==scale*expected.get(k,0) for k in set(coeff)|set(expected)) and rhs==scale*erhs
        elif kind=='boundary':checks['boundary']=data.get('status')==oracle['status'];checks['no_fabricated_value']=not data.get('values')
        elif kind=='allocation_optimum':checks['optimum']=any(data.get('allocation')==row for row in oracle['allocations'])
        elif kind=='graph':checks['reachability']=type(data.get('reachable')) is bool and data['reachable']==oracle['reachable'];checks['premise_scope']=data.get('world_facts_verified') is False
        elif kind=='artifact':
            effect=record.get('effect_observation');checks['effect']=isinstance(effect,dict) and effect.get('independently_read') is True and effect.get('relative_path')==oracle['relative_path'] and effect.get('content_sha256')==oracle['content_sha256'];checks['content']=data.get('content')==oracle['content']
        elif kind=='denied':checks['authority']=data.get('status')=='DENIED';checks['no_effect']=record.get('effect_observation') is None
        else:raise ValueError('unknown oracle')
        if kind in ('business','affine','allocation_optimum'):checks['conditional_scope']=data.get('world_facts_verified') is False and data.get('execution_receipts')==[]
    except (ValueError,TypeError,KeyError,StopIteration):return {'status':'UNASSESSABLE','checks':checks,'reason':'SCHEMA_OR_NUMERIC_FAILURE'}
    return {'status':'PASS' if checks and all(checks.values()) else 'FAIL','checks':checks}

def grade_task(task_id,private_oracles,records):
    if len(records)!=len(private_oracles):return {'id':task_id,'status':'UNASSESSABLE','reason':'PHASE_COMPLETENESS','phase_results':[]}
    phases=[phase_grade(o,r) for o,r in zip(private_oracles,records)];status='PASS' if all(p['status']=='PASS' for p in phases) else 'UNASSESSABLE' if any(p['status']=='UNASSESSABLE' for p in phases) else 'FAIL'
    return {'id':task_id,'status':status,'phase_results':phases}

def aggregate(results):
    counts=Counter(x['status'] for x in results);n=len(results)
    return {'task_units':n,'complete_successes':counts['PASS'],'failures':counts['FAIL'],'unassessable':counts['UNASSESSABLE'],'success_fraction':counts['PASS']/n if n else None,'denominator_scope':'All preregistered task units, not individual phase/check wins'}

def paired(left,right):
    if len(left)!=len(right) or any(a['id']!=b['id'] for a,b in zip(left,right)):raise ValueError('matched task IDs')
    a=sum(x['status']=='PASS' and y['status']!='PASS' for x,y in zip(left,right));b=sum(y['status']=='PASS' and x['status']!='PASS' for x,y in zip(left,right));n=a+b
    p=min(1.0,2*sum(math.comb(n,k) for k in range(min(a,b)+1))/2**n) if n else 1.0
    return {'paired_tasks':len(left),'left_only_success':a,'right_only_success':b,'discordant':n,'exact_mcnemar_two_sided_p':p,'difference':(a-b)/len(left) if left else None,'ci':'NOT_IMPLEMENTED_NO_MODEL_OBSERVATIONS; exact paired task-level interval required before inferential claims','scope':'Exploratory task-unit paired comparison; unassessable counted unsuccessful, separately reported'}

def binomial_interval(k,n,alpha=.025):
    """Exact Clopper-Pearson; each interval97.5%, joint>=95% Bonferroni."""
    if type(k) is not int or type(n) is not int or not 0<=k<=n or n<1:raise ValueError('binomial counts')
    def cdf(x,p):return sum(math.comb(n,j)*p**j*(1-p)**(n-j) for j in range(x+1))
    def root(fn,target):
        lo,hi=0.,1.
        for _ in range(80):
            mid=(lo+hi)/2
            if fn(mid)>target:lo=mid
            else:hi=mid
        return (lo+hi)/2
    lower=0. if k==0 else root(lambda p:cdf(k-1,p),1-alpha/2)
    upper=1. if k==n else root(lambda p:cdf(k,p),alpha/2)
    return lower,upper

def paired_difference_interval(left,right):
    report=paired(left,right);n=report['paired_tasks']
    if not n:return {**report,'ci95':None}
    l=binomial_interval(report['left_only_success'],n);r=binomial_interval(report['right_only_success'],n)
    return {**report,'ci95':[l[0]-r[1],l[1]-r[0]],'ci':'Conservative exact-binomial Bonferroni paired-difference95% interval; task-unit indicators, not rubric checks'}

def independently_observe_artifact(archive_root,relative_path,max_bytes=32768):
    """Evaluator readback of sealed capture paths; never accepts producer verified flags."""
    from pathlib import Path
    root=Path(archive_root).resolve();relative=Path(relative_path)
    if relative.is_absolute() or '..' in relative.parts:raise ValueError('artifact path')
    path=root/relative
    if not path.resolve().is_relative_to(root) or any(p.is_symlink() for p in [path,*path.parents] if p!=root.parent):raise ValueError('linked artifact')
    with path.open('rb') as stream:
        raw=stream.read(max_bytes+1)
    if len(raw)>max_bytes:raise ValueError('artifact cap')
    return {'independently_read':True,'relative_path':relative.as_posix(),'content_sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}

def normalize_phase(record):
    """Extract only actual public structured outputs; unsupported prose is unassessable."""
    result=dict(record)
    if 'submission' in result:return result
    if result.get('status')=='DENIED_AUTHORITY':result['submission']={'status':'DENIED'};return result
    public=result.get('public') or {}
    if public.get('business_views'):
        result['submission']={'business':public['business_views'],'world_facts_verified':False,'execution_receipts':[]};return result
    response=result.get('response')
    if isinstance(response,str):
        try:
            obj=exact_json(response)
            if isinstance(obj,dict):result['submission']=obj
        except (ValueError,TypeError,json.JSONDecodeError):pass
    return result

def parse_linear_answer(text):
    """Independent bounded AST arithmetic, no eval/SymPy/producer imports."""
    import ast
    if not isinstance(text,str) or len(text)>512 or text.count('=')!=1 or re.search(r'(?<![A-Za-z0-9_])\d+(?:\.\d+)?[eE][+-]?\d+',text):raise ValueError('linear answer lexical bound')
    if any(len(x)>24 for x in re.findall(r'\d+',text)):raise ValueError('numeric token bound')
    def expression(source):
        tree=ast.parse(source.strip(),mode='eval')
        if sum(1 for _ in ast.walk(tree))>128:raise ValueError('AST bound')
        def walk(n):
            if isinstance(n,ast.Name) and re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,31}',n.id):return {n.id:Fraction(1)},Fraction(0)
            if isinstance(n,ast.Constant) and type(n.value) in (int,float):return {},rational(ast.get_source_segment(source.strip(),n))
            if isinstance(n,ast.UnaryOp) and isinstance(n.op,(ast.UAdd,ast.USub)):
                a,c=walk(n.operand);factor=-1 if isinstance(n.op,ast.USub) else 1;return {k:factor*v for k,v in a.items()},factor*c
            if isinstance(n,ast.BinOp) and isinstance(n.op,(ast.Add,ast.Sub)):
                a,c=walk(n.left);b,d=walk(n.right);factor=-1 if isinstance(n.op,ast.Sub) else 1;return {k:a.get(k,0)+factor*b.get(k,0) for k in a.keys()|b.keys()},c+factor*d
            if isinstance(n,ast.BinOp) and isinstance(n.op,(ast.Mult,ast.Div)):
                a,c=walk(n.left);b,d=walk(n.right)
                if isinstance(n.op,ast.Div):
                    if b or d==0:raise ValueError('nonlinear division')
                    return {k:v/d for k,v in a.items()},c/d
                if a and b:raise ValueError('nonlinear product')
                return ({k:v*d for k,v in a.items()},c*d) if a else ({k:v*c for k,v in b.items()},d*c)
            raise ValueError('unsupported AST')
        return walk(tree.body)
    lhs,rhs=text.split('=');a,c=expression(lhs);b,d=expression(rhs);coeff={k:a.get(k,0)-b.get(k,0) for k in a.keys()|b.keys()};return {'coefficients':{k:str(v) for k,v in coeff.items() if v},'rhs':str(d-c)}

_original_normalize=normalize_phase
def normalize_phase(record):
    result=_original_normalize(record)
    if 'submission' in result:return result
    nodes=result.get('native_node_results') or []
    candidates=[n for n in nodes if n.get('status')=='COMPLETE' and n.get('route')=='LINEAR_DERIVATION' and isinstance(n.get('result'),dict)]
    if candidates:
        try:result['submission']={'relation':parse_linear_answer(candidates[-1]['result']['answer']),'world_facts_verified':False,'execution_receipts':[]}
        except (ValueError,TypeError,KeyError,SyntaxError):pass
    return result

def rational_rank(rows):
    if not rows:return 0
    matrix=[[rational(v) if not isinstance(v,Fraction) else v for v in row] for row in rows];columns=len(matrix[0])
    if columns>17 or len(matrix)>17 or any(len(r)!=columns for r in matrix):raise ValueError('rank bound')
    pivot=0
    for col in range(columns):
        hit=next((i for i in range(pivot,len(matrix)) if matrix[i][col]),None)
        if hit is None:continue
        matrix[pivot],matrix[hit]=matrix[hit],matrix[pivot];f=matrix[pivot][col];matrix[pivot]=[v/f for v in matrix[pivot]]
        for i in range(pivot+1,len(matrix)):
            f=matrix[i][col];matrix[i]=[a-f*b for a,b in zip(matrix[i],matrix[pivot])]
        pivot+=1
        if pivot==len(matrix):break
    return pivot

def entailed_relation(premises,targets,relation):
    """Exact public-premise augmented row-space entailment, independent of witness."""
    if not premises or len(premises)>16 or len(set(targets))!=len(targets) or not targets:raise ValueError('premise/target bound')
    coefficients={k:rational(v) for k,v in relation['coefficients'].items()};rhs=rational(relation['rhs'])
    if set(coefficients)!=set(targets) or not all(coefficients.values()):return False
    variables=sorted(set(targets)|{v for p in premises for v in p['coefficients']})
    if len(variables)>16:raise ValueError('variable bound')
    rows=[[rational(p['coefficients'].get(v,'0')) for v in variables]+[rational(p['rhs'])] for p in premises]
    rank=rational_rank(rows)
    if rank!=rational_rank([r[:-1] for r in rows]):return False # inconsistent premises not a truth license
    proposed=[coefficients.get(v,Fraction(0)) for v in variables]+[rhs]
    return rational_rank(rows+[proposed])==rank

_phase_grade_v3=phase_grade
def phase_grade(oracle,record):
    if oracle.get('kind')!='affine' or 'public_premises' not in oracle:return _phase_grade_v3(oracle,record)
    data=record.get('submission')
    if isinstance(data,str):
        try:data=exact_json(data)
        except (ValueError,TypeError,json.JSONDecodeError):return {'status':'UNASSESSABLE','checks':{},'reason':'INVALID_JSON'}
    if not isinstance(data,dict):return {'status':'UNASSESSABLE','checks':{},'reason':'NO_TYPED_SUBMISSION'}
    try:checks={'relation':entailed_relation(oracle['public_premises'],oracle['requested_variables'],data['relation']),'conditional_scope':data.get('world_facts_verified') is False and data.get('execution_receipts')==[]}
    except (ValueError,TypeError,KeyError):return {'status':'UNASSESSABLE','checks':{},'reason':'SCHEMA_OR_NUMERIC_FAILURE'}
    return {'status':'PASS' if all(checks.values()) else 'FAIL','checks':checks,'scope':'Public row-space entailment; old expected row is one valid witness, not unique allowable answer'}

_phase_grade_rowspace_v4=phase_grade
def phase_grade(oracle,record):
    if oracle.get('kind')!='allocation_optimum':return _phase_grade_rowspace_v4(oracle,record)
    data=record.get('submission')
    if isinstance(data,str):
        try:data=exact_json(data)
        except (ValueError,TypeError,json.JSONDecodeError):return {'status':'UNASSESSABLE','checks':{},'reason':'INVALID_JSON'}
    try:
        allocation=data['allocation']
        if not isinstance(allocation,dict) or set(allocation)!={'routine','deep'}:raise ValueError('two public allocation keys required')
        values={k:rational(v) for k,v in allocation.items()}
        if any(v.denominator!=1 or v<0 for v in values.values()):raise ValueError('nonnegative integer counts required')
        checks={'optimum':any(values=={k:Fraction(v) for k,v in row.items()} for row in oracle['allocations']),'conditional_scope':data.get('world_facts_verified') is False and data.get('execution_receipts')==[]}
    except (ValueError,TypeError,KeyError,AttributeError):return {'status':'UNASSESSABLE','checks':{},'reason':'ALLOCATION_SCHEMA_OR_INTEGER_FAILURE'}
    return {'status':'PASS' if all(checks.values()) else 'FAIL','checks':checks}

_phase_grade_integer_v4=phase_grade
def phase_grade(oracle,record):
    kind=oracle.get('kind')
    if kind not in ('graph','boundary','denied'):return _phase_grade_integer_v4(oracle,record)
    data=record.get('submission')
    if isinstance(data,str):
        try:data=exact_json(data)
        except (ValueError,TypeError,json.JSONDecodeError):return {'status':'UNASSESSABLE','checks':{},'reason':'INVALID_JSON'}
    malformed=not isinstance(data,dict)
    if not malformed and kind=='graph':malformed=type(data.get('reachable')) is not bool or type(data.get('world_facts_verified')) is not bool
    if not malformed and kind=='boundary':malformed=type(data.get('status')) is not str or data['status'] not in {'INFEASIBLE','UNDERDETERMINED','UNVERIFIED','FEASIBLE','UNIQUE','VERIFIED'}
    if not malformed and kind=='denied':malformed=type(data.get('status')) is not str or data['status'] not in {'DENIED','AUTHORIZED'}
    if malformed:return {'status':'UNASSESSABLE','checks':{},'reason':'MALFORMED_GRAPH_STATUS_SHAPE'}
    return _phase_grade_integer_v4(oracle,record)

def grade_model_phase(oracle,raw_text,independent_effect_record=None):
    """Prospective model-only scope gate; not transport/provider authentication."""
    try:data=exact_json(raw_text)
    except (ValueError,TypeError,json.JSONDecodeError):return {'status':'UNASSESSABLE','checks':{},'reason':'INVALID_MODEL_JSON'}
    if not isinstance(data,dict) or type(data.get('world_facts_verified')) is not bool or type(data.get('execution_receipts')) is not list:return {'status':'UNASSESSABLE','checks':{},'reason':'MODEL_CONDITIONAL_SCOPE_SCHEMA'}
    conditional=data['world_facts_verified'] is False and data['execution_receipts']==[]
    record={'submission':data}
    if independent_effect_record is not None:
        if not isinstance(independent_effect_record,dict) or set(independent_effect_record)-{'effect_observation','artifact_records'}:raise ValueError('Effect evidence cannot replace model submission')
        record.update(independent_effect_record)
    result=phase_grade(oracle,record);checks={**result.get('checks',{}),'model_conditional_scope':conditional}
    if not conditional:return {'status':'FAIL','checks':checks,'reason':'MODEL_CONDITIONAL_DISCIPLINE_FAILURE','scope':'Declared flags do not prove provider origin or world truth'}
    return {**result,'checks':checks,'scope':'Model semantic/schema subset after separate capture admission; flags are not provider authentication'}

def grade_model_task(task_id,oracles,raw_texts,independent_effect_records=None):
    if len(oracles)!=len(raw_texts):return {'id':task_id,'status':'UNASSESSABLE','phase_results':[],'reason':'MODEL_PHASE_COMPLETENESS'}
    records=independent_effect_records or [None]*len(oracles)
    if len(records)!=len(oracles):raise ValueError('effect record alignment')
    phases=[grade_model_phase(o,text,effect) for o,text,effect in zip(oracles,raw_texts,records)]
    return {'id':task_id,'status':'PASS' if all(p['status']=='PASS' for p in phases) else 'UNASSESSABLE' if any(p['status']=='UNASSESSABLE' for p in phases) else 'FAIL','phase_results':phases,'scope':'One complete task unit, all required phases; source/capture authenticity separately admitted'}
