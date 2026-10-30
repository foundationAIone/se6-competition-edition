"""Explicit CANDIDATE 3D source-coupled toroidal field, not canonical/physical law.

Quasi-static point-source diagnostics and a separate constitutive solenoidal
computational field are deliberately distinct. Geometry alone implies no torus.
"""
import hashlib,itertools,json,math,re
from copy import deepcopy
SCHEMA='se6-candidate-toroidal-field-v1'
OMEGA_MAX=4.
AXIS=(1/math.sqrt(3),)*3
U=(1/math.sqrt(2),-1/math.sqrt(2),0.)
V=(1/math.sqrt(6),1/math.sqrt(6),-2/math.sqrt(6))
DEFAULT={'geometry_radius':1.,'major_radius':1.,'width_r':.75,'width_z':.75,
 'rates':[1.,1.],'directions':[1,-1],'phases':[0.,0.],'source_gains':[1.,1.],
 'polarities':[1,-1],'toroidal_gain':1.,'poloidal_gain':1.,'softening':.15,
 'dt':.1,'decay':.9,'gain':.1,'feedback_gain':.05,'line_steps':128,'line_step':.05}

def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def finite(v,lo,hi):
 if type(v) not in (float,int) or not math.isfinite(v) or not lo<=v<=hi:raise ValueError('FINITE_BOUND')
 return float(v)
def vec(v,bound=4):
 if not isinstance(v,(list,tuple)) or len(v)!=3:raise ValueError('VECTOR_SHAPE')
 out=[finite(x,-bound,bound) for x in v]
 if math.sqrt(sum(x*x for x in out))>bound+1e-12:raise ValueError('VECTOR_NORM')
 return out
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
def norm(v):return math.sqrt(dot(v,v))
def add(a,b):return [x+y for x,y in zip(a,b)]
def mul(s,v):return [s*x for x in v]
def rotate(v,angle):
 c=math.cos(angle);s=math.sin(angle)
 return add(add(mul(c,v),mul(s,cross(AXIS,v))),mul((1-c)*dot(AXIS,v),AXIS))
def parameters(value=None):
 p=deepcopy(DEFAULT if value is None else value)
 if not isinstance(p,dict) or set(p)!=set(DEFAULT):raise ValueError('PARAMETER_FIELDS')
 for name in ('rates','directions','phases','source_gains','polarities'):
  if not isinstance(p[name],list) or len(p[name])!=2:raise ValueError('FRAME_PAIR')
 for name in ('directions','polarities'):
  if any(type(x) is not int or x not in (-1,0,1) for x in p[name]):raise ValueError('SIGNED_SOURCE_FRAME')
 p['rates']=[finite(x,0,OMEGA_MAX) for x in p['rates']];p['phases']=[finite(x,-math.pi,math.pi) for x in p['phases']]
 p['source_gains']=[finite(x,0,1) for x in p['source_gains']]
 for k in ('geometry_radius','major_radius'):p[k]=finite(p[k],.25,2)
 for k in ('width_r','width_z'):p[k]=finite(p[k],.25,1.5)
 p['softening']=finite(p['softening'],.1,1)
 for k in ('toroidal_gain','poloidal_gain','dt','decay','gain','feedback_gain'):p[k]=finite(p[k],0,1)
 if type(p['line_steps']) is not int or not 8<=p['line_steps']<=128:raise ValueError('LINE_BUDGET')
 p['line_step']=finite(p['line_step'],.005,.1)
 return p

def geometry(radius=1):
 radius=finite(radius,.25,2);vertices=[mul(radius/math.sqrt(3),v) for v in itertools.product((-1,1),repeat=3)]
 groups=[[i for i,v in enumerate(itertools.product((-1,1),repeat=3)) if math.prod(v)==sign] for sign in (1,-1)]
 return {'axis':list(AXIS),'basis_u':list(U),'basis_v':list(V),'stationary_vertices':vertices,'tetrahedra':groups,
  'edges':[list(edge) for g in groups for edge in itertools.combinations(g,2)],
  'faces':[list(face) for g in groups for face in itertools.combinations(g,3)],
  'projection':[{'vertex':i,'point':[dot(v,U),dot(v,V)],'axis_position':dot(v,AXIS)} for i,v in enumerate(vertices)],
  'scope':'Centered parity tetrahedra; eight vertices, six outer projected points and two projected center vertices; candidate polarity separate'}

def sources_from_plan(plan,actual_mapping=None):
 if not isinstance(plan,dict) or not isinstance(plan.get('nodes'),list) or not 1<=len(plan['nodes'])<=12:raise ValueError('PLAN_BOUND')
 nodes=plan['nodes'];seen=set();depth={};out={};sources=[];points=[];bindings=[]
 for n in nodes:
  if not isinstance(n,dict) or not isinstance(n.get('id'),str) or not 1<=len(n['id'])<=64 or n['id'] in seen:raise ValueError('PLAN_IDENTITY')
  deps=n.get('depends_on',[])
  if not isinstance(deps,list) or any(not isinstance(d,str) or d not in seen for d in deps) or len(set(deps))!=len(deps):raise ValueError('PLAN_DEPENDENCIES')
  if type(n.get('connected')) is not bool or not isinstance(n.get('input',''),str) or len(n.get('input','').encode())>4096:raise ValueError('PLAN_FEATURES')
  depth[n['id']]=max((depth[d]+1 for d in deps),default=0);out[n['id']]=0
  for d in deps:out[d]+=1
  seen.add(n['id'])
 mapping={}
 if actual_mapping is not None:
  rows=actual_mapping.get('node_bindings',[])
  if len(rows)!=len(nodes) or [b.get('id') for b in rows]!=[n['id'] for n in nodes]:raise ValueError('MAPPING_BINDING')
  for b,n in zip(rows,nodes):
   text=n.get('input') or ('Typed route '+n['route'])
   if b.get('route')!=n['route'] or b.get('input_sha256')!=hashlib.sha256(text.encode()).hexdigest():raise ValueError('MAPPING_INPUT')
   mapping[n['id']]=b['node_id']
 for i,n in enumerate(nodes):
  extent=len(n.get('input','').encode())/4096;degree=out[n['id']]-len(n.get('depends_on',[]))
  amplitude=min(1,.25+.5*int(n['connected'])+.25*extent)
  r=.5+depth[n['id']]/(max(depth.values())+1);phi=2*math.pi*i/len(nodes);z=.375*degree/max(1,len(nodes)-1)
  position=add(add(mul(r*math.cos(phi),U),mul(r*math.sin(phi),V)),mul(z,AXIS))
  sources.append({'id':n['id'],'amplitude':amplitude});points.append({'id':n['id'],'position':position})
  bindings.append({'id':n['id'],'mapped_node_id':mapping.get(n['id']),'depth':depth[n['id']],'degree':degree,'input_extent':extent})
 return {'sources':sources,'sample_points':points,'bindings':bindings,'input_sha256':digest({'plan':plan,'actual_mapping':actual_mapping}),
  'scope':'Candidate relational amplitude/sampling embedding; full typed mapping validity remains preflight HOST obligation, no physical positions inferred'}

def field_at(position,ct,cp,p=None):
 p=parameters(p);position=vec(position);ct=finite(ct,-1,1);cp=finite(cp,-1,1)
 x=dot(position,U);y=dot(position,V);z=dot(position,AXIS);r2=x*x+y*y;r=math.sqrt(r2)
 exponent=-((r2-p['major_radius']**2)**2/p['width_r']**4)-z*z/p['width_z']**2
 g=math.exp(exponent);radial_factor=2*cp*z/p['width_z']**2*g
 bz=2*cp*g*(1-2*r2*(r2-p['major_radius']**2)/p['width_r']**4)
 tor=add(mul(-ct*y*g,U),mul(ct*x*g,V));pol=add(add(mul(radial_factor*x,U),mul(radial_factor*y,V)),mul(bz,AXIS))
 return {'field':add(tor,pol),'toroidal':tor,'poloidal':pol,'cylindrical':[radial_factor*r,ct*r*g,bz],'flux':cp*r2*g,'profile':g,'energy':dot(add(tor,pol),add(tor,pol))}

def point_diagnostic(position,sources,softening=.15):
 position=vec(position);epsilon=finite(softening,.1,1);e=[0.,0.,0.];b=[0.,0.,0.]
 if not isinstance(sources,list) or len(sources)!=8:raise ValueError('EIGHT_VERTEX_SOURCES')
 for source in sources:
  if not isinstance(source,dict):raise ValueError('DIAGNOSTIC_SOURCE')
  pos=vec(source['position'],2);velocity=vec(source['velocity'],8);charge=finite(source['charge'],-.25,.25)
  d=[x-y for x,y in zip(position,pos)];den=(dot(d,d)+epsilon*epsilon)**1.5
  e=add(e,mul(charge/den,d));b=add(b,mul(charge/den,cross(velocity,d)))
 return {'E':e,'B':b,'scope':'Dimensionless regularized quasi-static Coulomb/Biot-Savart diagnostic, not complete Maxwell/radiative solution; no automatic toroidal consequence'}

def line(position,ct,cp,p):
 points=[list(position)];initial=field_at(position,ct,cp,p)['flux'];drift=0.;escaped=False
 if ct==0 and cp==0:return {'points':points,'flux_initial':0.,'maximum_flux_drift':0.,'return_distance':0.,'domain_exit':False,'closure':'NO_STREAMLINE_ZERO_FIELD','status':'ZERO_FIELD_STATIONARY','scope':'No nonzero tangent field; no circulation inferred'}
 def direction(x):
  f=field_at(x,ct,cp,p)['field'];size=norm(f)
  return mul(1/max(size,1e-15),f)
 for _ in range(p['line_steps']):
  x=points[-1];h=p['line_step'];k1=direction(x);k2=direction(add(x,mul(h/2,k1)));k3=direction(add(x,mul(h/2,k2)));k4=direction(add(x,mul(h,k3)))
  nextpoint=add(x,mul(h/6,add(add(k1,mul(2,k2)),add(mul(2,k3),k4))))
  if norm(nextpoint)>3.8:escaped=True;break
  points.append(nextpoint);drift=max(drift,abs(field_at(nextpoint,ct,cp,p)['flux']-initial))
 return {'points':points,'flux_initial':initial,'maximum_flux_drift':drift,'return_distance':norm([a-b for a,b in zip(points[0],points[-1])]),'domain_exit':escaped,
  'closure':'NOT_ASSERTED_FROM_FINITE_PATH','scope':'RK4 normalized frozen vector field; small return distance is not exact topology proof'}

def realize_toroidal(mapped_sources,prior_state=None,parameters=None,sample_points=None,enabled=True):
 p=globals()['parameters'](parameters)
 if type(enabled) is not bool or not isinstance(mapped_sources,list) or not 1<=len(mapped_sources)<=12:raise ValueError('SOURCE_BOUND')
 ids=[];seeds=[]
 for s in mapped_sources:
  if not isinstance(s,dict) or len(json.dumps(s,allow_nan=False).encode())>65536 or set(s)!={'id','amplitude'} or not isinstance(s['id'],str) or not 1<=len(s['id'])<=64 or s['id'] in ids:raise ValueError('SOURCE_IDENTITY')
  ids.append(s['id']);seeds.append(finite(s['amplitude'],0,1))
 points=deepcopy(sample_points if sample_points is not None else [{'id':i,'position':mul(.75,U)} for i in ids])
 if not isinstance(points,list) or len(points)!=len(ids) or [x.get('id') for x in points]!=ids:raise ValueError('SAMPLE_BINDING')
 for row in points:
  if set(row)!={'id','position'}:raise ValueError('SAMPLE_FIELDS')
  row['position']=vec(row['position'])
 inputsha=digest(mapped_sources);step=0;amps=seeds[:];rebase=None
 if prior_state is not None:
  s=prior_state
  if not isinstance(s,dict) or len(json.dumps(s,allow_nan=False).encode())>65536 or set(s)!={'schema','step','parameters','parameters_sha256','input_sha256','ids','amplitudes','previous_numeric_sha256','feedback','state_sha256'} or s['schema']!=SCHEMA or digest({k:v for k,v in s.items() if k!='state_sha256'})!=s['state_sha256']:raise ValueError('STATE_SEAL')
  if type(s['step']) is not int or not 0<=s['step']<1024 or s['parameters_sha256']!=digest(globals()['parameters'](s['parameters'])):raise ValueError('STATE_PARAMETER')
  if any(not isinstance(s[k],str) or re.fullmatch('[0-9a-f]{64}',s[k]) is None for k in ('parameters_sha256','input_sha256','previous_numeric_sha256','state_sha256')):raise ValueError('STATE_HASH_FORMAT')
  if not isinstance(s['ids'],list) or any(not isinstance(i,str) or not 1<=len(i)<=64 for i in s['ids']) or not 1<=len(s['ids'])<=12 or len(set(s['ids']))!=len(s['ids']) or len(s['amplitudes'])!=len(s['ids']):raise ValueError('STATE_IDENTITY')
  old=dict(zip(s['ids'],[finite(a,0,1) for a in s['amplitudes']]))
  step=s['step'];changed=s['input_sha256']!=inputsha
  amps=[.5*old[i]+.5*a if changed and i in old else old.get(i,a) for i,a in zip(ids,seeds)]
  rebase={'retained_ids':[i for i in ids if i in old],'added_ids':[i for i in ids if i not in old],'removed_ids':[i for i in old if i not in ids],'input_changed':changed,'parameter_changed':s['parameters_sha256']!=digest(p)}
 t=step*p['dt'];g=geometry(p['geometry_radius']);average=sum(amps)/len(amps);sources=[];groups=[];moments=[]
 for k,vertices in enumerate(g['tetrahedra']):
  omega=p['rates'][k]*p['directions'][k];angle=math.remainder(omega*t+p['phases'][k],2*math.pi);group=[]
  for index in vertices:
   pos=rotate(g['stationary_vertices'][index],angle);velocity=mul(omega,cross(AXIS,pos));q=p['polarities'][k]*p['source_gains'][k]*average/4
   source={'vertex':index,'group':k,'position':pos,'velocity':velocity,'charge':q,'angle':angle};sources.append(source);group.append(source)
  groups.append(group);moments.append(sum(s['charge']*dot(cross(s['position'],s['velocity']),AXIS) for s in group)/(OMEGA_MAX*p['geometry_radius']**2))
 overlap=sum(1/(1+sum((a-b)**2 for a,b in zip(s['position'],u['position']))) for s in groups[0] for u in groups[1])/16
 relative=(p['rates'][0]*p['directions'][0]-p['rates'][1]*p['directions'][1])/(2*OMEGA_MAX)
 ct=.5*(moments[0]+moments[1])*p['toroidal_gain'];cp=overlap*moments[0]*moments[1]*relative*p['poloidal_gain']
 samples=[]
 for row in points:
  field=field_at(row['position'],ct,cp,p);diag=point_diagnostic(row['position'],sources,p['softening'])
  samples.append({'id':row['id'],'position':row['position'],**field,'diagnostic_E':diag['E'],'diagnostic_B':diag['B']})
 circle=[mul(p['major_radius'],add(mul(math.cos((1 if ct>=0 else -1)*2*math.pi*i/p['line_steps']),U),mul(math.sin((1 if ct>=0 else -1)*2*math.pi*i/p['line_steps']),V))) for i in range(p['line_steps']+1)]
 seed=mul(p['major_radius']*.8,U)
 lines={'toroidal':{'points':circle if ct else [seed],'closure':'EXACT_CIRCLE' if ct else 'NO_CIRCULATION_ZERO_CT','coefficient':ct,'scope':'Toroidal component control; mixed full field follows separately'},
  'poloidal':line(seed,0,cp,p),'mixed':line(seed,ct,cp,p)}
 numeric={'step':step,'time':t,'parameters':p,'source_amplitudes':amps,'geometry':g,'moving_sources':sources,
  'coefficients':{'ct':ct,'cp':cp,'moments':moments,'pair_kernel':overlap,'relative_signed_rate':relative,'average_amplitude':average,'stationary_coefficients_zero':all(p['rates'][k]*p['directions'][k]==0 for k in (0,1))},'samples':samples,'lines':lines,'state_rebase':rebase}
 numericsha=digest(numeric);state={'schema':SCHEMA,'step':step+1,'parameters':p,'parameters_sha256':digest(p),'input_sha256':inputsha,'ids':ids,'amplitudes':[min(1,max(0,p['decay']*a+p['gain']*seed)) for a,seed in zip(amps,seeds)],'previous_numeric_sha256':numericsha,'feedback':None};state['state_sha256']=digest(state)
 candidates=[{'id':row['id'],'field_priority':sample['energy'] if enabled else 0.} for row,sample in zip(points,samples)];ranking=sorted(ids,key=lambda ident:(-next(r['field_priority'] for r in candidates if r['id']==ident),ident))
 material={'schema':SCHEMA,'status':'CANDIDATE_COMPUTATIONAL_TOROIDAL','inputs':{'mapped_sources':deepcopy(mapped_sources),'sample_points':points,'prior_state':deepcopy(prior_state)},'input_sha256':inputsha,'numeric':numeric,'numeric_sha256':numericsha,'projection':{'enabled':enabled,'candidates':candidates,'ranking':ranking,'authority':'NONE'},'checkpoint':state,
 'scope':'Explicit 3D constitutive computational field. Point-charge diagnostic is separate, not full Maxwell. Polarity/coupling are candidate assumptions, not canonical/historical law; no cognitive advantage or evidence authority.'}
 return {**material,'result_sha256':digest(material)}

def validate_result(result):
 if not isinstance(result,dict) or result.get('schema')!=SCHEMA or digest({k:v for k,v in result.items() if k!='result_sha256'})!=result.get('result_sha256'):raise ValueError('RESULT_SEAL')
 numeric=result['numeric'];cp=result['checkpoint'];p=parameters(numeric['parameters']);ids=[s['id'] for s in result['inputs']['mapped_sources']]
 if digest(numeric)!=result['numeric_sha256'] or cp['previous_numeric_sha256']!=result['numeric_sha256']:raise ValueError('NUMERIC_SEAL')
 if cp['state_sha256']!=digest({k:v for k,v in cp.items() if k!='state_sha256'}):raise ValueError('CHECKPOINT_SEAL')
 if cp['schema']!=SCHEMA or cp['ids']!=ids or cp['step']!=numeric['step']+1 or cp['parameters']!=p or cp['parameters_sha256']!=digest(p) or cp['input_sha256']!=result['input_sha256'] or result['input_sha256']!=digest(result['inputs']['mapped_sources']):raise ValueError('RESULT_BINDING')
 expected=[min(1,max(0,p['decay']*a+p['gain']*seed['amplitude'])) for a,seed in zip(numeric['source_amplitudes'],result['inputs']['mapped_sources'])]
 if len(expected)!=len(ids) or cp['amplitudes']!=expected or cp['feedback'] is not None:raise ValueError('CHECKPOINT_EVOLUTION')
 return True

def finish_toroidal(result,audits):
 validate_result(result)
 if not isinstance(audits,list) or len(audits)>12:raise ValueError('AUDIT_BOUND')
 state=deepcopy(result['checkpoint']);seen=set()
 for row in audits:
  if not isinstance(row,dict) or set(row)!={'id','passed'} or row['id'] not in state['ids'] or row['id'] in seen or type(row['passed']) is not bool:raise ValueError('AUDIT_BINDING')
  i=state['ids'].index(row['id']);state['amplitudes'][i]=min(1,max(0,state['amplitudes'][i]+result['numeric']['parameters']['feedback_gain']*(1 if row['passed'] else -1)));seen.add(row['id'])
 state['feedback']={'audits':deepcopy(audits),'scope':'HOST-declared selected audit; separate candidate amplitudes, no truth/authority effect'};state['state_sha256']=digest({k:v for k,v in state.items() if k!='state_sha256'})
 return state
