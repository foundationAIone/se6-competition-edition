"""Prospective isolated orchestration admission. No core replacement or effect."""
import hashlib,json,re
from operator_executor import execute,digest,load

ROUTES={'LINEAR_MATH','LINEAR_DERIVATION','RELATIONAL','HOST_BUSINESS','HOST_BUDGET'}
BLOCKED={'DIRECT_MODEL','UNSUPPORTED'}
def sha(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()

def preflight(question,plan,checkpoint_summary=None):
    if not isinstance(question,str) or not question.strip() or len(question)>4000 or len(question.encode('utf8'))>4096:raise ValueError('QUESTION_BOUND')
    if not isinstance(plan,dict) or not isinstance(plan.get('nodes'),list) or len(plan['nodes'])>12:raise ValueError('PLAN_BOUND')
    nodes=plan['nodes'];ids=[n.get('id') for n in nodes]
    if any(not isinstance(i,str) or not i or len(i)>64 for i in ids) or len(set(ids))!=len(ids):raise ValueError('PLAN_IDENTITY')
    admitted=[];skips=[];seen=set()
    for n in nodes:
        route=n.get('route');deps=n.get('depends_on',[])
        if route not in ROUTES|BLOCKED:raise ValueError('INVENTED_ROUTE')
        if type(n.get('connected',False)) is not bool:raise ValueError('CONNECTION_TYPE')
        if not isinstance(deps,list) or any(d not in seen for d in deps):raise ValueError('DANGLING_OR_FORWARD_DEPENDENCY')
        seen.add(n['id'])
        if route in BLOCKED or not n.get('connected',False) or any(d not in {a['id'] for a in admitted} for d in deps):
            skips.append({'id':n['id'],'route':route,'reason':'NO_NATIVE_AUTHORITY_OR_DEPENDENCY'});continue
        admitted.append(n)
    m,q,k,f,E,pins=load()
    observation=f.create_source_observation(source_reference='plan:question',summary=question,
        epistemic_status=E.REPORTED,evidence_references=('plan:'+sha(plan),))
    source=m.create_reality_object(label='public-plan-source',description=question,source_observations=(observation,))
    terminals={};bindings=[]
    for n in nodes:
        text=n.get('input') or ('Typed route '+n['route'])
        if not isinstance(text,str) or len(text)>4000 or len(text.encode('utf8'))>4096:raise ValueError('PLAN_INPUT_BOUND')
        spans=n.get('source_spans',[])
        if not isinstance(spans,list) or len(spans)>64 or any(not isinstance(s,list) or len(s)!=2 or any(type(i) is not int for i in s) or not 0<=s[0]<=s[1]<=len(question) for s in spans):raise ValueError('PLAN_SOURCE_SPANS')
        node_obs=f.create_source_observation(source_reference='plan-node:'+sha(n),summary=text,
            epistemic_status=E.REPORTED,evidence_references=('question:'+hashlib.sha256(question.encode()).hexdigest(),))
        terminals[n['id']]=m.create_mapper_node(kind=m.NodeKind.TERMINAL,label=n['id']+':'+n['route'],description=text,
            epistemic_status=E.SYMBOLIC,source_observations=(observation,node_obs))
        bindings.append({'id':n['id'],'route':n['route'],'source_spans':spans,'input_sha256':hashlib.sha256(text.encode()).hexdigest(),'node_id':terminals[n['id']].node_id})
    relations=[]
    if terminals:
        relations.append(m.create_mapper_relation(kind=m.RelationKind.RELATES_TO,label='source-to-exact-plan-terminals',source_nodes=(source,),target_nodes=tuple(terminals.values()),epistemic_status=E.SYMBOLIC,source_observations=(observation,)))
    for n in nodes:
        for dep in n.get('depends_on',[]):
            relations.append(m.create_mapper_relation(kind=m.RelationKind.DEPENDS_ON,label=n['id']+' depends-on '+dep,source_nodes=(terminals[n['id']],),target_nodes=(terminals[dep],),epistemic_status=E.SYMBOLIC,source_observations=(observation,)))
    views=tuple(m.create_perspective_view(source,perspective_key=p,representation=p+' exact plan provenance') for p in ('owner','dependency-verifier'))
    lineage=[]
    if terminals:
        flower=m.create_flower_center(source,terminals=tuple(terminals.values()));lineage=[flower]
    if admitted:
        lineage.append(m.recenter_flower(flower,terminals[admitted[0]['id']],terminals=(source,)))
    mapping=m.create_universal_map(vertices=(source,*terminals.values()),relations=relations,
        hyperedges=tuple(m.create_mapper_hyperedge(r) for r in relations),perspectives=views,
        invariants=(m.extract_common_denominator(source,views),),flower_lineage=tuple(lineage))
    plan_mapping={'model':mapping.model_dump(mode='json'),'node_bindings':bindings,
        'counts':{'vertices':len(mapping.vertices),'dependency_relations':sum(len(n.get('depends_on',[])) for n in nodes),'relations':len(relations),'hyperedges':len(relations),'flower_centers':len(lineage)},
        'recenter_scope':'TOPOLOGICAL_CONTEXT_ONLY; not identity/state change, geometric rotation, inference or world verification',
        'typed_readback_verified':m.UniversalMap.model_validate_json(mapping.model_dump_json())==mapping}
    # One whole validated batch is the bounded possibility, not a route ranking.
    # Native engine retains its exact plan/dependency ordering and all 12 nodes.
    model=None;decision='PAUSE'
    if admitted:
        model=execute({'observation':'Public question SHA256 '+hashlib.sha256(question.encode()).hexdigest(),
            'state_summary':'Actual checkpoint SHA256 '+sha(checkpoint_summary),
            'candidates':[{'id':'native-batch','value':'batch:'+sha(admitted)[:56],
                'benefit':1,'cost':0,'risk':0,'uncertainty':0,'irreversibility':0}]})
        decision='EXECUTE_NATIVE_BATCH'
    material={'schema':'canonical-v7-native-bridge-v1','question_sha256':hashlib.sha256(question.encode()).hexdigest(),'plan_sha256':sha(plan),'checkpoint_sha256':sha(checkpoint_summary),'admitted_ids':[n['id'] for n in admitted],'skips':skips,'decision':decision,'selection_policy':'HOST_GATE_VALIDATED_WHOLE_BATCH; no empirical expected utility','operators':model,'plan_mapping':plan_mapping,'authority':'NONE; host gate for existing native routes only'}
    return {**material,'preflight_sha256':sha(material)}

def postflight(preflight,beforehash,afterhash,nativeverifiedreceipts,*,verify_native=None):
    """Host verifier MUST reconstruct actual native checkpoint/proofs separately.

    Receipt declared flags alone never suffice for successor admission. This
    bridge cannot independently authenticate the host callback itself.
    """
    if sha({k:v for k,v in preflight.items() if k!='preflight_sha256'})!=preflight['preflight_sha256']:raise ValueError('PREFLIGHT_CHANGED')
    for h in (beforehash,afterhash):
        if not isinstance(h,str) or re.fullmatch('[0-9a-f]{64}',h) is None:raise ValueError('CHECKPOINT_DIGEST')
    if beforehash!=preflight['checkpoint_sha256']:raise ValueError('STALE_CHECKPOINT')
    if not isinstance(nativeverifiedreceipts,list) or len(nativeverifiedreceipts)>20:raise ValueError('RECEIPT_BOUND')
    m,q,k,f,E,pins=load();framehash=preflight['question_sha256']
    center=k.build_traversal_center(state_hash=beforehash,frame_hash=framehash)
    terminal=k.build_traversal_terminal(source_center_id=center.center_id,references=(k.TraversalReference(kind=k.TraversalReferenceKind.MAPPED,reference_id='map:'+preflight['preflight_sha256']),),summary='Admitted native plan; result requires independent HOST proof replay')
    verification=False
    if verify_native is not None and nativeverifiedreceipts and preflight['admitted_ids']:
        verification=verify_native({'before_sha256':beforehash,'after_sha256':afterhash,'receipts':nativeverifiedreceipts,'preflight_sha256':preflight['preflight_sha256']}) is True
    evidence=None
    if verification:
        ref=sha(nativeverifiedreceipts)
        evidence=k.build_verified_consequence_assimilation(source_center_id=center.center_id,consequence_reference='native:'+ref,verification_reference='host-replay:'+ref,assimilation_reference='checkpoint:'+afterhash,next_state_hash=afterhash,next_frame_hash=framehash)
    traversal=k.traverse_merkabah(center=center,terminal=terminal,verified_assimilation=evidence)
    return {'traversal':traversal.model_dump(mode='json'),'host_independent_replay_passed':verification,'host_independence':'Injected verifier contract; flags alone rejected; actual checkpoint replay owned by host','source_pins':pins,'provider_calls':0}
