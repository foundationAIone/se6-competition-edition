"""Opt-in DEVELOPMENT finite-consensus selection; no effects or new authority.

Reuses Flower, Merkabah traversal, QPRE and the existing fixed-point evaluator.
The numeric policy is an explicit host input, not learned authority. This is a
bounded candidate coupling, NOT a realization of all full-form operators.
"""
import json

from . import universal_mapper as mapper, merkabah_traversal as traversal, qpre
from .symbolic_realization import _evaluation
from .observation_grounding import digest, require
POST_QPRE_ORDER = 'qpre-before-sphere-v1'

VERSION = 'se6-grounded-consensus-selection-candidate-v1'
PILLARS = {'AUTHENTICITY', 'INTEGRITY', 'RESPONSIBILITY', 'ENRICHMENT'}
REVERSIBILITY = ['REVERSIBLE', 'PARTIALLY_REVERSIBLE', 'UNKNOWN', 'IRREVERSIBLE']


def validate_policy(policy):
    """Pure admission shape check, before any effect or permission request."""
    require(type(policy) is dict, 'SELECTION_POLICY_OBJECT')
    require(set(policy)-{'state_semantics','native_correspondence','retention_limits','representation_seed','decision_inputs_version','operator_order_contract','probability_learning','native_sphere','reflection_consequences','native_relation_transport','native_expected_value','native_material_contract','native_typed_valuation','native_situated_awareness'} == {'version', 'goal_value_units', 'uncertainty_units',
            'frame', 'actions'}, 'SELECTION_POLICY_FIELDS')
    if 'native_situated_awareness' in policy:
        from .native_situated_awareness import validate_config
        validate_config(policy['native_situated_awareness'])
        require(policy.get('operator_order_contract')==POST_QPRE_ORDER and
            policy.get('native_sphere',{}).get('mode')=='DYNAMIC','NATIVE_SITUATED_DYNAMIC_SOURCE_ORDER')
    if 'native_typed_valuation' in policy:
        from .native_typed_valuation import validate_config
        validate_config(policy['native_typed_valuation'])
        require('native_expected_value' not in policy and 'probability_learning' in policy and
            'native_material_contract' in policy and policy.get('operator_order_contract')==POST_QPRE_ORDER,
            'NATIVE_TYPED_VALUE_CALIBRATION_CAP_ORDER')
    if 'native_material_contract' in policy:
        from .grounded_native_input import NATIVE_MATERIAL_CAP_CONTRACT_V2
        require(policy['native_material_contract']==NATIVE_MATERIAL_CAP_CONTRACT_V2,'NATIVE_EXACT_MATERIAL_CONTRACT')
    if 'native_expected_value' in policy:
        from .native_expected_value import validate_config
        validate_config(policy['native_expected_value'])
        require('probability_learning' in policy and 'native_material_contract' in policy and
            policy.get('operator_order_contract')==POST_QPRE_ORDER,'NATIVE_VALUE_CALIBRATION_CAP_ORDER')
    if 'native_relation_transport' in policy:
        from .native_merkabah_transport import VERSION as transport_version
        require(policy['native_relation_transport']==transport_version and
                policy.get('operator_order_contract')==POST_QPRE_ORDER,
                'NATIVE_TRANSPORT_TYPED_POST_QPRE_CONTRACT')
    if 'reflection_consequences' in policy:
        from .native_reflection_consequences import validate_config
        validate_config(policy['reflection_consequences'])
        require('native_sphere' in policy and 'probability_learning' in policy,
                'REFLECTION_REQUIRES_NATIVE_SPHERE_CALIBRATION')
    if 'native_sphere' in policy:
        from .native_sphere_projection import validate_policy as validate_sphere_policy
        validate_sphere_policy(policy['native_sphere'])
        require(policy.get('operator_order_contract')==POST_QPRE_ORDER,'NATIVE_SPHERE_POST_QPRE_REQUIRED')
    if 'probability_learning' in policy:
        from .qpre_native_learning import VERSION as learning_version
        require(policy['probability_learning']==learning_version, 'NATIVE_PROBABILITY_POLICY_VERSION')
    if 'operator_order_contract' in policy:
        require(policy['operator_order_contract'] == POST_QPRE_ORDER and
                'state_semantics' in policy and 'decision_inputs_version' in policy,
                'POST_QPRE_ORDER_REQUIRES_TYPED_SEMANTICS')
    if 'state_semantics' in policy:
        from .candidate_state_transition import validate_config
        validate_config(policy['state_semantics'])
    if 'decision_inputs_version' in policy:
        from .candidate_state_transition import INPUT_VERSION
        require(policy['decision_inputs_version']==INPUT_VERSION and 'state_semantics' in policy,
                'DECISION_INPUT_POLICY')
    if 'representation_seed' in policy:
        from .grounded_canonical_context import VERSION as NATIVE_VERSION,REPRESENTATION_VERSION
        require(policy.get('native_correspondence')==NATIVE_VERSION and
                policy['representation_seed']==REPRESENTATION_VERSION,'REPRESENTATION_POLICY_BINDING')
    if 'native_correspondence' in policy or 'retention_limits' in policy:
        from . import grounded_canonical_context as canonical_state
        require('state_semantics' in policy, 'CANONICAL_STATE_SEMANTICS_REQUIRED')
        if 'native_correspondence' in policy:
            require(policy['native_correspondence'] == canonical_state.VERSION, 'NATIVE_CORRESPONDENCE_VERSION')
        if 'retention_limits' in policy:
            canonical_state.limits(policy['retention_limits'])
    require(policy['version'] == VERSION, 'SELECTION_POLICY_VERSION')
    for name in ('goal_value_units', 'uncertainty_units'):
        require(type(policy[name]) is int and 0 <= policy[name] <= 1000000, 'SELECTION_FIXED_POINT')
    require(policy['frame'] == {'domain': 'finite-action-history', 'basis': 'opaque-observation-history',
            'version': 1}, 'SELECTION_DECLARED_FRAME')
    require(type(policy['actions']) is dict and 0 < len(policy['actions']) <= 64
            and all(type(k) is str and 0 < len(k) <= 128 for k in policy['actions']), 'SELECTION_POLICY_ACTIONS')
    for value in policy['actions'].values():
        require(set(value) == {'risk_units', 'reversibility', 'conduct'}, 'SELECTION_ASSESSMENT_FIELDS')
        require(type(value['risk_units']) is int and 0 <= value['risk_units'] <= 100, 'SELECTION_RISK_UNITS')
        require(value['reversibility'] in REVERSIBILITY, 'SELECTION_REVERSIBILITY')
        require(set(value['conduct']) == PILLARS and all(type(x) is bool for x in value['conduct'].values()),
                'SELECTION_FOUR_PILLARS')


def select_mapped(graph, admitted, boundary, binding, *, semantic=None, probability_state=None, sphere_scene=None):
    """Consume attributable graph edges before selecting an executable prefix.

    Consensus predictions use a degenerate conditional expectation, NOT a
    probability inferred from model counts. Unknown outcomes are not assigned
    zero risk or a probability. Units and uncertainty charge must be explicit.
    """
    policy = boundary['selection_policy']
    validate_policy(policy)
    post_qpre = policy.get('operator_order_contract') == POST_QPRE_ORDER
    if sphere_scene is not None:
        from .sphere_continuous import SphereScene
        require(post_qpre and semantic is not None and isinstance(sphere_scene,SphereScene),
                'CONTINUOUS_SPHERE_REQUIRES_POST_QPRE_TYPED_CONTRACT')
        require('native_sphere' not in policy,'NATIVE_SPHERE_AMBIGUOUS_SCENE')
    require(binding and boundary['authorized'] is True and boundary['identity'] == binding['entity_id'],
            'SELECTION_CURRENT_AUTHORITY')
    prices = {a['id']: a['cost'] for a in admitted}
    require(len(prices) == len(admitted) and set(prices) <= set(boundary['permissions']), 'SELECTION_ACTION_AUTHORITY')
    require(set(policy['actions']) == set(prices), 'SELECTION_COMPLETE_ASSESSMENTS')
    native = None
    if 'native_correspondence' in policy:
        from .grounded_canonical_context import effective_native_limit
        require(semantic is not None and 'native_context' in semantic, 'NATIVE_CONTEXT_REQUIRED')
        native = semantic['native_context']
        if 'representation_seed' in policy:
            from .grounded_canonical_context import require_generative_reference
            interpreted=require_generative_reference(native)
            require(interpreted['current_state']['identity']==binding['entity_id'],'REPRESENTATION_ENTITY')
        require(native['current_state_sha256'] == binding['entity_state']
                and native['current_state']['identity'] == binding['entity_id'], 'NATIVE_CONTEXT_CURRENT_BINDING')
        if native['current_state']['actions_used'] >= effective_native_limit(native,boundary['max_native_actions']):
            return dict(status='UNKNOWN',actions=[],reason='SAVED_NATIVE_RESOURCE_LIMIT',authority_effect='NONE')
    if 'state_semantics' in policy:
        from . import candidate_state_transition as state_ops
        require(semantic is not None,'STATE_SEMANTICS_INPUT_REQUIRED')
        if not semantic['eligible']:
            return dict(status='UNKNOWN',actions=[],reason='NO_APPLICABLE_RETAINED_RELATION',
                        state_sha256=digest(semantic['packet']),authority_effect='NONE')
        current_state=state_ops.recover(semantic['packet'],semantic['packet']['context'])
        retained_unknown=tuple(current_state['U'])
    else:
        retained_unknown=()
    inputs=semantic.get('decision_inputs') if semantic is not None else None
    if 'decision_inputs_version' in policy:
        require(inputs is not None,'TYPED_DECISION_INPUT_REQUIRED')
        retained_unknown+=tuple(inputs['uncertainty'])
        if not inputs['observation_allowed']:
            return dict(status='UNKNOWN',actions=[],reason='CURRENT_OBSERVATION_NOT_JUSTIFIED',
                selection=dict(version=VERSION,decision_inputs=inputs,authority_effect='NONE',full_canonical=False))
    graph = mapper.UniversalMap.model_validate_json(json.dumps(graph))
    center = graph.vertices[0]
    require(center.label == binding['entity_id'], 'SELECTION_CENTER_ENTITY')
    if native is not None:
        from .grounded_canonical_context import center_view
        require(json.loads(center.description) == center_view(native), 'CENTER_COMPLETE_NATIVE_CONTEXT')
    # Only exact outgoing learned relations provide eligible terminals. Orphan
    # nodes cannot become candidates merely by their position in a JSON list.
    refs = {r.node_id for edge in graph.relations
            if edge.label == 'action-conditioned-prediction' and edge.source_nodes == (center.reference,)
            for r in edge.target_nodes}
    terminals = sorted((n for n in graph.vertices if n.node_id in refs), key=lambda n: n.node_id)
    require(len(terminals) <= 64, 'SELECTION_QPRE_BOUND')
    if not terminals:
        return dict(status='UNKNOWN', actions=[], reason='NO_MAPPED_RELATIONAL_PATH',
                    selection=dict(version=VERSION, policy_sha256=digest(policy), binding=binding,
                                   authority_effect='NONE', full_canonical=False))
    flower = mapper.create_flower_center(center, terminals=terminals)
    frame=inputs['frame'] if inputs else policy['frame']
    tcenter = traversal.build_traversal_center(state_hash=binding['entity_state'], frame_hash=digest(frame))
    by_node = {n.node_id: n for n in terminals}
    candidates, lookup, traces, excluded = [], {}, [], []
    terminal_refs=flower.terminals
    substrates=None
    if semantic is not None:
        substrates=state_ops.differentiate(terminals,inputs)
        by_ref={r.node_id:r for r in flower.terminals}
        terminal_refs=[by_ref[n] for fiber in substrates for n in fiber['nodes']]
    transformed={};reflected={};predictions_by_node={};route_ids_by_node={};routes_by_node={}
    for terminal_ref in terminal_refs:
        node = by_node[terminal_ref.node_id]
        # Traversal references, rather than the caller's proposed answer,
        # determine which mapped prediction reaches the possibility renderer.
        terminal = traversal.build_traversal_terminal(source_center_id=tcenter.center_id,
            references=(traversal.TraversalReference(kind=traversal.TraversalReferenceKind.MAPPED,
                        reference_id=node.node_id),), summary='Inspect an action-conditioned mapped prediction')
        route = traversal.traverse_merkabah(center=tcenter, terminal=terminal)
        prediction = json.loads(by_node[route.terminal.references[0].reference_id].description)
        predictions_by_node[node.node_id] = prediction
        route_ids_by_node[node.node_id] = route.traversal_id
        routes_by_node[node.node_id] = route
        word = prediction['continuation']
        require(word and set(word) <= set(prices), 'SELECTION_PREDICTION_ACTIONS')
        require(node.source_observation_bindings == center.source_observation_bindings, 'SELECTION_PREDICTION_PROVENANCE')
        if semantic is not None:
            transformed[node.node_id]=state_ops.transform_trace(prediction,semantic['proposal'],semantic['history'])
        reasons = []
        if prediction['status'] != 'PREDICTED_WITHIN_BOUND' or prediction['outcomes'] is None:
            reasons.append('UNKNOWN_CONSEQUENCE')
        elif len(prediction['outcomes']) != len(word) or prediction['outcomes'][-1][1] is not True:
            reasons.append('NO_PREDICTED_GOAL')
        cost = sum(prices[a] for a in word)
        risk = sum(policy['actions'][a]['risk_units'] for a in word)
        rev = max((policy['actions'][a]['reversibility'] for a in word), key=REVERSIBILITY.index)
        if any(policy['actions'][a]['reversibility'] == 'UNKNOWN' for a in word):
            reasons.append('UNKNOWN_IRREVERSIBILITY')
        if risk > 100: reasons.append('QPRE_RISK_DOMAIN')
        if any(not all(policy['actions'][a]['conduct'].values()) for a in word): reasons.append('CONDUCT_REFUSED')
        if len(word) > min(boundary['remaining_actions'], boundary['remaining_effects']) or cost > boundary['remaining_cost']:
            reasons.append('RESOURCE_REFUSED')
        if reasons:
            excluded.append({'node_id': node.node_id, 'reasons': reasons}); continue
        provenance = (node.node_id, route.traversal_id)
        sphere_unknown=()
        if semantic is not None:
            reflected[node.node_id]=state_ops.reflect(transformed[node.node_id],prediction,cost,prices,semantic['eligible'],inputs)
            if inputs is not None:
                sphere=reflected[node.node_id]['sphere'];sphere_unknown=tuple(sphere['uncertainty'])
                provenance+=(sphere['graph']['map_hash'],sphere['source_frame'])
        realized = qpre.build_candidate_realization(source_state_hash=tcenter.state_hash, frame_hash=tcenter.frame_hash,
            candidate_state=(qpre.CandidateStateField(name='continuation', possible_value=json.dumps(word)),),
            transformations=(qpre.TransformationStep(operation=VERSION, input_reference=node.node_id,
                            possible_output='Conditional finite-history goal prediction'),),
            predicted_consequences=(qpre.build_predicted_consequence(summary=json.dumps(prediction['outcomes']),
                                    provenance_references=provenance),),
            reversibility=qpre.Reversibility(rev), cost_units=cost, risk_score=risk, provenance_references=provenance)
        candidate = qpre.build_qpre_candidate(source_state_hash=tcenter.state_hash, frame_hash=tcenter.frame_hash,
            assumptions=('Finite learned model remains applicable within admitted source and epoch.',),
            uncertainty=qpre.StructuredUncertainty(known=('All retained consistent models agree on this continuation.',),
                unknown=tuple(dict.fromkeys(retained_unknown+sphere_unknown+('Generalization outside observed finite model class is not established.',))),
                assumptions=('Finite learned model remains applicable within admitted source and epoch.',)),
            realization=realized, provenance_references=provenance)
        candidates.append(candidate); lookup[candidate.candidate_id] = prediction
        traces.append(route.model_dump(mode='json'))
    audit = dict(version=VERSION, policy_sha256=digest(policy), binding=binding, flower=flower.model_dump(mode='json'),
                 traversals=traces, excluded=excluded, authority_effect='NONE', full_canonical=False)
    if native is not None: audit['native_context'] = native
    if inputs is not None:audit['decision_inputs']=inputs
    if not candidates:
        return dict(status='UNKNOWN', actions=[], reason='NO_DEFINED_ADMISSIBLE_GOAL_PATH', selection=audit)
    render = qpre.render_qpre(qpre.build_possibility_field(source_state_hash=tcenter.state_hash,
                                frame_hash=tcenter.frame_hash, candidates=candidates))
    probability_render=None
    if 'probability_learning' in policy:
        from .qpre_native_learning import probability_render as build_probability_render
        require(probability_state is not None,'NATIVE_PROBABILITY_STATE_REQUIRED')
        probability_render=build_probability_render(render,lookup,policy,binding,probability_state)
    field = render.possibility_field
    evaluated_candidates=field.candidates
    if semantic is not None:
        if post_qpre:
            from .grounded_post_qpre_sphere import VERSION as stage_version, sphere_over_render
            require(stage_version == POST_QPRE_ORDER, 'SPHERE_STAGE_SOURCE_VERSION')
            rows=sphere_over_render(render,predictions_by_node=predictions_by_node,
                traces_by_node=transformed,route_ids_by_node=route_ids_by_node,
                precursor_by_node=reflected,
                prices=prices,assessments=policy['actions'],
                applicable=semantic['eligible'],inputs=inputs,
                expected_state_hash=binding['entity_state'],probability_render=probability_render)
            if probability_render is not None:
                require(all(r['mirror']['probability_binding']['render_id']==probability_render.render_id
                    for r in rows),'NATIVE_SPHERE_PROBABILITY_BINDING')
            audit['operator_order_contract']=POST_QPRE_ORDER
            audit['qpre_render_id']=render.render_id
            actual_routes=tuple(routes_by_node[c.provenance_references[0]] for c in field.candidates)
            if 'native_sphere' in policy:
                from .native_sphere_projection import reflect_native
                directional,projection=reflect_native(graph=graph,render=render,traversals=actual_routes,
                    predictions_by_node=predictions_by_node,prices=prices,assessments=policy['actions'],
                    config=policy['native_sphere'],probability_render=probability_render)
                audit['native_sphere_projection']=projection
                if directional is not None:
                    audit['continuous_sphere']=directional.model_dump(mode='json')
                    audit['continuous_sphere_authority_effect']='NONE'
            elif sphere_scene is not None:
                from .sphere_continuous import render_sphere
                audit['continuous_sphere']=render_sphere(graph=graph,scene=sphere_scene,
                    traversals=actual_routes,qpre_render=render).model_dump(mode='json')
                audit['continuous_sphere_authority_effect']='NONE'
        else:
            rows=[]
            for c in field.candidates:
                node_id=c.provenance_references[0]
                mirror=reflected[node_id]
                rows.append(dict(candidate_id=c.candidate_id,source=node_id,mirror=mirror,
                                 realization=c.model_dump(mode='json')))
        ctx=dict(version=state_ops.VERSION,schema='qpre-evaluation-projection-v1',
            entity=binding['entity_id'],predecessor=binding['memory_head'],frame=tcenter.frame_hash,
            governing=semantic['packet']['context']['governing'],source_pins=policy['state_semantics']['source_pins'],
            projection='field-evaluation-v1',paths=[])
        projected=state_ops.pack(rows,ctx)
        state_ops.recover(projected,ctx)
        views=state_ops.un_tree(projected['view'])
        ids={r['candidate_id'] for r in views if r['admissible']}
        evaluated_candidates=[c for c in field.candidates if c.candidate_id in ids]
        audit.update(substrates=substrates,transformation=transformed,sphere=rows,projection=projected,
                     state_sha256=digest(semantic['packet']))
        if not evaluated_candidates:
            return dict(status='UNKNOWN',actions=[],reason='MIRROR_PROJECTION_REFUSED',selection=audit)
    if 'native_relation_transport' in policy:
        from .native_merkabah_transport import certify_projection
        audit['native_relation_transport']=certify_projection(render=render,routes=actual_routes,
            eligible_candidate_ids=tuple(c.candidate_id for c in evaluated_candidates),
            expected_source_state_hash=binding['entity_state'],expected_frame_hash=tcenter.frame_hash)
    evaluations = [_evaluation(c, benefit=policy['goal_value_units'], uncertainty=policy['uncertainty_units'])
                   for c in evaluated_candidates]
    winner = min(evaluations, key=lambda e: (-e.net_score, e.irreversibility_units, e.risk_units, e.cost_units, e.candidate_id))
    audit.update(possibility_field=field.model_dump(mode='json'), evaluations=[e.model_dump(mode='json') for e in evaluations],
                 selected_candidate_id=winner.candidate_id, expectation='DEGENERATE_CONDITIONAL_CONSENSUS',
                 tie_order='irreversibility,risk,cost,canonical_candidate_hash')
    selected_id=winner.candidate_id
    if 'probability_learning' in policy:
        from .qpre_native_learning import render_and_rank
        require(probability_state is not None,'NATIVE_PROBABILITY_STATE_REQUIRED')
        selected_id, probability=render_and_rank(render,evaluated_candidates,lookup,policy,binding,probability_state,rendered=probability_render)
        audit.update(probability_learning=probability, selected_candidate_id=selected_id,
            expectation='EMPIRICAL_ONE_STEP_POSTERIOR_WITH_EXPLICIT_OTHER',tie_order='canonical_candidate_hash')
        if selected_id is None:
            return dict(status='UNKNOWN',actions=[],reason='NO_POSITIVE_CALIBRATED_UTILITY',selection=audit)
    else:require(probability_state is None,'NATIVE_PROBABILITY_DOWNGRADE_REFUSED')
    chosen = lookup[selected_id]
    if inputs is not None:
        selected_sphere=next(r['mirror']['sphere'] for r in rows if r['candidate_id']==selected_id)
        additional_qpre_unknown=[]
        if post_qpre:
            selected_row=next(r for r in rows if r['candidate_id']==selected_id)
            additional_qpre_unknown=selected_row['mirror']['qpre_unknown']
        audit['decision_inputs']={**inputs,'selected_sphere':selected_sphere,
            'uncertainty':list(dict.fromkeys(inputs['uncertainty']+additional_qpre_unknown+selected_sphere['uncertainty']))}
    if 'reflection_consequences' in policy:
        from .native_reflection_consequences import findings
        require(semantic is not None and 'reflection_evidence' in semantic, 'REFLECTION_AUTHENTICATED_INPUT_REQUIRED')
        audit['reflection_consequences']=findings(graph.model_dump(mode='json'),audit,selected_id,
            semantic['reflection_evidence'],policy['reflection_consequences'])
    return dict(status='GOAL_PATH_PREDICTED', actions=chosen['continuation'], prediction=chosen, selection=audit)


def select_audited_general_state(store, read_only_requests):
    """Second typed state domain, through the existing canonical selector API.

    The finite-action-history selector above is unchanged. An audited Entity
    head is NOT Native state and cannot be smuggled through `select_mapped`.
    This entry point is read-only: `actions=[]`, no World or authority effect.
    """
    from .grounded_general_state import select_entity_readonly
    return select_entity_readonly(store, read_only_requests)
