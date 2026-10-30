"""Audited Entity domain for SE6's existing typed realization operators.

This is a *second verified state domain* alongside finite-action-history, not
an assertion of unbounded general-state completeness. All inputs are audited
read-only EntityStore data. QPRE remains possibility, the Sphere compares
provenance/actual persisted bytes, and no World action/authority is offered.

Exact route:
  audited Entity X,Theta,M,E,U -> seed/Pack -> mapped typed paths -> Flower
  -> Merkabah -> T(path comparison) -> QPRE -> Sphere -> outer P ->
  read-only boundary -> deterministic selection.

World/VerifyAssimilate/Return/Renewal on external effects are NOT implemented
here and are explicitly not claimed.
"""
from __future__ import annotations

from copy import deepcopy
import json
from typing import Any

from . import candidate_state_transition as typed
from . import entity_research_bridge as bridge
from . import merkabah_traversal as merkabah
from . import qpre, universal_mapper as mapper
from . import grounded_general_operator_port as operator_port
from . import grounded_owner_math_port as math_port
from .epistemic_status import EpistemicStatus
from .observation_grounding import digest, require
from .symbolic_realization import _evaluation
from .entity_store import EntityStore

VERSION = 'se6-audited-general-state-selector-v1'
DOMAIN = 'audited-entity-state-v1'
SEED = '([{01*}])'
PILLARS = {'AUTHENTICITY', 'INTEGRITY', 'RESPONSIBILITY', 'ENRICHMENT'}


def _json_bytes(x: Any) -> str:
    return json.dumps(x, separators=(',', ':'), sort_keys=True, ensure_ascii=False)


def _bounded_request(r: dict) -> None:
    require(type(r) is dict and set(r) == {'id','path','equals','benefit_units','cost_units',
            'uncertainty_units','conduct'}, 'GENERAL_QUERY_FIELDS')
    require(type(r['id']) is str and 1 <= len(r['id']) <= 64 and r['id'].isascii() and
            all(c.isalnum() or c in '_-.' for c in r['id']), 'GENERAL_QUERY_ID')
    require(type(r['path']) is list and 1 <= len(r['path']) <= 8 and
            all((type(k) is str and len(k) <= 128) or
                (type(k) is int and 0 <= k < 1024) for k in r['path']), 'GENERAL_QUERY_PATH')
    typed.tree(r['equals'])
    require(type(r['benefit_units']) is int and 0 <= r['benefit_units'] <= 1_000_000 and
            type(r['cost_units']) is int and 0 <= r['cost_units'] <= 1_000_000 and
            type(r['uncertainty_units']) is int and 0 <= r['uncertainty_units'] <= 1_000_000,
            'GENERAL_QUERY_FIXED_POINT')
    require(type(r['conduct']) is dict and set(r['conduct']) == PILLARS and
            all(type(v) is bool for v in r['conduct'].values()), 'GENERAL_QUERY_CONDUCT')


def _bounded_disposable_action_request(r: dict) -> None:
    """Strict sandbox-only effect candidate, not an execution permission."""
    require(type(r) is dict and set(r) == {
        'id','path','equals','benefit_units','cost_units',
        'uncertainty_units','conduct','effect'}, 'GENERAL_ACTION_FIELDS')
    _bounded_request({key:r[key] for key in r if key != 'effect'})
    effect=r['effect']
    require(type(effect) is dict and set(effect) == {'kind','target'} and
            effect.get('kind') == 'DISPOSABLE_COUNTER_SET' and
            type(effect.get('target')) is int and
            effect['target'] in (1,2), 'GENERAL_ACTION_BOUNDED_EFFECT')


def _bounded_math_request(r: dict, *, action_mode: bool):
    fields={'id','path','equals','conduct'} | ({'effect'} if action_mode else set())
    require(type(r) is dict and set(r)==fields, 'MATH_REQUEST_FORBIDS_CALLER_SCORES')
    compatible=dict(r,benefit_units=0,uncertainty_units=0,cost_units=0)
    if action_mode:
        _bounded_disposable_action_request(compatible)
    else:
        _bounded_request(compatible)


def proposal_binding(proposal):
    if 'owner_semantics_proposal' in proposal.get('audit',{}):
        require(proposal.get('status')=='UNKNOWN' and proposal.get('actions')==[] and
                proposal.get('selected_query') is None and 'proposed_action' not in proposal,
                'OWNER_PROPOSAL_REFUSAL_CANNOT_BECOME_ACTION')
        return digest({k:v for k,v in proposal.items() if k!='owner_semantics_binding_sha256'})
    material=dict(action=proposal['proposed_action'],candidate=proposal['selected_candidate_id'],
        head=proposal['source_entity_state_id'],receipt=proposal['source_receipt_id'],
        projection=proposal['source_projection'])
    if 'owner_math' in proposal['audit'] or proposal['audit'].get('typed_semantics'):
        # Full mathematical ancestry is inside every existing downstream proposal
        # reference, and thus the claim / witness / verified memory gate chain.
        if 'owner_math' in proposal['audit']:
            material['owner_math']=proposal['audit']['owner_math']
        material['selection_audit_binding_version']=('se6-full-typed-selection-audit-v2'
            if proposal['audit'].get('typed_semantics') else 'se6-full-math-selection-audit-v2')
        material['selection_audit']=proposal['audit']
    else:
        # Bind the entire QPRE/Sphere audit in ordinary development proposals.
        material['selection_audit_binding_version']='se6-full-qpre-sphere-selection-audit-v3'
        material['selection_audit']=proposal['audit']
    for key in ('correspondence_required','ranking_correspondence','verified_return','typed_semantics','typed_operator_consumption'):
        if key in proposal['audit']:
            material[key]=proposal['audit'][key]
    return digest(material)


def project_general_state(store: EntityStore):
    """Construct a COMPLETE lossless bounded general Z from a live audited head.

    A saved projection is not a credential; selection re-audits the store.
    Entity X and Native X are NOT interchangeable. An Entity persisted record
    is verified as a stored record, not as independent World actuality.
    """
    p = bridge.project_audited_entity(store)
    bridge.recheck_current(store, p)
    return p, packet_from_audited_projection(p)


def packet_from_audited_projection(p):
    """Pure full-state projection; caller must independently authenticate p.

    This helper grants no truth or authority. Return uses it only after the
    actual historical state and receipt have been matched to audited lineage.
    """
    state = p.restored_state()
    x = state.model_dump(mode='json')
    theta = p.source_frame.model_dump(mode='json')
    m = dict(source='ENTITY_AUDITED_LINEAGE', active_entity_memory=state.memory.model_dump(mode='json'),
             version=state.state_version,
             event_sequence=state.event_sequence, previous_state_id=state.previous_entity_state_id,
             state_count=p.state_lineage_count, receipt_count=p.receipt_lineage_count,
             receipt_hash=p.receipt_hash)
    e = dict(status='AUDITED_PERSISTED_RECORD_NOT_WORLD_TRUTH',
             entity_state_id=p.entity_state_id, receipt_id=p.receipt_id,
             receipt_hash=p.receipt_hash, checkpoint_id=p.checkpoint_id,
             checkpoint_hash=p.checkpoint_hash, source_locator=p.store_locator_sha256,
             source_projection=p.projection_hash)
    u = dict(entity_uncertainty=state.uncertainty.model_dump(mode='json'),
             known=['Persisted Entity state and receipt lineage audited at read time.'],
             unknown=['Current external World consequence is not established by this store read.',
                      'No inference from this projection authorizes an action.'])
    z = dict(schema=DOMAIN, seed=SEED, entity=state.identity.instance_id,
             source_state_hash=state.state_hash, authority_effect='NONE',
             X=x, Theta=theta, M=m, E=e, U=u)
    ctx = dict(version=typed.VERSION, schema=DOMAIN, entity=state.identity.instance_id,
               predecessor=state.previous_entity_state_id,frame=typed.seal(theta),
               governing=typed.seal(m),source_pins={'entity_state':state.state_hash,
                 'source_projection':p.projection_hash,'store_locator':p.store_locator_sha256},
               projection='structural-paths-v1',paths=[['X'],['Theta'],['M'],['E'],['U']])
    packet = typed.pack(z, ctx)
    require(typed.exact(typed.recover(packet,ctx),z), 'GENERAL_STATE_LOSSLESS_ROUND_TRIP')
    return packet


def recheck_general_state(store: EntityStore, projection, packet):
    """Require exact live EntityStore head, full typed record and context."""
    bridge.recheck_current(store, projection)
    require(type(packet) is dict and type(packet.get('context')) is dict,
            'GENERAL_STATE_PACKET_REQUIRED')
    z = typed.recover(packet,packet['context'])
    require(type(z) is dict and z.get('schema') == DOMAIN and z.get('seed') == SEED
            and z.get('authority_effect') == 'NONE', 'GENERAL_STATE_DOMAIN')
    require(z['E']['source_projection'] == projection.projection_hash and
            z['E']['source_locator'] == projection.store_locator_sha256 and
            z['E']['receipt_hash'] == projection.receipt_hash and
            z['E']['entity_state_id'] == projection.entity_state_id,
            'GENERAL_STATE_EVIDENCE_BINDING')
    require(z['entity'] == projection.identity_instance_id and
            z['source_state_hash'] == projection.entity_state_hash and
            typed.exact(z['X'],projection.restored_state().model_dump(mode='json')) and
            typed.exact(z['Theta'],projection.source_frame.model_dump(mode='json')),
            'GENERAL_STATE_FULL_SOURCE_BINDING')
    expected_p, expected_packet = project_general_state(store)
    require(expected_p.projection_hash == projection.projection_hash and
            typed.exact(expected_packet,packet), 'GENERAL_STATE_CURRENT_SOURCE')
    return z


def verify_audited_successor(store: EntityStore, previous_projection, previous_packet):
    """Verify a REAL newer EntityStore commit as a lossless general-Z successor.

    Both heads must belong to the same audited source; the old head must be
    present in the current audit's immutable state/receipt lineage.  This is
    verification of a durable EntityStore transition, NOT independent proof
    of a World effect or a new owner authorization.
    """
    from .entity_state import SE6EntityState
    from .entity_research_bridge import EntityResearchFrame, _store_locator
    require(type(store) is EntityStore, 'GENERAL_SUCCESSOR_STORE_REQUIRED')
    old = EntityResearchFrame.model_validate_json(previous_projection.model_dump_json())
    require(_store_locator(store) == old.store_locator_sha256,
            'GENERAL_SUCCESSOR_STORE_LOCATOR')
    require(type(previous_packet) is dict and type(previous_packet.get('context')) is dict,
            'GENERAL_SUCCESSOR_PREDECESSOR_PACKET')
    before = typed.recover(previous_packet,previous_packet['context'])
    old_state=old.restored_state()
    require(before['schema'] == DOMAIN and before['seed'] == SEED and
            before['entity'] == old.identity_instance_id and
            before['source_state_hash'] == old.entity_state_hash and
            typed.exact(before['X'],old_state.model_dump(mode='json')) and
            typed.exact(before['Theta'],old.source_frame.model_dump(mode='json')) and
            before['E']['receipt_hash'] == old.receipt_hash and
            before['E']['source_projection'] == old.projection_hash,
            'GENERAL_SUCCESSOR_PREDECESSOR_BINDING')
    integrity,restart,lineage=store.inspect_read_only()
    require(integrity.valid and lineage is not None and restart is not None,
            'GENERAL_SUCCESSOR_AUDIT_REQUIRED')
    old_states=[s for s in lineage.states if s.entity_state_id == old.entity_state_id]
    old_receipts=[r for r in lineage.receipts if r.receipt_id == old.receipt_id]
    require(len(old_states)==1 and old_states[0] == old_state and
            len(old_receipts)==1 and old_receipts[0].receipt_hash == old.receipt_hash,
            'GENERAL_SUCCESSOR_HISTORICAL_MEMBERSHIP')
    current=restart.state
    require(current.state_version == old_state.state_version+1 and
            current.previous_entity_state_id == old_state.entity_state_id and
            current.identity == old_state.identity and
            current.event_sequence > old_state.event_sequence and
            integrity.receipt_count == old.receipt_lineage_count+1 and
            integrity.state_count == old.state_lineage_count+1,
            'GENERAL_SUCCESSOR_EXACT_COMMIT_ANCESTRY')
    new_projection,new_packet=project_general_state(store)
    require(typed.exact(new_projection.restored_state().model_dump(mode='json'),
                       current.model_dump(mode='json')),
            'GENERAL_SUCCESSOR_NEW_RECORD_MISMATCH')
    return dict(status='AUDITED_ENTITY_SUCCESSOR_VERIFIED',
        before_entity_state_id=old_state.entity_state_id,
        after_entity_state_id=current.entity_state_id,
        before_version=old_state.state_version,after_version=current.state_version,
        predecessor_receipt=old.receipt_id,new_receipt=new_projection.receipt_id,
        before_packet_hash=digest(previous_packet),after_packet_hash=digest(new_packet),
        external_world_truth_verified=False,authority_effect='NONE',
        new_projection=new_projection,new_packet=new_packet)


def _select_entity(store: EntityStore, requests: list[dict], *, action_mode: bool = False,
                   math_memory_id: str | None = None, require_correspondence: bool = False,
                   verified_return=None, typed_semantics: bool = False, source_exact_value: bool = False,
                   owner_semantics_proposal: dict | None = None, probability_context=None):
    """Shared bounded operator chain for read-only queries and test action proposals.

    Action mode includes the effect in the QPRE possibility and post-QPRE Sphere
    validation. Neither mode grants authority or independently verifies World.
    """
    require(type(requests) is list and 0 < len(requests) <= 12,'GENERAL_REQUEST_BOUND')
    if probability_context is not None:
        from .qpre_development_learning import DevelopmentCalibration
        require(type(probability_context) is DevelopmentCalibration and action_mode and
            probability_context.store is store and math_memory_id is None and
            not typed_semantics and not require_correspondence and not source_exact_value and
            owner_semantics_proposal is None, 'PROBABILITY_DEVELOPMENT_MODE_ONLY')
    owner_mode=owner_semantics_proposal is not None
    if owner_mode:
        require(type(owner_semantics_proposal) is dict and
                set(owner_semantics_proposal) in ({'expected_source_pins'},
                    {'expected_source_pins','other_operator_evidence'}),
                'OWNER_PROPOSAL_CONFIGURATION_REQUIRED')
        require(math_memory_id is None and not require_correspondence and not source_exact_value,
                'OWNER_PROPOSAL_FORBIDS_FALLBACK_OR_MIXED_SEMANTICS')
        typed_semantics=True
    math_mode = math_memory_id is not None
    require(type(require_correspondence) is bool and (not require_correspondence or math_mode),
            "CORRESPONDENCE_REQUIRES_RETAINED_MATH_MODEL")
    require(type(typed_semantics) is bool,'TYPED_SEMANTICS_FLAG')
    require(type(source_exact_value) is bool and
            (not source_exact_value or (typed_semantics and math_memory_id is None and
                                        not require_correspondence)),
            'SOURCE_EXACT_REQUIRES_TYPED_NONOWNER_MODE')
    typed_mode = typed_semantics or require_correspondence
    require(not(typed_semantics and math_mode and not require_correspondence),
            'TYPED_MODE_REFUSES_UNPROVEN_NUMERIC_OWNER_COMBINATION')
    numeric_mode = math_mode and not require_correspondence
    flower_context = None
    if math_mode:
        require(type(math_memory_id) is str, 'MATH_MEMORY_ID_REQUIRED')
        for r in requests:
            _bounded_math_request(r, action_mode=action_mode)
        original_requests = deepcopy(requests)
        # Compatibility fields are internal placeholders only. The math branch
        # never consumes them for score or uncertainty. Caller scores are refused.
        requests = [dict(r,benefit_units=0,uncertainty_units=0,cost_units=0) for r in requests]
    for r in requests:
        if action_mode:
            _bounded_disposable_action_request(r)
        else:
            _bounded_request(r)
    require(len({r['id'] for r in requests}) == len(requests), 'GENERAL_REQUEST_IDS')
    if source_exact_value or owner_mode:
        require(all(r['benefit_units']==0 and r['uncertainty_units']==0 for r in requests),
                'SOURCE_EXACT_CALLER_BENEFIT_FORBIDDEN')
    p,packet = project_general_state(store)
    z = recheck_general_state(store,p,packet)
    source_exact_pins = None
    if source_exact_value:
        from .grounded_typed_math_v2 import actual_source_pins
        source_exact_pins = actual_source_pins()
    math_rows = {}; math_binding = None
    if numeric_mode:
        math_rows, math_binding = math_port.evaluate_current(store=store,projection=p,z=z,
            memory_id=math_memory_id,requests=original_requests)
        requests = [dict(r,cost_units=math_rows[r['id']]['cost']) for r in requests]
    source = p.source_frame.x.source_observations[0]
    center = mapper.create_mapper_node(kind=mapper.NodeKind.THING,
        label=p.identity_instance_id,
        description='Audited persisted Entity head '+p.entity_state_id,
        epistemic_status=EpistemicStatus.REPORTED,source_observations=(source,))
    nodes=[]; lookups={}; comparisons={}; relations=[]
    for r in requests:
        node=mapper.create_mapper_node(kind=mapper.NodeKind.THING,
            label=('action:' if action_mode else 'query:')+r['id'],
            description=('Bounded possible test action with typed Entity precondition'
                         if action_mode else 'Bounded read-only typed Entity query'),
            epistemic_status=EpistemicStatus.INFERRED,source_observations=(source,))
        nodes.append(node);lookups[node.node_id]=r
        relations.append(mapper.create_mapper_relation(kind=mapper.RelationKind.RELATES_TO,
            label=('typed-entity-action-precondition' if action_mode else 'typed-audited-state-query'), source_nodes=(center,),target_nodes=(node,),
            epistemic_status=EpistemicStatus.INFERRED,source_observations=(source,)))
    graph=mapper.create_universal_map(vertices=(center,*nodes),relations=tuple(relations))
    flower=mapper.create_flower_center(center,terminals=nodes)
    frame_hash=p.source_frame.theta_hash
    traversal_center=merkabah.build_traversal_center(
        state_hash=p.entity_state_hash,frame_hash=frame_hash)
    if verified_return is not None:
        from .grounded_verified_return_binding import validate_return_center
        traversal_center=validate_return_center(store=store,returned=verified_return)
        require(traversal_center.state_hash==p.entity_state_hash and
                traversal_center.frame_hash==frame_hash,"RETURN_CENTER_CURRENT_SOURCE")
    # F -> D -> K -> T is now one consumed causal port.  Merkabah receives
    # only the content-addressed Flower terminals, while T receives the exact
    # typed D value and the resulting K traversal.  No operator can be omitted
    # without a source-bound validation failure.
    substrate=operator_port.differentiate(z=z,graph=graph,flower=flower,
                                          requests_by_node=lookups)
    strict_model_binding = None
    if require_correspondence:
        # A source-authenticated declaration is retained evidence, not proof
        # that its matrices implement similarly named owner operators.
        model,record=math_port._load(store,p,math_memory_id)
        for r in requests:
            spec=model['candidates'].get(r['id'])
            require(type(spec) is dict and typed.exact(spec['path'],r['path']) and
                    typed.exact(spec['equals'],r['equals']) and
                    typed.exact(spec['effect'],r.get('effect')),'TYPED_OWNER_REQUEST_MODEL_SCOPE')
            declared_cost=math_port.rational(spec['cost'])
            require(declared_cost.denominator==1 and 0<=declared_cost<=1_000_000,
                    'TYPED_OWNER_DECLARED_COST_DOMAIN')
            r['cost_units']=int(declared_cost)
        lookups={node:{r['id']:r for r in requests}[r['id']] for node,r in lookups.items()}
        strict_model_binding=dict(memory_id=record.memory_id,model_sha256=digest(model),
            source_events=list(record.source_event_ids),
            status='PERSISTED_DECLARATION_NOT_OWNER_OPERATOR_SEMANTICS',
            numeric_surrogates_consumed=False)
    nodes_by_id={n.node_id:n for n in nodes}
    candidates=[]; traces={}; typed_inputs={}; typed_fields={}; consumed_transforms={}
    for cell in substrate['rows']:
        node=nodes_by_id[cell['node']]
        r=lookups[node.node_id]
        terminal=merkabah.build_traversal_terminal(
            source_center_id=traversal_center.center_id,
            references=(merkabah.TraversalReference(
                kind=merkabah.TraversalReferenceKind.MAPPED,reference_id=cell['node']),),
            summary=('Typed-substrate-'+cell['presence'].lower()+'-disposable-action'
                     if action_mode else 'Typed-substrate-'+cell['presence'].lower()+'-entity-query'))
        traverse=merkabah.traverse_merkabah(center=traversal_center,terminal=terminal)
        comparisons[node.node_id]=operator_port.transform(z=z,
            differentiation=substrate,request=r,node_id=node.node_id,
            traversal=traverse)
        if typed_mode:
            typed_inputs[node.node_id]=dict(z=z,graph=graph,flower=flower,
                requests_by_node=lookups,node_id=node.node_id,traversal=traverse,
                expected_observation_bindings=tuple(s.binding for s in p.source_frame.x.source_observations))
            actual_output=operator_port.actual_typed_output(**typed_inputs[node.node_id])
            typed_fields[node.node_id]=operator_port.typed_output_fields(actual_output)
        status=comparisons[node.node_id]['status']
        provenance=(node.node_id,traverse.traversal_id,
                    p.entity_state_id,p.receipt_id,p.source_frame.theta_hash)
        if numeric_mode:
            provenance += ('sha256:'+math_rows[r['id']]['hash'],)
        action_target=r['effect']['target'] if action_mode else None
        possibility_name='disposable-counter-target' if action_mode else 'read-only-intent'
        possibility_value=str(action_target) if action_mode else r['id']
        step_name=('typed-entity-action-precondition-v1' if action_mode
                   else 'typed-path-equality-v1')
        consequence=('Possible disposable counter='+str(action_target)+
                     '; not an observed World consequence.' if action_mode else
                     'Possible read-only observation; not an external World prediction.')
        assumptions=('Entity predicates use only persisted state; World preimage and authority require separate checks.'
                     if action_mode else 'Only persisted Entity record claims are evaluated.',)
        unknown=('External World action and independent consequence remain unverified.'
                 if action_mode else 'External World actuality is not established.',)
        if numeric_mode:
            unknown += ('Finite model forecast is not external truth; certified tail and exact arithmetic residual are recorded.',)
        candidate_fields=(qpre.CandidateStateField(name=possibility_name,possible_value=possibility_value),)
        if numeric_mode:
            candidate_fields += tuple(qpre.CandidateStateField(name=key,possible_value=value)
                for key,value in math_port.qpre_payload(math_rows[r['id']]).items())
        if typed_mode:
            candidate_fields += typed_fields[node.node_id]
        realization=qpre.build_candidate_realization(
            source_state_hash=p.entity_state_hash,frame_hash=frame_hash,
            candidate_state=candidate_fields,
            transformations=(qpre.TransformationStep(operation=step_name,
                input_reference=node.node_id,possible_output=status),),
            predicted_consequences=(qpre.build_predicted_consequence(
                summary=consequence,provenance_references=provenance),),
            reversibility=(qpre.Reversibility.PARTIALLY_REVERSIBLE if action_mode
                           else qpre.Reversibility.REVERSIBLE),
            cost_units=r['cost_units'],risk_score=(1 if action_mode else 0),
            provenance_references=provenance)
        c=qpre.build_qpre_candidate(
            source_state_hash=p.entity_state_hash,frame_hash=frame_hash,
            assumptions=assumptions,
            uncertainty=qpre.StructuredUncertainty(
                known=('The EntityStore record has been audited.',),
                unknown=unknown,assumptions=assumptions),
            realization=realization,provenance_references=provenance)
        candidates.append(c);traces[node.node_id]=traverse.traversal_id
    render=qpre.render_qpre(qpre.build_possibility_field(source_state_hash=p.entity_state_hash,
        frame_hash=frame_hash,candidates=candidates))
    probability = (probability_context.build(render,lookups)
                   if probability_context is not None else None)
    rows=[];valid=[]
    for c in render.possibility_field.candidates:
        nid=c.provenance_references[0]
        require(nid in lookups and nid in comparisons,'GENERAL_SPHERE_QPRE_SOURCE')
        r=lookups[nid];cmp=comparisons[nid]
        expected_provenance=(nid,traces[nid],p.entity_state_id,p.receipt_id,p.source_frame.theta_hash)
        if numeric_mode:
            expected_provenance += ('sha256:'+math_rows[r['id']]['hash'],)
        reasons=[]
        if typed_mode:
            try:
                cmp=operator_port.consume_typed_output(c,**typed_inputs[nid])
                consumed_transforms[nid]=cmp
            except (ValueError,TypeError,KeyError) as error:
                reasons.append(str(error))
                # Do not fall back to pre-render comparisons after bad transport.
                cmp=dict(status='TYPED_OUTPUT_REFUSED',match=False)
        # Post-QPRE Sphere recomputes candidate truth-condition and source
        # coherence, not a second independent World witness.
        if c.provenance_references != expected_provenance or c.realization.provenance_references != expected_provenance:
            reasons.append('GENERAL_SPHERE_PROVENANCE')
        if c.realization.cost_units != r['cost_units'] or \
           c.realization.risk_score != (1 if action_mode else 0) or \
           c.realization.reversibility is not (qpre.Reversibility.PARTIALLY_REVERSIBLE if action_mode else qpre.Reversibility.REVERSIBLE):
            reasons.append('GENERAL_SPHERE_COST_OR_RISK')
        if (c.source_state_hash != p.entity_state_hash or c.frame_hash != frame_hash or
            c.realization.source_state_hash != p.entity_state_hash or
            c.realization.frame_hash != frame_hash):
            reasons.append('GENERAL_SPHERE_STATE_FRAME')
        if (len(c.realization.candidate_state)!=((1+len(typed_fields[nid])) if typed_mode else (6 if numeric_mode else 1)) or
            c.realization.candidate_state[0].name != ('disposable-counter-target' if action_mode else 'read-only-intent') or
            c.realization.candidate_state[0].possible_value != (str(r['effect']['target']) if action_mode else r['id']) or
            len(c.realization.transformations)!=1 or
            c.realization.transformations[0].operation != ('typed-entity-action-precondition-v1' if action_mode else 'typed-path-equality-v1') or
            c.realization.transformations[0].input_reference != nid or
            c.realization.transformations[0].possible_output != cmp['status']):
            reasons.append('GENERAL_SPHERE_TRANSFORMATION')
        predictions=c.realization.predicted_consequences
        if (len(predictions)!=1 or
            predictions[0].summary != (('Possible disposable counter='+str(r['effect']['target'])+'; not an observed World consequence.') if action_mode else 'Possible read-only observation; not an external World prediction.') or
            predictions[0].provenance_references != expected_provenance):
            reasons.append('GENERAL_SPHERE_CONSEQUENCE_PROVENANCE')
        if (('External World action and independent consequence remain unverified.' if action_mode else 'External World actuality is not established.') not in c.uncertainty.unknown or
            c.uncertainty.known != ('The EntityStore record has been audited.',)):
            reasons.append('GENERAL_SPHERE_UNCERTAINTY_SCOPE')
        if numeric_mode:
            math_unknown=(('External World action and independent consequence remain unverified.' if action_mode
                           else 'External World actuality is not established.'),
                          'Finite model forecast is not external truth; certified tail and exact arithmetic residual are recorded.')
            if c.uncertainty.unknown != math_unknown:
                reasons.append('MATH_QPRE_UNCERTAINTY_CHANGED')
        if not cmp['match']:reasons.append(cmp['status'])
        if not all(r['conduct'].values()): reasons.append('GENERAL_CONDUCT_REFUSED')
        if numeric_mode:
            expected_fields=math_port.qpre_payload(math_rows[r['id']])
            actual_fields={f.name:f.possible_value for f in c.realization.candidate_state[1:]}
            if actual_fields != expected_fields:
                reasons.append('MATH_QPRE_EVALUATION_CHANGED')
            model_row=math_port.from_qpre(c)
            if model_row['score']-model_row['radius'] <= 0:
                reasons.append('MATH_CERTIFIED_VALUE_NOT_POSITIVE')
        row=dict(candidate_id=c.candidate_id,source=nid,
                 mirror=dict(consistent=not reasons,reasons=list(dict.fromkeys(reasons))),
                 realization=c.model_dump(mode='json'))
        if numeric_mode:
            row['owner_math'] = dict(math_rows[r['id']]['public'],
                                    rendered_payload=actual_fields)
        rows.append(row)
    context=dict(version=typed.VERSION,schema='audited-entity-possibility-projection-v1',
        entity=p.identity_instance_id,predecessor=p.previous_entity_state_id,
        frame=frame_hash,governing=typed.seal(z['M']),
        source_pins={'entity_state':p.entity_state_hash,'receipt':p.receipt_hash,
                     'store_locator':p.store_locator_sha256},
        projection='field-evaluation-v1',paths=[])
    projected=typed.pack(rows,context)
    views=typed.un_tree(projected['view'])
    require(typed.exact(typed.recover(projected,context),rows),'GENERAL_PROJECTION_LOSSLESS')
    ids={x['candidate_id'] for x in views if x['admissible']}
    scored=[(c,lookups[c.provenance_references[0]]) for c in render.possibility_field.candidates if c.candidate_id in ids]
    evaluations=([_evaluation(c,benefit=r['benefit_units'],uncertainty=r['uncertainty_units'])
                  for c,r in scored] if not math_mode else [])
    # Source must still be current after QPRE/selection. No stored projection
    # can confer authority if the source changes in the meantime.
    recheck_general_state(store,p,packet)
    audit=dict(schema=VERSION,domain=DOMAIN,source_projection=p.projection_hash,
        full_canonical=False,identity=p.identity_instance_id,
        state_id=p.entity_state_id,receipt_id=p.receipt_id,source_state=p.entity_state_hash,
        frame=p.source_frame.theta_hash,representation_seed=SEED,
        state_packet_hash=digest(packet),map_hash=graph.map_hash,
        flower_hash=flower.flower_hash,
        traversals=traces,traversal_center_id=traversal_center.center_id,
        traversal_predecessor_center_id=traversal_center.predecessor_center_id,
        substrate_hash=substrate['differentiation_hash'],
        substrate_dimensions=[dict(node=row['node'],path_depth=row['path_depth'],
                                   primitive_tag=row['primitive_tag'],presence=row['presence'])
                              for row in substrate['rows']],
        transform_contract=operator_port.TRANSFORM,transform=comparisons,
        qpre_field_id=render.possibility_field.possibility_field_id,
        qpre_render_id=render.render_id,sphere=rows,
        projected_candidate_ids=[x['candidate_id'] for x in views if x['admissible']],
        projection_sha256=digest(projected),
        boundary=('TEST_PROPOSAL_REQUIRES_INDEPENDENT_AUTHORITY' if action_mode else 'READ_ONLY_NO_WORLD_AUTHORITY'),
        authority_effect='NONE',world_effect=False,renewal=False)
    if probability is not None:
        probability_context.verify_material(probability,audit)
        audit['probability']=probability
        chosen,scores=probability_context.select(probability,scored)
        audit['probability_scores']=scores
        if chosen is None:
            return dict(status='UNKNOWN',reason='CALIBRATED_VALUE_NOT_POSITIVE',actions=[],selected_query=None,audit=audit)
        candidate,request=next((c,r) for c,r in scored if c.candidate_id==chosen)
        result=dict(status='TEST_ACTION_PROPOSAL',reason='DEV_CALIBRATED_EXPECTED_VALUE',actions=[],
            selected_query=request['id'],selected_candidate_id=chosen,
            proposed_action=dict(kind='DISPOSABLE_COUNTER_SET',target=request['effect']['target']),
            source_entity_state_id=p.entity_state_id,source_receipt_id=p.receipt_id,
            source_projection=p.projection_hash,audit=audit)
        result['proposal_sha256']=proposal_binding(result)
        return result
    if typed_mode:
        audit['typed_semantics']=True
        audit['typed_operator_consumption']=dict(contract=operator_port.TYPED_OUTPUT,
            consumed_transforms=consumed_transforms,retained_model=strict_model_binding,
            requests=deepcopy(original_requests if math_mode else requests),
            utility_scope='DECLARED_V6_FIXED_POINT_NOT_OWNER_DERIVED_UTILITY',
            verified_complete_outputs=(len(consumed_transforms)==len(candidates)),
            transport_required=True,numeric_owner_equivalence=False)
    if verified_return is not None:
        audit['verified_return']=verified_return
    if owner_mode:
        from .grounded_owner_semantics_proposal_v1 import propose_owner_semantics
        report=propose_owner_semantics(store=store,requests=requests,action_mode=action_mode,
            candidates=list(render.possibility_field.candidates),sphere_rows=rows,
            expected_source_pins=owner_semantics_proposal['expected_source_pins'],
            verified_return=verified_return,
            other_operator_evidence=owner_semantics_proposal.get('other_operator_evidence'))
        recheck_general_state(store,p,packet)
        require(report.get('status')=='PROPOSED' and report.get('selection') is None and
                report.get('source_state_hash')==p.entity_state_hash,
                'OWNER_PROPOSAL_CANNOT_AUTHORIZE_SELECTION')
        audit['owner_semantics_proposal']=report
        audit['owner_semantics_configuration']=deepcopy(owner_semantics_proposal)
        # A verified subgraph or mathematical expression is not an adopted
        # complete owner utility/ranking contract. Never fall through to V3.
        result=dict(status='UNKNOWN',reason=report['reason'],actions=[],selected_query=None,
            source_entity_state_id=p.entity_state_id,source_receipt_id=p.receipt_id,
            source_projection=p.projection_hash,audit=audit)
        result['owner_semantics_binding_sha256']=digest(result)
        return result
    if source_exact_value:
        from .grounded_operational_exact_value_v3 import evaluate as source_value_evaluate
        chosen,certificate=source_value_evaluate(
            candidates=list(render.possibility_field.candidates),sphere_rows=rows,
            actual_inputs=typed_inputs,requests_by_node=lookups,
            expected_source_pins=source_exact_pins)
        audit['source_exact_value']=certificate
        if chosen is None:
            return dict(status='UNKNOWN',reason=certificate['reason'],
                        actions=[],selected_query=None,audit=audit)
        chosen_c,chosen_request=next((c,r) for c,r in scored if r['id']==chosen)
        if action_mode:
            action={'kind':'DISPOSABLE_COUNTER_SET','target':chosen_request['effect']['target']}
            result=dict(status='TEST_ACTION_PROPOSAL',reason=certificate['reason'],
                actions=[],selected_query=chosen,proposed_action=action,
                selected_candidate_id=chosen_c.candidate_id,
                source_entity_state_id=p.entity_state_id,source_receipt_id=p.receipt_id,
                source_projection=p.projection_hash,audit=audit)
            result['proposal_sha256']=proposal_binding(result)
            return result
        return dict(status='READ_ONLY_PROPOSAL',reason=certificate['reason'],
                    actions=[],selected_query=chosen,audit=audit)
    if require_correspondence:
        audit['correspondence_required']=True
    if require_correspondence:
        # The source supplies the actual operational partial maps, but not a
        # lawful scalar combination of the owner's comma-separated terms.
        # A field permutation or retained matrix declaration cannot fill this.
        audit['owner_semantics']=dict(status='UNSPECIFIED',
            missing=['owner typed combination and contribution algebra',
                     'evidence measure and gains',
                     'ethical/knowledge/adjoint/cube correspondence',
                     'self/future utility and decision-unit calibration'],
            authority_effect='NONE',full_canonical=False)
        return dict(status='UNKNOWN',reason='OWNER_TERM_SEMANTICS_UNSPECIFIED',
                    actions=[],selected_query=None,audit=audit)
    if numeric_mode:
        audit['owner_math'] = dict(math_binding, memory_id=math_memory_id,
            inputs={key:row['binding'] for key,row in math_rows.items()},
            interpretation='PROPOSED_EXACT_INTERVAL_REFINEMENT_NOT_CANONICAL_EQUIVALENCE')
        # Re-derive the entire model/input binding after QPRE. No cached caller
        # vector or saved projection may stand in for current retained evidence.
        checked_rows, checked_binding = math_port.evaluate_current(store=store,projection=p,z=z,
            memory_id=math_memory_id,requests=original_requests,flower_context=flower_context)
        require(checked_binding == math_binding and
                {k:v['hash'] for k,v in checked_rows.items()} == {k:v['hash'] for k,v in math_rows.items()},
                'MATH_INPUTS_CHANGED_DURING_SELECTION')
        qpre_ids={r['id']:c.candidate_id for c,r in scored}
        # Selection consumes the values that actually survived QPRE -> Sphere
        # -> projection. Source evaluation is only the independent equality check.
        rendered_rows={r['id']:math_port.from_qpre(c) for c,r in scored}
        chosen,reason=math_port.choose_certified(rendered_rows,qpre_ids)
        if chosen is None:
            return dict(status='UNKNOWN',reason=reason,actions=[],selected_query=None,audit=audit)
        chosen_c,chosen_request=next((c,r) for c,r in scored if r['id']==chosen)
        if action_mode:
            action={'kind':'DISPOSABLE_COUNTER_SET','target':chosen_request['effect']['target']}
            result=dict(status='TEST_ACTION_PROPOSAL',reason=reason,actions=[],selected_query=chosen,
                proposed_action=action,selected_candidate_id=chosen_c.candidate_id,
                source_entity_state_id=p.entity_state_id,source_receipt_id=p.receipt_id,
                source_projection=p.projection_hash,audit=audit)
            result['proposal_sha256']=proposal_binding(result)
            return result
        return dict(status='READ_ONLY_PROPOSAL',reason=reason,actions=[],selected_query=chosen,audit=audit)
    if not evaluations:
        return dict(status='UNKNOWN',reason='GENERAL_POSSIBILITY_REFUSED',
                    actions=[],selected_query=None,audit=audit)
    paired=list(zip(evaluations,scored))
    winning=min(paired,key=lambda p:(-p[0].net_score,p[0].irreversibility_units,
                                    p[0].risk_units,p[0].cost_units,p[0].candidate_id))
    if winning[0].net_score <= 0:
        return dict(status='UNKNOWN',reason='GENERAL_READ_ONLY_VALUE_NOT_POSITIVE',
                    actions=[],selected_query=None,audit=audit)
    if action_mode:
        chosen_c, chosen_request=winning[1]
        action={'kind':'DISPOSABLE_COUNTER_SET','target':chosen_request['effect']['target']}
        # Only a potential action, not a grant. Bind the *actual QPRE candidate*
        # and audited head so a caller cannot silently switch to another effect.
        result=dict(status='TEST_ACTION_PROPOSAL',reason='AUDITED_PRECONDITION_AND_QPRE_SPHERE_ELIGIBLE',
                    actions=[],selected_query=chosen_request['id'],
                    proposed_action=action, selected_candidate_id=chosen_c.candidate_id,
                    source_entity_state_id=p.entity_state_id,
                    source_receipt_id=p.receipt_id,
                    source_projection=p.projection_hash,
                    audit=audit)
        result['proposal_sha256']=proposal_binding(result)
        return result
    return dict(status='READ_ONLY_PROPOSAL',reason='PERSISTED_ENTITY_PREDICATE_MATCH',
                actions=[],selected_query=winning[1][1]['id'],audit=audit)


def select_entity_readonly(store: EntityStore, requests: list[dict], *, math_memory_id: str | None = None, require_correspondence: bool = False,
                   verified_return=None, typed_semantics: bool = False, source_exact_value: bool = False,
                   owner_semantics_proposal: dict | None = None, probability_context=None):
    """Legacy bounded read-only Entity query. No external authority."""
    return _select_entity(store,requests,action_mode=False,math_memory_id=math_memory_id,
        require_correspondence=require_correspondence,verified_return=verified_return,typed_semantics=typed_semantics,
        source_exact_value=source_exact_value,owner_semantics_proposal=owner_semantics_proposal,
        probability_context=probability_context)


def select_entity_disposable_action(store: EntityStore, requests: list[dict], *, math_memory_id: str | None = None, require_correspondence: bool = False,
                   verified_return=None, typed_semantics: bool = False, source_exact_value: bool = False,
                   owner_semantics_proposal: dict | None = None, probability_context=None):
    """Select the effect *within QPRE/Sphere*; grant no execution authority.

    Deliberately limited to independent scratch-world counter actions. This
    does not define a general World action or implement the full equation.
    """
    return _select_entity(store,requests,action_mode=True,math_memory_id=math_memory_id,
        require_correspondence=require_correspondence,verified_return=verified_return,typed_semantics=typed_semantics,
        source_exact_value=source_exact_value,owner_semantics_proposal=owner_semantics_proposal,
        probability_context=probability_context)


__all__=['VERSION','DOMAIN','project_general_state','recheck_general_state',
         'verify_audited_successor','select_entity_readonly','select_entity_disposable_action']
