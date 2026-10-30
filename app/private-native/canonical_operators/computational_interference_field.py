"""Candidate computational field v1; not canonical/physical electromagnetism.

Two bounded counter-rotating dimensionless source vectors generate a discrete
relational field. This module grants no effect/evidence/identity authority.
"""
from copy import deepcopy
import hashlib,json,math

SCHEMA='se6-candidate-computational-field-v1'
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def number(v,lo,hi):
    if type(v) not in (float,int) or not math.isfinite(v) or not lo<=v<=hi:raise ValueError('FINITE_FIELD_BOUND')
    return float(v)
def vector(v):
    if not isinstance(v,list) or len(v)!=2:raise ValueError('VECTOR_SHAPE')
    return [number(x,-1,1) for x in v]
def norm(v):return math.hypot(*v)
def rotate(v,a):
    c,s=math.cos(a),math.sin(a);return [c*v[0]-s*v[1],s*v[0]+c*v[1]]
def config_checked(config):
    if not isinstance(config,dict) or set(config)!={'sources','omega','dt','decay','learning_rate'}:raise ValueError('CONFIG_FIELDS')
    omega=number(config['omega'],0,10);dt=number(config['dt'],0,1);decay=number(config['decay'],0,1);lr=number(config['learning_rate'],0,1)
    sources=config['sources']
    if not isinstance(sources,list) or len(sources)!=2:raise ValueError('TWO_SOURCES_REQUIRED')
    result=[]
    for s in sources:
        if not isinstance(s,dict) or set(s)!={'position','force','phase','direction'}:raise ValueError('SOURCE_FIELDS')
        if type(s['direction']) is not int or s['direction'] not in (-1,1):raise ValueError('COUNTER_ROTATION_DIRECTION')
        force=vector(s['force'])
        if norm(force)>1+1e-15:raise ValueError('SOURCE_NORM_BOUND')
        result.append({'position':vector(s['position']),'force':force,'phase':number(s['phase'],-math.pi,math.pi),'direction':s['direction']})
    if {s['direction'] for s in result}!={-1,1}:raise ValueError('OPPOSING_ROTATIONS_REQUIRED')
    return {'sources':result,'omega':omega,'dt':dt,'decay':decay,'learning_rate':lr}
def default_config():
    return {'sources':[{'position':[-.5,0],'force':[1,0],'phase':0,'direction':1},{'position':[.5,0],'force':[1,0],'phase':0,'direction':-1}],'omega':1,'dt':.25,'decay':1,'learning_rate':0}

def evaluate(config,samples,state=None,feedback=None):
    config=config_checked(config);pin=digest(config)
    if not isinstance(samples,list) or not 1<=len(samples)<=12:raise ValueError('SAMPLE_BOUND')
    ids=[];points=[]
    for s in samples:
        if not isinstance(s,dict) or set(s)!={'id','position'} or not isinstance(s['id'],str) or not s['id'] or len(s['id'])>64:raise ValueError('SAMPLE_FIELDS')
        ids.append(s['id']);points.append(vector(s['position']))
    if len(set(ids))!=len(ids):raise ValueError('DUPLICATE_SAMPLE')
    step=0;forces=[s['force'] for s in config['sources']];previous=None
    if state is not None:
        if not isinstance(state,dict) or set(state)!={'schema','config_sha256','step','time','forces','previous_result_sha256','state_sha256'}:raise ValueError('STATE_FIELDS')
        if state['schema']!=SCHEMA or state['config_sha256']!=pin or state['state_sha256']!=digest({k:v for k,v in state.items() if k!='state_sha256'}):raise ValueError('STATE_BINDING')
        if type(state['step']) is not int or not 0<=state['step']<1024 or state['time']!=state['step']*config['dt']:raise ValueError('STATE_TIME')
        if not isinstance(state['forces'],list) or len(state['forces'])!=2:raise ValueError('STATE_FORCES')
        forces=[vector(v) for v in state['forces']]
        if any(norm(v)>1+1e-15 for v in forces):raise ValueError('STATE_FORCE_BOUND')
        if not isinstance(state['previous_result_sha256'],str) or len(state['previous_result_sha256'])!=64:raise ValueError('STATE_ANCESTRY')
        step=state['step'];previous=state['previous_result_sha256']
    t=step*config['dt'];rows=[]
    for ident,x in zip(ids,points):
        terms=[];weights=[];rotation_error=[]
        for source,force in zip(config['sources'],forces):
            d2=sum((a-b)**2 for a,b in zip(x,source['position']));w=1/(1+d2)
            angle=math.remainder(source['direction']*config['omega']*t+source['phase'],2*math.pi)
            turned=rotate(force,angle);terms.append([w*v for v in turned]);weights.append(w);rotation_error.append(abs(norm(turned)-norm(force)))
        total=[sum(v[j] for v in terms) for j in (0,1)];energy=sum(v*v for v in total)
        component_energy=sum(sum(v*v for v in term) for term in terms);interference=2*sum(a*b for a,b in zip(*terms))
        bound=sum(w*norm(force) for w,force in zip(weights,forces))
        if norm(total)>bound+1e-12:raise ValueError('FIELD_STABILITY')
        rows.append({'id':ident,'position':x,'time':t,'field':total,'magnitude':norm(total),'energy':energy,'component_energy':component_energy,'interference':interference,'energy_identity_error':abs(energy-component_energy-interference),'analytic_norm_bound':bound,'rotation_norm_error':max(rotation_error)})
    errors=[[0.,0.],[0.,0.]]
    if feedback is not None:
        if not isinstance(feedback,dict) or set(feedback)!={'error_vectors','reference'} or not isinstance(feedback['reference'],str) or not feedback['reference'] or len(feedback['reference'])>128:raise ValueError('FEEDBACK_FIELDS')
        if not isinstance(feedback['error_vectors'],list) or len(feedback['error_vectors'])!=2:raise ValueError('FEEDBACK_BOUND')
        errors=[vector(v) for v in feedback['error_vectors']]
    next_forces=[]
    for force,error in zip(forces,errors):
        raw=[config['decay']*a+config['learning_rate']*b for a,b in zip(force,error)];size=norm(raw)
        next_forces.append([v/max(1,size) for v in raw])
    material={'schema':SCHEMA,'status':'CANDIDATE_COMPUTATIONAL_ONLY','config_sha256':pin,'step':step,'time':t,'samples':rows,'previous_result_sha256':previous,'feedback':feedback,
        'source_force_norms':[norm(f) for f in forces],'next_force_norms':[norm(f) for f in next_forces],
        'units':'Dimensionless 2D relational coordinates, force vectors and phase radians; time is bounded step*dt, not physical time',
        'scope':'Finite numerical interference candidate; no Maxwell/EM, canonical equivalence, truth/receipt mutation, authority or effect'}
    result_hash=digest(material)
    checkpoint={'schema':SCHEMA,'config_sha256':pin,'step':step+1,'time':(step+1)*config['dt'],'forces':next_forces,'previous_result_sha256':result_hash}
    checkpoint['state_sha256']=digest(checkpoint)
    return {**material,'result_sha256':result_hash,'checkpoint':checkpoint}

def samples_from_plan(plan):
    nodes=plan.get('nodes') if isinstance(plan,dict) else None
    if not isinstance(nodes,list) or not 1<=len(nodes)<=12:raise ValueError('PLAN_BOUND')
    ids=[n.get('id') for n in nodes]
    if any(not isinstance(i,str) or not i or len(i)>64 for i in ids) or len(set(ids))!=len(ids):raise ValueError('PLAN_IDENTITY')
    return [{'id':ident,'position':[0. if len(ids)==1 else -1+2*i/(len(ids)-1),0.]} for i,ident in enumerate(ids)]

def select_verification_work(plan,field,budget=1):
    """Optional extra audit order only; mandatory native proof replay never skips."""
    if type(budget) is not int or not 0<=budget<=12:raise ValueError('WORK_BUDGET')
    if digest({k:v for k,v in field.items() if k not in ('result_sha256','checkpoint')})!=field.get('result_sha256'):raise ValueError('FIELD_RESULT_CHANGED')
    samples=samples_from_plan(plan)
    if [(s['id'],s['position']) for s in samples]!=[(s['id'],s['position']) for s in field['samples']]:raise ValueError('FIELD_PLAN_BINDING')
    strengths={s['id']:s['energy'] for s in field['samples']};eligible=[];seen=set()
    routes={'LINEAR_MATH','LINEAR_DERIVATION','RELATIONAL','HOST_BUSINESS','HOST_BUDGET'}
    for n in plan['nodes']:
        deps=n.get('depends_on',[])
        if not isinstance(deps,list) or any(d not in seen for d in deps):raise ValueError('PLAN_DEPENDENCY')
        seen.add(n['id'])
        if n.get('connected') is True and n.get('route') in routes and all(d in eligible for d in deps):eligible.append(n['id'])
    chosen=sorted(eligible,key=lambda ident:(-strengths[ident],ident))[:budget]
    return {'selected_ids':chosen,'ranking':[{'id':i,'field_energy':strengths[i]} for i in sorted(eligible,key=lambda ident:(-strengths[ident],ident))],
        'plan_sha256':digest(plan),'field_result_sha256':field['result_sha256'],'budget':budget,'scope':'Optional additional verification work only; mandatory proof/state/evidence/authority unchanged'}

def plan_field_step(plan,question,prior_field_checkpoint=None,*,budget=1):
    """Deterministic candidate default, not a recovered Merkabah specification.

    Fixed source positions +/-0.5 and frequency1; an explicit public 'Correct'
    token sets source2 phase pi/2. This is a declared lexical feature, not
    semantic inference or correction verification. Changed config is rebased
    only after old candidate state validation; canonical checkpoint untouched.
    """
    if not isinstance(question,str) or not question.strip() or len(question.encode())>4096:raise ValueError('PUBLIC_QUESTION_BOUND')
    samples=samples_from_plan(plan);config=default_config();config['learning_rate']=.25
    import re
    correction=bool(re.search(r'\bCorrect\b',question,re.I))
    if correction:config['sources'][1]['phase']=math.pi/2
    state=None;rebase=None
    if prior_field_checkpoint is not None:
        cp=prior_field_checkpoint
        if not isinstance(cp,dict) or set(cp)!={'schema','config','field_state','plan_sha256','question_sha256','checkpoint_sha256'} or cp['schema']!=SCHEMA or cp['checkpoint_sha256']!=digest({k:v for k,v in cp.items() if k!='checkpoint_sha256'}):raise ValueError('CANDIDATE_CHECKPOINT')
        # Independent replay of bounded previous numeric state before rebase.
        evaluate(cp['config'],samples,state=cp['field_state'])
        state=deepcopy(cp['field_state']);newpin=digest(config_checked(config))
        if state['config_sha256']!=newpin:
            rebase={'old_config_sha256':state['config_sha256'],'new_config_sha256':newpin,'reason':'Explicit public Correct lexical feature; no truth/state promotion'}
            state['config_sha256']=newpin;state['state_sha256']=digest({k:v for k,v in state.items() if k!='state_sha256'})
    field=evaluate(config,samples,state=state);work=select_verification_work(plan,field,budget)
    total=sum(s['energy'] for s in field['samples'])
    projection={'operator':'CANDIDATE_FIELD_ATTENTION_T','possibility_only':True,
        'rows':[{'id':s['id'],'field_vector':s['field'],'attention_weight':s['energy']/total if total>1e-24 else 1/len(samples)} for s in field['samples']],
        'scope':'Additional numerical candidate T/QPRE attention view; not canonical transformation equivalence, probability, evidence truth or authority'}
    material={'schema':SCHEMA,'plan':deepcopy(plan),'plan_sha256':digest(plan),'question_sha256':hashlib.sha256(question.encode()).hexdigest(),
        'source_construction':{'positions':'Fixed +/-0.5 relational positions','omega':1,'dt':.25,'correction_lexical_feature':correction,'physical_claim':False},
        'config':config,'prior_numeric_state':state,'configuration_rebase':rebase,'field':field,'projection':projection,'verification_work':work}
    return {**material,'step_sha256':digest(material)}

def advance_field_feedback(step,actual_native_outputs,*,independent_audit=None):
    """Execute only selected extra HOST audits through an injected callback.

    Callback(request)->bool must independently read/reconstruct actual output.
    No callback means NOT_AUDITED, never an inferred successful verification.
    Source feedback changes only the candidate's next force vectors.
    """
    if digest({k:v for k,v in step.items() if k!='step_sha256'})!=step.get('step_sha256'):raise ValueError('CANDIDATE_STEP_CHANGED')
    if not isinstance(actual_native_outputs,dict) or actual_native_outputs.get('question_sha256')!=step['question_sha256']:raise ValueError('NATIVE_QUESTION_BINDING')
    actual=actual_native_outputs.get('nodes')
    if not isinstance(actual,list) or len(actual)!=len(step['plan']['nodes']):raise ValueError('ACTUAL_PLAN_BOUND')
    for planned,observed in zip(step['plan']['nodes'],actual):
        if any(planned.get(k)!=observed.get(k) for k in ('id','route','depends_on')):raise ValueError('ACTUAL_PLAN_BINDING')
    lookup={n['id']:n for n in actual};audits=[]
    for ident in step['verification_work']['selected_ids']:
        passed=None
        if independent_audit is not None:
            observed=independent_audit({'id':ident,'node':deepcopy(lookup[ident]),'plan_sha256':step['plan_sha256'],'question_sha256':step['question_sha256']})
            if type(observed) is not bool:raise ValueError('AUDIT_BOOLEAN_REQUIRED')
            passed=observed
        audits.append({'id':ident,'status':'NOT_AUDITED' if passed is None else 'HOST_AUDIT_PASSED' if passed else 'HOST_AUDIT_FAILED','passed':passed})
    done=[a for a in audits if a['passed'] is not None];feedback=None
    if done:
        good=sum(a['passed'] is True for a in done)/len(done);bad=1-good
        feedback={'error_vectors':[[good,bad],[-bad,good]],'reference':'host-audit:'+digest(audits)}
    updated=evaluate(step['config'],samples_from_plan(step['plan']),state=step['prior_numeric_state'],feedback=feedback)
    cp={'schema':SCHEMA,'config':step['config'],'field_state':updated['checkpoint'],'plan_sha256':step['plan_sha256'],'question_sha256':step['question_sha256']}
    cp['checkpoint_sha256']=digest(cp)
    return {'schema':SCHEMA,'audits':audits,'feedback':feedback,'checkpoint':cp,'updated_field':updated,
        'authority_effect':'NONE','evidence_truth_changed':False,'mandatory_native_verification_skipped':False,
        'scope':'Selected extra audit callbacks are actual HOST work; callback independence remains trusted HOST obligation; candidate checkpoint separate from native evidence'}
