"""Existing typed component execution; numeric geometric rotation unavailable."""
import importlib,json,time
from operator_executor import load

def inspect_components(question,plan_mapping,qpre_render=None):
    start=time.perf_counter_ns();cpu=time.process_time_ns()
    m,q,k,f,E,pins=load()
    if not isinstance(question,str) or not question.strip() or len(question)>4000 or len(question.encode())>4096:raise ValueError('COMPONENT_QUESTION_BOUND')
    if not isinstance(plan_mapping,dict) or set(plan_mapping)-{'model','node_bindings','counts','recenter_scope','typed_readback_verified'}:raise ValueError('MAPPING_FIELDS')
    # Full original content/provenance/closure validation before any effect admission.
    mapping=m.UniversalMap.model_validate_json(json.dumps(plan_mapping['model']))
    sources=[n for n in mapping.vertices if n.kind is m.NodeKind.REALITY_OBJECT]
    if len(sources)!=1 or sources[0].description!=question:raise ValueError('COMPONENT_QUESTION_BINDING')
    bindings=plan_mapping['node_bindings'];nodes={n.node_id:n for n in mapping.vertices}
    if not isinstance(bindings,list) or len(bindings)>12:raise ValueError('COMPONENT_NODE_BOUND')
    if len({b['id'] for b in bindings})!=len(bindings):raise ValueError('DUPLICATE_PLAN_ID')
    for b in bindings:
        if b['node_id'] not in nodes or nodes[b['node_id']].label!=b['id']+':'+b['route']:raise ValueError('NODE_BINDING_MISMATCH')
    periodic=None
    if bindings:
        periodic=m.create_periodic_dimension(name='actual-plan-routes',property_name='Explicit SYMBOLIC route representation; not physical observation',
            terminals=tuple(m.create_periodic_terminal(nodes[b['node_id']],label=b['route']+':'+b['id'],grounding=m.PeriodicGrounding.SYMBOLIC,epistemic_status=E.SYMBOLIC) for b in bindings))
    # Existing mapper builder preserves every input graph field while appending
    # typed periodic differentiation; no arithmetic/geometry is manufactured.
    expanded=m.create_universal_map(vertices=mapping.vertices,hyperedges=mapping.hyperedges,relations=mapping.relations,
        dimensions=(*mapping.dimensions,*((periodic,) if periodic else ())),scales=mapping.scales,
        perspectives=mapping.perspectives,flower_lineage=mapping.flower_lineage,invariants=mapping.invariants,inversions=mapping.inversions)
    qpre=None
    if qpre_render is not None:qpre=q.QPRERender.model_validate_json(json.dumps(qpre_render))
    rotation=importlib.import_module('se666_core.merkabah_rotation').rotate_perspectives(question)
    sphere=importlib.import_module('se666_core.sphere_of_mirrors').reflect_task(question)
    lattice=importlib.import_module('se666_core.flower_of_life_lattice').map_lattice(question)
    result={'schema':'se6-v8-existing-components-v1','source_pins':pins,
        'admission':'VALIDATED_ORIGINAL_TYPED_CONTRACTS; no effect authority',
        'periodic_map':expanded.model_dump(mode='json'),
        'invariants':{'source_vertices_preserved':expanded.vertices==mapping.vertices,'dependencies_preserved':expanded.relations==mapping.relations,
            'perspective_provenance_preserved':expanded.invariants==mapping.invariants,'flower_lineage_preserved':expanded.flower_lineage==mapping.flower_lineage,
            'periodic_symbolic_only':all(t.grounding is m.PeriodicGrounding.SYMBOLIC for d in expanded.dimensions for t in d.terminals),
            'qpre_not_actual':qpre.actual is False if qpre else None},
        'legacy_advisory':{'flower_token_lattice':lattice.model_dump(),'merkabah_rotation_questions':rotation.model_dump(),'sphere_reflection_questions':sphere.model_dump()},
        'numerical_geometric_rotation':{'status':'UNAVAILABLE','reason':'Reviewed original modules contain prompt templates and typed topology, no executable numeric geometric rotation contract'},
        'roundtrip_verified':m.UniversalMap.model_validate_json(expanded.model_dump_json())==expanded,
        'scope':'Actual copied typed contracts and text templates; not full primary equation, semantic inference, physical geometry or forecasting',
        'measurements':{'wall_ns':time.perf_counter_ns()-start,'cpu_ns':time.process_time_ns()-cpu,'provider_calls':0,'external_effects':0}}
    return result
