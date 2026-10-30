"""Source-bound finite C/FoL/D/K/T contract for audited Entity selection.

This is a *bounded computational refinement* of the full-form operators, NOT a
proof of the general symbolic equation or of any physical substrate.  D uses
an authenticated persisted X and the exact Flower terminal set, then K walks
those terminal references; T consumes the differentiated typed value from D.

No authority, World access, model-provider request, file IO, or memory mutation.
"""
from __future__ import annotations

from copy import deepcopy

from . import candidate_state_transition as typed
from .observation_grounding import digest, require

VERSION = 'se6-entity-flower-substrate-trace-v1'
TRANSFORM = 'se6-entity-typed-predicate-T-v1'


def differentiate(*, z: dict, graph, flower, requests_by_node: dict) -> dict:
    """F -> D: preserve every exact Flower terminal, classify its typed path.

    Domain: one audited Entity Z and its source-authenticated mapper/Flower,
    1..12 source nodes with bounded finite typed paths; codomain is a complete
    typed differentiated layer with explicit missingness and exact complements.
    No unknown path becomes a false observation or a fact of the external World.
    """
    require(type(z) is dict and z.get('schema') == 'audited-entity-state-v1' and
            z.get('authority_effect') == 'NONE', 'D_SOURCE_DOMAIN')
    require(type(requests_by_node) is dict and 1 <= len(requests_by_node) <= 12,
            'D_TERMINAL_BOUND')
    vertices = {n.node_id:n for n in graph.vertices}
    terminals = flower.terminals
    require(flower.center.node_id in vertices and
            len(terminals) == len(requests_by_node) and
            {t.node_id for t in terminals} == set(requests_by_node) and
            all(t.node_id in vertices and t == vertices[t.node_id].reference for t in terminals),
            'D_FLOWER_TERMINALS_NOT_EXACT')
    rows = []
    for ref in sorted(terminals, key=lambda ref: ref.node_id):
        r = requests_by_node[ref.node_id]
        require(type(r) is dict and type(r.get('path')) is list and
                1 <= len(r['path']) <= 8, 'D_TYPED_PATH_DOMAIN')
        try:
            value = typed.at(z['X'],r['path'])
            observed = typed.tree(value)
            status = 'PRESENT'
        except ValueError:
            observed = None
            status = 'MISSING'
        rows.append(dict(node=ref.node_id, node_hash=ref.node_hash,
                         request_id=r['id'], path=deepcopy(r['path']),
                         presence=status, observed_typed=observed,
                         # These dimensions are computational path/type axes,
                         # not assertions of physical substrate coordinates.
                         path_depth=len(r['path']),
                         primitive_tag=(observed[0] if observed else 'unknown')))
    result=dict(version=VERSION, domain=z['schema'], entity=z['entity'],
                x_hash=z['source_state_hash'], frame_hash=z['Theta']['theta_hash'],
                receipt_id=z['E']['receipt_id'], source_projection=z['E']['source_projection'],
                map_hash=graph.map_hash,
                flower_hash=flower.flower_hash, rows=rows,
                epistemic_scope='PERSISTED_ENTITY_NOT_EXTERNAL_WORLD',authority_effect='NONE')
    result['differentiation_hash']=digest(result)
    return result


def transform(*, z: dict, differentiation: dict, request: dict,
              node_id: str, traversal) -> dict:
    """K -> T: compare a typed value supplied by D, not a new raw path lookup.

    Domain: source-coherent D row and K terminal for a bounded Entity X path.
    Codomain: MATCH, CONTRADICTED_BY_PERSISTED_STATE, or UNKNOWN_PATH,
    with a self-contained typed-value witness and explicit source/trace pins.

    Invariants: (1) no unknown=>false coercion, (2) no bool/int alias,
    (3) typed D value must equal the actual audited X path, (4) K must
    traverse exactly this D node, (5) no World truth/authority is produced.
    """
    expected_hash = differentiation.get('differentiation_hash')
    require(type(expected_hash) is str and
            expected_hash == digest({k:v for k,v in differentiation.items()
                                    if k != 'differentiation_hash'}), 'T_D_INTEGRITY')
    require(differentiation['x_hash'] == z['source_state_hash'] and
            differentiation['entity'] == z['entity'] and
            differentiation['domain'] == z['schema'] and
            differentiation['frame_hash'] == z['Theta']['theta_hash'] and
            differentiation['receipt_id'] == z['E']['receipt_id'] and
            differentiation['source_projection'] == z['E']['source_projection'] and
            differentiation['authority_effect'] == 'NONE', 'T_STATE_SCOPE')
    rows = [row for row in differentiation['rows'] if row['node'] == node_id]
    require(len(rows)==1 and rows[0]['request_id'] == request['id'] and
            typed.exact(rows[0]['path'],request['path']), 'T_D_NODE_SCOPE')
    from .merkabah_traversal import TraversalReferenceKind
    require(traversal.terminal.references and
            len(traversal.terminal.references) == 1 and
            traversal.terminal.references[0].kind is TraversalReferenceKind.MAPPED and
            traversal.terminal.references[0].reference_id == node_id and
            traversal.source_center.state_hash == z['source_state_hash'] and
            traversal.source_center.frame_hash == z['Theta']['theta_hash'] and
            traversal.terminal.source_center_id == traversal.source_center.center_id,
            'T_K_TERMINAL_NOT_CONSUMED')
    row=rows[0]
    expected_typed=typed.tree(request['equals'])
    if row['presence']=='MISSING':
        require(row['observed_typed'] is None and
                row['primitive_tag']=='unknown', 'T_D_MISSINGNESS_INTEGRITY')
        try:
            typed.at(z['X'], row['path'])
        except ValueError:
            pass
        else:
            raise ValueError('T_D_OMITTED_PRESENT_VALUE')
        match=False;status='UNKNOWN_PATH'
    else:
        require(row['presence']=='PRESENT' and row['observed_typed'] is not None,
                'T_D_PRESENCE_STATUS')
        observed=typed.un_tree(row['observed_typed'])
        try:
            live=typed.at(z['X'],row['path'])
        except ValueError as e:
            raise ValueError('T_D_MISSING_AUTHENTIC_VALUE') from e
        require(typed.exact(observed,live) and
                row['primitive_tag']==row['observed_typed'][0],
                'T_D_AUTHENTIC_VALUE_MISMATCH')
        match=typed.exact(observed,request['equals'])
        status='MATCH' if match else 'CONTRADICTED_BY_PERSISTED_STATE'
    return dict(version=TRANSFORM, match=match, status=status,
                path=deepcopy(row['path']), expected=expected_typed,
                observed_typed=deepcopy(row['observed_typed']),
                state_hash=z['source_state_hash'],
                substrate_hash=differentiation['differentiation_hash'],
                map_hash=differentiation['map_hash'],
                flower_hash=differentiation['flower_hash'],
                traversal_id=traversal.traversal_id,
                epistemic_scope='PERSISTED_ENTITY_NOT_EXTERNAL_WORLD',
                authority_effect='NONE')


TYPED_OUTPUT = 'se6-actual-typed-fol-d-k-t-output-v1-development'
TYPED_FIELD_PREFIX = 'canonical-typed-output-'


def actual_typed_output(*, z, graph, flower, requests_by_node, node_id,
                        traversal, expected_observation_bindings):
    """Return the actual partial-map output with its lossless typed inputs.

    This is not a representation of owner Phi/K/G-adjoint/cube by matrices.
    No scalar projection or aggregation is defined here. Full graph topology,
    values/types, state/frame, retained knowledge and uncertainty are retained.
    Authentication comes from the enclosing current-Entity rebinding path.
    """
    from .universal_mapper import UniversalMap, FlowerCenter
    from .merkabah_traversal import MerkabahTraversal, traverse_merkabah
    graph=UniversalMap.model_validate_json(graph.model_dump_json())
    flower=FlowerCenter.model_validate_json(flower.model_dump_json())
    traversal=MerkabahTraversal.model_validate_json(traversal.model_dump_json())
    require(traversal.verified_assimilation is None and not traversal.state_changed and
            traversal == traverse_merkabah(center=traversal.source_center,terminal=traversal.terminal),
            'TYPED_OUTPUT_ACTUAL_PROPOSAL_TRAVERSAL_REQUIRED')
    vertices={v.node_id:v for v in graph.vertices}
    require(type(expected_observation_bindings) is tuple and bool(expected_observation_bindings) and
            flower.center.node_id in vertices and
            vertices[flower.center.node_id].reference == flower.center and
            vertices[flower.center.node_id].source_observation_bindings == expected_observation_bindings,
            'TYPED_OUTPUT_FLOWER_SOURCE')
    require(all(r.node_id in vertices and vertices[r.node_id].reference == r and
                vertices[r.node_id].source_observation_bindings == expected_observation_bindings
                for r in flower.terminals), 'TYPED_OUTPUT_TERMINAL_SOURCE')
    links={(s.node_id,t.node_id) for relation in graph.relations
           for s in relation.source_nodes for t in relation.target_nodes}
    require(all((flower.center.node_id,r.node_id) in links for r in flower.terminals),
            'TYPED_OUTPUT_FLOWER_GRAPH_CONNECTION')
    differentiated=differentiate(z=z,graph=graph,flower=flower,requests_by_node=requests_by_node)
    require(node_id in requests_by_node,'TYPED_OUTPUT_REQUEST_MISSING')
    transformed=transform(z=z,differentiation=differentiated,
        request=requests_by_node[node_id],node_id=node_id,traversal=traversal)
    result=dict(version=TYPED_OUTPUT,source=deepcopy(z),
        graph=graph.model_dump(mode='json'),flower=flower.model_dump(mode='json'),
        requests_by_node=deepcopy(requests_by_node),selected_node=node_id,
        differentiation=differentiated,traversal=traversal.model_dump(mode='json'),
        transform=transformed,
        observation_bindings=[b.model_dump(mode='json') for b in expected_observation_bindings],
        scope='ACTUAL_TYPED_OPERATIONAL_PARTIAL_MAPS_NOT_OWNER_NUMERATOR_EQUIVALENCE',
        authority_effect='NONE')
    # The existing finite-tree contract supplies the injective representation.
    require(typed.exact(typed.un_tree(typed.tree(result)),result),'TYPED_OUTPUT_ROUND_TRIP')
    return result


def typed_output_fields(result):
    """Lossless QPRE transport, within its existing 1024-character field cap.

    Chunking is a representation only. No information is dropped or replaced
    with a hash, and no operator semantics depend on arbitrary numeric features.
    """
    import json
    import base64
    from .qpre import CandidateStateField
    require(type(result) is dict and result.get('version')==TYPED_OUTPUT,'TYPED_OUTPUT_DOMAIN')
    text=json.dumps(typed.tree(result),ensure_ascii=False,sort_keys=True,separators=(',',':'))
    text=base64.b64encode(text.encode('utf-8')).decode('ascii')
    return tuple(CandidateStateField(name=TYPED_FIELD_PREFIX+str(i//1024).zfill(6),
                                   possible_value=text[i:i+1024])
                 for i in range(0,len(text),1024))


def decode_typed_output(candidate):
    """Decode full QPRE data; this does not authenticate or certify it."""
    import json
    import base64
    fields=candidate.realization.candidate_state[1:]
    require(bool(fields) and all(f.name==TYPED_FIELD_PREFIX+str(i).zfill(6)
            for i,f in enumerate(fields)), 'TYPED_OUTPUT_MISSING_OR_REORDERED')
    encoded=''.join(f.possible_value for f in fields)
    try:
        raw=base64.b64decode(encoded,validate=True)
        require(base64.b64encode(raw).decode('ascii')==encoded,'TYPED_OUTPUT_NONCANONICAL_BASE64')
        text=raw.decode('utf-8')
        value=typed.un_tree(json.loads(text))
    except (ValueError,TypeError,KeyError) as e:
        raise ValueError('TYPED_OUTPUT_NOT_CANONICAL') from e
    require(type(value) is dict and value.get('version')==TYPED_OUTPUT and
            text==json.dumps(typed.tree(value),ensure_ascii=False,sort_keys=True,separators=(',',':')),
            'TYPED_OUTPUT_NONCANONICAL_TRANSPORT')
    return value


def consume_typed_output(candidate, **actual_inputs):
    """Sphere reads QPRE's full output, rederives it, and returns its T result.

    The returned predicate, not a parallel pre-render lookup, gates projection.
    Missing, changed, cross-state or type-erased transport fails closed.
    """
    decoded=decode_typed_output(candidate)
    independently_recomputed=actual_typed_output(**actual_inputs)
    require(typed.exact(decoded,independently_recomputed), 'TYPED_OUTPUT_ACTUAL_SOURCE_MISMATCH')
    return decoded['transform']
