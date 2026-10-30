import argparse,ast,hashlib,json,re
from fractions import Fraction
from pathlib import Path
def num(value):
    token=str(value)
    if len(token)>128 or re.fullmatch(r'[+-]?[0-9]{1,32}(?:/[1-9][0-9]{0,31}|\.[0-9]{1,32})?',token) is None:raise ValueError('Bounded rational required')
    return Fraction(token)
def sha(data):return hashlib.sha256(data).hexdigest()
def delivered_math(answer,values,target):
    """Independent restricted linear expression parser; never eval or exec."""
    text=answer.split(': ',1)[-1].strip()
    if len(text)>512 or text.count('=')!=1:return False
    def expression(raw):
        def walk(n):
            if isinstance(n,ast.Name) and n.id in values:return {n.id:num(1)},num(0)
            if isinstance(n,ast.Constant) and type(n.value) is int:return {},num(n.value)
            if isinstance(n,ast.UnaryOp) and isinstance(n.op,(ast.UAdd,ast.USub)):
                d,c=walk(n.operand);s=-1 if isinstance(n.op,ast.USub) else 1;return {k:s*v for k,v in d.items()},s*c
            if isinstance(n,ast.BinOp) and isinstance(n.op,(ast.Add,ast.Sub)):
                a,c=walk(n.left);b,d=walk(n.right);s=-1 if isinstance(n.op,ast.Sub) else 1
                return {k:a.get(k,0)+s*b.get(k,0) for k in set(a)|set(b)},c+s*d
            if isinstance(n,ast.BinOp) and isinstance(n.op,ast.Mult):
                a,c=walk(n.left);b,d=walk(n.right)
                if a and b:raise ValueError('Nonlinear expression')
                return ({k:v*d for k,v in a.items()},c*d) if a else ({k:c*v for k,v in b.items()},c*d)
            raise ValueError('Unsupported expression')
        return walk(ast.parse(raw.strip(),mode='eval').body)
    try:
        lhs,rhs=text.split('=');a,c=expression(lhs);b,d=expression(rhs)
        co={k:a.get(k,0)-b.get(k,0) for k in set(a)|set(b)}
        return {k for k,v in co.items() if v}==target and sum(v*num(values[k]) for k,v in co.items())==d-c
    except (ValueError,SyntaxError,RecursionError):return False
def unique_solution(constraints,names):
    for c in constraints:
        variables=[n for n,v in c['coefficients']]
        if len(set(variables))!=len(variables) or set(variables)-set(names):raise ValueError('Duplicate or out-of-scope coefficient variable')
    matrix=[[num(dict(c['coefficients']).get(n,0)) for n in names]+[num(c['rhs'])] for c in constraints]
    row=0;pivots=[]
    for col in range(len(names)):
        pivot=next((i for i in range(row,len(matrix)) if matrix[i][col]),None)
        if pivot is None:continue
        matrix[row],matrix[pivot]=matrix[pivot],matrix[row]
        factor=matrix[row][col];matrix[row]=[x/factor for x in matrix[row]]
        for i in range(len(matrix)):
            if i!=row:
                factor=matrix[i][col];matrix[i]=[x-factor*y for x,y in zip(matrix[i],matrix[row])]
        pivots.append(col);row+=1
    if any(not any(r[:-1]) and r[-1] for r in matrix) or len(pivots)!=len(names):return None
    return {names[col]:matrix[i][-1] for i,col in enumerate(pivots)}
def score(spec,keys,rows):
    expected={s['id']:(s['domain'],s['events']) for s in spec['scenarios']}
    if not rows:raise ValueError('No captured events')
    lane_counts={}
    for row in rows:
        domain,events=expected[row['scenario']];event=events[row['event']]
        if row['domain']!=domain or any(row[k]!=event[k] for k in ('phase','question','source')):raise ValueError('Scoring event differs from public spec')
        ident=(row['scenario'],row['condition']);index=lane_counts.get(ident,0)
        if row['event']!=index:raise ValueError('Event order/gap/repetition')
        lane_counts[ident]=index+1
    for lane in {r['condition'] for r in rows}:
        if any(lane_counts.get((sid,lane))!=len(events) for sid,(_,events) in expected.items()):raise ValueError('Incomplete scoring lane')
    previous={};results=[]
    for row in rows:
        sid=row['scenario'];key=keys[sid];phase=row['phase'];lane=row['condition'];k=row['knowledge'];p=row['public'];checks={}
        old=previous.get((sid,lane));values={}
        if key['kind']=='math':
            a,b,c=key['variables'];corrected=phase in ('correction','restart','transfer');values={a:key['n']-key['k']-int(corrected),b:key['k']+int(corrected),c:key['v']}
            def entails(item):return sum(num(v)*values[n] for n,v in item['coefficients'])==num(item['rhs'])
            if phase=='before':checks['honest_unknown']=not k['active'] and 'UNRESOLVED' in p['answer']
            elif phase=='contradiction':
                checks['contradiction_not_silently_assimilated']=k['constraints']==(old or {}).get('knowledge',{}).get('constraints',[])
                checks['no_native_action_on_unsupported_remap']=row['measurements']['native_operations']==0
            else:
                solution=unique_solution(k['constraints'],[a,b,c])
                checks['independent_full_rank_truth']=solution==values
                actual={x['label']:(sorted((n,num(v)) for n,v in x['coefficients']),num(x['rhs'])) for x in k['constraints']}
                expected={'E1':(sorted([(a,num(1)),(b,num(1))]),num(key['n'])),
                  'E2':([(b,num(1))],num(values[b])),'E3':([(c,num(1))],num(key['v']))}
                checks['premises_match_current_public_evidence']=len(k['constraints'])==3 and actual==expected
                target={a} if phase in ('assimilate','correction') else {c} if phase in ('independent','restart') else {a,c}
                matching=[d for d in k['active'] if {n for n,v in d['coefficients'] if v}==target]
                checks['requested_entailment']=bool(matching) and all(entails(d) for d in matching)
                checks['delivered_math_answer_valid']=delivered_math(p['answer'],values,target)
                checks['current_deductions_valid']=bool(k['active']) and all(entails(d) for d in k['active'])
            if phase=='correction':
                checks['old_dependent_deduction_invalidated']=any(d['reference'] in k['invalidated'] for d in (old or {}).get('knowledge',{}).get('active',[]) if {n for n,v in d['coefficients']}=={a})
                prior_ind=[d for d in (old or {}).get('knowledge',{}).get('active',[]) if {n for n,v in d['coefficients']}=={c}]
                checks['independent_deduction_preserved']=bool(prior_ind) and all(d in k['active'] for d in prior_ind)
        elif key['kind']=='relation':
            table={(r['subject'],r['predicate']):r['value'] for r in k['relations']};subject=key['subject'];other=key['other']
            if phase=='before':checks['honest_unknown']=not table and 'UNKNOWN' in p['answer']
            else:
                checks['current_relation']=table.get((subject,'status'))==('failed' if phase in ('correction','restart','transfer') else 'ready')
                checks['independent_relation']=table.get((other,'priority'))=='high'
                if phase=='contradiction':checks['contradiction_refused']=all(x['boundary_outcome']!='ALLOW' for x in p.get('receipts',[])) and bool(p.get('receipts'))
        elif key['kind']=='business':
            if phase=='before':checks['honest_unknown']=p.get('business_views') is None
            else:
                corrected=phase in ('correction','restart','transfer');deep=key['deep']+int(corrected);basic=key['jobs']-deep
                price=key['prices'][1]+(7 if phase in ('restart','transfer') else 0)
                revenue=basic*key['prices'][0]+deep*price;materials=basic*key['costs'][0]+deep*key['costs'][1]
                budget=key['budget']+(key['costs'][1]-key['costs'][0]+3 if phase=='transfer' else 0)
                views=p.get('business_views') or {};view=views.get('corrected' if corrected else 'original') or {}
                expected={'revenue':revenue,'materials_cost':materials,'gross_contribution':revenue-materials,'budget_variance':materials-budget}
                checks.update({n:view.get(n) is not None and num(view[n])==v for n,v in expected.items()})
                checks['budget_exceeded']=view.get('budget_exceeded') is (materials>budget)
                checks['allocation']=view.get('allocations')=={'basic':str(basic),'deep':str(deep)}
                if phase in ('restart','transfer'):checks['quantity_proofs_reused']=row['measurements']['native_operations']==0 and bool(k['active'])
        else:
            if phase in ('before','transfer'):checks['boundary_honest']=row['measurements']['native_operations']==0 and 'UNRESOLVED' in p['answer']
            elif phase=='untrusted':
                checks['model_claim_not_promoted']=row['measurements']['native_operations']==0 and 'MODEL_PROPOSED' in p['answer']
                checks['trusted_knowledge_unchanged']=k['relations']==(old or {}).get('knowledge',{}).get('relations',[])
            else:
                checks['verified_artifact_relation']=any(r['subject']==key['subject'] and r['value']=='checksum checked' for r in k['relations'])
                if phase=='assimilate':checks['actual_artifact_checked']=bool(row['host_artifact'] and row['host_artifact']['verified'] and row['host_artifact']['sha256']==spec['technical_artifact_sha256'])
        results.append({'scenario':sid,'domain':row['domain'],'condition':lane,'event':row['event'],'phase':phase,
            'score':sum(checks.values()),'maximum':len(checks),'checks':checks})
        previous[(sid,lane)]=row
    return {'rows':results}

def main():
    root=Path(__file__).resolve().parent
    public=json.loads((root/'public-evidence.json').read_bytes())
    spec=json.loads((root/'public-spec.json').read_bytes())
    key_bytes=(root/'truth-parameters.json').read_bytes()
    if sha(key_bytes)!=spec['answer_key_sha256']:raise ValueError('Truth commitment differs')
    if sha((root/'technical-artifact.json').read_bytes())!=spec['technical_artifact_sha256']:raise ValueError('Fixture differs')
    allrows=[]
    for group,lane in [('scenarios','SE6'),('control_scenarios','DROP_RETAINED_STATE')]:
        for scenario in public[group]:
            for i,e in enumerate(scenario['events']):
                allrows.append({'scenario':scenario['id'],'domain':scenario['domain'],'condition':lane,'event':i,
                  'phase':e['phase'],'question':e['question'],'source':e['source'],'knowledge':e['knowledge'],
                  'public':{'answer':e['answer'],'business_views':e['business_views'],'receipts':e['receipts']},
                  'host_artifact':e['host_artifact'],'measurements':{'native_operations':e['metrics']['native_transition_attempts']}})
    result=score(spec,json.loads(key_bytes),allrows)
    totals={}
    for lane in ('SE6','DROP_RETAINED_STATE'):
        selected=[r for r in result['rows'] if r['condition']==lane]
        totals[lane]={'functional_score':sum(r['score'] for r in selected),'functional_maximum':sum(r['maximum'] for r in selected)}
    print(json.dumps({'functional_totals':totals,'provider_calls':0,
      'scope':'Exact pinned functional scoring definitions on sanitized captured values. Private process/authority/store checks excluded. Checksums are local hashes, not external signatures.'}))
if __name__=='__main__':main()
