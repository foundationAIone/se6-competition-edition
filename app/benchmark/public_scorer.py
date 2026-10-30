"""Original standalone public arithmetic checker; Python standard library only.

No inherited SE6 imports, private key, inference, credentials or network access.
"""
from fractions import Fraction
from pathlib import Path
import hashlib,json,re,sys
def need(v,message):
    if not v:raise ValueError(message)
def number(v):
    need(type(v) is int or isinstance(v,str),'Exact numeric value required')
    need(len(str(v))<=64,'Number too long')
    if isinstance(v,str):need(re.fullmatch(r'[+-]?(?:[0-9]+(?:/[0-9]+|\.[0-9]*)?|\.[0-9]+)',v),'Unsafe numeric syntax')
    return Fraction(v)
def strict(pairs):
    out={}
    for key,value in pairs:
        need(key not in out,'Duplicate output key');out[key]=value
    return out
def decode(raw):return json.loads(raw,object_pairs_hook=strict,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Nonfinite output')))
def row(value):
    need(isinstance(value,dict) and set(value)=={'coefficients','rhs'},'Equation shape')
    c=value['coefficients'];need(isinstance(c,dict) and bool(c) and set(c)<=set('pqrs'),'Coefficient object required')
    return {k:number(v) for k,v in c.items() if number(v)},number(value['rhs'])
def equal_relation(left,right):
    if not left[0] or not right[0]:return False
    pivot=next(iter(right[0]));factor=left[0].get(pivot,0)/right[0][pivot]
    return bool(factor) and left[1]==factor*right[1] and all(left[0].get(k,0)==factor*right[0].get(k,0) for k in set(left[0])|set(right[0]))
def certificate_steps(answer,premises):
    available=dict(premises);valid=[];invalid=[]
    need(isinstance(answer['steps'],list) and 1<=len(answer['steps'])<=8,'Step limit')
    for item in answer['steps']:
        try:
            need(isinstance(item,dict) and set(item)=={'id','weights','conclusion'},'Step shape')
            label=item['id'];need(isinstance(label,str) and bool(label) and label not in available,'Step label')
            need(isinstance(item['weights'],dict) and bool(item['weights']),'Weights shape')
            c={};rhs=Fraction(0)
            for source,weight in item['weights'].items():
                premise=available[source];w=number(weight);rhs+=w*premise[1]
                for name,value in premise[0].items():c[name]=c.get(name,Fraction(0))+w*value
            c={k:v for k,v in c.items() if v};need(bool(c) and row(item['conclusion'])==(c,rhs),'Weighted row mismatch')
            available[label]=(c,rhs);valid.append(label)
        except (ValueError,KeyError,TypeError,ZeroDivisionError):invalid.append(item.get('id') if isinstance(item,dict) else None)
    return valid,invalid,available
def premises(campaign,index):
    if campaign=='first-linear':return {'E1':({'p':Fraction(2),'q':Fraction(1),'r':Fraction(1)},Fraction(29)),'E2':({'p':Fraction(1),'r':Fraction(1),'s':Fraction(1)},Fraction(17))}
    return {'E1':({'p':Fraction(1),'q':Fraction(1),'r':Fraction(1)},Fraction(24)),'E2':({'r':Fraction(1),'s':Fraction(1)},Fraction(12 if index==0 else 15))}
def linear(value,campaign,index,prior=None):
    if campaign=='successor':
        need(isinstance(value,dict) and set(value)=={'answer','retained_step_ids','invalidated_step_ids'},'Wrapper shape');a=value['answer']
    else:a=value
    need(isinstance(a,dict) and set(a)=={'relation','steps','execution_receipts','unique_solution','world_facts_verified'},'Answer shape')
    relation=row(a['relation']);valid,invalid,available=certificate_steps(a,premises(campaign,index))
    need(isinstance(a['execution_receipts'],list) and type(a['unique_solution']) is bool and type(a['world_facts_verified']) is bool,'Claim shape')
    expected=({'p':Fraction(1),'q':Fraction(1),'s':Fraction(-1)},Fraction(9 if campaign=='successor' and index else 12))
    correct=equal_relation(relation,expected);proof=not invalid and any(equal_relation(available[k],relation) for k in valid)
    discipline=correct and not invalid and not a['unique_solution'] and not a['world_facts_verified'] and a['execution_receipts']==[]
    result={'status':'ASSESSABLE','score':int(correct)+int(proof)+int(discipline),'maximum_score':3,'correct_relation':correct,'valid_certificate':proof,'epistemic_discipline':discipline}
    if campaign=='successor':
        for name in ('retained_step_ids','invalidated_step_ids'):
            need(isinstance(value[name],list) and all(isinstance(x,str) for x in value[name]) and len(set(value[name]))==len(value[name]),'Retention list shape')
        if index:
            need(prior is not None,'Missing previous own answer');old=prior['answer'];ids=[s.get('id') for s in old['steps']];need(all(isinstance(x,str) and x for x in ids) and len(ids)==len(set(ids)),'Unique prior IDs required')
            before,_,_=certificate_steps(old,premises(campaign,0));after,_,_=certificate_steps(old,premises(campaign,1));keep=set(before)&set(after);drop=set(ids)-keep
            result['correction_retention_correct']=set(value['retained_step_ids'])==keep and set(value['invalidated_step_ids'])==drop
        else:need(value['retained_step_ids']==value['invalidated_step_ids']==[],'Initial lists empty');result['correction_retention_correct']=None
    return result
def business(value):
    need(set(value)=={'original','corrected','investigate_spending','world_facts_verified','recommendation'},'Business shape')
    need(isinstance(value['recommendation'],str) and 1<=len(value['recommendation'])<=2000,'Recommendation shape')
    checks={}
    for phase,hours in [('original',24),('corrected',27)]:
        d=(Fraction(hours)-10*Fraction('1.5'))/(3-Fraction('1.5'));r=10-d;revenue=r*Fraction('67.25')+d*Fraction('132.10');materials=r*Fraction('12.50')+d*Fraction('30.75')
        expected={'routine':r,'deep':d,'revenue':revenue,'materials':materials,'gross_contribution':revenue-materials,'budget_variance':materials-260,'budget_exceeded':materials>260}
        need(isinstance(value[phase],dict) and set(value[phase])==set(expected),'View shape')
        for key,target in expected.items():
            actual=value[phase][key];checks[phase+'.'+key]=(type(actual) is bool and actual==target) if type(target) is bool else number(actual)==target
    need(type(value['investigate_spending']) is bool and type(value['world_facts_verified']) is bool,'Boolean flags')
    checks['investigate_spending']=value['investigate_spending'] is True;checks['world_facts_verified']=value['world_facts_verified'] is False
    return {'status':'ASSESSABLE','score':sum(checks.values()),'maximum_score':16,'checks':checks,'recommendation':'UNSCORED'}
def replay(data):
    result={};previous={}
    for pair in data['pairs']:
        lanes={}
        for lane,capture in pair['lanes'].items():
            try:
                value=decode(capture['response_content'])
                scored=business(value) if pair['case']=='mixed-business' else linear(value,pair['campaign'],pair['round'],previous.get(lane))
                if pair['campaign']=='successor' and pair['case']=='linear-correction':previous[lane]=value
                lanes[lane]=scored
            except (ValueError,KeyError,TypeError,ZeroDivisionError):lanes[lane]={'status':'UNASSESSABLE','score':None}
        winner=None
        if all(x['status']=='ASSESSABLE' for x in lanes.values()):winner='TIE' if lanes['se6']['score']==lanes['baseline']['score'] else max(lanes,key=lambda k:lanes[k]['score'])
        result[pair['id']]={'lanes':lanes,'arithmetic_winner':winner}
    resources={}
    for campaign,limits in data['declared_campaign_limits'].items():
        captures=[capture for pair in data['pairs'] if pair['campaign']==campaign for capture in pair['lanes'].values()]
        need(len(captures)==limits['capture_count'],'Selected capture count mismatch')
        inputs=outputs=tokens=0;cost=Fraction(0)
        for capture in captures:
            usage=capture['usage'];need(all(type(usage[k]) is int and usage[k]>=0 for k in ('prompt_tokens','completion_tokens','total_tokens')),'Usage counts')
            need(usage['total_tokens']==usage['prompt_tokens']+usage['completion_tokens'],'Token total mismatch')
            need(usage['completion_tokens']<=limits['output_tokens_per_call'],'Output cap exceeded')
            amount=capture['metrics']['serialized_original_input_bytes'];need(type(amount) is int and amount>=0,'Original byte count')
            inputs+=amount;outputs+=usage['completion_tokens'];tokens+=usage['total_tokens']
            estimate=(usage['prompt_tokens']*Fraction(3,10)+usage['completion_tokens']*Fraction(9,10))/1000000;cost+=estimate
            need(abs(float(estimate)-capture['metrics']['tariff_estimate_usd'])<=1e-12,'Tariff mismatch')
        need(inputs<=limits['combined_input_bytes'] and outputs<=limits['total_output_tokens'] and cost<=number(str(limits['usd'])),'Campaign cap exceeded')
        resources[campaign]={'selected_capture_count':len(captures),'original_input_bytes_reported':inputs,'completion_tokens_reported':outputs,'total_tokens_reported':tokens,'tariff_estimate_usd':float(cost),'actual_billed_usd':None,'within_declared_caps':True,'source':'Sanitized selected metrics; original reservation/authorization records remain private'}
    return {'schema':'se6-public-replay-v1','pairs':result,'resources':resources,'overall_winner':None,'replay_inference_calls':0,'scope':'Arithmetic from sanitized public captures; no native/vendor/private provenance verification'}
def verify_bundle(root):
    manifest=json.loads((root/'derived-manifest.json').read_bytes())
    need(set(manifest['files'])=={'BENCHMARK_EVIDENCE.json','PUBLIC_SCORECARD.json','public_scorer.py','test_public_evidence.py','README.md','SANITIZATION_MANIFEST.json'},'Complete public derived manifest required')
    for name,digest in manifest['files'].items():
        path=root/name;need(not Path(name).is_absolute() and path.resolve().is_relative_to(root.resolve()),'Unsafe path');need(hashlib.sha256(path.read_bytes()).hexdigest()==digest,'Derived file changed')
    return replay(json.loads((root/'BENCHMARK_EVIDENCE.json').read_bytes()))
if __name__=='__main__':print(json.dumps(verify_bundle(Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).parent),indent=2))
