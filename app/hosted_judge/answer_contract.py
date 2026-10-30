"""Common public answer validation; trusted scope/evidence are separate.

No model is asked to invent internal receipts, identifiers or provenance.
Semantic checks reuse approved exact row-space code and independently check
business conservation and graph closure. No provider, state mutation or oracle.
"""
from fractions import Fraction
import hashlib,json,re,math
from itertools import product
from .benchmark_scoring import rational_rank

SCHEMA='se6-common-answer-contract-v1'
BUSINESS={'allocations','revenue','materials_cost','gross_contribution','budget_variance','budget_exceeded'}
BOUNDARIES={'BLOCKED','UNVERIFIED','INFEASIBLE','UNDERDETERMINED','DENIED','UNSUPPORTED'}

def encode(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(v):return hashlib.sha256(encode(v)).hexdigest()
def rational(v):
    if type(v) is int:v=str(v)
    if not isinstance(v,str) or len(v)>64 or not re.fullmatch(r'[+-]?\d{1,24}(?:/\d{1,24}|\.\d{1,24})?',v):raise ValueError('RATIONAL_TYPE')
    try:return Fraction(v)
    except ZeroDivisionError:raise ValueError('RATIONAL_DENOMINATOR') from None
def decode_final(text,finish_reason):
    if finish_reason!='stop':raise ValueError('NONFINAL_RESPONSE')
    if not isinstance(text,str) or not 0<len(text.encode())<=32768:raise ValueError('FINAL_BYTE_BOUND')
    def pairs(items):
        out={}
        for k,v in items:
            if k in out:raise ValueError('DUPLICATE_FIELD')
            out[k]=v
        return out
    try:
        value=json.loads(text,object_pairs_hook=pairs,parse_float=lambda s:s,
            parse_constant=lambda s:(_ for _ in ()).throw(ValueError('NONFINITE')))
    except (json.JSONDecodeError,RecursionError):raise ValueError('INVALID_FINAL_JSON') from None
    if not isinstance(value,dict):raise ValueError('OBJECT_REQUIRED')
    return value

def _verify_public_integer_domain(facts, relation=None):
    """Verifier only: exhaustive finite public assumptions, never generates answers."""
    bounds=facts['public_integer_domain']
    if not isinstance(bounds,list) or len(bounds)!=2 or any(type(v) is not int for v in bounds) or not -10000<=bounds[0]<=bounds[1]<=10000 or bounds[1]-bounds[0]>=128:raise ValueError('PUBLIC_DOMAIN_BOUND')
    variables=sorted({v for p in facts['premises'] for v in p['coefficients']}|set(facts['requested_variables']))
    if not 1<=len(variables)<=6 or not 1<=len(facts['premises'])<=4:raise ValueError('AFFINE_BOUND')
    cells=(bounds[1]-bounds[0]+1)**len(variables)
    if cells>250000:raise ValueError('PUBLIC_DOMAIN_RESOURCE_BOUND')
    def integer_row(coeff,rhs):
        vals=[rational(coeff.get(v,0)) for v in variables]+[rational(rhs)]
        scale=math.lcm(*(x.denominator for x in vals))
        return [int(x*scale) for x in vals]
    rows=[integer_row(p['coefficients'],p['rhs']) for p in facts['premises']]
    proposed=integer_row(relation['coefficients'],relation['rhs']) if relation is not None else None
    count=0;entailed=True;target_values=set();indices=[variables.index(v) for v in facts['requested_variables']]
    for assignment in product(range(bounds[0],bounds[1]+1),repeat=len(variables)):
        if not all(sum(c*x for c,x in zip(row[:-1],assignment))==row[-1] for row in rows):continue
        count+=1
        if len(target_values)<2:target_values.add(tuple(assignment[i] for i in indices))
        if proposed is not None and sum(c*x for c,x in zip(proposed[:-1],assignment))!=proposed[-1]:entailed=False
    return {'solutions':count,'multiple_target_values':len(target_values)>1,'entailed':count>0 and entailed,'cells_checked':cells,'verification_scope':'EXHAUSTIVE_EXPLICIT_PUBLIC_INTEGER_DOMAIN_ONLY'}

def verify_user_answer(task_type,user_answer,facts):
    """No receipt/scope requirements imposed on direct or assisted model JSON."""
    checks={'schema':False,'semantic':None};reason=None
    try:
        if not isinstance(user_answer,dict):raise ValueError('OBJECT_REQUIRED')
        if 'status' in user_answer:
            if set(user_answer)!={'status'} or user_answer['status'] not in BOUNDARIES:raise ValueError('BOUNDARY_SCHEMA')
            checks['schema']=True
            if task_type=='business' and user_answer['status']=='INFEASIBLE':
                classes=facts['classes']
                if not isinstance(classes,list) or len(classes)!=2 or len(set(classes))!=2:raise ValueError('BUSINESS_CLASS_BOUND')
                jobs=rational(facts['total_jobs']);hours=rational(facts['total_hours'])
                h0,h1=(rational(facts['hours_per_job'][c]) for c in classes)
                # Separate direct conservation diagnostic; no producer status flag.
                if jobs<0 or jobs.denominator!=1:infeasible=True
                elif h0==h1:infeasible=hours!=h0*jobs
                else:
                    first=(hours-h1*jobs)/(h0-h1);second=jobs-first
                    infeasible=any(v<0 or v.denominator!=1 for v in (first,second))
                checks['semantic']=infeasible
                checks['verification_scope']='PUBLIC_COMPLETED_JOBS_NONNEGATIVE_INTEGER_CONSERVATION_ONLY'
            elif task_type=='affine' and 'public_integer_domain' in facts and user_answer['status'] in ('INFEASIBLE','UNDERDETERMINED'):
                domain=_verify_public_integer_domain(facts)
                checks['semantic']=domain['solutions']==0 if user_answer['status']=='INFEASIBLE' else domain['solutions']>0 and len(facts['requested_variables'])==1 and domain['multiple_target_values']
                checks.update({k:v for k,v in domain.items() if k in ('cells_checked','verification_scope')})
            else:checks['semantic']=user_answer['status']==facts.get('boundary_status')
            return {**checks,'reason':None if checks['semantic'] else 'BOUNDARY_NOT_ESTABLISHED'}
        if task_type=='business':
            if set(user_answer)!=BUSINESS or type(user_answer['budget_exceeded']) is not bool:raise ValueError('BUSINESS_SCHEMA')
            allocations=user_answer['allocations'];classes=facts['classes']
            if not isinstance(allocations,dict) or set(allocations)!=set(classes):raise ValueError('ALLOCATION_SCHEMA')
            counts={n:rational(allocations[n]) for n in classes}
            values={k:rational(user_answer[k]) for k in BUSINESS-{'allocations','budget_exceeded'}}
            checks['schema']=True
            integral=all(v>=0 and v.denominator==1 for v in counts.values())
            hours=sum(counts[n]*rational(facts['hours_per_job'][n]) for n in classes)
            cost=sum(counts[n]*rational(facts['materials_per_job'][n]) for n in classes)
            revenue=sum(counts[n]*rational(facts['revenue_per_job'][n]) for n in classes)
            checks['semantic']=integral and sum(counts.values())==rational(facts['total_jobs']) and hours==rational(facts['total_hours']) and values=={'revenue':revenue,'materials_cost':cost,'gross_contribution':revenue-cost,'budget_variance':cost-rational(facts['budget'])} and user_answer['budget_exceeded']==(cost>rational(facts['budget']))
        elif task_type=='affine':
            if set(user_answer)!={'relation'} or not isinstance(user_answer['relation'],dict) or set(user_answer['relation'])!={'coefficients','rhs'}:raise ValueError('AFFINE_SCHEMA')
            relation=user_answer['relation'];coeff=relation['coefficients']
            if not isinstance(coeff,dict) or set(coeff)!=set(facts['requested_variables']) or any(not rational(v) for v in coeff.values()):raise ValueError('TARGET_SCHEMA')
            rational(relation['rhs']);checks['schema']=True
            variables=sorted({n for p in facts['premises'] for n in p['coefficients']}|set(coeff))
            if len(variables)>6 or not 1<=len(facts['premises'])<=4:raise ValueError('AFFINE_BOUND')
            rows=[[rational(p['coefficients'].get(v,'0')) for v in variables]+[rational(p['rhs'])] for p in facts['premises']]
            rank=rational_rank(rows)
            proposed=[rational(coeff.get(v,'0')) for v in variables]+[rational(relation['rhs'])]
            if 'public_integer_domain' in facts:
                domain=_verify_public_integer_domain(facts,relation)
                checks['semantic']=domain['entailed']
                checks.update({k:v for k,v in domain.items() if k in ('cells_checked','verification_scope')})
            else:checks['semantic']=rank==rational_rank([r[:-1] for r in rows]) and rational_rank(rows+[proposed])==rank
        elif task_type=='graph':
            if set(user_answer)!={'reachable'} or type(user_answer['reachable']) is not bool:raise ValueError('GRAPH_SCHEMA')
            checks['schema']=True
            # Distinct fixed-point closure, not the producer's stack traversal.
            seen={facts['start']}
            for _ in range(len(facts['edges'])+1):
                nxt=seen|{b for a,b in facts['edges'] if a in seen}
                if nxt==seen:break
                seen=nxt
            checks['semantic']=user_answer['reachable']==(facts['target'] in seen)
        else:raise ValueError('UNSUPPORTED_TASK')
        if not checks['semantic']:reason='SEMANTIC_MISMATCH'
    except (ValueError,TypeError,KeyError,ZeroDivisionError,OverflowError) as exc:
        reason='PUBLIC_DOMAIN_RESOURCE_BOUND' if str(exc)=='PUBLIC_DOMAIN_RESOURCE_BOUND' else 'SCHEMA_OR_PUBLIC_FACT_BOUNDARY'
    return {**checks,'reason':reason}

def make_envelope(prepared,user_answer,*,task_id,cycle,origin,evidence=None,finish_reason='stop'):
    """Caller binds task/source outside model output; nothing is a world fact."""
    if origin not in ('MODEL','NATIVE_DETERMINISTIC','HOST_DETERMINISTIC'):raise ValueError('ORIGIN')
    if not isinstance(task_id,str) or not re.fullmatch('[A-Za-z0-9_-]{1,64}',task_id) or type(cycle) is not int or cycle<0:raise ValueError('SCOPE_IDENTITY')
    checks=verify_user_answer(prepared['task_type'],user_answer,prepared['public_facts'])
    finish=finish_reason=='stop'
    # Evidence is independently admitted by the server/native proof worker.
    # Its omission never changes direct model semantic/schema correctness.
    evidence_ok=bool(evidence and evidence.get('verified') is True)
    accepted=checks['schema'] is True and checks['semantic'] is True and finish
    status='COMPLETE' if accepted and 'status' not in user_answer else user_answer.get('status','BLOCKED') if accepted else 'BLOCKED'
    return {'schema':SCHEMA,'status':status,'origin':origin,'user_answer':user_answer,
        'scope':{'task_id':task_id,'cycle':cycle,'question_sha256':prepared['original_question_sha256'],'world_facts_verified':False},
        'provenance':{'prepared_sha256':prepared['sha256'],'native_question_sha256':prepared.get('native_question_sha256'),
            'classification':'MODEL_PROPOSED' if origin=='MODEL' else 'CONDITIONAL_DETERMINISTIC','model_answer_substituted':False},
        'checks':{**checks,'finish':finish,'evidence':evidence_ok,'evidence_scope':'Separate capability; not a common model correctness requirement'},
        'evidence':evidence or {'verified':False,'kind':'NOT_EXECUTED'},
        'end_to_end_native_complete':status=='COMPLETE' and origin=='NATIVE_DETERMINISTIC' and evidence_ok
            and evidence.get('kind')=='SOURCE_BOUND_NATIVE_CHECKPOINT_PROOF' and bool(evidence.get('receipt_hashes'))}
