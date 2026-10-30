"""Opt-in witnessed invariant -> derived Sphere concern -> existing Boundary.

Only the independently admitted host can authenticate observations. Geometry
locates evidence; it supplies neither truth nor action authority. Version one
supports a Boolean, action/payload-specific invariant under exact source,
epoch, public history and base-frame semantics. A refusal is a local decision,
never a World effect or a calibration outcome.
"""
from copy import deepcopy
from dataclasses import asdict
import json

from .observation_grounding import digest, require
from . import universal_mapper as mapper, realization_frame as frames
from .epistemic_status import EpistemicStatus as E

VERSION = 'se6-witnessed-reflection-consequence-v1'
PREDICATE = 'ACTION_PRESERVES_BOOLEAN_INVARIANT_V1'


def validate_config(config):
    require(type(config) is dict and set(config) == {'version', 'enabled', 'evidence'}, 'REFLECTION_CONFIG_FIELDS')
    require(config['version'] == VERSION and type(config['enabled']) is bool, 'REFLECTION_CONFIG_VERSION')
    require(type(config['evidence']) is list and 0 < len(config['evidence']) <= 16, 'REFLECTION_EVIDENCE_BOUND')
    ids = []
    for row in config['evidence']:
        require(type(row) is dict and set(row) == {'version', 'evidence_id', 'entity_id', 'source', 'epoch',
            'history_sha256', 'base_frame_sha256', 'action_id', 'payload_sha256', 'invariant_id',
            'predicate', 'observed_holds', 'witness_reference'}, 'REFLECTION_EVIDENCE_FIELDS')
        require(row['version'] == VERSION and row['predicate'] == PREDICATE and
            type(row['observed_holds']) is bool, 'REFLECTION_SUPPORTED_PREDICATE')
        require(all(type(row[k]) is str and row[k] for k in row if k != 'observed_holds'), 'REFLECTION_EVIDENCE_STRINGS')
        require(row['evidence_id'] == digest({k: v for k, v in row.items() if k != 'evidence_id'}), 'REFLECTION_EVIDENCE_HASH')
        ids.append(row['evidence_id'])
    require(len(ids) == len(set(ids)), 'REFLECTION_DUPLICATE_EVIDENCE')


def authenticate(config, authority, binding, history, actions, frame):
    validate_config(config)
    admitted = {a['id']: a for a in actions}
    verifier = getattr(authority, 'authenticate_reflection_evidence', None)
    require(callable(verifier), 'REFLECTION_INDEPENDENT_AUTHORITY_REQUIRED')
    for row in config['evidence']:
        require(all(row[k] == binding[k] for k in ('entity_id', 'source', 'epoch')) and
            row['history_sha256'] == digest(history) and row['base_frame_sha256'] == digest(frame), 'REFLECTION_SOURCE_SCOPE')
        require(row['action_id'] in admitted and row['payload_sha256'] == digest(admitted[row['action_id']]['payload']),
            'REFLECTION_ACTION_PAYLOAD')
        require(verifier(deepcopy(row)) is True, 'REFLECTION_INDEPENDENT_WITNESS_REQUIRED')
    return deepcopy(config['evidence'])


def augment_graph(graph, rows):
    """Called only after the Native host's exact evidence authentication."""
    graph = mapper.UniversalMap.model_validate_json(json.dumps(graph))
    nodes = list(graph.vertices); relations = list(graph.relations)
    center = nodes[0]
    predictions = {r.node_id for e in relations if e.label == 'action-conditioned-prediction'
        and e.source_nodes == (center.reference,) for r in e.target_nodes}
    for row in rows:
        observation = frames.create_source_observation(source_reference=row['witness_reference'],
            summary='Independently witnessed Boolean invariant for exact admitted action payload',
            epistemic_status=E.VERIFIED, evidence_references=('evidence:' + row['evidence_id'],))
        evidence = mapper.create_mapper_node(kind=mapper.NodeKind.EVENT, label='witness:' + row['evidence_id'],
            description=json.dumps(row, sort_keys=True, separators=(',', ':')), epistemic_status=E.VERIFIED,
            source_observations=(observation,))
        nodes.append(evidence)
        for node in graph.vertices:
            if node.node_id not in predictions:
                continue
            prediction = json.loads(node.description)
            if prediction['continuation'][0] == row['action_id']:
                relations.append(mapper.create_mapper_relation(
                    kind=mapper.RelationKind.INVARIANT_OF if row['observed_holds'] else mapper.RelationKind.CONTRADICTS,
                    label='verified-invariant-evidence', source_nodes=(node,), target_nodes=(evidence,),
                    epistemic_status=E.VERIFIED, source_observations=(observation,)))
    return mapper.create_universal_map(vertices=nodes, relations=relations).model_dump(mode='json')


def findings(graph, audit, selected_id, rows, config):
    """Exact view/evidence/candidate bindings; support count confers no authority."""
    validate_config(config)
    projection = audit['native_sphere_projection']
    require(projection['projection_sha256'] == digest({k: v for k, v in projection.items() if k != 'projection_sha256'}),
        'REFLECTION_PROJECTION_HASH')
    result = dict(version=VERSION, enabled=config['enabled'], binding=deepcopy(projection['binding']),
        selected_candidate_id=selected_id, consequences=[], uncertainty=[], authority_effect='NONE')
    field = audit['possibility_field']
    selected = next(c for c in field['candidates'] if c['candidate_id'] == selected_id)
    node_id = selected['provenance_references'][0]
    sphere = audit.get('continuous_sphere')
    if sphere is None:
        result['uncertainty'].append('LEGACY_PROMPTS_DO_NOT_ESTABLISH_EVIDENCE_VISIBILITY')
    else:
        from . import sphere_continuous, qpre, merkabah_traversal
        typed_graph = mapper.UniversalMap.model_validate_json(json.dumps(graph))
        typed_render = qpre.QPRERender.model_validate_json(json.dumps(audit['probability_learning']['render']['base_render']))
        exact = sphere_continuous.render_sphere(graph=typed_graph,
            scene=sphere_continuous.SphereScene.model_validate_json(json.dumps(sphere['scene'])),
            traversals=tuple(merkabah_traversal.MerkabahTraversal.model_validate_json(json.dumps(t)) for t in audit['traversals']),
            qpre_render=typed_render).model_dump(mode='json')
        require(exact == sphere and projection['reflection_sha256'] == digest(sphere), 'REFLECTION_EXACT_RENDER')
        probability = audit['probability_learning']['render']
        require(projection['binding']['probability_render_id'] == probability['render_id'] and
            projection['binding']['calibration_state_hash'] == probability['calibration_state_hash'], 'REFLECTION_CALIBRATION_BINDING')
        evidence_nodes = {n['label'][8:]: n for n in graph['vertices'] if n['label'].startswith('witness:')}
        for row in rows:
            evidence = evidence_nodes[row['evidence_id']]
            require(json.loads(evidence['description']) == row, 'REFLECTION_EXACT_EVIDENCE_NODE')
            relevant = [r for r in graph['relations'] if r['label'] == 'verified-invariant-evidence' and
                r['source_nodes'][0]['node_id'] == node_id and r['target_nodes'][0]['node_id'] == evidence['node_id']]
            for relation in relevant:
                views = [v for v in sphere['views'] if relation['relation_id'] in v['visible_relations']]
                if not views:
                    result['uncertainty'].append('EVIDENCE_OUTSIDE_ADMITTED_VIEW:' + row['evidence_id'])
                for view in views:
                    lens = next(l for l in sphere['scene']['lenses'] if l['lens_id'] == view['lens_id'])
                    result['consequences'].append(dict(evidence_id=row['evidence_id'], witness_reference=row['witness_reference'],
                        candidate_id=selected_id, claim=row['predicate'], invariant_id=row['invariant_id'],
                        observed_holds=row['observed_holds'], epistemic_class='INDEPENDENTLY_WITNESSED_INVARIANT',
                        relation_id=relation['relation_id'], source_observation_bindings=evidence['source_observation_bindings'],
                        sphere_render_id=sphere['sphere_render_id'], view_id=view['view_id'], lens=deepcopy(lens),
                        permitted_consequence='RETAIN_ELIGIBILITY' if row['observed_holds'] else 'REFUSE'))
    result['requires_conflict_check'] = config['enabled'] and any(not r['observed_holds'] for r in result['consequences'])
    result['receipt_sha256'] = digest(result)
    return result


def apply_boundary(decision, state, core, binding, actions, boundary):
    """Reuse kernel transition_coherence for the exact proposed action.

    This is a necessary veto only. A nonconflicting result cannot grant host
    dispatch rights. The Native GROUNDING_EVALUATE computation remains separate.
    """
    audit = decision.get('selection', {})
    receipt = audit.get('reflection_consequences')
    if receipt is None or not receipt['requires_conflict_check']:
        return decision
    require(decision['status'] == 'GOAL_PATH_PREDICTED' and
        receipt['receipt_sha256'] == digest({k:v for k,v in receipt.items() if k != 'receipt_sha256'}), 'REFLECTION_DECISION_BINDING')
    action = next(a for a in actions if a['id'] == decision['actions'][0])
    observation = core.SEObservation('REFLECTION_INVARIANT_CHECK', binding['entity_id'], PREDICATE,
        source=binding['source'], evidence_refs=tuple(r['witness_reference'] for r in receipt['consequences']))
    candidate = core.SECandidateTransition(state.state_hash, observation.observation_id, None, (), True,
        core.SEAction(action['id'], json.dumps(action['payload'], sort_keys=True)), 'Preserve admitted witnessed invariant')
    context = core._context(dict(identity=binding['entity_id'], authorized=boundary['authorized'],
        permissions=boundary['permissions'], integrity_valid=True, evidence_valid=True,
        max_actions=boundary['max_native_actions'], risk=0, max_risk=0, sensitive=False, human_approval_for=None))
    result = core._bound(state, observation, candidate, context)
    require(result.outcome == 'REFUSE' and 'EXPLICIT_CORRECTION_REQUIRED' in result.reasons, 'REFLECTION_BOUNDARY_VETO')
    audit['reflection_boundary'] = dict(decision=asdict(result), candidate=asdict(candidate),
        source_native_state=state.state_hash, observation=asdict(observation), context=context,
        consequence_receipt=receipt['receipt_sha256'], world_effects=0)
    return dict(status='UNKNOWN', actions=[], reason='WITNESSED_INVARIANT_BOUNDARY_REFUSED', selection=audit)
