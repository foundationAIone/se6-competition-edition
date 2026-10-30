"""Candidate field-guided inspection of actual typed Flower relationships.

Metric overlay is new; mapped dependency directions remain unchanged. Reverse
arcs mean inspection of the same relation, not permission to reverse causality.
"""
import json,math,re
from copy import deepcopy
from toroidal_field_realization import digest,field_at,validate_result,U,V,AXIS
ENV='se6-candidate-fol-environment-v1';SCHEMA='se6-candidate-field-navigation-v1'

def hex_centers():
 centers=[(q,r) for q in range(-2,3) for r in range(-2,3) if max(abs(q),abs(r),abs(q+r))<=2]
 centers.sort(key=lambda qr:(max(abs(qr[0]),abs(qr[1]),abs(sum(qr))),math.atan2(math.sqrt(3)*qr[1]/2,qr[0]+qr[1]/2)%(2*math.pi)))
 return [{'index':i,'axial':[q,r],'position':[q+r/2,math.sqrt(3)*r/2],'radius':1.} for i,(q,r) in enumerate(centers)]
def point(center):return [center[0]*a+center[1]*b for a,b in zip(U,V)]
def norm(v):return math.sqrt(sum(x*x for x in v))
def unit(v):return [x/max(norm(v),1e-15) for x in v]
def hashstr(v):return isinstance(v,str) and re.fullmatch('[0-9a-f]{64}',v) is not None

def environment(plan_mapping,plan,admitted_ids):
 if not isinstance(plan,dict) or not isinstance(plan.get('nodes'),list) or not 1<=len(plan['nodes'])<=12:raise ValueError('PLAN_BOUND')
 nodes=plan['nodes'];ids=[n.get('id') for n in nodes]
 if any(not isinstance(i,str) or not 1<=len(i)<=64 or i=='source' for i in ids) or len(set(ids))!=len(ids):raise ValueError('PLAN_IDENTITY')
 if not isinstance(admitted_ids,list) or len(set(admitted_ids))!=len(admitted_ids) or any(i not in ids for i in admitted_ids):raise ValueError('ADMISSION_BINDING')
 if not isinstance(plan_mapping,dict) or len(json.dumps(plan_mapping).encode())>262144:raise ValueError('MAPPING_BOUND')
 model=plan_mapping['model'];bindings=plan_mapping['node_bindings']
 if [b['id'] for b in bindings]!=ids:raise ValueError('MAPPING_PLAN_IDENTITY')
 vertices=model['vertices'];source_nodes=[v for v in vertices if v['kind']=='REALITY_OBJECT']
 if len(source_nodes)!=1 or len(vertices)!=len(nodes)+1:raise ValueError('MAPPING_SOURCE')
 source=source_nodes[0];actualids={v['node_id']:v for v in vertices};aliases={source['node_id']:'source'}
 circles=hex_centers();mapped=[{'id':'source','mapped_node_id':source['node_id'],'position':point(circles[0]['position']),'admitted':True,'circle_index':0}]
 for i,(n,b) in enumerate(zip(nodes,bindings),1):
  import hashlib
  if b['node_id'] not in actualids or b['route']!=n['route'] or b['input_sha256']!=hashlib.sha256((n.get('input') or ('Typed route '+n['route'])).encode()).hexdigest():raise ValueError('MAPPING_PLAN_INPUT')
  if n['id'] in admitted_ids and (not n['connected'] or n['route'] not in {'RELATIONAL','LINEAR_MATH','LINEAR_DERIVATION','HOST_BUSINESS','HOST_BUDGET'} or any(d not in admitted_ids for d in n.get('depends_on',[]))):raise ValueError('ADMITTED_BOUNDARY')
  aliases[b['node_id']]=n['id'];mapped.append({'id':n['id'],'mapped_node_id':b['node_id'],'position':point(circles[i]['position']),'admitted':n['id'] in admitted_ids,'circle_index':i})
 arcs=[];dep_pairs=set();relates_targets=set();relationids=set()
 for relation in model['relations']:
  kind=relation['kind']
  if kind not in ('RELATES_TO','DEPENDS_ON') or relation['relation_id'] in relationids:raise ValueError('UNSUPPORTED_OR_DUPLICATE_RELATION')
  relationids.add(relation['relation_id'])
  for a in relation['source_nodes']:
   for b in relation['target_nodes']:
    if a['node_id'] not in aliases or b['node_id'] not in aliases:raise ValueError('DANGLING_RELATION')
    x,y=aliases[a['node_id']],aliases[b['node_id']]
    if kind=='DEPENDS_ON':
     if (x,y) in dep_pairs:raise ValueError('DUPLICATE_DEPENDENCY')
     dep_pairs.add((x,y))
    if kind=='RELATES_TO':
     if x!='source' or y in relates_targets:raise ValueError('SOURCE_RELATION')
     relates_targets.add(y)
    for start,end,direction in ((x,y,'FORWARD'),(y,x,'REVERSE_INSPECTION')):
     arcs.append({'from':start,'to':end,'kind':kind,'direction':direction,'relation_id':relation['relation_id'],
       'original_source_node_id':a['node_id'],'original_target_node_id':b['node_id'],'scope':'RELATION_AUDIT; dependency causality/eligibility unchanged'})
 if dep_pairs!={(n['id'],d) for n in nodes for d in n.get('depends_on',[])} or relates_targets!=set(ids):raise ValueError('RELATION_PLAN_BINDING')
 material={'schema':ENV,'source_id':'source','vertices':mapped,'arcs':arcs,'admitted_ids':deepcopy(admitted_ids),
  'circles':circles,'model_sha256':digest(model),'plan_sha256':digest(plan),'flower_lineage':deepcopy(model['flower_lineage']),
  'sample_points':[{'id':r['id'],'position':r['position']} for r in mapped if r['id']!='source'],
  'scope':'Actual typed mapping edges/provenance with separate candidate19-circle metric overlay; not canonical geometric Flower or evidence authority'}
 return {**material,'environment_sha256':digest(material)}

def navigate(env,state,field,U,mode='field'):
 if env.get('schema')!=ENV or digest({k:v for k,v in env.items() if k!='environment_sha256'})!=env['environment_sha256']:raise ValueError('ENVIRONMENT_SEAL')
 validate_result(field)
 if mode not in ('field','ordinary'):raise ValueError('NAVIGATION_MODE')
 if not isinstance(U,dict) or set(U)!={'goal_ids','budget','audit_budget'} or not isinstance(U['goal_ids'],list) or len(set(U['goal_ids']))!=len(U['goal_ids']) or any(i not in env['admitted_ids'] for i in U['goal_ids']):raise ValueError('GOAL_ADMISSION')
 if type(U['budget']) is not int or not 0<=U['budget']<=4 or type(U['audit_budget']) is not int or not 0<=U['audit_budget']<=1:raise ValueError('NAVIGATION_BUDGET')
 if field['inputs']['sample_points']!=env['sample_points']:raise ValueError('FIELD_ENVIRONMENT_SAMPLING')
 if [s['id'] for s in field['inputs']['mapped_sources']]!=[r['id'] for r in env['sample_points']]:raise ValueError('FIELD_SOURCE_IDS')
 vertices={r['id']:r for r in env['vertices']};position='source';step=0;rebase=None;orientation=[0.,0.,0.]
 if state is not None:
  if not isinstance(state,dict) or len(json.dumps(state,allow_nan=False).encode())>65536 or set(state)!={'schema','step','environment_sha256','position','mapped_node_id','orientation','field_numeric_sha256','last_trajectory','previous_state_sha256','state_sha256'} or state['schema']!=SCHEMA or digest({k:v for k,v in state.items() if k!='state_sha256'})!=state['state_sha256']:raise ValueError('NAVIGATION_STATE_SEAL')
  if type(state['step']) is not int or not 0<=state['step']<1024 or not hashstr(state['environment_sha256']) or not hashstr(state['field_numeric_sha256']) or (state['previous_state_sha256'] is not None and not hashstr(state['previous_state_sha256'])):raise ValueError('STATE_BOUND')
  if not isinstance(state['orientation'],list) or len(state['orientation'])!=3 or any(type(x) not in (float,int) or not math.isfinite(x) for x in state['orientation']) or norm(state['orientation'])>1+1e-12:raise ValueError('STATE_ORIENTATION')
  if not isinstance(state['last_trajectory'],list) or len(state['last_trajectory'])>5:raise ValueError('STATE_HISTORY_BOUND')
  step=state['step']
  if state['position'] in vertices and vertices[state['position']]['mapped_node_id']==state['mapped_node_id'] and vertices[state['position']]['admitted']:
   position=state['position'];orientation=deepcopy(state['orientation'])
  else:rebase={'reason':'ACTUAL_MAPPED_IDENTITY_CHANGED_RESET_TO_SOURCE','prior_environment_sha256':state['environment_sha256'],'prior_position':state['position'],'scope':'Candidate location rebase; native memory/Entity identity unchanged'}
  if state['environment_sha256']==env['environment_sha256'] and rebase is not None:raise ValueError('STATE_CURRENT_BINDING')
 samples={r['id']:r for r in field['numeric']['samples']};coeff=field['numeric']['coefficients'];p=field['numeric']['parameters']
 sourcefield=field_at(vertices['source']['position'],coeff['ct'],coeff['cp'],p);samples['source']={'field':sourcefield['field'],'energy':sourcefield['energy']}
 if any(any(type(x) not in (float,int) or not math.isfinite(x) for x in s['field']) or type(s['energy']) not in (float,int) or not math.isfinite(s['energy']) for s in samples.values()):raise ValueError('NONFINITE_FIELD')
 zero=max((s['energy'] for s in samples.values()),default=0)<=1e-24
 trajectory=[position];edges=[];choices=[];visited={position};reason='BUDGET_COMPLETED'
 if mode=='field' and zero:reason='ZERO_FIELD_IDENTITY'
 elif not U['goal_ids']:reason='NO_ADMITTED_GOALS_IDENTITY'
 else:
  for _ in range(U['budget']):
   options=[]
   for arc in env['arcs']:
    target=arc['to']
    if arc['from']!=position or target in visited or not vertices[target]['admitted']:continue
    delta=[b-a for a,b in zip(vertices[position]['position'],vertices[target]['position'])]
    if norm(delta)<1e-12:raise ValueError('DEGENERATE_METRIC_EDGE')
    phi=[.5*(a+b) for a,b in zip(samples[position]['field'],samples[target]['field'])]
    alignment=sum(a*b for a,b in zip(unit(phi),unit(delta)))
    energy=samples[target]['energy'];potential=energy/(1+energy)
    rawscore=.75*alignment+.25*potential
    score=round(rawscore,12) if mode=='field' else 0.
    options.append({'target':target,'alignment':alignment,'energy_potential':potential,'field_score':rawscore,'effective_score':score,'arc':deepcopy(arc)})
   # Distinct mapped relations can connect same nodes: stable relation-id tie.
   options.sort(key=lambda row:(-row['effective_score'],row['target'],row['arc']['relation_id'],row['arc']['direction']))
   choices.append({'from':position,'reachable_choices':options})
   if not options:reason='NO_UNVISITED_ADMITTED_NEIGHBOR';break
   chosen=options[0];edges.append(chosen['arc']);orientation=unit([b-a for a,b in zip(vertices[position]['position'],vertices[chosen['target']]['position'])]);position=chosen['target'];visited.add(position);trajectory.append(position)
 selected=[i for i in reversed(trajectory[1:]) if i in U['goal_ids']][:U['audit_budget']]
 cp={'schema':SCHEMA,'step':step+1,'environment_sha256':env['environment_sha256'],'position':position,'mapped_node_id':vertices[position]['mapped_node_id'],'orientation':orientation,'field_numeric_sha256':field['numeric_sha256'],'last_trajectory':trajectory,'previous_state_sha256':state['state_sha256'] if state else None};cp['state_sha256']=digest(cp)
 material={'schema':SCHEMA,'status':'CANDIDATE_TRAJECTORY' if edges else 'JUSTIFIED_IDENTITY','mode':mode,'environment_sha256':env['environment_sha256'],'field_numeric_sha256':field['numeric_sha256'],'start':trajectory[0],
  'navigation_step':step,'prior_state_sha256':state['state_sha256'] if state else None,'start_mapped_node_id':vertices[trajectory[0]]['mapped_node_id'],'trajectory':trajectory,'trajectory_mapped_node_ids':[vertices[i]['mapped_node_id'] for i in trajectory],
  'traversed_relationships':edges,'choices':choices,'selected_ids':selected,'U':deepcopy(U),'rotations':{'time':field['numeric']['time'],'rates':p['rates'],'directions':p['directions'],'phases':p['phases'],'polarities':p['polarities']},
  'reason':reason,'state_rebase':rebase,'proposed_checkpoint':cp,'authority':'NONE; all paths are HOST candidate inspections until native proof and typed recenter are verified','scope':'Directional field+energy edge policy over actualrelationships, ordinary arm computes same weights butneutralizes influence; reverse arcs are inspections, not reversed dependencycausality'}
 return {**material,'navigation_sha256':digest(material)}

def finish_navigation(env,result,verified_ids):
 if digest({k:v for k,v in result.items() if k!='navigation_sha256'})!=result.get('navigation_sha256') or env['environment_sha256']!=result['environment_sha256']:raise ValueError('NAVIGATION_RESULT_SEAL')
 if not isinstance(verified_ids,list) or len(set(verified_ids))!=len(verified_ids) or any(i not in env['admitted_ids'] for i in verified_ids):raise ValueError('VERIFIED_ID_BOUNDARY')
 vertices={v['id']:v for v in env['vertices']};path=result['trajectory'];arcs=result['traversed_relationships']
 if not path or len(path)>5 or len(set(path))!=len(path) or len(arcs)!=len(path)-1 or any(i not in vertices for i in path):raise ValueError('ACTUAL_PATH_BOUND')
 for i,arc in enumerate(arcs):
  if arc not in env['arcs'] or arc['from']!=path[i] or arc['to']!=path[i+1]:raise ValueError('ACTUAL_EDGE_BINDING')
 if any(i!='source' and i not in verified_ids for i in path):raise ValueError('ACTUAL_NODE_NOT_VERIFIED')
 if result['trajectory_mapped_node_ids']!=[vertices[i]['mapped_node_id'] for i in path] or result['start']!=path[0] or result['start_mapped_node_id']!=vertices[path[0]]['mapped_node_id']:raise ValueError('ACTUAL_MAPPED_PATH')
 if result['selected_ids']!=[i for i in reversed(path[1:]) if i in result['U']['goal_ids']][:result['U']['audit_budget']]:raise ValueError('ACTUAL_GOAL_SELECTION')
 cp=deepcopy(result['proposed_checkpoint'])
 if cp['state_sha256']!=digest({k:v for k,v in cp.items() if k!='state_sha256'}) or cp['position']!=path[-1] or cp['mapped_node_id']!=vertices[path[-1]]['mapped_node_id'] or cp['last_trajectory']!=path:raise ValueError('ACTUAL_CENTER_BINDING')
 if cp['step']!=result['navigation_step']+1 or cp['environment_sha256']!=env['environment_sha256'] or cp['field_numeric_sha256']!=result['field_numeric_sha256'] or cp['previous_state_sha256']!=result['prior_state_sha256']:raise ValueError('ACTUAL_STATE_BINDING')
 if arcs:
  expected=unit([b-a for a,b in zip(vertices[path[-2]]['position'],vertices[path[-1]]['position'])])
  if cp['orientation']!=expected:raise ValueError('ACTUAL_ORIENTATION')
 return {'status':'HOST_VERIFIED_NAVIGATION' if arcs else 'VERIFIED_IDENTITY','checkpoint':cp,'relationships':deepcopy(arcs),'selected_ids':result['selected_ids'],
  'scope':'Actual verified native completed IDs and exact mappededge bindings; typed Flower recenter performed/validated separately byHOST; no new native fact or physicalmotion inferred'}
