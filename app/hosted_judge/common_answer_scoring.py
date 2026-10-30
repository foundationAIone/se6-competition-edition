"""Prospective common-answer evaluator. Stdlib only; no native/provider imports.
Evaluator-only task specs; never pass oracle specs to generators.
Evidence is separate from user correctness and must be independently admitted.
"""
import json,re,hashlib
from fractions import Fraction
SCHEMA='se6-prospective-common-answer-evaluation-v1'
class InvalidSchema(ValueError):pass
def require(ok,msg):
 if not ok:raise InvalidSchema(msg)
def rational(value):
 require(type(value) in (str,int,float),'numeric type')
 s=str(value);require(len(s)<=64 and re.fullmatch(r'[+-]?\d{1,24}(?:/\d{1,24}|\.\d{1,24})?',s) is not None,'bounded rational lexical')
 return Fraction(s)
def unique(items):
 out={}
 for k,v in items:require(k not in out,'duplicate field');out[k]=v
 return out
def parse(text):
 require(isinstance(text,str) and len(text.encode())<=32768,'answer bound')
 obj=json.loads(text,object_pairs_hook=unique,parse_int=str,parse_float=str,parse_constant=lambda _:(_ for _ in ()).throw(InvalidSchema('nonfinite')))
 require(type(obj) is dict,'single object');return obj
def rank(rows):
 require(len(rows)<=17 and all(len(r)<=17 for r in rows),'matrix bound')
 if not rows:return 0
 a=[list(r) for r in rows];width=len(a[0]);require(all(len(r)==width for r in a),'matrix shape');i=0
 for col in range(width):
  hit=next((j for j in range(i,len(a)) if a[j][col]),None)
  if hit is None:continue
  a[i],a[hit]=a[hit],a[i];d=a[i][col];a[i]=[v/d for v in a[i]]
  for j in range(len(a)):
   if j!=i:
    d=a[j][col];a[j]=[v-d*w for v,w in zip(a[j],a[i])]
  i+=1
  if i==len(a):break
 return i
def current_premises(phases):
 """Explicit public structured equality updates; duplicate/unknown edits rejected.
 These are evaluator reconstructed facts, not a generator input interface.
 """
 facts={}
 for phase in phases:
  require(set(phase)<= {'add','replace'},'public update schema')
  for item in phase.get('add',[]):
   require(item['id'] not in facts,'duplicate premise');facts[item['id']]=dict(item)
  for item in phase.get('replace',[]):
   require(item['id'] in facts,'unknown correction');facts[item['id']]=dict(item)
 return list(facts.values())
def affine_truth(spec,relation):
 require(set(relation)=={'coefficients','rhs'} and type(relation['coefficients']) is dict,'relation schema')
 target=spec['requested_variables'];require(len(target)==len(set(target)) and 0<len(target)<=16,'target bounds')
 require(set(relation['coefficients'])==set(target),'exact requested variables')
 coeff={k:rational(v) for k,v in relation['coefficients'].items()};require(all(coeff.values()),'nonzero requested coefficients');rhs=rational(relation['rhs'])
 premises=spec['premises'];require(0<len(premises)<=16,'premise bound');names=sorted(set().union(*(p['coefficients'] for p in premises))|set(target));require(len(names)<=16,'variable bound')
 rows=[[rational(p['coefficients'].get(n,0)) for n in names]+[rational(p['rhs'])] for p in premises]
 require(rank([r[:-1] for r in rows])==rank(rows),'contradictory public premises cannot prove answer')
 answer=[coeff.get(n,Fraction(0)) for n in names]+[rhs]
 if spec.get('public_integer_domain') is not None:return bounded_affine_truth(rows,answer,spec['public_integer_domain'])
 return rank(rows)==rank(rows+[answer])
def bounded_affine_truth(rows,answer,domain):
 require(type(domain) is list and len(domain)==2 and all(type(v) is int for v in domain) and -10000<=domain[0]<=domain[1]<=10000 and domain[1]-domain[0]<128,'integer domain bound')
 n=len(answer)-1;a=[list(r) for r in rows];pivot=0;pivots=[]
 for col in range(n):
  hit=next((j for j in range(pivot,len(a)) if a[j][col]),None)
  if hit is None:continue
  a[pivot],a[hit]=a[hit],a[pivot];d=a[pivot][col];a[pivot]=[v/d for v in a[pivot]]
  for j in range(len(a)):
   if j!=pivot:
    d=a[j][col];a[j]=[v-d*w for v,w in zip(a[j],a[pivot])]
  pivots.append(col);pivot+=1
  if pivot==len(a):break
 if pivot==n:
  values=[Fraction(0) for _ in range(n)]
  for i,col in enumerate(pivots):values[col]=a[i][-1]
  require(all(v.denominator==1 and domain[0]<=v<=domain[1] for v in values),'no public integer witness')
  return sum(c*v for c,v in zip(answer[:-1],values))==answer[-1]
 width=domain[1]-domain[0]+1;require(width**n<=100000,'independent finite oracle enumeration cap')
 from itertools import product
 witnesses=0
 for values in product(range(domain[0],domain[1]+1),repeat=n):
  if all(sum(c*v for c,v in zip(row[:-1],values))==row[-1] for row in rows):
   witnesses+=1
   if sum(c*v for c,v in zip(answer[:-1],values))!=answer[-1]:return False
 require(witnesses>0,'no public integer witness');return True
def business_truth(spec):
 jobs=rational(spec['jobs']);hours=rational(spec['hours']);budget=rational(spec['budget']);classes=spec['classes'];require(type(classes) is dict and len(classes)==2 and all(isinstance(n,str) and re.fullmatch(r'[a-z][a-z0-9_]{0,31}',n) for n in classes),'business classes');first,second=tuple(classes)
 require(jobs.denominator==1 and 0<=jobs<=10000,'job bound');h1=rational(classes[first]['hours']);h2=rational(classes[second]['hours']);require(h1!=h2,'unique resource allocation')
 d=(hours-jobs*h1)/(h2-h1);r=jobs-d;require(r.denominator==d.denominator==1 and r>=0 and d>=0,'feasible integral allocation')
 revenue=sum(count*rational(classes[k]['revenue']) for k,count in [(first,r),(second,d)])
 materials=sum(count*rational(classes[k]['materials']) for k,count in [(first,r),(second,d)])
 return {'allocations':{first:r,second:d},'revenue':revenue,'materials_cost':materials,'gross_contribution':revenue-materials,'budget_variance':materials-budget,'budget_exceeded':materials>budget}
def graph_truth(spec):
 edges=spec['edges'];require(len(edges)<=64 and all(type(e) is list and len(e)==2 and all(isinstance(v,str) and len(v)<=64 for v in e) for e in edges),'graph bounds')
 seen={spec['start']};queue=[spec['start']]
 while queue:
  node=queue.pop()
  for a,b in edges:
   if a==node and b not in seen:seen.add(b);queue.append(b)
 return spec['goal'] in seen
def affine_boundary_status(spec):
 premises=spec['premises'];targets=spec['requested_variables'];require(0<len(premises)<=16 and 0<len(targets)<=16 and len(targets)==len(set(targets)),'affine boundary bound')
 names=sorted(set().union(*(p['coefficients'] for p in premises))|set(targets));require(len(names)<=16,'affine boundary variables')
 rows=[[rational(p['coefficients'].get(n,0)) for n in names]+[rational(p['rhs'])] for p in premises]
 if rank([r[:-1] for r in rows])!=rank(rows):return 'INFEASIBLE'
 n=len(names);a=[list(r) for r in rows];pivot=0;cols=[]
 for col in range(n):
  hit=next((j for j in range(pivot,len(a)) if a[j][col]),None)
  if hit is None:continue
  a[pivot],a[hit]=a[hit],a[pivot];d=a[pivot][col];a[pivot]=[v/d for v in a[pivot]]
  for j in range(len(a)):
   if j!=pivot:
    d=a[j][col];a[j]=[v-d*w for v,w in zip(a[j],a[pivot])]
  cols.append(col);pivot+=1
  if pivot==len(a):break
 if spec.get('public_integer_domain') is None:
  directions=[];indices=[names.index(v) for v in targets]
  for free in [i for i in range(n) if i not in cols]:
   delta=[Fraction(0) for _ in names];delta[free]=Fraction(1)
   for row,col in enumerate(cols):delta[col]=-a[row][free]
   directions.append([delta[i] for i in indices])
  for i in range(len(targets)):
   unit=[Fraction(int(j==i)) for j in range(len(targets))]
   if rank(directions+[unit])==rank(directions):return 'UNDERDETERMINED'
  return None
 domain=spec['public_integer_domain'];require(type(domain) is list and len(domain)==2 and all(type(v) is int for v in domain) and -10000<=domain[0]<=domain[1]<=10000 and domain[1]-domain[0]<128,'integer domain bound')
 if pivot==n:
  values=[Fraction(0) for _ in names]
  for i,col in enumerate(cols):values[col]=a[i][-1]
  return None if all(v.denominator==1 and domain[0]<=v<=domain[1] for v in values) else 'INFEASIBLE'
 width=domain[1]-domain[0]+1;require(width**n<=100000,'independent finite oracle enumeration cap')
 from itertools import product
 base=None;directions=[];indices=[names.index(v) for v in targets]
 for values in product(range(domain[0],domain[1]+1),repeat=n):
  if all(sum(c*v for c,v in zip(row[:-1],values))==row[-1] for row in rows):
   point=[Fraction(values[i]) for i in indices]
   if base is None:base=point
   else:
    delta=[v-w for v,w in zip(point,base)]
    if rank(directions+[delta])>rank(directions):directions.append(delta)
 if base is None:return 'INFEASIBLE'
 for i in range(len(targets)):
  unit=[Fraction(int(j==i)) for j in range(len(targets))]
  if rank(directions+[unit])==rank(directions):return 'UNDERDETERMINED'
 return None

def answer_boundary_status(spec):
 if spec['kind']=='boundary':return spec['expected_status']
 if spec['kind']=='affine':return affine_boundary_status(spec)
 if spec['kind']=='business':
  classes=spec['classes'];require(len(classes)==2,'business classes');first,second=tuple(classes);j=rational(spec['jobs']);h=rational(spec['hours']);require(j.denominator==1 and 0<=j<=10000,'job bound')
  solutions=sum(r*rational(classes[first]['hours'])+(int(j)-r)*rational(classes[second]['hours'])==h for r in range(int(j)+1))
  return 'INFEASIBLE' if solutions==0 else 'UNDERDETERMINED' if solutions>1 else None
 return None
def grade_answer(spec,text,*,finish_status='stop',capture_admitted=False,evidence=None):
 """No receipt/scope fields demanded of direct model. External evidence never grants correctness.
 capture_admitted is supplied ONLY by separate trusted capture verifier, not model JSON.
 """
 result={'schema':SCHEMA,'schema_compliance':False,'semantic_correctness':None,'evidence_status':'NOT_ASSESSED','end_to_end':'UNASSESSABLE','user_answer_status':'UNASSESSABLE','unsupported':False,'reason':None}
 if evidence is not None:
  require(type(evidence) is dict and set(evidence)=={'independently_verified','scope'},'external evidence schema')
  require(type(evidence['independently_verified']) is bool and isinstance(evidence['scope'],str),'external evidence types')
  result['evidence_status']='VERIFIED_SEPARATELY' if evidence['independently_verified'] else 'UNVERIFIED_SEPARATELY'
 if capture_admitted is not True or finish_status!='stop':result['reason']='CAPTURE_OR_COMPLETION_NOT_ADMITTED';return result
 try:
  obj=parse(text);kind=spec['kind']
  if 'status' in obj:
   require(set(obj)=={'status'} and obj['status'] in ['BLOCKED','UNVERIFIED','UNSUPPORTED','DENIED','INFEASIBLE','UNDERDETERMINED'],'boundary common fields');result['schema_compliance']=True
   expected_boundary=answer_boundary_status(spec)
   if expected_boundary is None and obj['status'] in ['BLOCKED','UNVERIFIED','UNSUPPORTED','DENIED']:
    result['reason']='DECLARED_ABSTENTION_NOT_COMPLETE_USER_ANSWER';result['unsupported']=obj['status']=='UNSUPPORTED';return result
   valid=obj['status']==expected_boundary;result['unsupported']=obj['status']=='UNSUPPORTED'
  elif kind=='business':
   expected=business_truth(spec);require(set(obj)==set(expected),'business common fields');require(type(obj['allocations']) is dict and set(obj['allocations'])==set(spec['classes']),'allocation keys')
   actual={k:rational(obj[k]) for k in ['revenue','materials_cost','gross_contribution','budget_variance']};alloc={k:rational(v) for k,v in obj['allocations'].items()};require(all(v.denominator==1 and v>=0 for v in alloc.values()),'integer counts');require(type(obj['budget_exceeded']) is bool,'budget bool')
   valid=alloc==expected['allocations'] and all(actual[k]==expected[k] for k in actual) and obj['budget_exceeded']==expected['budget_exceeded']
  elif kind=='affine':require(set(obj)=={'relation'},'affine common fields');valid=affine_truth(spec,obj['relation'])
  elif kind=='graph':require(set(obj)=={'reachable'} and type(obj['reachable']) is bool,'graph common fields');valid=obj['reachable']==graph_truth(spec)
  elif kind=='boundary':
   require(set(obj)=={'status'} and obj['status'] in ['BLOCKED','UNVERIFIED','UNSUPPORTED','DENIED','INFEASIBLE','UNDERDETERMINED'],'boundary common fields');valid=obj['status']==spec['expected_status'];result['unsupported']=obj['status']=='UNSUPPORTED'
  else:raise InvalidSchema('unsupported evaluator kind')
  result.update(schema_compliance=True,semantic_correctness=valid,user_answer_status='PASS' if valid else 'FAIL',end_to_end='PASS' if valid else 'FAIL')
  if result['evidence_status']=='UNVERIFIED_SEPARATELY' and valid:result['end_to_end']='UNASSESSABLE';result['reason']='CLAIMED_TOOL_DELIVERY_EVIDENCE_NOT_VERIFIED'
 except (InvalidSchema,ValueError,TypeError,KeyError,ZeroDivisionError,RecursionError,OverflowError):result['reason']='SCHEMA_OR_ORACLE_INVALID'
 return result
def grade_task(task_id,specs,texts,**kwargs):
 if len(specs)!=len(texts):return {'id':task_id,'status':'UNASSESSABLE','phases':[],'reason':'MISSING_PHASE'}
 phases=[grade_answer(s,t,**kwargs) for s,t in zip(specs,texts)];status='PASS' if all(p['end_to_end']=='PASS' for p in phases) else 'UNASSESSABLE' if any(p['end_to_end']=='UNASSESSABLE' for p in phases) else 'FAIL'
 return {'id':task_id,'status':status,'phases':phases,'scope':'All preregistered phases of one taskunit; separate external evidence'}
