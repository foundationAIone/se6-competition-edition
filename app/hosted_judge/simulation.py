"""Explicit offline integration fixture. No NVIDIA/Nebius inference or performance evidence."""
import json
from fractions import Fraction
from pathlib import Path

def linear_fixture(truth):
    equations,target=truth;labels=list(equations);names=sorted(set().union(*(set(c) for c,r in equations.values())))
    rows=[[co.get(k,Fraction(0)) for k in names]+[rhs]+[Fraction(int(i==j)) for j in range(len(labels))] for i,(co,rhs) in enumerate(equations.values())]
    pivot=0
    for col,name in enumerate(names):
        if name in target:continue
        at=next((i for i in range(pivot,len(rows)) if rows[i][col]),None)
        if at is None:continue
        rows[pivot],rows[at]=rows[at],rows[pivot];scale=rows[pivot][col];rows[pivot]=[v/scale for v in rows[pivot]]
        for i in range(len(rows)):
            if i!=pivot:
                scale=rows[i][col];rows[i]=[x-scale*y for x,y in zip(rows[i],rows[pivot])]
        pivot+=1
    remaining=rows[pivot:]
    for offset in range(1,9):
        combined=[sum(Fraction(offset**i)*row[c] for i,row in enumerate(remaining)) for c in range(len(names)+1+len(labels))]
        coefficients={n:str(combined[i]) for i,n in enumerate(names) if combined[i]}
        if set(coefficients)==target:
            return {'relation':{'coefficients':coefficients,'rhs':str(combined[len(names)])},
                'certificate':{label:str(combined[len(names)+1+i]) for i,label in enumerate(labels) if combined[len(names)+1+i]},
                'world_facts_verified':False,'execution_receipts':[]}
    return {'unsupported':'SIMULATED fixture has no supported exact target relation'}

def fixture(messages):
    from .v8_scoring import public_linear,public_business,derived_question,rational
    users=[m['content'] for m in messages if m['role']=='user']
    history=[q.removeprefix('Prior same-task public input:\n') for q in users[:-1]]
    question=derived_question(users[-1],history)
    truth=public_linear(question)
    if truth:return linear_fixture(truth)
    facts=public_business(question)
    if facts:
        a,b=facts['classes'];ha=rational(facts['hours_per_job'][a]);hb=rational(facts['hours_per_job'][b]);views={}
        for tag,hours in facts['hours'].items():
            qb=(rational(hours)-ha*facts['total_jobs'])/(hb-ha);qa=facts['total_jobs']-qb
            revenue=sum(q*rational(facts['facts'][n+':revenue']['value']) for n,q in ((a,qa),(b,qb)))
            cost=sum(q*rational(facts['facts'][n+':expense']['value']) for n,q in ((a,qa),(b,qb)))
            delta=cost-rational(facts['facts']['budget']['value'])
            views[tag]={'allocations':{a:str(qa),b:str(qb)},'revenue':str(revenue),'materials_cost':str(cost),
                'gross_contribution':str(revenue-cost),'budget_variance':str(delta),'budget_exceeded':delta>0}
        return {'business':views,'world_facts_verified':False,'execution_receipts':[]}
    return {'unsupported':'SIMULATED_TEST; no model or automatic prose assessment'}

class SimulatedNebiusTransport:
    SIMULATED=True
    def __init__(self,settings):self.settings=settings
    def request(self,body,directory,timeout):
        from src.workbench.provider_router import payload_bytes,parse_nebius_completion,NEBIUS_MODEL
        directory=Path(directory)
        with (directory/'request.json').open('xb') as f:f.write(payload_bytes(self.settings,body))
        try:answer=current_fixture(body['input']) if getattr(self,'answer_protocol',None)=='SE6_COMMON_PUBLIC_ANSWER_V1' else fixture(body['input'])
        except (ValueError,TypeError,KeyError,ZeroDivisionError):answer={'unsupported':'SIMULATED_TEST; public facts unresolved'}
        # Fake usage exercises strict parser/cap handling. It is not billed or measured model usage.
        raw=json.dumps({'id':'SIMULATED_TEST','model':NEBIUS_MODEL,'choices':[{'finish_reason':'stop','message':{'role':'assistant','content':json.dumps(answer)}}],
            'usage':{'prompt_tokens':200,'completion_tokens':100,'total_tokens':300,**({'completion_tokens_details':{'reasoning_tokens':0}} if getattr(self,'answer_protocol',None)=='SE6_COMMON_PUBLIC_ANSWER_V1' else {})}}).encode()
        with (directory/'provider.json').open('xb') as f:f.write(raw)
        parsed=parse_nebius_completion(raw,NEBIUS_MODEL,provider_reasoning_control=self.settings.provider_reasoning_control)
        with (directory/'returned-text.txt').open('xb') as f:f.write(parsed['text'].encode())
        return parsed


def current_fixture(messages):
    """Explicit COMMON simulated answers only. No model evidence or hidden oracle."""
    from .common_pair_contract import derive_public_spec
    from .common_answer_scoring import business_truth,graph_truth,answer_boundary_status
    users=[m['content'] for m in messages if m['role']=='user']
    history=[q.removeprefix('Prior same-task public input:\n') for q in users[:-1]]
    spec=derive_public_spec(users[-1],history)
    boundary=answer_boundary_status(spec)
    if boundary:return {'status':boundary}
    if spec['kind']=='business':
        values=business_truth(spec)
        return {k:({n:str(q) for n,q in v.items()} if isinstance(v,dict) else v if type(v) is bool else str(v)) for k,v in values.items()}
    if spec['kind']=='graph':return {'reachable':graph_truth(spec)}
    equations={f'E{i+1}':({n:Fraction(q) for n,q in row['coefficients'].items()},Fraction(row['rhs'])) for i,row in enumerate(spec['premises'])}
    value=linear_fixture((equations,set(spec['requested_variables'])))
    if 'relation' not in value:return {'status':'UNSUPPORTED'}
    return {'relation':value['relation']}
