"""Independent stdlib oracle of the explicit candidate contract, not Maxwell physics."""
import math
import hashlib,itertools,json

SCHEMA='se6-candidate-toroidal-field-v1'
DEFAULT={'geometry_radius':1.,'major_radius':1.,'width_r':.75,'width_z':.75,
 'rates':[1.,1.],'directions':[1,-1],'phases':[0.,0.],'source_gains':[1.,1.],
 'polarities':[1,-1],'toroidal_gain':1.,'poloidal_gain':1.,'softening':.15,
 'dt':.1,'decay':.9,'gain':.1,'feedback_gain':.05,'line_steps':128,'line_step':.05}
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def require(ok,label):
    if not ok:raise ValueError(label)
def number(v,lo,hi):
    require(type(v) in (int,float) and math.isfinite(v) and lo<=v<=hi,'NUMBER_BOUND')
    return float(v)
def keys(v,expected):require(isinstance(v,dict) and set(v)==set(expected),'EXACT_FIELDS')
def check_parameters(p):
    keys(p,DEFAULT)
    for k in ('rates','directions','phases','source_gains','polarities'):
        require(isinstance(p[k],list) and len(p[k])==2,'PARAMETER_PAIR')
    for k in ('directions','polarities'):require(all(type(v) is int and v in (-1,0,1) for v in p[k]),'SIGNED_PARAMETER')
    for k in ('rates',):
        for v in p[k]:number(v,0,4)
    for v in p['phases']:number(v,-math.pi,math.pi)
    for v in p['source_gains']:number(v,0,1)
    for k in ('geometry_radius','major_radius'):number(p[k],.25,2)
    for k in ('width_r','width_z'):number(p[k],.25,1.5)
    number(p['softening'],.1,1)
    for k in ('dt','decay','gain','feedback_gain','toroidal_gain','poloidal_gain'):number(p[k],0,1)
    require(type(p['line_steps']) is int and 8<=p['line_steps']<=128,'LINE_STEPS')
    number(p['line_step'],.005,.1)
    return p
def compare(actual,expected,errors):
    if isinstance(expected,dict):
        keys(actual,expected)
        for k in expected:compare(actual[k],expected[k],errors)
    elif isinstance(expected,(list,tuple)):
        require(isinstance(actual,(list,tuple)) and len(actual)==len(expected),'LIST_SHAPE')
        for a,b in zip(actual,expected):compare(a,b,errors)
    elif type(expected) is float:
        require(type(actual) in (float,int) and math.isfinite(actual),'FINITE_OBSERVATION')
        error=abs(actual-expected);errors.append(error)
        require(error<=2e-10*(1+abs(expected)),'NUMERICAL_MISMATCH')
    else:require(type(actual) is type(expected) and actual==expected,'IDENTITY_MISMATCH')

AXIS=tuple(1/math.sqrt(3) for _ in range(3))
U=(1/math.sqrt(2),-1/math.sqrt(2),0.)
V=(1/math.sqrt(6),1/math.sqrt(6),-2/math.sqrt(6))

def dot(a,b): return sum(x*y for x,y in zip(a,b))
def cross(a,b): return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def rotate(x,angle):
    c,s=math.cos(angle),math.sin(angle); ax=cross(AXIS,x); z=dot(AXIS,x)
    return [c*x[i]+s*ax[i]+(1-c)*z*AXIS[i] for i in range(3)]
def tetrahedra(radius=1.):
    # Enumerate cube vertices by sign parity, independently of candidate ordering.
    groups=[[],[]]
    for x in (-1,1):
        for y in (-1,1):
            for z in (-1,1):groups[0 if x*y*z>0 else 1].append([radius*t/math.sqrt(3) for t in (x,y,z)])
    return groups
def field(position,ct,cp,p):
    x,y,z=dot(position,U),dot(position,V),dot(position,AXIS); r2=x*x+y*y
    d=r2-p['major_radius']**2
    g=math.exp(-d*d/p['width_r']**4-z*z/p['width_z']**2)
    # Cartesian expression avoids coordinate singularity or candidate formulas.
    a=2*cp*z*g/p['width_z']**2
    bz=2*cp*g*(1-2*r2*d/p['width_r']**4)
    bx=a*x-ct*g*y; by=a*y+ct*g*x
    return [bx*U[i]+by*V[i]+bz*AXIS[i] for i in range(3)]
def flux(position,cp,p):
    z=dot(position,AXIS); r2=dot(position,U)**2+dot(position,V)**2
    return cp*r2*math.exp(-(r2-p['major_radius']**2)**2/p['width_r']**4-z*z/p['width_z']**2)
def divergence(position,ct,cp,p,h=1e-5):
    out=0.
    for j in range(3):
        a=list(position);b=list(position);a[j]+=h;b[j]-=h
        out+=(field(a,ct,cp,p)[j]-field(b,ct,cp,p)[j])/(2*h)
    return out
def flux_tangent(position,ct,cp,p,h=1e-5):
    grad=[]
    for j in range(3):
        a=list(position);b=list(position);a[j]+=h;b[j]-=h
        grad.append((flux(a,cp,p)-flux(b,cp,p))/(2*h))
    return dot(grad,field(position,ct,cp,p))

def vector(v):
    require(isinstance(v,list) and len(v)==3,'VECTOR_SHAPE')
    for x in v:number(x,-4,4)
    require(math.sqrt(dot(v,v))<=4+1e-12,'VECTOR_NORM')
    return v
def combine(*vectors):return [sum(v[i] for v in vectors) for i in range(3)]
def scale(v,s):return [x*s for x in v]
def norm(v):return math.sqrt(dot(v,v))
def field_record(x,ct,cp,p):
    out=field(x,ct,cp,p); tor=field(x,ct,0.,p);pol=field(x,0.,cp,p)
    a,b,z=dot(x,U),dot(x,V),dot(x,AXIS);r=math.hypot(a,b)
    g=math.exp(-(r*r-p['major_radius']**2)**2/p['width_r']**4-z*z/p['width_z']**2)
    br=2*cp*r*z*g/p['width_z']**2
    bz=2*cp*g*(1-2*r*r*(r*r-p['major_radius']**2)/p['width_r']**4)
    return {'field':out,'toroidal':tor,'poloidal':pol,'cylindrical':[br,ct*r*g,bz],'flux':flux(x,cp,p),'profile':g,'energy':dot(out,out)}
def diagnostic(x,sources,epsilon):
    e=[0.,0.,0.];b=[0.,0.,0.]
    for s in sources:
        displacement=[a-b for a,b in zip(x,s['position'])]
        weight=s['charge']/(dot(displacement,displacement)+epsilon*epsilon)**1.5
        e=combine(e,scale(displacement,weight));b=combine(b,scale(cross(s['velocity'],displacement),weight))
    return e,b
def trajectory(seed,ct,cp,p):
    points=[list(seed)];initial=flux(seed,cp,p);drift=0.;escaped=False
    if ct==0 and cp==0:return {'points':points,'flux_initial':0.,'maximum_flux_drift':0.,'return_distance':0.,'domain_exit':False,'closure':'NO_STREAMLINE_ZERO_FIELD','status':'ZERO_FIELD_STATIONARY','scope':'No nonzero tangent field; no circulation inferred'}
    def direction(x):
        b=field(x,ct,cp,p);return scale(b,1/max(norm(b),1e-15))
    for _ in range(p['line_steps']):
        x=points[-1];h=p['line_step'];a=direction(x);b=direction(combine(x,scale(a,h/2)));c=direction(combine(x,scale(b,h/2)));d=direction(combine(x,scale(c,h)))
        new=combine(x,scale(combine(a,scale(b,2),scale(c,2),d),h/6))
        if norm(new)>3.8:escaped=True;break
        points.append(new);drift=max(drift,abs(flux(new,cp,p)-initial))
    return {'points':points,'flux_initial':initial,'maximum_flux_drift':drift,'return_distance':math.dist(seed,points[-1]),'domain_exit':escaped,
     'closure':'NOT_ASSERTED_FROM_FINITE_PATH','scope':'RK4 normalized frozen vector field; small return distance is not exact topology proof'}

def verify_result(result):
    """Reject inconsistent candidate outputs; local hashes are not origin authentication.

    HOST must bind input graph/mapping and persisted ancestry independently.
    This evaluator imports neither native kernels nor candidate producers.
    """
    require(isinstance(result,dict) and len(json.dumps(result,allow_nan=False))<2_000_000,'RESULT_BOUND')
    keys(result,('schema','status','inputs','input_sha256','numeric','numeric_sha256','projection','checkpoint','scope','result_sha256'))
    require(result['schema']==SCHEMA and result['status']=='CANDIDATE_COMPUTATIONAL_TOROIDAL','SCHEMA')
    require(result['scope']=='Explicit 3D constitutive computational field. Point-charge diagnostic is separate, not full Maxwell. Polarity/coupling are candidate assumptions, not canonical/historical law; no cognitive advantage or evidence authority.','SCOPE')
    require(digest({k:v for k,v in result.items() if k!='result_sha256'})==result['result_sha256'],'RESULT_SEAL')
    inp=result['inputs'];keys(inp,('mapped_sources','sample_points','prior_state'))
    sources=inp['mapped_sources'];require(isinstance(sources,list) and 1<=len(sources)<=12,'SOURCE_BOUND')
    ids=[];seeds=[]
    for row in sources:
        keys(row,('id','amplitude'));ident=row['id']
        require(isinstance(ident,str) and 1<=len(ident)<=64 and ident not in ids,'SOURCE_ID')
        ids.append(ident);seeds.append(number(row['amplitude'],0,1))
    points=inp['sample_points'];require(isinstance(points,list) and len(points)==len(ids),'POINTS_BOUND')
    for ident,row in zip(ids,points):
        keys(row,('id','position'));require(row['id']==ident,'POINT_ID');vector(row['position'])
    require(result['input_sha256']==digest(sources),'INPUT_SEAL')
    num=result['numeric'];keys(num,('step','time','parameters','source_amplitudes','geometry','moving_sources','coefficients','samples','lines','state_rebase'))
    p=check_parameters(num['parameters']);step=0;amps=seeds[:];rebase=None
    prior=inp['prior_state']
    if prior is not None:
        keys(prior,('schema','step','parameters','parameters_sha256','input_sha256','ids','amplitudes','previous_numeric_sha256','feedback','state_sha256'))
        require(prior['schema']==SCHEMA and digest({k:v for k,v in prior.items() if k!='state_sha256'})==prior['state_sha256'],'PRIOR_SEAL')
        require(type(prior['step']) is int and 0<=prior['step']<1024,'PRIOR_STEP')
        require(prior['parameters_sha256']==digest(check_parameters(prior['parameters'])),'PRIOR_PARAMETERS')
        require(isinstance(prior['ids'],list) and 1<=len(prior['ids'])<=12 and len(set(prior['ids']))==len(prior['ids']) and all(isinstance(i,str) and 1<=len(i)<=64 for i in prior['ids']),'PRIOR_IDS')
        require(isinstance(prior['amplitudes'],list) and len(prior['amplitudes'])==len(prior['ids']),'PRIOR_AMPLITUDES')
        for name in ('previous_numeric_sha256','input_sha256'):
            require(isinstance(prior[name],str) and len(prior[name])==64 and all(c in '0123456789abcdef' for c in prior[name]),'PRIOR_HASH')
        if prior['feedback'] is not None:
            feedback=prior['feedback'];keys(feedback,('audits','scope'))
            require(feedback['scope']=='HOST-declared selected audit; separate candidate amplitudes, no truth/authority effect','FEEDBACK_SCOPE')
            require(isinstance(feedback['audits'],list) and len(feedback['audits'])<=12,'FEEDBACK_BOUND')
            audited=set()
            for audit in feedback['audits']:
                keys(audit,('id','passed'))
                require(audit['id'] in prior['ids'] and audit['id'] not in audited and type(audit['passed']) is bool,'FEEDBACK_ID')
                audited.add(audit['id'])
        old=dict(zip(prior['ids'],[number(a,0,1) for a in prior['amplitudes']]))
        step=prior['step'];changed=prior['input_sha256']!=digest(sources)
        amps=[.5*old[i]+.5*s if changed and i in old else old.get(i,s) for i,s in zip(ids,seeds)]
        rebase={'retained_ids':[i for i in ids if i in old],'added_ids':[i for i in ids if i not in old],'removed_ids':[i for i in old if i not in ids],'input_changed':changed,'parameter_changed':prior['parameters_sha256']!=digest(p)}
    errors=[]
    compare(num['step'],step,errors);compare(num['time'],step*p['dt'],errors);compare(num['source_amplitudes'],amps,errors);compare(num['state_rebase'],rebase,errors)
    vertices=[[p['geometry_radius']*x/math.sqrt(3) for x in v] for v in itertools.product((-1,1),repeat=3)]
    groups=[[i for i,v in enumerate(itertools.product((-1,1),repeat=3)) if math.prod(v)==s] for s in (1,-1)]
    geo={'axis':list(AXIS),'basis_u':list(U),'basis_v':list(V),'stationary_vertices':vertices,'tetrahedra':groups,
     'edges':[list(e) for g in groups for e in itertools.combinations(g,2)],'faces':[list(f) for g in groups for f in itertools.combinations(g,3)],
     'projection':[{'vertex':i,'point':[dot(v,U),dot(v,V)],'axis_position':dot(v,AXIS)} for i,v in enumerate(vertices)],
     'scope':'Centered parity tetrahedra; eight vertices, six outer projected points and two projected center vertices; candidate polarity separate'}
    compare(num['geometry'],geo,errors)
    moving=[];moments=[];average=sum(amps)/len(amps)
    for k,indices in enumerate(groups):
        omega=p['rates'][k]*p['directions'][k];angle=math.remainder(omega*step*p['dt']+p['phases'][k],2*math.pi);group=[]
        for index in indices:
            pos=rotate(vertices[index],angle);vel=scale(cross(AXIS,pos),omega);charge=p['polarities'][k]*p['source_gains'][k]*average/4
            group.append({'vertex':index,'group':k,'position':pos,'velocity':vel,'charge':charge,'angle':angle})
        moving.extend(group);moments.append(sum(s['charge']*dot(cross(s['position'],s['velocity']),AXIS) for s in group)/(4*p['geometry_radius']**2))
    overlap=sum(1/(1+math.dist(a['position'],b['position'])**2) for a in moving[:4] for b in moving[4:])/16
    relative=(p['rates'][0]*p['directions'][0]-p['rates'][1]*p['directions'][1])/8
    ct=.5*sum(moments)*p['toroidal_gain'];cp=overlap*math.prod(moments)*relative*p['poloidal_gain']
    coeff={'ct':ct,'cp':cp,'moments':moments,'pair_kernel':overlap,'relative_signed_rate':relative,'average_amplitude':average,'stationary_coefficients_zero':all(p['rates'][k]*p['directions'][k]==0 for k in (0,1))}
    compare(num['moving_sources'],moving,errors);compare(num['coefficients'],coeff,errors)
    samples=[]
    for row in points:
        e,b=diagnostic(row['position'],moving,p['softening'])
        samples.append({'id':row['id'],'position':row['position'],**field_record(row['position'],ct,cp,p),'diagnostic_E':e,'diagnostic_B':b})
    compare(num['samples'],samples,errors)
    orientation=1 if ct>=0 else -1
    circle=[scale(combine(scale(U,math.cos(orientation*2*math.pi*i/p['line_steps'])),scale(V,math.sin(orientation*2*math.pi*i/p['line_steps']))),p['major_radius']) for i in range(p['line_steps']+1)]
    seed=scale(U,p['major_radius']*.8)
    lines={'toroidal':{'points':circle if ct else [seed],'closure':'EXACT_CIRCLE' if ct else 'NO_CIRCULATION_ZERO_CT','coefficient':ct,'scope':'Toroidal component control; mixed full field follows separately'},'poloidal':trajectory(seed,0.,cp,p),'mixed':trajectory(seed,ct,cp,p)}
    compare(num['lines'],lines,errors)
    require(result['numeric_sha256']==digest(num),'NUMERIC_SEAL')
    expected_cp={'schema':SCHEMA,'step':step+1,'parameters':p,'parameters_sha256':digest(p),'input_sha256':digest(sources),'ids':ids,'amplitudes':[min(1,max(0,p['decay']*a+p['gain']*s)) for a,s in zip(amps,seeds)],'previous_numeric_sha256':digest(num),'feedback':None}
    expected_cp['state_sha256']=digest(expected_cp)
    compare(result['checkpoint'],expected_cp,errors)
    projection=result['projection'];keys(projection,('enabled','candidates','ranking','authority'));require(type(projection['enabled']) is bool,'ENABLED_TYPE')
    # Reconstructed energies were independently checked above. Preserve captured
    # IEEE values for exact ranking of symmetry ties; do not turn tiny roundoff
    # differences from algebraically equivalent formulas into contradictory IDs.
    candidates=[{'id':s['id'],'field_priority':s['energy'] if projection['enabled'] else 0.} for s in num['samples']]
    ranking=[r['id'] for r in sorted(candidates,key=lambda r:(-r['field_priority'],r['id']))]
    compare(projection,{'enabled':projection['enabled'],'candidates':candidates,'ranking':ranking,'authority':'NONE'},errors)
    return {'verified':True,'scope':'Independent numerical consistency, not origin authentication, Maxwell or cognitive proof','sample_count':len(samples),'vertex_count':8,'maximum_numeric_error':max(errors,default=0.),'ct':ct,'cp':cp,'step':step,'next_step':step+1}
