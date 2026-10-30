"""Owner-side finite integer verifier and proof-certificate evaluator.

Never imported by the lane builder or serving Workbench. No eval, solver
service, provider call or answer-key input. Mathematical entailment is checked
only within the declared finite domain, against the explicitly named premises.
"""
from functools import lru_cache
from itertools import product
import hashlib
import json
import re
import time

MAX_CELLS=5_000_000
MAX_PROOF_STEPS=16
OPS={'eq','ne','lt','le','gt','ge'}


def parse_model_response(raw):
    """Parse without changing retained bytes; reject ambiguous/nonfinite JSON."""
    if type(raw) is not bytes or len(raw)>131072:
        raise ValueError('Bounded raw UTF-8 response bytes required.')
    text=raw.decode('utf-8').strip()
    fenced=re.fullmatch(r'```(?:json)?\s*(.*?)\s*```',text,re.S|re.I)
    if fenced:text=fenced.group(1)
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:raise ValueError('Duplicate response key.')
            result[key]=value
        return result
    def nonfinite(value):raise ValueError('Nonfinite response value.')
    try:
        value=json.loads(text,object_pairs_hook=pairs,parse_constant=nonfinite)
    except RecursionError as exc:
        raise ValueError('Response nesting exceeds parser limits.') from exc
    if not isinstance(value,dict):raise ValueError('Whole JSON object required.')
    return value


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)


def predicate(value,variables):
    if not isinstance(value,dict) or set(value) not in ({'terms','op','rhs'},{'terms','op','rhs','mod'}):
        raise ValueError('Use a linear predicate with terms/op/rhs and optional positive mod.')
    if value['op'] not in OPS or type(value['rhs']) is not int or abs(value['rhs'])>10000:
        raise ValueError('Invalid comparison/rhs.')
    if not isinstance(value['terms'],dict) or not value['terms'] or not set(value['terms'])<=set(variables):
        raise ValueError('Unknown/empty variable terms.')
    if not all(type(c) is int and 0<abs(c)<=64 for c in value['terms'].values()):
        raise ValueError('Coefficients must be bounded nonzero integers.')
    if 'mod' in value and (type(value['mod']) is not int or not 2<=value['mod']<=64):
        raise ValueError('Invalid positive modulus.')
    return value


def validate(problem):
    if not isinstance(problem,dict) or set(problem)!={'schema','variables','domain','constraints'} or problem['schema']!='se6-math-constraints-v1':
        raise ValueError('Only public problem fields are accepted.')
    variables=problem['variables']
    if (not isinstance(variables,list) or not 1<=len(variables)<=7 or len(set(variables))!=len(variables)
        or not all(isinstance(v,str) and v.isalpha() and len(v)<=8 for v in variables)):
        raise ValueError('Invalid variable list.')
    bounds=problem['domain']
    if not isinstance(bounds,list) or len(bounds)!=2 or any(type(x) is not int for x in bounds) or bounds[0]>bounds[1]:
        raise ValueError('Invalid bounded integer domain.')
    cells=(bounds[1]-bounds[0]+1)**len(variables)
    if cells>MAX_CELLS:raise ValueError('Exhaustive verifier resource limit exceeded.')
    ids=[]
    if not isinstance(problem['constraints'],list) or not 1<=len(problem['constraints'])<=20:
        raise ValueError('Invalid constraint list.')
    for row in problem['constraints']:
        if not isinstance(row,dict) or 'id' not in row or not isinstance(row['id'],str):
            raise ValueError('Constraint ID required.')
        ids.append(row['id']);predicate({k:v for k,v in row.items() if k!='id'},variables)
    if len(set(ids))!=len(ids):raise ValueError('Duplicate constraint IDs.')
    return problem


def compile_predicate(claim,variables):
    predicate(claim,variables)
    terms=tuple((variables.index(v),coefficient) for v,coefficient in claim['terms'].items())
    rhs,op,mod=claim['rhs'],claim['op'],claim.get('mod')
    def check(values):
        lhs=sum(values[i]*coefficient for i,coefficient in terms)
        if mod is not None:lhs%=mod
        if op=='eq':return lhs==rhs
        if op=='ne':return lhs!=rhs
        if op=='lt':return lhs<rhs
        if op=='le':return lhs<=rhs
        if op=='gt':return lhs>rhs
        return lhs>=rhs
    return check


def domain(problem):
    low,high=problem['domain']
    return product(range(low,high+1),repeat=len(problem['variables']))


@lru_cache(maxsize=8)
def _exhaustive(serialized):
    problem=validate(json.loads(serialized))
    checks=[compile_predicate({k:v for k,v in row.items() if k!='id'},problem['variables']) for row in problem['constraints']]
    solutions=[];visited=0
    for values in domain(problem):
        visited+=1
        if all(check(values) for check in checks):solutions.append(values)
    return tuple(solutions),visited


def exhaustive_verify(problem):
    started=time.perf_counter()
    solutions,visited=_exhaustive(canonical(validate(problem)))
    return {'problem_sha256':hashlib.sha256(canonical(problem).encode()).hexdigest(),
        'assignments_checked':visited,'complete_domain_checked':True,'solution_count':len(solutions),
        'solutions':[dict(zip(problem['variables'],values)) for values in solutions],
        'verifier_seconds':time.perf_counter()-started,'scope':'Finite-domain enumeration; private owner/evaluator data.'}


def assignment_check(problem,assignment):
    validate(problem)
    if not isinstance(assignment,dict) or set(assignment)!=set(problem['variables']):
        return {'correct':False,'errors':['Exact variable assignment required.']}
    if any(type(x) is not int or not problem['domain'][0]<=x<=problem['domain'][1] for x in assignment.values()):
        return {'correct':False,'errors':['Every value must be an integer within the stated domain.']}
    values=tuple(assignment[v] for v in problem['variables'])
    failed=[row['id'] for row in problem['constraints'] if not compile_predicate({k:v for k,v in row.items() if k!='id'},problem['variables'])(values)]
    return {'correct':not failed,'errors':failed}


def entails(problem,premises,claim):
    """Countermodel search; reject vacuous support and unsupported operators."""
    validate(problem);predicate(claim,problem['variables'])
    checks=[compile_predicate(p,problem['variables']) for p in premises]
    conclusion=compile_predicate(claim,problem['variables'])
    givens=[{k:v for k,v in row.items() if k!='id'} for row in problem['constraints']]
    # Reuse the exhaustive, independent full-theory model set only when every
    # given is explicitly among the cited premises. Weaker premises get their
    # own complete-domain/countermodel check, not the secret unique answer.
    if {canonical(p) for p in givens}<={canonical(p) for p in premises}:
        values,_=_exhaustive(canonical(problem))
    else:
        values=domain(problem)
    witnesses=0;checked=0
    for candidate in values:
        checked+=1
        if all(check(candidate) for check in checks):
            witnesses+=1
            if not conclusion(candidate):
                return {'valid':False,'reason':'COUNTEREXAMPLE','counterexample':dict(zip(problem['variables'],candidate)),'checked':checked}
    return {'valid':witnesses>0,'reason':'FINITE_DOMAIN_ENTAILMENT' if witnesses else 'INCONSISTENT_PREMISES','checked':checked}


def proof_check(problem,steps):
    validate(problem)
    if not isinstance(steps,list) or len(steps)>MAX_PROOF_STEPS:
        raise ValueError('Provide at most 16 structured proof steps.')
    registry={row['id']:{k:v for k,v in row.items() if k!='id'} for row in problem['constraints']}
    seen=set(registry);results=[];valid_claims={}
    for step in steps:
        try:
            if (not isinstance(step,dict) or set(step)!={'id','premises','claim'} or not isinstance(step['id'],str)
                or step['id'] in seen or not isinstance(step['premises'],list)
                or len(set(step['premises']))!=len(step['premises']) or not all(isinstance(p,str) and p in registry for p in step['premises'])):
                raise ValueError('Duplicate/forward/unknown premise or malformed step.')
            seen.add(step['id'])
            checked=entails(problem,[registry[p] for p in step['premises']],step['claim'])
            if checked['valid']:
                registry[step['id']]=step['claim'];valid_claims[step['id']]=step
            results.append({'id':step['id'],**checked})
        except (ValueError,TypeError,KeyError) as exc:
            results.append({'id':step.get('id') if isinstance(step,dict) else None,'valid':False,'reason':'UNSUPPORTED_PROOF','detail':str(exc)})
    return results,valid_claims


def evaluate_response(problem,response,previous_problem=None,previous_response=None):
    """No prose points or LLM judge; invalid/unsupported claims stay distinct."""
    validate(problem)
    fields={'assignment','proof_steps','unique','retained_step_ids','invalidated_step_ids'}
    if not isinstance(response,dict) or set(response)!=fields or type(response['unique']) is not bool:
        raise ValueError('Use the documented mathematical response schema.')
    for key in ('retained_step_ids','invalidated_step_ids'):
        if not isinstance(response[key],list) or not all(isinstance(x,str) for x in response[key]) or len(set(response[key]))!=len(response[key]):
            raise ValueError('Correction references must be unique step IDs.')
    assignment=assignment_check(problem,response['assignment'])
    steps,valid=proof_check(problem,response['proof_steps'])
    singleton=set()
    for step in valid.values():
        claim=step['claim']
        if claim['op']=='eq' and 'mod' not in claim and len(claim['terms'])==1:
            variable,coefficient=next(iter(claim['terms'].items()))
            if coefficient==1 and assignment['correct'] and claim['rhs']==response['assignment'][variable]:
                singleton.add(variable)
    uniqueness_certificate=assignment['correct'] and singleton==set(problem['variables']) and response['unique']
    unique_claim_correct=response['unique']==(len(_exhaustive(canonical(problem))[0])==1)
    retention=None;correction=None
    if previous_problem is not None and previous_response is not None:
        _,prior_valid=proof_check(previous_problem,previous_response['proof_steps'])
        current_steps,current_supported=proof_check(problem,list(prior_valid.values()))
        current_valid=set(current_supported)
        still_true=set()
        current_givens=[{k:v for k,v in row.items() if k!='id'} for row in problem['constraints']]
        for identifier,step in prior_valid.items():
            if entails(problem,current_givens,step['claim'])['valid']:still_true.add(identifier)
        invalidated=set(prior_valid)-current_valid
        reported_retained=set(response['retained_step_ids']);reported_invalid=set(response['invalidated_step_ids'])
        retention={'valid_previous_steps':sorted(current_valid),'invalidated_previous_steps':sorted(invalidated),
            'retained_correct':len(reported_retained&current_valid),'forgotten_valid':len(current_valid-reported_retained),
            'incorrectly_retained':sorted(reported_retained-current_valid),'invalidated_correct':len(reported_invalid&invalidated),
            'missed_invalidations':sorted(invalidated-reported_invalid),'incorrect_invalidations':sorted(reported_invalid-invalidated)}
        retention['true_conclusions_requiring_new_proof']=sorted(still_true-current_valid)
        correction=assignment['correct'] and not assignment_check(problem,previous_response['assignment'])['correct']
    return {'exact_mathematical_correctness':assignment['correct'],'assignment_errors':assignment['errors'],
        'proof_steps':steps,'valid_proof_steps':sum(s['valid'] for s in steps),
        'incorrect_deductions':sum(s['reason']=='COUNTEREXAMPLE' for s in steps),
        'unsupported_claims':sum(s['reason'] in ('UNSUPPORTED_PROOF','INCONSISTENT_PREMISES') for s in steps),
        'uniqueness_claim_correct':unique_claim_correct,
        'uniqueness_certificate_valid':uniqueness_certificate,'successful_correction':correction,'retention':retention,
        'scoring_scope':'Finite integer domain, cited premises and supported linear/modular predicates only; prose not scored.',
        'metrics':{k:None for k in ('actual_input_tokens','actual_output_tokens','total_tokens','model_latency_seconds','inference_calls')}}
