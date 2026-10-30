"""Stdlib admission control; no native imports, inference or private answer keys."""
import hashlib,json
def digest(v):
    # These admitted contracts use tuples for every serialized array. Rebuild
    # their documented type-tagged scalar/tuple/object serialization in stdlib.
    def tagged(x):
        if x is None:return {'$type':'null'}
        if isinstance(x,bool):return {'$type':'boolean','value':x}
        if isinstance(x,int):return {'$type':'integer','value':x}
        if isinstance(x,float):return {'$type':'float','value':x}
        if isinstance(x,str):return {'$type':'string','value':x}
        if isinstance(x,list):return {'$type':'tuple','value':[tagged(i) for i in x]}
        if isinstance(x,dict):return {'$type':'object','value':{k:tagged(i) for k,i in x.items()}}
        raise ValueError('UNSUPPORTED_CANONICAL_VALUE')
    return hashlib.sha256(json.dumps(tagged(v),sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
PAIRS={'map_id':'map_hash','node_id':'node_hash','relation_id':'relation_hash','edge_id':'edge_hash','dimension_id':'dimension_hash','terminal_id':'terminal_hash','perspective_id':'perspective_hash','invariant_id':'invariant_hash','flower_id':'flower_hash'}
QIDS={'render_id','possibility_field_id','candidate_id','realization_id','prediction_id'}
def require(c):
    if not c:raise ValueError('INDEPENDENT_COMPONENT_CONTRACT')
def hashcheck(v):
    if isinstance(v,dict):
        if len(v)>4:
            for ident,h in PAIRS.items():
                if ident in v and h in v:
                    require(v[h]==digest({k:x for k,x in v.items() if k not in (ident,h)}));require(v[ident].endswith(v[h]))
            for ident in QIDS:
                if ident in v:require(v[ident].endswith(digest({k:x for k,x in v.items() if k!=ident})))
        for x in v.values():hashcheck(x)
    elif isinstance(v,list):
        for x in v:hashcheck(x)

def validate(question,projection,qpre=None,*,omit=None):
    graph=projection['model'];hashcheck(graph)
    nodes={n['node_id']:n for n in graph['vertices']};require(len(nodes)==len(graph['vertices']))
    def ref(r):require(r['node_id'] in nodes and nodes[r['node_id']]['node_hash']==r['node_hash'])
    source=[n for n in nodes.values() if n['kind']=='REALITY_OBJECT'];require(len(source)==1 and source[0]['description']==question)
    for binding in projection['node_bindings']:require(nodes[binding['node_id']]['label']==binding['id']+':'+binding['route'])
    for relation in graph['relations']:
        for r in relation['source_nodes']+relation['target_nodes']:ref(r)
    if omit!='flower':
        centers={f['flower_id']:f for f in graph['flower_lineage']}
        for f in centers.values():
            ref(f['center'])
            for r in f['terminals']:ref(r)
            if f['previous_flower_id'] is not None:
                parent=centers[f['previous_flower_id']];require(f['previous_flower_hash']==parent['flower_hash'] and f['depth']==parent['depth']+1 and f['center'] in parent['terminals'])
    if omit!='sphere':
        views={v['perspective_id']:v for v in graph['perspectives']}
        for v in views.values():
            ref(v['source_reality_object']);n=nodes[v['source_reality_object']['node_id']]
            require(n['kind']=='REALITY_OBJECT' and v['source_observation_bindings']==n['source_observation_bindings'])
        for inv in graph['invariants']:
            ref(inv['source_reality_object']);require(inv['common_observation_bindings']==nodes[inv['source_reality_object']['node_id']]['source_observation_bindings'])
            for r in inv['perspectives']:require(views[r['perspective_id']]['perspective_hash']==r['perspective_hash'])
    if omit!='periodic':
        for d in graph['dimensions']:
            for t in d['terminals']:
                ref(t['node'])
                if t['grounding']=='PHYSICAL_OBSERVATION':require(t['epistemic_status'] in ('MEASURED','VERIFIED') and bool(t['source_observation_bindings']))
    if qpre is not None:
        hashcheck(qpre)
        if omit!='qpre':
            field=qpre['possibility_field'];require(field['source_state_hash']==qpre['source_state_hash'] and field['frame_hash']==qpre['frame_hash'])
            require(all(qpre[k] is False for k in ['actual','verified','authority','memory_eligible']))
            for c in field['candidates']:
                require(all(c[k] is False for k in ['actual','verified','authority','memory_eligible']))
                require(c['source_state_hash']==field['source_state_hash'] and c['frame_hash']==field['frame_hash'])
                require(c['realization']['source_state_hash']==c['source_state_hash'] and c['realization']['frame_hash']==c['frame_hash'])
    return True
