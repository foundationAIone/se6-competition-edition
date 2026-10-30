"""Independent stdlib numerical oracle; no expected native answers enter executor."""
import importlib.util,sys,math,json,copy,random
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
DIR=ROOT/'private-native/canonical_operators';sys.path.insert(0,str(DIR))
import relational_field_realization as field

def plan():
 return {'nodes':[{'id':'a','route':'RELATIONAL','connected':True,'depends_on':[],'input':'public premise'}, {'id':'b','route':'LINEAR_MATH','connected':True,'depends_on':['a'],'input':'derive public consequence'}, {'id':'c','route':'HOST_BUSINESS','connected':True,'depends_on':['a'],'input':'conditional budget'}]}
def clip(v):
 z=complex(*v);return z/max(1,abs(z))
def geometry(p):
 depth={};out={n['id']:0 for n in p['nodes']}
 for n in p['nodes']:
  depth[n['id']]=max([depth[x]+1 for x in n['depends_on']] or [0])
  for x in n['depends_on']:out[x]+=1
 maxd=max(depth.values());N=len(p['nodes']);rows=[]
 for n in p['nodes']:
  degree=out[n['id']]-len(n['depends_on']);position=clip([depth[n['id']]/max(1,maxd),degree/max(1,N-1)])
  force=clip([.25+.5*int(n['connected'])+.25*min(1,len(n['input'].encode())/4096),degree/max(1,N)])
  rows.append((n['id'],position,force))
 return rows

def oracle(p,params,prior=None):
 rows=geometry(p);N=len(rows);step=prior['step'] if prior else 0;t=step*params['dt'];forces=[[complex(*v) for v in group] for group in prior['forces']] if prior else [[r[2] for r in rows] for _ in range(2)]
 turns=[complex(math.cos(d*w*t+phase),math.sin(d*w*t+phase)) for d,w,phase in zip(params['directions'],params['rates'],params['phases'])]
 sources=[[(pos*turn,v*turn*gain) for (_,pos,_),v in zip(rows,group)] for turn,gain,group in zip(turns,params['source_gains'],forces)]
 values=[]
 for _,pos,_ in rows:values.append(sum(vec/(1+abs(pos-sourcepos)**2)/(2*N) for group in sources for sourcepos,vec in group))
 interactions=[]
 for k,group in enumerate(sources):
  interactions.append([clip([(z.real),(z.imag)]) for pos,vec in group for z in [sum((othervec-vec)/(1+abs(pos-otherpos)**2)/N for otherpos,othervec in sources[1-k])/turns[k]]])
 nextforces=[[clip([(params['decay']*v+params['gain']*params['interaction']*c).real,(params['decay']*v+params['gain']*params['interaction']*c).imag]) for v,c in zip(group,responses)] for group,responses in zip(forces,interactions)]
 return rows,values,interactions,nextforces

def test_independent_graph_field_coupling_recurrence_and_persistence():
 rng=random.Random(902761)
 for _ in range(25):
  p=copy.deepcopy(field.DEFAULT);p.update(rates=[rng.uniform(0,10),rng.uniform(0,10)],phases=[rng.uniform(-math.pi,math.pi),rng.uniform(-math.pi,math.pi)],directions=[rng.choice([-1,0,1]),rng.choice([-1,0,1])],source_gains=[rng.random(),rng.random()])
  state=None
  for _ in range(4):
   expected=oracle(plan(),p,state);got=field.realize_field(plan(),prior_state=state,parameters=p)
   for row,(_,position,force),value in zip(got['numeric']['G0'],expected[0],expected[1]):
    assert row['position']==pytest.approx([position.real,position.imag],abs=1e-12)
   for row,value in zip(got['numeric']['samples'],expected[1]):
    assert row['field']==pytest.approx([value.real,value.imag],abs=1e-12);assert math.hypot(*row['field'])<=1+1e-12
   for group,wanted in zip(got['checkpoint']['forces'],expected[3]):
    for v,z in zip(group,wanted):assert v==pytest.approx([z.real,z.imag],abs=1e-12)
   state=json.loads(json.dumps(got['checkpoint']))

def test_zero_source_zero_rotation_phases_and_co_counter_rotation():
 p=copy.deepcopy(field.DEFAULT);p['source_gains']=[0,0]
 assert all(s['energy']==0 for s in field.realize_field(plan(),parameters=p)['numeric']['samples'])
 one={'nodes':[{'id':'a','route':'RELATIONAL','connected':True,'depends_on':[],'input':''}]}
 p=copy.deepcopy(field.DEFAULT);p.update(phases=[0,math.pi],gain=0,decay=1)
 assert field.realize_field(one,parameters=p)['numeric']['samples'][0]['energy']==pytest.approx(0,abs=1e-24)
 p.update(phases=[0,0],rates=[0,0]);a=field.realize_field(one,parameters=p);b=field.realize_field(one,parameters=p,prior_state=a['checkpoint'])
 assert a['numeric']['samples']==b['numeric']['samples']
 p.update(rates=[1,1],directions=[1,1]);co=field.realize_field(one,parameters=p,prior_state=field.realize_field(one,parameters=p)['checkpoint'])
 p['directions']=[1,-1];counter=field.realize_field(one,parameters=p,prior_state=field.realize_field(one,parameters=p)['checkpoint'])
 assert co['numeric']['samples'][0]['field']!=counter['numeric']['samples'][0]['field']

def test_neutralization_identical_numeric_state_and_feedback():
 yes=field.realize_field(plan());no=field.realize_field(plan(),enabled=False)
 assert yes['numeric']==no['numeric'] and yes['checkpoint']==no['checkpoint']
 assert all(r['field_priority']==0 for r in no['projection']['candidates'])
 audits=[{'id':'a','passed':True}]
 assert field.finish_field(yes,audits)==field.finish_field(no,audits)
 assert yes['projection']['possibility_only'] and 'NONE' in yes['projection']['authority']

def test_mapping_binding_and_eligibility_and_invalid_parameters():
 p=plan();g=field.realize_field(p)['numeric']['G0'];assert [r['features']['depth'] for r in g]==[0,1,1]
 from native_bridge import preflight
 mapping=preflight('derive supported public relation',p)['plan_mapping']
 bound=field.realize_field(p,actual_mapping=mapping);assert {r['id']:r['mapped_node_id'] for r in bound['numeric']['G0']}=={b['id']:b['node_id'] for b in mapping['node_bindings']} and bound['lineage']
 mapping['node_bindings'][0]['input_sha256']='0'*64
 with pytest.raises(ValueError):field.realize_field(p,actual_mapping=mapping)
 p['nodes'][0]['connected']=False;assert not field.realize_field(p)['projection']['ranking']
 bad=copy.deepcopy(field.DEFAULT);bad['rates'][0]=float('nan')
 with pytest.raises(ValueError):field.realize_field(plan(),parameters=bad)

def test_feedback_seal_and_change_of_input_state_scope():
 p=plan();r=field.realize_field(p);cp=field.finish_field(r,[{'id':'a','passed':False}]);assert cp['feedback']['audits'][0]['passed'] is False
 altered=copy.deepcopy(cp);altered['forces'][0][0][0]+=.1
 with pytest.raises(ValueError):field.realize_field(p,prior_state=altered)
 changed=copy.deepcopy(p);changed['nodes'][0]['input']='corrected explicit public premise';nextstep=field.realize_field(changed,prior_state=cp)
 assert nextstep['numeric']['step']==1 and nextstep['numeric']['prior_state_sha256']==cp['state_sha256']


def test_graph_membership_rebase_preserves_only_shared_bounded_sources():
 old=field.realize_field(plan());cp=field.finish_field(old,[{'id':'a','passed':True}])
 new={'nodes':[{'id':'a','route':'RELATIONAL','connected':True,'depends_on':[],'input':'changed public premise'}]}
 result=field.realize_field(new,prior_state=cp)
 rebase=result['numeric']['state_rebase'];assert rebase['retained_ids']==['a'] and rebase['removed_ids']==['b','c'] and rebase['added_ids']==[]
 assert result['numeric']['step']==cp['step']
 force=geometry(new)[0][2];angle=cp['step']*field.DEFAULT['dt']
 expected=clip([.5*cp['forces'][0][0][0]+.5*force.real,.5*cp['forces'][0][0][1]+.5*force.imag])*complex(math.cos(angle),math.sin(angle))
 assert result['numeric']['rotating_frames'][0]['sources'][0]['vector']==pytest.approx([expected.real,expected.imag],abs=1e-12)
 added=copy.deepcopy(new);added['nodes'].append({'id':'new','route':'HOST_BUDGET','connected':True,'depends_on':['a'],'input':'new bounded public node'})
 assert field.realize_field(added,prior_state=result['checkpoint'])['numeric']['state_rebase']['added_ids']==['new']


def test_final_mapper_span_and_dependency_bindings_cannot_be_substituted():
 from native_bridge import preflight
 p=plan();mapping=preflight('derive supported public relation',p)['plan_mapping']
 bad=copy.deepcopy(mapping);bad['node_bindings'][0]['source_spans']=[[0,1]]
 with pytest.raises(ValueError):field.realize_field(p,actual_mapping=bad)
 changed=copy.deepcopy(p);changed['nodes'][1]['depends_on']=[]
 with pytest.raises(ValueError):field.realize_field(changed,actual_mapping=mapping)
