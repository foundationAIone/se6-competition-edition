"""Independent public-plan/UniversalMap structural checks; no producer imports."""
import hashlib,json
import math
try:
    from . import toroidal_field_oracle as f
except ImportError:
    import toroidal_field_oracle_navigation_v2 as f

SUPPORTED={'LINEAR_MATH','LINEAR_DERIVATION','RELATIONAL','HOST_BUSINESS','HOST_BUDGET'}
BLOCKED={'DIRECT_MODEL','UNSUPPORTED'}
def require(ok,why):
    if not ok:raise ValueError(why)
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()).hexdigest()

def derive_graph(plan,mapping):
    require(isinstance(plan,dict) and isinstance(plan.get('nodes'),list) and 1<=len(plan['nodes'])<=12,'PLAN')
    seen=set();eligible=set();nodes=plan['nodes'];ids=[]
    for n in nodes:
        ident=n.get('id');require(isinstance(ident,str) and ident and ident not in seen,'PLAN_ID')
        deps=n.get('depends_on',[])
        require(isinstance(deps,list) and len(set(deps))==len(deps) and all(d in seen for d in deps),'DEPENDENCY')
        require(n.get('route') in SUPPORTED|BLOCKED and type(n.get('connected')) is bool,'ROUTE')
        if n['route'] in SUPPORTED and n['connected'] and all(d in eligible for d in deps):eligible.add(ident)
        ids.append(ident);seen.add(ident)
    require(isinstance(mapping,dict) and isinstance(mapping.get('model'),dict),'MAPPING')
    binding=mapping.get('node_bindings');require(isinstance(binding,list) and len(binding)==len(nodes),'BINDINGS')
    terminal={};vertexset={v['node_id'] for v in mapping['model']['vertices']}
    require(len(vertexset)==len(nodes)+1,'VERTICES')
    for n,b in zip(nodes,binding):
        text=n.get('input') or ('Typed route '+n['route'])
        require(b.get('id')==n['id'] and b.get('route')==n['route'] and b.get('node_id') in vertexset,'BINDING_ID')
        require(b.get('input_sha256')==hashlib.sha256(text.encode()).hexdigest() and b.get('source_spans',[])==n.get('source_spans',[]),'INPUT_PROVENANCE')
        require(b['node_id'] not in terminal.values(),'UNIQUE_TERMINAL')
        terminal[n['id']]=b['node_id']
    roots=vertexset-set(terminal.values());require(len(roots)==1,'SOURCE_VERTEX');root=next(iter(roots))
    observed=[]
    for relation in mapping['model']['relations']:
        kind=relation['kind'];require(kind in ('RELATES_TO','DEPENDS_ON'),'RELATION_KIND')
        for source in relation['source_nodes']:
            for target in relation['target_nodes']:
                require(source['node_id'] in vertexset and target['node_id'] in vertexset,'EDGE_MEMBERSHIP')
                observed.append((kind,source['node_id'],target['node_id']))
    expected=[('RELATES_TO',root,terminal[i]) for i in ids]+[('DEPENDS_ON',terminal[n['id']],terminal[d]) for n in nodes for d in n.get('depends_on',[])]
    require(len(observed)==len(expected) and set(observed)==set(expected),'EXACT_EDGES')
    lineage=mapping['model'].get('flower_lineage',[]);require(isinstance(lineage,list) and 1<=len(lineage)<=16,'FLOWER_LINEAGE')
    first=lineage[0]
    require(first['center']['node_id']==root and [r['node_id'] for r in first['terminals']]==[terminal[i] for i in ids],'FLOWER_SOURCE_TERMINALS')
    require(first['depth']==0 and first['previous_flower_id'] is None and first['previous_flower_hash'] is None and first['recentered_from_terminal'] is None,'FLOWER_ROOT')
    for prior,current in zip(lineage,lineage[1:]):
        require(current['previous_flower_id']==prior['flower_id'] and current['previous_flower_hash']==prior['flower_hash'] and current['depth']==prior['depth']+1,'FLOWER_ANCESTRY')
        require(current['recentered_from_terminal'] in prior['terminals'] and current['center']==current['recentered_from_terminal'],'FLOWER_RECENTER')
        require([r['node_id'] for r in current['terminals']]==[prior['center']['node_id']],'FLOWER_PREVIOUS_CENTER')
    require(all(f.get('shadow_only') is True and f.get('authority_effect')=='NONE' for f in lineage),'FLOWER_AUTHORITY')
    return {'source_vertex':root,'terminals':terminal,'eligible_ids':sorted(eligible),'edges':observed,'scope':'Actual typed relational and FlowerCenter structure; no assertion that native token rings define metric geometry'}

def bounded_reachability(start,edges,allowed,max_hops=4):
    """Directed traversal only; any reverse adapter must expose its own contract."""
    reached={start};frontier={start}
    for _ in range(max_hops):
        frontier={b for a,b in edges if a in frontier and b in allowed}-reached
        reached|=frontier
    return reached

def alignment_score(position_a,position_b,phi_a,phi_b):
    """Candidate directional alignment, independently evaluated with Euclidean norm."""
    displacement=[b-a for a,b in zip(position_a,position_b)]
    average=[(a+b)/2 for a,b in zip(phi_a,phi_b)]
    d=math.hypot(*displacement);f=math.hypot(*average)
    alignment=sum(x*y for x,y in zip(displacement,average))/(max(d,1e-15)*max(f,1e-15))
    energy=sum(x*x for x in phi_b)
    return round(.75*alignment+.25*energy/(1+energy),12)

def ordinary_or_field_path(start,arcs,positions,fields,allowed,budget,mode):
    """Inspect actual relation arcs; reverse arcs must be explicitly supplied."""
    require(type(budget) is int and 0<=budget<=4 and mode in ('field','ordinary'),'TRAVERSAL_BUDGET')
    require(start in positions and start in fields,'START')
    path=[start];visited={start};weights=[]
    if mode=='field' and all(math.hypot(*b)==0 for b in fields.values()):return path,weights
    for _ in range(budget):
        neighbors=sorted({b for a,b in arcs if a==path[-1] and b in allowed and b not in visited})
        if not neighbors:break
        scores={b:alignment_score(positions[path[-1]],positions[b],fields[path[-1]],fields[b]) for b in neighbors}
        nxt=min(neighbors,key=lambda b:(-scores[b] if mode=='field' else 0,b))
        weights.append({'from':path[-1],'to':nxt,'score':scores[nxt],'effective_score':scores[nxt] if mode=='field' else 0.})
        path.append(nxt);visited.add(nxt)
    return path,weights

def candidate_hex_centers():
    centers=[]
    for q in range(-2,3):
        for r in range(-2,3):
            ring=max(abs(q),abs(r),abs(q+r))
            if ring<=2:centers.append((ring,math.atan2(math.sqrt(3)*r/2,q+r/2)%(2*math.pi),q,r))
    return [{'index':i,'axial':[q,r],'position':[q+r/2,math.sqrt(3)*r/2],'radius':1.} for i,(_,_,q,r) in enumerate(sorted(centers))]

def verify_navigation(env,result,state,field,plan,mapping):
    """HOST supplies actual plan/map/prior; rejects self-rehashed false proposals."""
    f.require(len(json.dumps(env,allow_nan=False))<500000 and len(json.dumps(result,allow_nan=False))<500000,'NAV_BOUND')
    graph=derive_graph(plan,mapping);circles=candidate_hex_centers();nodes=plan['nodes'];ids=[n['id'] for n in nodes]
    model=mapping['model'];alias={graph['source_vertex']:'source',**{v:k for k,v in graph['terminals'].items()}}
    vertices=[]
    for i,ident in enumerate(['source',*ids]):
        position=[circles[i]['position'][0]*u+circles[i]['position'][1]*v for u,v in zip(f.U,f.V)]
        vertices.append({'id':ident,'mapped_node_id':graph['source_vertex'] if ident=='source' else graph['terminals'][ident],'position':position,'admitted':ident=='source' or ident in graph['eligible_ids'],'circle_index':i})
    arcs=[]
    for relation in model['relations']:
        for a in relation['source_nodes']:
            for b in relation['target_nodes']:
                x,y=alias[a['node_id']],alias[b['node_id']]
                for start,end,direction in ((x,y,'FORWARD'),(y,x,'REVERSE_INSPECTION')):
                    arcs.append({'from':start,'to':end,'kind':relation['kind'],'direction':direction,'relation_id':relation['relation_id'],'original_source_node_id':a['node_id'],'original_target_node_id':b['node_id'],'scope':'RELATION_AUDIT; dependency causality/eligibility unchanged'})
    # Admission ordering belongs to actual topological plan, not set iteration.
    admitted=[i for i in ids if i in graph['eligible_ids']]
    expected_env={'schema':'se6-candidate-fol-environment-v1','source_id':'source','vertices':vertices,'arcs':arcs,'admitted_ids':admitted,'circles':circles,'model_sha256':f.digest(model),'plan_sha256':f.digest(plan),'flower_lineage':model['flower_lineage'],'sample_points':[{'id':r['id'],'position':r['position']} for r in vertices if r['id']!='source'],'scope':'Actual typed mapping edges/provenance with separate candidate19-circle metric overlay; not canonical geometric Flower or evidence authority'}
    expected_env['environment_sha256']=f.digest(expected_env)
    errors=[];f.compare(env,expected_env,errors)
    f.verify_result(field)
    require(field['inputs']['sample_points']==env['sample_points'],'FIELD_SAMPLE_GRAPH_BINDING')
    expected_sources=[{'id':n['id'],'amplitude':min(1,.25+.5*int(n['connected'])+.25*len(n.get('input','').encode())/4096)} for n in nodes]
    require(field['inputs']['mapped_sources']==expected_sources,'FIELD_SOURCE_GRAPH_BINDING')
    f.keys(result,('schema','status','mode','environment_sha256','field_numeric_sha256','start','navigation_step','prior_state_sha256','start_mapped_node_id','trajectory','trajectory_mapped_node_ids','traversed_relationships','choices','selected_ids','U','rotations','reason','state_rebase','proposed_checkpoint','authority','scope','navigation_sha256'))
    require(result['navigation_sha256']==f.digest({k:v for k,v in result.items() if k!='navigation_sha256'}),'NAV_SEAL')
    mode=result['mode'];require(mode in ('field','ordinary'),'MODE');goals=result['U']
    f.keys(goals,('goal_ids','budget','audit_budget'))
    require(isinstance(goals['goal_ids'],list) and len(set(goals['goal_ids']))==len(goals['goal_ids']) and all(i in admitted for i in goals['goal_ids']),'GOALS')
    require(type(goals['budget']) is int and 0<=goals['budget']<=4 and type(goals['audit_budget']) is int and 0<=goals['audit_budget']<=1,'BUDGET')
    byid={v['id']:v for v in vertices};position='source';orientation=[0.,0.,0.];step=0;rebase=None
    if state is not None:
        f.keys(state,('schema','step','environment_sha256','position','mapped_node_id','orientation','field_numeric_sha256','last_trajectory','previous_state_sha256','state_sha256'))
        require(state['schema']=='se6-candidate-field-navigation-v1' and state['state_sha256']==f.digest({k:v for k,v in state.items() if k!='state_sha256'}),'STATE_SEAL')
        require(type(state['step']) is int and 0<=state['step']<1024,'STATE_STEP')
        for k in ('environment_sha256','field_numeric_sha256'):
            require(isinstance(state[k],str) and len(state[k])==64 and all(c in '0123456789abcdef' for c in state[k]),'STATE_HASH')
        require(state['previous_state_sha256'] is None or isinstance(state['previous_state_sha256'],str) and len(state['previous_state_sha256'])==64 and all(c in '0123456789abcdef' for c in state['previous_state_sha256']),'STATE_PREVIOUS')
        f.vector(state['orientation']);require(math.hypot(*state['orientation'])<=1+1e-12,'STATE_ORIENTATION')
        require(isinstance(state['last_trajectory'],list) and len(state['last_trajectory'])<=5,'STATE_HISTORY')
        step=state['step']
        if state['position'] in byid and byid[state['position']]['mapped_node_id']==state['mapped_node_id'] and byid[state['position']]['admitted']:
            position=state['position'];orientation=state['orientation']
        else:rebase={'reason':'ACTUAL_MAPPED_IDENTITY_CHANGED_RESET_TO_SOURCE','prior_environment_sha256':state['environment_sha256'],'prior_position':state['position'],'scope':'Candidate location rebase; native memory/Entity identity unchanged'}
        require(not (state['environment_sha256']==env['environment_sha256'] and rebase is not None),'CURRENT_STATE_BINDING')
    samples={r['id']:r for r in field['numeric']['samples']};coeff=field['numeric']['coefficients'];p=field['numeric']['parameters']
    sourcephi=f.field(byid['source']['position'],coeff['ct'],coeff['cp'],p);samples['source']={'field':sourcephi,'energy':sum(x*x for x in sourcephi)}
    path=[position];traversed=[];choices=[];visited={position};reason='BUDGET_COMPLETED'
    if mode=='field' and max(s['energy'] for s in samples.values())<=1e-24:reason='ZERO_FIELD_IDENTITY'
    elif not goals['goal_ids']:reason='NO_ADMITTED_GOALS_IDENTITY'
    else:
        for _ in range(goals['budget']):
            options=[]
            for arc in arcs:
                target=arc['to']
                if arc['from']!=position or target in visited or not byid[target]['admitted']:continue
                delta=[b-a for a,b in zip(byid[position]['position'],byid[target]['position'])];dn=math.hypot(*delta);require(dn>=1e-12,'DEGENERATE_EDGE')
                phi=[.5*(a+b) for a,b in zip(samples[position]['field'],samples[target]['field'])];pn=math.hypot(*phi)
                alignment=sum(a*b for a,b in zip(phi,delta))/(max(pn,1e-15)*max(dn,1e-15))
                energy=samples[target]['energy'];potential=energy/(1+energy);score=.75*alignment+.25*potential
                options.append({'target':target,'alignment':alignment,'energy_potential':potential,'field_score':score,'effective_score':round(score,12) if mode=='field' else 0.,'arc':arc})
            options.sort(key=lambda r:(-r['effective_score'],r['target'],r['arc']['relation_id'],r['arc']['direction']))
            choices.append({'from':position,'reachable_choices':options})
            if not options:reason='NO_UNVISITED_ADMITTED_NEIGHBOR';break
            chosen=options[0];traversed.append(chosen['arc']);delta=[b-a for a,b in zip(byid[position]['position'],byid[chosen['target']]['position'])];orientation=[x/max(math.hypot(*delta),1e-15) for x in delta]
            position=chosen['target'];visited.add(position);path.append(position)
    selected=[i for i in reversed(path[1:]) if i in goals['goal_ids']][:goals['audit_budget']]
    cp={'schema':'se6-candidate-field-navigation-v1','step':step+1,'environment_sha256':env['environment_sha256'],'position':position,'mapped_node_id':byid[position]['mapped_node_id'],'orientation':orientation,'field_numeric_sha256':field['numeric_sha256'],'last_trajectory':path,'previous_state_sha256':state['state_sha256'] if state else None};cp['state_sha256']=f.digest(cp)
    expected={'schema':'se6-candidate-field-navigation-v1','status':'CANDIDATE_TRAJECTORY' if traversed else 'JUSTIFIED_IDENTITY','mode':mode,'environment_sha256':env['environment_sha256'],'field_numeric_sha256':field['numeric_sha256'],'start':path[0],'navigation_step':step,'prior_state_sha256':state['state_sha256'] if state else None,'start_mapped_node_id':byid[path[0]]['mapped_node_id'],'trajectory':path,'trajectory_mapped_node_ids':[byid[i]['mapped_node_id'] for i in path],'traversed_relationships':traversed,'choices':choices,'selected_ids':selected,'U':goals,'rotations':{'time':field['numeric']['time'],'rates':p['rates'],'directions':p['directions'],'phases':p['phases'],'polarities':p['polarities']},'reason':reason,'state_rebase':rebase,'proposed_checkpoint':cp,'authority':'NONE; all paths are HOST candidate inspections until native proof and typed recenter are verified','scope':'Directional field+energy edge policy over actualrelationships, ordinary arm computes same weights butneutralizes influence; reverse arcs are inspections, not reversed dependencycausality'}
    # State seal uses independently reconstructed floats; compare all CP semantics
    # first, then validate actual seal rather than requiring identical float encoding.
    actual_cp=result['proposed_checkpoint'];expected_cp=expected['proposed_checkpoint'];cp_expected_sha=expected_cp.pop('state_sha256')
    f.keys(actual_cp,(*expected_cp,'state_sha256'));f.compare({k:v for k,v in actual_cp.items() if k!='state_sha256'},expected_cp,errors)
    require(actual_cp['state_sha256']==f.digest({k:v for k,v in actual_cp.items() if k!='state_sha256'}),'NEXT_STATE_SEAL')
    expected['proposed_checkpoint']=actual_cp
    f.compare({k:v for k,v in result.items() if k!='navigation_sha256'},expected,errors)
    return {'verified':True,'trajectory':path,'selected_ids':selected,'edge_count':len(traversed),'admitted_count':len(admitted),'maximum_numeric_error':max(errors,default=0.),'scope':'Independent candidate path/weights/CP consistency; HOST input/prior and completed native proof are separate trust premises'}
