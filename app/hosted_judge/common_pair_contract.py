"""Current public-only common answer contract; no native or provider imports.
Historical v8 scoring remains separate. Unknown updates refuse grading, never reuse stale truth.
"""
import ast,json,re
from copy import deepcopy
from fractions import Fraction
from . import common_answer_scoring as grader
from .v8_scoring import public_business
PROTOCOL='SE6_COMMON_PUBLIC_ANSWER_V1'
NAME=r'[A-Za-z][A-Za-z0-9_]{0,31}'
NUMBER=r'\d+(?:/\d+|\.\d+)?'
CONTRACT=('Return one JSON object only. Answer the CURRENT conditional public question, using '
 'shared public history and only explicitly declared corrections. Correct E# replaces ONLY the named equality. '
 'Business answers use exactly allocations, revenue, materials_cost, gross_contribution, budget_variance, '
 'budget_exceeded; allocations has exactly the two declared lowercase class names. Gross contribution '
 'is revenue minus materials; budget variance is materials minus budget; exceeded means materials > budget. '
 'Affine answers use only relation:{coefficients:{requested_variable:rational},rhs:rational}; '
 'all and only requested variables must have nonzero coefficients. Graph answers use only reachable:boolean '
 'for directed edges. A legitimate boundary uses only status. No internal receipts, provenance, task hashes, '
 'certificates or world-fact flags are required. Values are conditional supplied premises, not verified world facts. ')

def _row(text):
    text=text.strip().rstrip('.').replace('\u2212','-')
    if len(text)>512 or text.count('=')!=1 or re.search(r'(?<![A-Za-z0-9_])\d+(?:\.\d+)?[eE][+-]?\d+',text):raise ValueError('affine lexical bound')
    def side(raw):
        raw=re.sub(r'(?<![A-Za-z0-9_])(\d+(?:\.\d+)?(?:/\d+)?)([A-Za-z_])',r'\1*\2',raw.strip())
        tree=ast.parse(raw,mode='eval')
        if len(list(ast.walk(tree)))>128:raise ValueError('AST bound')
        def visit(n):
            if isinstance(n,ast.Name) and re.fullmatch(NAME,n.id):return {n.id:Fraction(1)},Fraction(0)
            if isinstance(n,ast.Constant) and type(n.value) in (int,float):return {},grader.rational(ast.get_source_segment(raw,n))
            if isinstance(n,ast.UnaryOp) and isinstance(n.op,(ast.UAdd,ast.USub)):
                c,b=visit(n.operand);s=-1 if isinstance(n.op,ast.USub) else 1;return {k:s*v for k,v in c.items()},s*b
            if isinstance(n,ast.BinOp):
                a,b=visit(n.left);c,d=visit(n.right)
                if isinstance(n.op,(ast.Add,ast.Sub)):
                    s=-1 if isinstance(n.op,ast.Sub) else 1;return {k:a.get(k,0)+s*c.get(k,0) for k in set(a)|set(c)},b+s*d
                if isinstance(n.op,ast.Mult) and not(a and c):
                    return ({k:v*d for k,v in a.items()},b*d) if not c else ({k:v*b for k,v in c.items()},d*b)
                if isinstance(n.op,ast.Div) and not c and d:return {k:v/d for k,v in a.items()},b/d
            raise ValueError('nonaffine expression')
        return visit(tree.body)
    left,right=text.split('=');a,b=side(left);c,d=side(right)
    coefficients={k:str(a.get(k,0)-c.get(k,0)) for k in sorted(set(a)|set(c)) if a.get(k,0)!=c.get(k,0)}
    if len(coefficients)>6:raise ValueError('variable bound')
    return {'coefficients':coefficients,'rhs':str(d-b)}

def derive_public_spec(question,history):
    if not isinstance(question,str) or not 0<len(question.encode())<=4096 or not isinstance(history,list) or len(history)>7 or any(not isinstance(q,str) or len(q.encode())>4096 for q in history):raise ValueError('public input bound')
    state=None;equations={};domain=None;last_targets=None
    for text in [*history,question]:
        body=text.strip()
        if re.search(r'\bDerive\b',body,re.I):
            prefix,request=re.split(r'\bDerive\b',body,maxsplit=1,flags=re.I)
            target=re.fullmatch(r'\s*(?:a |the )?(?:relation|relationship) (?:involving|between|among) (.+?)\.?\s*',request,re.I)
            if not target:raise ValueError('requested affine syntax')
            targets=[x.strip() for x in re.sub(r'\s+and\s+',',',target[1].rstrip('.')).split(',')]
            if not 1<=len(targets)<=6 or len(set(targets))!=len(targets) or any(not re.fullmatch(NAME,x) for x in targets):raise ValueError('target bound')
            dm=list(re.finditer(r'Variables are integers (?:between (-?\d+) and (-?\d+)|in \[(-?\d+),\s*(-?\d+)\])\.?',prefix,re.I))
            if len(dm)>1:raise ValueError('ambiguous integer domain')
            if dm:
                m=dm[0];new=[int(m[1] or m[3]),int(m[2] or m[4])]
                if not -10000<=new[0]<=new[1]<=10000 or new[1]-new[0]>=128 or domain is not None and domain!=new:raise ValueError('domain bound/change')
                domain=new;prefix=prefix[:m.start()]+prefix[m.end():]
            prefix=prefix.strip();update=re.fullmatch(r'Correct\s+('+NAME+r')\s*(?::|\bto\b)\s*(.+)',prefix,re.I|re.S)
            if update:
                label,literal=update.groups()
                if label not in equations:raise ValueError('unknown equality correction')
                equations[label]=_row(literal)
            elif prefix:
                if equations:raise ValueError('unannounced equality replacement')
                prefix=re.sub(r'^Given(?: (?:the |these )?(?:linear )?equations)?\s*:\s*','',prefix,flags=re.I)
                parts=[p.strip() for p in re.split(r'[\n;]',prefix) if p.strip()]
                if not 1<=len(parts)<=4:raise ValueError('equation count')
                for index,part in enumerate(parts):
                    m=re.fullmatch(r'('+NAME+r'):\s*(.+)',part);label,literal=m.groups() if m else (f'E{index+1}',part)
                    if label in equations:raise ValueError('duplicate equality')
                    equations[label]=_row(literal)
            elif not equations:raise ValueError('missing premises')
            names=set().union(*(set(r['coefficients']) for r in equations.values()))
            if not set(targets)<=names or len(names)>6:raise ValueError('unknown variables')
            state={'kind':'affine','premises':list(equations.values()),'requested_variables':targets}
            if domain is not None:state['public_integer_domain']=domain
            last_targets=targets
        elif 'RELATES_TO' in body:
            edges=deepcopy(state['edges']) if state and state['kind']=='graph' else []
            found=[list(p) for p in re.findall(r'('+NAME+r') RELATES_TO ('+NAME+r')',body)]
            query=re.search(r'Can ('+NAME+r') (?:still )?be reached from ('+NAME+r')(?: following these directed links)?\?',body)
            if not query or len(re.findall(r'Can ',body))!=1:raise ValueError('directed query')
            residue=re.sub(r'('+NAME+r') RELATES_TO ('+NAME+r')','',body)
            residue=re.sub(r'Can '+NAME+r' (?:still )?be reached from '+NAME+r'(?: following these directed links)?\?','',residue)
            for phrase in ('Conditional directed relations:', 'Remove the directed edge', 'Return reachable true/false.', 'Do not invent geometric adjacency.'):
                residue=residue.replace(phrase,'')
            if residue.strip(' ;.\n\t'):raise ValueError('unrecognized graph instruction')
            if body.startswith('Remove the directed edge'):
                if len(found)!=1 or found[0] not in edges:raise ValueError('unknown edge removal')
                edges.remove(found[0])
            else:
                if edges:raise ValueError('unannounced graph replacement')
                edges=found
            if len(edges)>12 or len({tuple(p) for p in edges})!=len(edges):raise ValueError('graph bound')
            state={'kind':'graph','edges':edges,'start':query[2],'goal':query[1]}
        else:
            facts=public_business(text)
            if facts:
                if re.search(r'\bCorrect\b',body,re.I):raise ValueError('combined business update unsupported')
                if state is not None:raise ValueError('unannounced business replacement')
                for pattern in [r'completed (\d+) jobs',r'original \w+ recorded ('+NUMBER+r') [A-Za-z]+-hours',r'materials budget is (?:\$|USD)\s*('+NUMBER+r')']:
                    if len({grader.rational(v) for v in re.findall(pattern,text,re.I)})>1:raise ValueError('ambiguous public scalar')
                state={'kind':'business','jobs':str(facts['total_jobs']),'hours':facts['hours'].get('corrected',facts['hours']['original']),
                    'budget':facts['facts']['budget']['value'],'classes':{n:{'hours':facts['hours_per_job'][n],'materials':facts['facts'][n+':expense']['value'],'revenue':facts['facts'][n+':revenue']['value']} for n in facts['classes']}}
            elif state and state['kind']=='business':
                match=re.fullmatch(r'Correct(?: the)? (?:technician-hours|recorded hours)(?: to) ('+NUMBER+r')(?: technician-hours)?\.?\s*(.*)',body,re.I|re.S)
                monetary=re.fullmatch(r'Correct (?:(\w+) (materials cost|customer revenue)|materials budget) to (?:\$|USD)\s*('+NUMBER+r')\.?\s*(.*)',body,re.I|re.S)
                if match:
                    amount,suffix=match.groups();state['hours']=str(grader.rational(amount))
                elif monetary:
                    name,column,amount,suffix=monetary.groups()
                    if name is None:state['budget']=str(grader.rational(amount))
                    elif name.lower() in state['classes']:state['classes'][name.lower()]['materials' if column.lower()=='materials cost' else 'revenue']=str(grader.rational(amount))
                    else:raise ValueError('unknown class')
                else:raise ValueError('unrecognized current business update')
                if suffix:
                    request=re.fullmatch(r'Calculate (.+?)\.?',suffix,re.I)
                    allowed={'allocations','revenue','materials','materials cost','contribution','gross contribution','budget variance'}
                    items=[x.strip().lower() for x in re.split(r',\s*|\s+and\s+',request[1])] if request else []
                    if not items or any(x not in allowed for x in items):raise ValueError('unknown correction request')
            else:raise ValueError('unsupported public question')
    return deepcopy(state)

def safe_spec(question,history):
    try:return derive_public_spec(question,history)
    except (ValueError,TypeError,KeyError,ZeroDivisionError,SyntaxError,RecursionError):return None

def public_shape(question,history):
    spec=safe_spec(question,history)
    if spec is None:return CONTRACT+'Unsupported intake must abstain with {"status":"UNSUPPORTED"}; no automatic winner is assigned.'
    if spec['kind']=='business':shape={'allocations':{n:'RATIONAL' for n in spec['classes']},'revenue':'RATIONAL','materials_cost':'RATIONAL','gross_contribution':'RATIONAL','budget_variance':'RATIONAL','budget_exceeded':'BOOLEAN'}
    elif spec['kind']=='affine':shape={'relation':{'coefficients':{n:'NONZERO_RATIONAL' for n in spec['requested_variables']},'rhs':'RATIONAL'}}
    else:shape={'reachable':'BOOLEAN'}
    return CONTRACT+' Exact public output keys/type placeholders (not solutions): '+json.dumps(shape,separators=(',',':'))

def score_pair(spec,captures,simulated=False):
    lanes={}
    for lane in ('se6','baseline'):
        if spec is None:row={'schema_compliance':False,'semantic_correctness':None,'user_answer_status':'UNASSESSABLE','reason':'UNSUPPORTED_OR_AMBIGUOUS_PUBLIC_INTAKE'}
        else:row=grader.grade_answer(spec,captures[lane]['text'],capture_admitted=True)
        assessed=row['user_answer_status']!='UNASSESSABLE'
        lanes[lane]={**row,'status':'ASSESSABLE' if assessed else 'UNASSESSABLE','score':int(row['semantic_correctness'] is True),'maximum':1,'checks':{'schema_compliance':row['schema_compliance'],'semantic_correctness':row['semantic_correctness']},'scope':'One current conditional public user answer; provenance scored separately.'}
    winner=None
    if not simulated and all(r['status']=='ASSESSABLE' for r in lanes.values()):
        winner='tie' if lanes['se6']['score']==lanes['baseline']['score'] else max(lanes,key=lambda k:lanes[k]['score'])
    return {'lanes':lanes,'arithmetic_winner':None,'common_user_answer_winner':winner,'overall_winner':None,'scope':'Current public conditional answer only; no architectural or general model superiority.'}
