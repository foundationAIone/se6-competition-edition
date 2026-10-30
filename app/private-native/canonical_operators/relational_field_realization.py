"""CANDIDATE relational field v1: dimensionless computation, no canonical/EM law.

G0 is stationary task graph geometry. Two independent rotating copies generate
bounded vector fields and explicit source interactions. Priorities are proposals
only; host native admission, QPRE type validation and mandatory replay stay separate.
"""
from copy import deepcopy
import math,re,json
from computational_interference_field import digest,rotate

SCHEMA='se6-candidate-relational-field-v1'
ROUTES={'LINEAR_MATH','LINEAR_DERIVATION','RELATIONAL','HOST_BUSINESS','HOST_BUDGET'}
ALL_ROUTES=ROUTES|{'DIRECT_MODEL','UNSUPPORTED'}
DEFAULT={'dt':.25,'rates':[1.,1.],'directions':[1,-1],'phases':[0.,0.], 'decay':.9,'gain':.1,'interaction':.1,'source_gains':[1.,1.]}

def finite(x,a,b):
    if type(x) not in (int,float) or not math.isfinite(x) or not a<=x<=b:raise ValueError('FINITE_PARAMETER')
    return float(x)
def clip(v,bound=1.):
    length=math.hypot(*v)
    return [x/max(1.,length/bound) for x in v]
def params(value):
    p=deepcopy(DEFAULT if value is None else value)
    if not isinstance(p,dict) or set(p)!=set(DEFAULT):raise ValueError('PARAMETER_FIELDS')
    for name in ('rates','directions','phases','source_gains'):
        if not isinstance(p[name],list) or len(p[name])!=2:raise ValueError('TWO_INDEPENDENT_FRAMES')
    if any(type(d) is not int or d not in (-1,0,1) for d in p['directions']):raise ValueError('DIRECTION')
    p['source_gains']=[finite(x,0,1) for x in p['source_gains']]
    p['rates']=[finite(x,0,10) for x in p['rates']];p['phases']=[finite(x,-math.pi,math.pi) for x in p['phases']]
    for k in ('dt','decay','gain','interaction'):p[k]=finite(p[k],0,1)
    return p

def graph(plan,mapping):
    if not isinstance(plan,dict) or not isinstance(plan.get('nodes'),list) or not 1<=len(plan['nodes'])<=12:raise ValueError('PLAN_BOUND')
    if len(str(plan).encode())>65536:raise ValueError('PLAN_BYTES')
    nodes=plan['nodes']
    if any(not isinstance(n,dict) or not isinstance(n.get('id'),str) for n in nodes):raise ValueError('PLAN_NODE')
    seen=set();depth={};outgoing={n['id']:0 for n in nodes}
    for n in nodes:
        if not isinstance(n,dict) or not isinstance(n.get('id'),str) or not 1<=len(n['id'])<=64 or n['id'] in seen:raise ValueError('PLAN_IDENTITY')
        if n.get('route') not in ALL_ROUTES or type(n.get('connected')) is not bool:raise ValueError('PLAN_ROUTE')
        deps=n.get('depends_on',[])
        if not isinstance(deps,list) or len(set(deps))!=len(deps) or any(d not in seen for d in deps):raise ValueError('PLAN_DEPENDENCY')
        text=n.get('input','')
        if not isinstance(text,str) or len(text.encode())>4096:raise ValueError('PLAN_INPUT_BOUND')
        spans=n.get('source_spans',[])
        if not isinstance(spans,list) or len(spans)>64 or any(not isinstance(s,list) or len(s)!=2 or any(type(v) is not int for v in s) or not 0<=s[0]<=s[1]<=4096 for s in spans):raise ValueError('PLAN_SPANS')
        depth[n['id']]=max((depth[d]+1 for d in deps),default=0)
        for d in deps:outgoing[d]+=1
        seen.add(n['id'])
    lineage=None;bindings={}
    if mapping is not None:
        if not isinstance(mapping,dict) or len(str(mapping).encode())>262144:raise ValueError('MAPPING_BOUND')
        binding=mapping.get('node_bindings');model=mapping.get('model')
        if not isinstance(binding,list) or len(binding)!=len(nodes) or not isinstance(model,dict):raise ValueError('MAPPING_SHAPE')
        vertices=model.get('vertices',[])
        if not isinstance(vertices,list) or len(vertices)>32:raise ValueError('MAPPING_VERTICES')
        vertexids={v.get('node_id') for v in vertices if isinstance(v,dict)}
        for b,n in zip(binding,nodes):
            if not isinstance(b,dict) or b.get('id')!=n['id'] or b.get('route')!=n['route'] or b.get('node_id') not in vertexids:raise ValueError('MAPPING_BINDING')
            # Existing bridge input fallback must be respected exactly.
            text=n.get('input') or ('Typed route '+n['route'])
            import hashlib
            if b.get('input_sha256')!=hashlib.sha256(text.encode()).hexdigest() or b.get('source_spans',[])!=n.get('source_spans',[]):raise ValueError('MAPPING_INPUT')
            bindings[n['id']]=b['node_id']
        # Reuse copied authentic pure typed graph validator, never production runtime.
        from operator_executor import load
        mapper,_,_,_,_,_=load()
        mapper.UniversalMap.model_validate_json(json.dumps(model,allow_nan=False))
        expected={(bindings[n['id']],bindings[d]) for n in nodes for d in n.get('depends_on',[])}
        actual={(a['node_id'],b['node_id']) for r in model.get('relations',[]) if r.get('kind')=='DEPENDS_ON' for a in r['source_nodes'] for b in r['target_nodes']}
        if expected!=actual:raise ValueError('MAPPING_DEPENDENCIES')
        lineage=deepcopy(model.get('flower_lineage',[]))
        if not isinstance(lineage,list) or len(lineage)>16:raise ValueError('FLOWER_LINEAGE_BOUND')
    rows=[];eligible=set();maxdepth=max(depth.values(),default=0)
    for n in nodes:
        ident=n['id'];deps=n.get('depends_on',[]);incoming=len(deps);out=outgoing[ident]
        pos=clip([depth[ident]/max(1,maxdepth), (out-incoming)/max(1,len(nodes)-1)])
        # Graph structure and public input extent; never guessed answer/defect labels.
        text=n.get('input','');extent=min(1,len(text.encode())/4096)
        features={'depth':depth[ident],'incoming':incoming,'outgoing':out,'input_extent':extent,'connected':n['connected']}
        force=clip([(.25+.5*int(n['connected'])+.25*extent), (out-incoming)/max(1,len(nodes))])
        valid=n['connected'] and n['route'] in ROUTES and all(d in eligible for d in deps)
        if valid:eligible.add(ident)
        rows.append({'id':ident,'route':n['route'],'depends_on':deps,'position':pos,'source_force':force,'features':features,'eligible':valid,'mapped_node_id':bindings.get(ident)})
    return rows,lineage

def realize_field(plan,actual_mapping=None,prior_state=None,parameters=None,enabled=True):
    if type(enabled) is not bool:raise ValueError('ENABLED_TYPE')
    p=params(parameters);g0,lineage=graph(plan,actual_mapping);inputsha=digest({'plan':plan,'actual_mapping':actual_mapping});ids=[r['id'] for r in g0];step=0
    forces=[[r['source_force'] for r in g0] for _ in range(2)]
    prior_hash=None;rebase=None
    if prior_state is not None:
        s=prior_state
        if not isinstance(s,dict) or len(str(s).encode())>65536 or set(s)!={'schema','step','parameters','parameters_sha256','input_sha256','ids','forces','previous_numeric_sha256','feedback','state_sha256'} or s['schema']!=SCHEMA or digest({k:v for k,v in s.items() if k!='state_sha256'})!=s['state_sha256']:raise ValueError('STATE_SEAL')
        if type(s['step']) is not int or not 0<=s['step']<1024 or s['parameters_sha256']!=digest(params(s['parameters'])):raise ValueError('STATE_PARAMETERS')
        if any(not isinstance(s[k],str) or re.fullmatch('[0-9a-f]{64}',s[k]) is None for k in ('input_sha256','previous_numeric_sha256')):raise ValueError('STATE_ANCESTRY')
        if not isinstance(s['ids'],list) or not 1<=len(s['ids'])<=12 or any(not isinstance(x,str) or not 1<=len(x)<=64 for x in s['ids']) or len(set(s['ids']))!=len(s['ids']) or not isinstance(s['forces'],list) or len(s['forces'])!=2:raise ValueError('STATE_GRAPH_MEMBERSHIP')
        for group in s['forces']:
            if not isinstance(group,list) or len(group)!=len(s['ids']):raise ValueError('STATE_FORCES')
            for v in group:
                if not isinstance(v,list) or len(v)!=2 or any(type(x) not in (float,int) or not math.isfinite(x) for x in v) or math.hypot(*v)>1+1e-12:raise ValueError('STATE_FORCE_BOUND')
        step=s['step'];prior_hash=s['state_sha256']
        oldids=s['ids'];oldgroups=[dict(zip(oldids,group)) for group in s['forces']]
        changed=s['input_sha256']!=inputsha
        forces=[]
        for group in oldgroups:
            forces.append([clip([.5*a+.5*b for a,b in zip(group[r['id']],r['source_force'])]) if changed and r['id'] in group else deepcopy(group.get(r['id'],r['source_force'])) for r in g0])
        if changed or s['parameters_sha256']!=digest(p):
            rebase={'retained_ids':[i for i in ids if i in oldids],'added_ids':[i for i in ids if i not in oldids],'removed_ids':[i for i in oldids if i not in ids], 'input_changed':changed,'parameters_changed':s['parameters_sha256']!=digest(p),'shared_source_blend':.5 if changed else 0.,'old_input_sha256':s['input_sha256'],'scope':'Candidate graph/config rebase; no native knowledge/truth change'}
    t=step*p['dt'];frames=[]
    for k in range(2):
        angle=math.remainder(p['directions'][k]*p['rates'][k]*t+p['phases'][k],2*math.pi)
        frames.append({'angle':angle,'sources':[{'id':r['id'],'position':rotate(r['position'],angle),'vector':[p['source_gains'][k]*v for v in rotate(f,angle)],'base_force_norm':math.hypot(*f),'rotation_norm_error':abs(math.hypot(*rotate(f,angle))-math.hypot(*f))} for r,f in zip(g0,forces[k])]})
    samples=[];n=len(ids);interactions=[[],[]]
    for r in g0:
        terms=[]
        for frame in frames:
            group=[0.,0.]
            for src in frame['sources']:
                w=1/(1+sum((a-b)**2 for a,b in zip(r['position'],src['position'])))
                for j in (0,1):group[j]+=w*src['vector'][j]/(2*n)
            terms.append(group)
        total=[sum(v[j] for v in terms) for j in (0,1)]
        samples.append({'id':r['id'],'position':r['position'],'field':total,'energy':sum(x*x for x in total),'components':terms,'interference':2*sum(a*b for a,b in zip(*terms)),'norm_bound':1.})
    # Explicit opposite-source interaction in stationary G0 coordinates, not EM force.
    for k in range(2):
        inverse=-frames[k]['angle']
        for src in frames[k]['sources']:
            response=[0.,0.]
            for other in frames[1-k]['sources']:
                w=1/(1+sum((a-b)**2 for a,b in zip(src['position'],other['position'])))
                for j in (0,1):response[j]+=w*(other['vector'][j]-src['vector'][j])/n
            interactions[k].append(clip(rotate(response,inverse)))
    inputs={'plan':deepcopy(plan),'actual_mapping':deepcopy(actual_mapping)};inputsha=digest(inputs)
    numeric={'schema':SCHEMA,'input_sha256':inputsha,'parameters':p,'step':step,'time':t,'G0':g0,'rotating_frames':frames,'samples':samples,'source_interactions':interactions,'prior_state_sha256':prior_hash,'state_rebase':rebase}
    numericsha=digest(numeric)
    nextforces=[[clip([p['decay']*v[j]+p['gain']*p['interaction']*f[j] for j in (0,1)]) for v,f in zip(group,response)] for group,response in zip(forces,interactions)]
    state={'schema':SCHEMA,'step':step+1,'parameters':p,'parameters_sha256':digest(p),'input_sha256':inputsha,'ids':ids,'forces':nextforces,'previous_numeric_sha256':numericsha,'feedback':None};state['state_sha256']=digest(state)
    rows=[{'id':r['id'],'route':r['route'],'eligible':r['eligible'],'mapped_node_id':r['mapped_node_id'],'field_priority':sample['energy'] if enabled else 0.,'transformed_position':frames[0]['sources'][i]['position'],'features':r['features']} for i,(r,sample) in enumerate(zip(g0,samples))]
    ranking=sorted((r for r in rows if r['eligible']),key=lambda r:(-r['field_priority'],r['id']))
    projection={'operator':'CANDIDATE_RELATIONAL_FIELD_T','possibility_only':True,'enabled':enabled,'candidates':rows,'ranking':[r['id'] for r in ranking],'authority':'NONE; native admission and mandatory replay unchanged'}
    material={'schema':SCHEMA,'status':'CANDIDATE_COMPUTATIONAL_ONLY','units':'Dimensionless relational coordinates/vectors; phase radians; bounded step time','inputs':inputs,'prior_state':deepcopy(prior_state),'input_sha256':inputsha,'numeric':numeric,'numeric_sha256':numericsha,'projection':projection,'lineage':lineage,'checkpoint':state,'scope':'No canonical equivalence, physical EM, answer truth, effect permission or solving advantage'}
    return {**material,'result_sha256':digest(material)}

def finish_field(result,audits):
    """HOST audit feedback on separate candidate forces. Caller authenticity trusted."""
    if digest({k:v for k,v in result.items() if k!='result_sha256'})!=result.get('result_sha256'):raise ValueError('RESULT_SEAL')
    if not isinstance(audits,list) or len(audits)>12:raise ValueError('AUDIT_BOUND')
    eligible={r['id'] for r in result['projection']['candidates'] if r['eligible']};seen=set()
    for row in audits:
        if not isinstance(row,dict) or set(row)!={'id','passed'} or row['id'] not in eligible or row['id'] in seen or type(row['passed']) is not bool:raise ValueError('AUDIT_BINDING')
        seen.add(row['id'])
    cp=deepcopy(result['checkpoint']);feedback={r['id']:(1. if r['passed'] else -1.) for r in audits};gain=result['numeric']['parameters']['gain']
    for group in cp['forces']:
        for i,ident in enumerate(cp['ids']):group[i]=clip([group[i][0]+gain*feedback.get(ident,0.),group[i][1]])
    cp['feedback']={'audits':deepcopy(audits),'host_trust':'Declared HOST audit; field does not authenticate evidence','authority_effect':'NONE'}
    cp['state_sha256']=digest({k:v for k,v in cp.items() if k!='state_sha256'})
    return cp
