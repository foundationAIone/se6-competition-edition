"""Candidate bounded artifact realization; native truth remains HOST replay-owned.

No canonical operator is rebuilt. Caller supplies actual V10 operator records.
No provider/network/production calls. Private sandbox effects only.
"""
from copy import deepcopy
import hashlib,json,os,re,subprocess,sys,time
from pathlib import Path
SCHEMA='se6-candidate-realization-loop-v1'
MAX_CYCLES=4
MAX_BYTES=4*1024*1024
ROUTES={'LINEAR_MATH','LINEAR_DERIVATION','RELATIONAL','HOST_BUSINESS','HOST_BUDGET'}
def encode(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf8')
def digest(v):return hashlib.sha256(encode(v)).hexdigest()
def require(ok,code):
 if not ok:raise ValueError(code)
def seal(v):return {**v,'sha256':digest(v)}
def checked(v):
 require(isinstance(v,dict) and len(encode(v))<=MAX_BYTES and v.get('sha256')==digest({k:x for k,x in v.items() if k!='sha256'}),'LOOP_SEAL')
 return v
def hexhash(v):return isinstance(v,str) and re.fullmatch('[0-9a-f]{64}',v) is not None
def root_path(path):
 p=Path(path).absolute();require(not any(x.is_symlink() or x.is_junction() for x in (p,*p.parents)),'LOOP_LINKED_PATH')
 require(not any(x.lower() in {'se6triad','private-native','canonical_core_vendor'} for x in p.parts),'LOOP_PRODUCTION_OR_SOURCE_PATH')
 return p

def prepare_candidates(toroidal,feedback,native_out,native_checkpoint,prior_state=None):
 """HOST inputs must be exact trusted worker records, not public flags."""
 wall=time.perf_counter_ns();cpu=time.process_time_ns()
 require(toroidal.get('prepared_sha256')==digest({k:v for k,v in toroidal.items() if k!='prepared_sha256'}),'LOOP_PREPARED_BINDING')
 require(feedback.get('native_replay_passed') is True,'LOOP_NATIVE_PROOF_REQUIRED')
 nav=toroidal['navigation'];nf=feedback['navigation'];typed=toroidal['typed'];env=toroidal['environment']
 require(nf['status']=='HOST_VERIFIED_NAVIGATION' and nf['typed_recenter_roundtrip_verified'] is True,'LOOP_VERIFIED_PATH_REQUIRED')
 require(toroidal['oracle']['verified'] is True and toroidal['navigation_oracle']['verified'] is True,'LOOP_NUMERIC_NAV_REPLAY')
 require(typed['typed_roundtrip_verified'] is True and typed['qpre'] is not None and typed['mirror_comparison']['same_source_and_provenance'] is True,'LOOP_OPERATOR_REQUIRED')
 selected=typed['selected_ids'];require(isinstance(selected,list) and len(selected)==1 and selected==nav['selected_ids'],'LOOP_ONE_SELECTED_ACTION')
 ident=selected[0];path=nav['trajectory'];require(ident in path[1:] and nf['relationships']==nav['traversed_relationships'],'LOOP_ACTUAL_TRAVERSED_SELECTION')
 require(all(i in nf['verified_ids'] for i in path[1:]),'LOOP_PATH_NODE_VERIFICATION')
 plan=toroidal['plan'];planned={n['id']:n for n in plan['nodes']};actual={n['id']:n for n in native_out['nodes']}
 require(len(actual)==len(native_out['nodes']) and ident in actual and ident in planned,'LOOP_NODE_BINDING')
 node=actual[ident];require(node['status']=='COMPLETE' and node['route'] in ROUTES and node['route']==planned[ident]['route'],'LOOP_UNSUPPORTED_OR_INCOMPLETE')
 require(native_out['question_sha256']==toroidal['question_sha256'] and native_out['checkpoint_hash']==native_checkpoint['checkpoint_hash'],'LOOP_NATIVE_CHECKPOINT')
 require(ident in toroidal['environment']['admitted_ids'],'LOOP_BOUNDARY_ADMISSION')
 if prior_state is not None:
  checked(prior_state);require(prior_state['schema']==SCHEMA and prior_state['step']<MAX_CYCLES,'LOOP_STATE_CAP')
  require(native_checkpoint.get('previous_checkpoint_hash')==prior_state['native_checkpoint_identity'],'LOOP_NATIVE_ANCESTRY')
 bindings={r['id']:r['mapped_node_id'] for r in env['vertices'] if r['id']!='source'}
 artifact={'schema':SCHEMA,'operation':'materialize-verified-selected-native-result',
  'selected_id':ident,'mapped_node_id':bindings[ident],'route':node['route'],
  'verified_native_result':deepcopy(node['result']),'native_checkpoint_sha256':digest(native_checkpoint),
  'native_checkpoint_identity':native_checkpoint['checkpoint_hash'],'prior_loop_state_sha256':prior_state['sha256'] if prior_state else None,
  'mapped_environment_sha256':env['environment_sha256'],'navigation_sha256':nav['navigation_sha256'],
  'relationships':deepcopy(nf['relationships']),'scope':'Conditional native result copied to authorized private artifact; no new world truth'}
 # Native tuples and JSON transport lists have identical encoded content.
 # Materialize exactly that JSON domain; do not relax bytes/hash verification.
 artifact=json.loads(encode(artifact))
 require(len(encode(artifact))<=8192,'LOOP_EFFECT_BYTE_CAP')
 operators=post_native_operators(toroidal,artifact)
 stages=[{'operator':x,'status':s,'scope':scope} for x,s,scope in [
 ('MAP','ACTUAL_EXECUTION','Existing typed UniversalMap and Flower lineage'),('NAVIGATE','ACTUAL_EXECUTION','Verified V10 candidate field navigation and native typed recenter'),
 ('TRANSFORM','CANDIDATE_EXECUTION','Selected actual completed-node result becomes immutable artifact action payload'),('GENERATE_CANDIDATES','ACTUAL_EXECUTION','New existing finite native QPRE render on actual post-native selected result'),
 ('MIRROR','ACTUAL_EXECUTION','New existing symbolic perspectives/common provenance on actual post-native result and artifact possibility'),('CLASSIFY','ACTUAL_EXECUTION','New existing SYMBOLIC periodic dimension on selected post-native result'),
 ('BOUNDARY','HOST_SCOPED_EXECUTION','Exact admitted native route, verified traversal and one private bounded artifact action'),('SELECT','CANDIDATE_EXECUTION','Actual traversed endpoint; no general utility maximization'),
 ('Full mathematical T/P/argmax/World/Theta','UNAVAILABLE','Canonical full numerical, utility, causal-world and learning contracts remain unspecified')]]
 return seal({'schema':SCHEMA,'artifact':artifact,'bindings':bindings,'prior_state':deepcopy(prior_state),
  'native_checkpoint':deepcopy(native_checkpoint),'native_out':deepcopy(native_out),'native_preflight':{'plan':deepcopy(plan),'question_sha256':toroidal['question_sha256'],'plan_sha256':toroidal['plan_sha256']},
  'post_native_context':{'actual_plan_mapping':deepcopy(toroidal['actual_plan_mapping']),'question_sha256':toroidal['question_sha256']},
  'operators':operators,'candidates':[{'id':'PAUSE','effect':'NONE'},{'id':'MATERIALIZE','effect_sha256':digest(artifact),'selected_node_id':ident}],
  'ranking':['MATERIALIZE','PAUSE'],'selection_policy':'HOST verified selected endpoint materialization, fallback PAUSE; not universal argmax',
  'stages':stages,'resources':{'prepare_wall_ns':time.perf_counter_ns()-wall,'prepare_cpu_ns':time.process_time_ns()-cpu,'provider_calls':0}})

def post_native_operators(toroidal,artifact):
 from operator_executor import load
 m,q,k,f,E,pins=load()
 mapping=m.UniversalMap.model_validate_json(json.dumps(toroidal['actual_plan_mapping']['model']))
 source=next(v for v in mapping.vertices if v.kind is m.NodeKind.REALITY_OBJECT)
 state=artifact['native_checkpoint_sha256'];frame=toroidal['question_sha256'];ref='verified-result:'+digest(artifact)
 candidates=[]
 for action in ('PAUSE','MATERIALIZE'):
  uncertainty=q.StructuredUncertainty(unknown=('Filesystem effect not yet observed',),assumptions=('Conditional native result, no world truth',))
  realization=q.build_candidate_realization(source_state_hash=state,frame_hash=frame,candidate_state=(q.CandidateStateField(name='action',possible_value=action),q.CandidateStateField(name='result_payload_sha256',possible_value=digest(artifact))),transformations=(q.TransformationStep(operation='verified-result-to-artifact' if action=='MATERIALIZE' else 'identity',input_reference=ref,possible_output=action),),predicted_consequences=(q.build_predicted_consequence(summary='Private artifact write, verification pending' if action=='MATERIALIZE' else 'No filesystem effect',provenance_references=(ref,)),),reversibility=q.Reversibility.REVERSIBLE,cost_units=1 if action=='MATERIALIZE' else 0,risk_score=0,provenance_references=(ref,))
  candidates.append(q.build_qpre_candidate(source_state_hash=state,frame_hash=frame,assumptions=uncertainty.assumptions,uncertainty=uncertainty,realization=realization,provenance_references=(ref,)))
 rendered=q.render_qpre(q.build_possibility_field(source_state_hash=state,frame_hash=frame,candidates=candidates))
 views=tuple(m.create_perspective_view(source,perspective_key=key,representation=json.dumps(value,sort_keys=True),epistemic_status=E.SYMBOLIC) for key,value in [('selected-native-result',artifact['verified_native_result']),('artifact-consequence-candidate',{'payload_sha256':digest(artifact),'action':'MATERIALIZE','verification':'PENDING'})])
 invariant=m.extract_common_denominator(source,views)
 node=next(v for v in mapping.vertices if v.node_id==artifact['mapped_node_id'])
 terminal=m.create_periodic_terminal(node,label='verified-conditional-result:artifact-candidate',grounding=m.PeriodicGrounding.SYMBOLIC,epistemic_status=E.SYMBOLIC)
 dimension=m.create_periodic_dimension(name='post-native-artifact-candidate',property_name='Selected verified conditional result; filesystem consequence still pending',terminals=(terminal,))
 require(q.QPRERender.model_validate_json(rendered.model_dump_json())==rendered,'LOOP_QPRE_ROUNDTRIP')
 return {'qpre':rendered.model_dump(mode='json'),'views':[v.model_dump(mode='json') for v in views],'common_denominator':invariant.model_dump(mode='json'),'symbolic_dimension':dimension.model_dump(mode='json'),'source_pins':pins,'scope':'Actual finite native contracts operate on post-native selected result; symbolic not physical/world authority'}

def post_native_operators_from_prepared(prepared):
 return post_native_operators(prepared['post_native_context'],prepared['artifact'])

def verify_restored_canonical(state):
 """Source-pinned verifier child hook for restored actual typed contracts.

 Native checkpoint journals are separately replayed by root's native verifier.
 """
 checked(state);typed=checked(state['typed_assimilation'])
 from operator_executor import load
 m,q,k,f,E,pins=load();require(typed['source_pins']==pins,'LOOP_RESTORED_SOURCE_PINS')
 x=f.RealizationState.model_validate_json(json.dumps(typed['x']));theta=f.RealizationFrame.model_validate_json(json.dumps(typed['theta']));traversal=k.MerkabahTraversal.model_validate_json(json.dumps(typed['traversal']))
 obs=f.SourceObservation.model_validate_json(json.dumps(typed['observation']))
 require(theta.x==x and obs in x.source_observations and traversal.returned_center.state_hash==x.x_hash and traversal.returned_center.frame_hash==theta.theta_hash and obs.source_reference=='private-effect:'+state['effect_sha256'],'LOOP_RESTORED_TYPED_BINDING')
 return True

def verify_prepared(prepared,expected_native_out,expected_checkpoint,expected_toroidal,expected_feedback,expected_prior_state=None):
 """Pure parent admission against captured trusted source-bound worker context.

 Expected inputs must come from immutable worker capture, never request JSON.
 Finalizer additionally regenerates all canonical post-native typed operators.
 """
 checked(prepared);require(prepared['native_out']==expected_native_out and prepared['native_checkpoint']==expected_checkpoint and prepared['prior_state']==expected_prior_state,'LOOP_EXPECTED_NATIVE_CONTEXT')
 t=expected_toroidal;f=expected_feedback
 require(f['native_replay_passed'] is True and f['navigation']['status']=='HOST_VERIFIED_NAVIGATION' and f['navigation']['typed_recenter_roundtrip_verified'] is True,'LOOP_EXPECTED_VERIFIED_PATH')
 require(prepared['post_native_context']=={'actual_plan_mapping':t['actual_plan_mapping'],'question_sha256':t['question_sha256']},'LOOP_EXPECTED_MAPPING')
 ident=t['typed']['selected_ids'][0];node=next(n for n in expected_native_out['nodes'] if n['id']==ident)
 bindings={v['id']:v['mapped_node_id'] for v in t['environment']['vertices'] if v['id']!='source'}
 expected={'schema':SCHEMA,'operation':'materialize-verified-selected-native-result','selected_id':ident,'mapped_node_id':bindings[ident],'route':node['route'],'verified_native_result':node['result'],'native_checkpoint_sha256':digest(expected_checkpoint),'native_checkpoint_identity':expected_checkpoint['checkpoint_hash'],'prior_loop_state_sha256':expected_prior_state['sha256'] if expected_prior_state else None,'mapped_environment_sha256':t['environment']['environment_sha256'],'navigation_sha256':t['navigation']['navigation_sha256'],'relationships':f['navigation']['relationships'],'scope':'Conditional native result copied to authorized private artifact; no new world truth'}
 expected=json.loads(encode(expected))
 require(prepared['artifact']==expected and prepared['bindings']==bindings,'LOOP_EXPECTED_ARTIFACT')
 require(prepared['native_preflight']=={'plan':t['plan'],'question_sha256':t['question_sha256'],'plan_sha256':t['plan_sha256']},'LOOP_EXPECTED_PREFLIGHT')
 require(prepared['candidates']==[{'id':'PAUSE','effect':'NONE'},{'id':'MATERIALIZE','effect_sha256':digest(expected),'selected_node_id':ident}] and prepared['ranking']==['MATERIALIZE','PAUSE'],'LOOP_EXPECTED_CANDIDATES')
 return True

def fresh_readback(path):
 """Fresh interpreter independent byte observation; no application imports."""
 code="import hashlib,json,sys,os,stat;from pathlib import Path;p=Path(sys.argv[1]);assert not any(x.is_symlink() or x.is_junction() for x in (p,*p.parents));f=os.open(p,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0));a=os.fstat(f);assert stat.S_ISREG(a.st_mode) and a.st_size<=8192;b=os.read(f,8193);z=os.fstat(f);os.close(f);c=p.stat();assert len(b)<=8192 and (a.st_ino,a.st_size,a.st_mtime_ns)==(z.st_ino,z.st_size,z.st_mtime_ns)==(c.st_ino,c.st_size,c.st_mtime_ns);print(json.dumps({'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)}))"
 env=dict(os.environ)
 for k in ('NEBIUS_API_KEY','OPENAI_API_KEY'):env.pop(k,None)
 r=subprocess.run([sys.executable,'-I','-B','-c',code,str(path)],env=env,capture_output=True,text=True,timeout=5)
 require(r.returncode==0,'LOOP_FRESH_READBACK_FAILED');return json.loads(r.stdout)

def finalize_verified(prepared,observation,prior_state=None):
 """Invoke in source-pinned proof-only child AFTER HOST observed byte effect.

 HOST authenticates native checkpoint and independently observed effect before
 supplying these inputs. Canonical typed contracts cannot authenticate HOST.
 """
 checked(prepared);require(prior_state==prepared['prior_state'],'LOOP_FINALIZE_PRIOR')
 require(prepared['operators']==post_native_operators_from_prepared(prepared),'LOOP_POST_NATIVE_OPERATOR_REPLAY')
 raw=encode(prepared['artifact']);effectsha=hashlib.sha256(raw).hexdigest()
 require(observation=={'sha256':effectsha,'bytes':len(raw)},'LOOP_FINALIZE_OBSERVATION')
 from operator_executor import load
 m,q,k,f,E,pins=load()
 obs=f.create_source_observation(source_reference='private-effect:'+effectsha,
  summary='Independently read back private artifact for selected '+prepared['artifact']['selected_id'],
  epistemic_status=E.VERIFIED,evidence_references=('readback-sha256:'+effectsha,'native-checkpoint:'+prepared['artifact']['native_checkpoint_sha256']))
 previous=(prior_state or {}).get('typed_assimilation')
 if previous is None:
  genesis=f.create_source_observation(source_reference='native-checkpoint:'+prepared['artifact']['native_checkpoint_sha256'],summary='HOST replayed conditional native checkpoint before private artifact action',epistemic_status=E.VERIFIED,evidence_references=('host-native-replay:'+prepared['artifact']['native_checkpoint_sha256'],))
  before=f.create_realization_state(state_summary='Initial bounded local artifact context',source_observations=(genesis,))
 else:before=f.RealizationState.model_validate_json(json.dumps(previous['x']))
 beforeframe=f.create_realization_frame(before,frame_name='bounded-private-artifact-context',dimensions=('selected-native-result','observed-artifact'),representation_rules=('No external world truth grant',))
 after=f.advance_realization_state(before,state_summary='Retain verified local artifact '+effectsha,additional_observations=(obs,))
 afterframe=f.create_realization_frame(after,frame_name='bounded-private-artifact-context',dimensions=('selected-native-result','observed-artifact'),representation_rules=('No external world truth grant',))
 center=k.build_traversal_center(state_hash=before.x_hash,frame_hash=beforeframe.theta_hash)
 terminal=k.build_traversal_terminal(source_center_id=center.center_id,references=(k.TraversalReference(kind=k.TraversalReferenceKind.MAPPED,reference_id='artifact:'+effectsha),),summary='Observed private artifact consequence')
 evidence=k.build_verified_consequence_assimilation(source_center_id=center.center_id,consequence_reference='artifact:'+effectsha,verification_reference='readback:'+effectsha,assimilation_reference='x:'+after.x_hash,next_state_hash=after.x_hash,next_frame_hash=afterframe.theta_hash)
 traversal=k.traverse_merkabah(center=center,terminal=terminal,verified_assimilation=evidence)
 require(f.RealizationState.model_validate_json(after.model_dump_json())==after and f.RealizationFrame.model_validate_json(afterframe.model_dump_json())==afterframe and k.MerkabahTraversal.model_validate_json(traversal.model_dump_json())==traversal,'LOOP_FINALIZE_TYPED_ROUNDTRIP')
 return seal({'schema':SCHEMA,'prepared_sha256':prepared['sha256'],'effect_sha256':effectsha,'prior_state_sha256':prior_state['sha256'] if prior_state else None,
  'observation':obs.model_dump(mode='json'),'x':after.model_dump(mode='json'),'theta':afterframe.model_dump(mode='json'),'traversal':traversal.model_dump(mode='json'),
  'source_pins':pins,'typed_roundtrip_verified':True,'scope':'Actual canonical SHADOW return/renew contracts over independently observed private artifact; HOST authenticates observations, no general World/Theta realization'})

def exclusive(path,raw):
 require(len(raw)<=MAX_BYTES,'LOOP_BYTE_CAP');require(not any(p.is_symlink() for p in (path,*path.parents)),'LOOP_LINKED_PATH')
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())

def effect_readback(root,effect_sha):
 require(hexhash(effect_sha),'LOOP_EFFECT_HASH');path=root/'effects'/(effect_sha+'.json')
 root_path(path)
 require(not path.is_symlink() and path.is_file() and path.stat().st_size<=8192,'LOOP_EFFECT_MISSING_OR_BOUND')
 observation=fresh_readback(path);require(observation['sha256']==effect_sha,'LOOP_EFFECT_READBACK_MISMATCH')
 with path.open('rb') as f:raw=f.read(8193)
 require(len(raw)<=8192 and hashlib.sha256(raw).hexdigest()==effect_sha,'LOOP_EFFECT_CHANGED_AFTER_READBACK')
 return json.loads(raw),observation

def load_restore(effect_directory):
 """Replay local immutable append-only ledger; hashes are not remote signatures."""
 root=root_path(effect_directory)
 if not root.exists():return None
 claims=root/'attempts';root_path(claims);attempts=sorted(claims.glob('*.json')) if claims.exists() else []
 require(len(attempts)<=MAX_CYCLES,'LOOP_ATTEMPT_CAP')
 claimed={}
 for number,path in enumerate(attempts,1):
  root_path(path);require(path.name==f'{number:04d}.json' and path.stat().st_size<=8192,'LOOP_ATTEMPT_FILE')
  claim=checked(json.loads(path.read_bytes()));require(set(claim)=={'schema','prepared_sha256','prior_state_sha256','status','sha256'} and claim['schema']==SCHEMA and claim['status']=='CLAIMED_NONREFUNDABLE' and hexhash(claim['prepared_sha256']) and (claim['prior_state_sha256'] is None or hexhash(claim['prior_state_sha256'])),'LOOP_ATTEMPT_BINDING')
  claimed[number]=claim
 cycles=root/'cycles';require(not cycles.is_symlink(),'LOOP_LINKED_PATH');files=sorted(cycles.glob('*.json')) if cycles.exists() else []
 require(len(files)<=MAX_CYCLES,'LOOP_CYCLE_CAP');prior=None
 for step,path in enumerate(files,1):
  require(path.name==f'{step:04d}.json' and not path.is_symlink() and path.stat().st_size<=MAX_BYTES,'LOOP_LEDGER_GAP_OR_BOUND')
  record=checked(json.loads(path.read_bytes()));require(record['schema']==SCHEMA and record['step']==step and record['prior_state_sha256']==(prior['sha256'] if prior else None),'LOOP_LEDGER_ANCESTRY')
  require(type(record['attempt']) is int and record['attempt'] in claimed and claimed[record['attempt']]['prepared_sha256']==record['prepared_sha256'] and claimed[record['attempt']]['prior_state_sha256']==record['prior_state_sha256'],'LOOP_LEDGER_ATTEMPT')
  require(hexhash(record['next_state_sha256']),'LOOP_STATE_HASH')
  state_path=root/'states'/(record['next_state_sha256']+'.json');root_path(state_path);require(not state_path.is_symlink() and state_path.stat().st_size<=MAX_BYTES,'LOOP_STATE_FILE_BOUND')
  state=checked(json.loads(state_path.read_bytes()));require(state['sha256']==record['next_state_sha256'] and state['step']==step and state['prior_state_sha256']==record['prior_state_sha256'],'LOOP_STATE_BINDING')
  artifact,_=effect_readback(root,record['effect_sha256']);require(artifact['prior_loop_state_sha256']==record['prior_state_sha256'] and artifact['native_checkpoint_identity']==state['native_checkpoint_identity'],'LOOP_EFFECT_STATE_BINDING')
  require(record['readback']=={'sha256':record['effect_sha256'],'bytes':len(encode(artifact))},'LOOP_RECORDED_READBACK')
  typed=checked(state['typed_assimilation']);require(typed['effect_sha256']==record['effect_sha256'] and typed['prior_state_sha256']==record['prior_state_sha256'] and typed['typed_roundtrip_verified'] is True and typed['prepared_sha256']==record['prepared_sha256'],'LOOP_TYPED_STATE_BINDING')
  require(typed['theta']['x']==typed['x'] and typed['traversal']['returned_center']['state_hash']==typed['x']['x_hash'] and typed['traversal']['returned_center']['frame_hash']==typed['theta']['theta_hash'],'LOOP_TYPED_RETURN_BINDING')
  require(typed['x']['previous_x_hash']==((prior or {}).get('typed_assimilation') or {}).get('x',{}).get('x_hash') if prior else typed['x']['previous_x_hash'] is not None,'LOOP_TYPED_ANCESTRY')
  if prior:require(typed['x']['source_observations'][:-1]==prior['typed_assimilation']['x']['source_observations'],'LOOP_OBSERVATION_HISTORY')
  require(typed['x']['source_observations'][-1]==typed['observation'] and typed['observation']['source_reference']=='private-effect:'+record['effect_sha256'],'LOOP_TYPED_OBSERVATION')
  knowledge=deepcopy(prior['knowledge']) if prior else {};invalidated=[]
  for ident in list(knowledge):
   if record['bindings'].get(ident)!=knowledge[ident]['mapped_node_id']:invalidated.append(ident);del knowledge[ident]
  knowledge[artifact['selected_id']]={'mapped_node_id':artifact['mapped_node_id'],'effect_sha256':record['effect_sha256'],'native_checkpoint_identity':artifact['native_checkpoint_identity'],'status':'VERIFIED_PRIVATE_ARTIFACT'}
  require(state['knowledge']==knowledge and state['invalidated_ids']==invalidated and state['native_checkpoint_sha256']==artifact['native_checkpoint_sha256'],'LOOP_KNOWLEDGE_REPLAY')
  require(state['effect_sha256']==record['effect_sha256'] and state['knowledge'][artifact['selected_id']]['effect_sha256']==record['effect_sha256'],'LOOP_KNOWLEDGE_BINDING')
  prior=state
 effect_paths=list((root/'effects').glob('*.json')) if (root/'effects').exists() else []
 require(len(effect_paths)<=MAX_CYCLES and {p.stem for p in effect_paths}=={checked(json.loads(p.read_bytes()))['effect_sha256'] for p in files},'LOOP_ORPHAN_EFFECT_NO_RETRY')
 require(set(claimed)=={checked(json.loads(p.read_bytes()))['attempt'] for p in files},'LOOP_UNRESOLVED_ATTEMPT_NO_RETRY')
 return prior

def act_verify_assimilate(prepared,effect_directory,*,verify_native,finalize):
 """One authorized sandbox effect. No retries; failures may leave orphan effects."""
 wall=time.perf_counter_ns();cpu=time.process_time_ns();checked(prepared)
 root=root_path(effect_directory);prior=prepared['prior_state'];restored=load_restore(root)
 require(restored==prior,'LOOP_STALE_DURABLE_STATE');step=1 if prior is None else prior['step']+1;require(step<=MAX_CYCLES,'LOOP_CYCLE_CAP')
 require(callable(finalize),'LOOP_TYPED_FINALIZER_REQUIRED')
 require(callable(verify_native) and verify_native(deepcopy({'checkpoint':prepared['native_checkpoint'],'out':prepared['native_out'],'preflight':prepared['native_preflight'],'artifact':prepared['artifact'],'prior_state':prior})) is True,'LOOP_NATIVE_PROOF_REQUIRED')
 attempt=0
 for number in range(1,MAX_CYCLES+1):
  try:exclusive(root/'attempts'/f'{number:04d}.json',encode(seal({'schema':SCHEMA,'prepared_sha256':prepared['sha256'],'prior_state_sha256':prior['sha256'] if prior else None,'status':'CLAIMED_NONREFUNDABLE'})));attempt=number;break
  except FileExistsError:continue
 require(attempt>0,'LOOP_ATTEMPT_CAP')
 artifact=prepared['artifact'];raw=encode(artifact);effectsha=hashlib.sha256(raw).hexdigest();path=root/'effects'/(effectsha+'.json')
 exclusive(path,raw);observed,readback=effect_readback(root,effectsha);require(observed==artifact,'LOOP_EFFECT_SEMANTIC_MISMATCH')
 typed=checked(finalize(deepcopy(prepared),deepcopy(readback),deepcopy(prior)))
 require(typed['schema']==SCHEMA and typed['prepared_sha256']==prepared['sha256'] and typed['effect_sha256']==effectsha and typed['prior_state_sha256']==(prior['sha256'] if prior else None) and typed['typed_roundtrip_verified'] is True,'LOOP_TYPED_FINALIZER_BINDING')
 knowledge=deepcopy(prior['knowledge']) if prior else {};invalidated=[]
 for ident in list(knowledge):
  if prepared['bindings'].get(ident)!=knowledge[ident]['mapped_node_id']:invalidated.append(ident);del knowledge[ident]
 knowledge[artifact['selected_id']]={'mapped_node_id':artifact['mapped_node_id'],'effect_sha256':effectsha,'native_checkpoint_identity':artifact['native_checkpoint_identity'],'status':'VERIFIED_PRIVATE_ARTIFACT'}
 state=seal({'schema':SCHEMA,'step':step,'prior_state_sha256':prior['sha256'] if prior else None,
  'native_checkpoint_identity':artifact['native_checkpoint_identity'],'native_checkpoint_sha256':artifact['native_checkpoint_sha256'],
  'effect_sha256':effectsha,'knowledge':knowledge,'invalidated_ids':invalidated,'typed_assimilation':typed,'scope':'Verified local artifact state; canonical premise correction remains native-engine owned'})
 exclusive(root/'states'/(state['sha256']+'.json'),encode(state))
 receipt=seal({'schema':SCHEMA,'step':step,'prior_state_sha256':state['prior_state_sha256'],'next_state_sha256':state['sha256'],'effect_sha256':effectsha,
  'readback':readback,'status':'BOUNDED_EFFECT_VERIFIED_ASSIMILATED','invalidated_ids':invalidated,'bindings':prepared['bindings'],'prepared_sha256':prepared['sha256'],'attempt':attempt,
  'resources':{'wall_ns':time.perf_counter_ns()-wall,'cpu_ns':time.process_time_ns()-cpu,'effect_bytes':len(raw),'provider_calls':0},
  'stages':prepared['stages']+[{'operator':x,'status':'HOST_SCOPED_EXECUTION','scope':scope} for x,scope in [('ACT','Exclusive content-addressed private write'),('VERIFY','Fresh independent interpreter readback of actual bytes'),('ASSIMILATE','Verified artifact knowledge; changed mapped identity invalidates dependent artifact'),('RETURN','Durable sealed state binds prior native checkpoint'),('RENEW','Next cycle must use retained native checkpoint ancestry')]]})
 exclusive(root/'cycles'/f'{step:04d}.json',encode(receipt));require(load_restore(root)==state,'LOOP_RESTORE_FAILED')
 return {'state':state,'receipt':receipt,'artifact':artifact,'full_mathematical_se6':False}

def renew(state,native_checkpoint):
 checked(state);require(digest(native_checkpoint)==state['native_checkpoint_sha256'] and native_checkpoint['checkpoint_hash']==state['native_checkpoint_identity'],'LOOP_RENEW_NATIVE_BINDING')
 return {'prior_state':deepcopy(state),'native_checkpoint_sha256':state['native_checkpoint_sha256'],'next_step':state['step']+1,'scope':'Retained local state input for prospective next native cycle'}
