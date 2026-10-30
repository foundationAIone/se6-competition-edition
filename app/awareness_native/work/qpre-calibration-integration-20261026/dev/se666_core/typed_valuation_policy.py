"""Typed policy producer with separate source, owner and World boundaries.

This module validates declared semantics; it does not choose owner preferences.
An authenticated login or self-hashed policy is not a policy-adoption decision.
Exact-purpose durable adoption is independently read from the existing owner
authority store. Synthetic owner stores supply test-only mathematical use and
can never be promoted into production or World authority.
"""
from __future__ import annotations
from copy import deepcopy
from datetime import UTC, datetime
import json
import re

from . import typed_valuation as typed
from .observation_grounding import digest, require
from .qpre_calibration_v1 import QPREProbabilityRender, DistributionSemantics

VERSION='se6-typed-valuation-policy-v1'
PURPOSE='VALUATION_POLICY_ADOPTION'
SOURCE_PURPOSE='TYPED_VALUATION_POLICY_SOURCE'
_REF=re.compile(r'^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$')
_SHA=re.compile(r'^[a-f0-9]{64}$')


def _ref(value):
    require(type(value) is str and _REF.fullmatch(value) is not None,'TYPED_POLICY_REFERENCE')


def _utc(value):
    require(type(value) is str,'TYPED_POLICY_TIMESTAMP')
    try:parsed=datetime.fromisoformat(value)
    except ValueError as error:raise ValueError('TYPED_POLICY_TIMESTAMP') from error
    require(parsed.utcoffset() is not None,'TYPED_POLICY_AWARE_TIMESTAMP')
    return parsed.astimezone(UTC)


def quantity_scope(policy):
    return 'scope:'+digest(policy['scope'])


def seal_policy(policy):
    """Schema construction only, never a source attestation or owner approval."""
    material=deepcopy(policy);material.pop('policy_hash',None)
    return {**material,'policy_hash':digest(material)}


def validate_policy_document(policy):
    fields={'version','policy_id','revision','origin','domain','source_identity','source_references',
        'scope','units','conversions','comparison','outcome_semantics','candidate_values',
        'effective_from_utc','expires_at_utc','policy_hash'}
    require(type(policy) is dict and set(policy)==fields,'TYPED_POLICY_FIELDS')
    require(policy['version']==VERSION,'TYPED_POLICY_VERSION')
    for name in ('policy_id','domain','source_identity'):_ref(policy[name])
    require(type(policy['revision']) is int and policy['revision']>0,'TYPED_POLICY_REVISION')
    require(policy['origin'] in ('SYNTHETIC_TEST_ONLY','OWNER_POLICY'),'TYPED_POLICY_ORIGIN')
    refs=policy['source_references']
    require(type(refs) is list and 0<len(refs)<=128 and len(refs)==len(set(refs)),'TYPED_POLICY_SOURCE_REFS')
    for ref in refs:_ref(ref)
    scope=policy['scope']
    require(type(scope) is dict and set(scope)=={'entity_id','source','epoch','frame_hash','model_version'},'TYPED_POLICY_SCOPE_FIELDS')
    for key,value in scope.items():
        if key=='frame_hash':require(type(value) is str and _SHA.fullmatch(value) is not None,'TYPED_POLICY_FRAME_HASH')
        else:_ref(value)
    units=policy['units']
    require(type(units) is dict and 0<len(units)<=16,'TYPED_POLICY_UNITS')
    for key,unit in units.items():
        _ref(key);typed.validate_unit(unit)
        require(key==unit['id'],'TYPED_POLICY_UNIT_ID')
    conversions=policy['conversions']
    require(type(conversions) is list and len(conversions)<=64,'TYPED_POLICY_CONVERSIONS')
    for conversion in conversions:
        typed.validate_conversion(conversion)
        require(conversion['source_unit']==units.get(conversion['source_unit']['id']) and
            conversion['target_unit']==units.get(conversion['target_unit']['id']) and
            conversion['reference'] in refs,'TYPED_POLICY_CONVERSION_SOURCE')
    require(len({digest(c) for c in conversions})==len(conversions),'TYPED_POLICY_DUPLICATE_CONVERSION')
    comparison=policy['comparison']
    require(type(comparison) is dict and set(comparison)=={'kind','directions','common_units'} and
        comparison['kind'] in ('SCALAR','PARETO','UNSPECIFIED'),'TYPED_POLICY_COMPARISON')
    require(type(comparison['directions']) is dict and type(comparison['common_units']) is dict,'TYPED_POLICY_COMPARISON_FIELDS')
    for dimension,direction in comparison['directions'].items():
        _ref(dimension);require(direction in ('MAXIMIZE','MINIMIZE'),'TYPED_POLICY_DIRECTION')
    for dimension,unit_id in comparison['common_units'].items():
        _ref(dimension);require(unit_id in units and units[unit_id]['kind']!='PROBABILITY','TYPED_POLICY_COMPARISON_UNIT')
    if comparison['kind']=='SCALAR':
        require(len(comparison['common_units'])==1 and set(comparison['directions'])==set(comparison['common_units']),
            'TYPED_POLICY_SCALAR_NEEDS_ONE_AUTHORIZED_UNIT')
    semantics=policy['outcome_semantics']
    require(type(semantics) is dict and 0<len(semantics)<=64,'TYPED_POLICY_OUTCOME_SEMANTICS')
    for outcome,reference in semantics.items():
        _ref(outcome);require(reference in refs,'TYPED_POLICY_OUTCOME_SOURCE_DEFINITION')
    candidates=policy['candidate_values']
    require(type(candidates) is list and 0<len(candidates)<=64,'TYPED_POLICY_CANDIDATES')
    ids=[]
    for candidate in candidates:
        require(type(candidate) is dict and set(candidate)=={'candidate_id','outcomes','outside_field'},'TYPED_POLICY_CANDIDATE_FIELDS')
        _ref(candidate['candidate_id']);ids.append(candidate['candidate_id'])
        require(type(candidate['outcomes']) is dict and 0<len(candidate['outcomes'])<=64 and
            set(candidate['outcomes'])<=set(semantics),'TYPED_POLICY_CANDIDATE_OUTCOMES')
        for vector in list(candidate['outcomes'].values())+([candidate['outside_field']] if candidate['outside_field'] is not None else []):
            require(type(vector) is dict and 0<len(vector)<=16,'TYPED_POLICY_VECTOR')
            if comparison['kind']=='SCALAR':
                require(set(vector)==set(comparison['common_units']),'TYPED_POLICY_SCALAR_VECTOR_BASIS')
            for dimension,quantity in vector.items():
                _ref(dimension);typed.validate_quantity(quantity)
                require(quantity['unit']==units.get(quantity['unit']['id']) and quantity['unit']['kind']!='PROBABILITY',
                    'TYPED_POLICY_OUTCOME_QUANTITY_UNIT')
                require(quantity['source_identity']==policy['source_identity'] and
                    quantity['policy_revision']=='revision:'+str(policy['revision']) and
                    quantity['scope']==quantity_scope(policy),'TYPED_POLICY_QUANTITY_SOURCE_SCOPE_REVISION')
                require(set(quantity['provenance'])<=set(refs),'TYPED_POLICY_QUANTITY_PROVENANCE')
    require(len(ids)==len(set(ids)),'TYPED_POLICY_DUPLICATE_CANDIDATE')
    require(_utc(policy['effective_from_utc'])<_utc(policy['expires_at_utc']),'TYPED_POLICY_TIME_INTERVAL')
    require(type(policy['policy_hash']) is str and policy['policy_hash']==digest({k:v for k,v in policy.items() if k!='policy_hash'}),
        'TYPED_POLICY_HASH')
    return deepcopy(policy)


def _bind(policy,render,context):
    require(type(render) is QPREProbabilityRender,'TYPED_POLICY_ACTUAL_QPRE_RENDER')
    render=QPREProbabilityRender.model_validate_json(render.model_dump_json())
    require(type(context) is dict and type(context.get('binding')) is dict,'TYPED_POLICY_CONTEXT')
    scope=policy['scope'];binding=context['binding']
    require(all(scope[k]==binding.get(k) for k in ('entity_id','source','epoch')) and
        binding.get('entity_state')==render.base_render.source_state_hash and
        scope['frame_hash']==context.get('frame_hash')==render.base_render.frame_hash and
        scope['model_version']==context.get('model_version')==render.model_version and
        context.get('source_state_hash')==render.base_render.source_state_hash and
        context.get('probability_render_id')==render.render_id and
        context.get('calibration_state_hash')==render.calibration_state_hash,'TYPED_POLICY_CURRENT_SOURCE_RENDER_SCOPE')
    candidates={row['candidate_id']:row for row in policy['candidate_values']}
    require(set(candidates)=={d.candidate_id for d in render.distributions},'TYPED_POLICY_COMPLETE_RENDER_CANDIDATES')
    for distribution in render.distributions:
        row=candidates[distribution.candidate_id]
        require(set(row['outcomes'])=={o.outcome_id for o in distribution.outcomes},'TYPED_POLICY_COMPLETE_OUTCOME_CATALOG')
        require((distribution.semantics is DistributionSemantics.OPEN_WORLD)==(row['outside_field'] is not None),
            'TYPED_POLICY_OPEN_WORLD_OUTSIDE_VECTOR')
    return render


def owner_action_binding(policy):
    return digest(dict(purpose=PURPOSE,policy_hash=policy['policy_hash'],revision=policy['revision'],
        domain=policy['domain'],scope=policy['scope'],source_identity=policy['source_identity']))


class ExistingOwnerPolicyPort:
    """Adapter to actual current read-only owner contracts, never a new grant.

    Current exact-purpose adoption is separate from login, runtime launch and
    World approval. A synthetic owner store never supplies production authority.
    """
    def __init__(self,owner_service,session_store,owner_action=None):
        from .production_owner_enrollment import ProductionOwnerEnrollmentService
        from .production_owner_session_store import DurableOwnerLoginSessionStore
        require(type(owner_service) is ProductionOwnerEnrollmentService and type(session_store) is DurableOwnerLoginSessionStore,
            'TYPED_POLICY_EXISTING_OWNER_PORT_TYPES')
        self.owner_service=owner_service;self.session_store=session_store;self.owner_action=owner_action

    def inspect(self,policy,context,now):
        decision=self.owner_service.read_valuation_policy_approval(
            policy_hash=policy['policy_hash'],revision=policy['revision'],
            scope_hash=digest(policy['scope']),action_binding_hash=owner_action_binding(policy),
            session_store=self.session_store,owner_action=self.owner_action)
        require(type(decision) is dict and decision['purpose']==PURPOSE and
            decision['policy_hash']==policy['policy_hash'] and decision['revision']==policy['revision'] and
            decision['scope_hash']==digest(policy['scope']) and
            decision['action_binding_hash']==owner_action_binding(policy) and
            decision['status'] in ('UNKNOWN','TEST_ONLY_MATH_ADMITTED','OWNER_ADMITTED') and decision['authority_effect']=='NONE' and
            decision['world_execution_approval']=='NOT_GRANTED',
            'TYPED_POLICY_OWNER_APPROVAL_EXACT_BINDING')
        if decision['status']!='UNKNOWN':
            review=decision.get('review_material',{})
            receipt=decision.get('adoption_receipt',{})
            require(review.get('policy')==policy and review.get('policy_hash')==policy['policy_hash'] and
                review.get('scope_hash')==digest(policy['scope']) and review.get('action_binding_hash')==owner_action_binding(policy) and
                decision.get('permission')=='MATHEMATICAL_READ_ONLY' and
                (decision['status']=='TEST_ONLY_MATH_ADMITTED') is self.owner_service.store.testing_only and
                receipt.get('payload',{}).get('adoption_id')==decision.get('adoption_id'),
                'TYPED_POLICY_OWNER_APPROVAL_EXACT_BINDING')
            historical=self.owner_service.read_valuation_policy_history(
                adoption_id=decision['adoption_id'],policy_hash=policy['policy_hash'],revision=policy['revision'],
                scope_hash=digest(policy['scope']),action_binding_hash=owner_action_binding(policy),
                review_hash=receipt['payload']['review_hash'],consumed_at_utc=self.owner_service._now(),
                expected_adoption_receipt_hash=receipt['receipt_hash'])
            require(historical['status']=='HISTORICALLY_VALID' and historical['review_material']==review and
                historical['adoption_receipt']==receipt,'TYPED_POLICY_OWNER_APPROVAL_EXACT_BINDING')
        return decision


def produce_policy(policy,*,render,context,source_authority=None,owner_port=None,at=None):
    result=dict(version=VERSION,status='UNKNOWN',source_authenticity={'status':'UNKNOWN'},
        policy_validity={'status':'UNKNOWN'},owner_authorization={'status':'UNKNOWN'},scope='UNKNOWN',
        policy_hash=None,typed_materials=None,world_execution_approval='NOT_GRANTED',authority_effect='NONE')
    if policy is None:
        return {**result,'reason':'TYPED_POLICY_NOT_SUPPLIED'}
    policy=validate_policy_document(policy);_bind(policy,render,context)
    result.update(policy_hash=policy['policy_hash'],policy_validity={'status':'VALID','revision':policy['revision']})
    now=datetime.now(UTC) if policy['origin']=='OWNER_POLICY' else (at or datetime.now(UTC))
    require(isinstance(now,datetime) and now.utcoffset() is not None,'TYPED_POLICY_CURRENT_TIME')
    now=now.astimezone(UTC)
    if not(_utc(policy['effective_from_utc'])<=now<_utc(policy['expires_at_utc'])):
        return {**result,'reason':'TYPED_POLICY_NOT_CURRENT'}
    verifier=getattr(source_authority,'authenticate_typed_valuation_policy',None)
    if not callable(verifier):
        return {**result,'reason':'TYPED_POLICY_SOURCE_VERIFIER_UNAVAILABLE'}
    # This port must re-read current source/revision/revocation state each call,
    # including recovery. No cached source flag is accepted as a credential.
    attestation=verifier(deepcopy(policy),deepcopy(context))
    fields={'purpose','policy_hash','revision','source_identity','scope_hash','context_sha256','origin','status','source_reference'}
    require(type(attestation) is dict and set(attestation)==fields and attestation['purpose']==SOURCE_PURPOSE and
        attestation['policy_hash']==policy['policy_hash'] and attestation['revision']==policy['revision'] and
        attestation['source_identity']==policy['source_identity'] and attestation['scope_hash']==digest(policy['scope']) and
        attestation['context_sha256']==digest(context) and attestation['origin']==policy['origin'],
        'TYPED_POLICY_EXACT_SOURCE_ATTESTATION')
    _ref(attestation['source_reference'])
    if attestation['status']!='ACTIVE':
        return {**result,'source_authenticity':{'status':'NOT_CURRENT','reference':attestation['source_reference']},
            'reason':'TYPED_POLICY_SOURCE_REVOKED_OR_SUPERSEDED'}
    result.update(source_authenticity={'status':'VERIFIED','reference':attestation['source_reference'],
        'revision':policy['revision'],'context_sha256':digest(context)},typed_materials=policy)
    if policy['origin']=='SYNTHETIC_TEST_ONLY':
        return {**result,'status':'TEST_ONLY','scope':'TEST_ONLY','owner_authorization':{'status':'NOT_OWNER_AUTHORITY'},
            'reason':'SYNTHETIC_TYPED_POLICY_MATH_ONLY'}
    if owner_port is None:
        return {**result,'reason':'OWNER_VALUATION_APPROVAL_READ_PORT_UNAVAILABLE'}
    require(type(owner_port) is ExistingOwnerPolicyPort,'TYPED_POLICY_OWNER_PORT_REQUIRED')
    owner=owner_port.inspect(policy,context,now)
    result['owner_authorization']=owner
    if owner['status']=='TEST_ONLY_MATH_ADMITTED':
        return {**result,'status':'TEST_ONLY','scope':'TEST_ONLY',
            'reason':'EXACT_DURABLE_TEST_OWNER_POLICY_MATH_ONLY'}
    if owner['status']!='OWNER_ADMITTED':return {**result,'reason':owner['reason']}
    return {**result,'status':'OWNER_ADMITTED','scope':'OWNER_ADMITTED','reason':'CURRENT_TYPED_OWNER_POLICY_VALIDATED'}


def admit_policy(policy,context,*,render,authority=None,owner_service=None,session_store=None,owner_action=None,at=None):
    port=None
    if owner_service is not None or session_store is not None:
        port=ExistingOwnerPolicyPort(owner_service,session_store,owner_action)
    return produce_policy(policy,render=render,context=context,source_authority=authority,owner_port=port,at=at)


__all__=['VERSION','PURPOSE','SOURCE_PURPOSE','seal_policy','quantity_scope','validate_policy_document','owner_action_binding',
    'ExistingOwnerPolicyPort','produce_policy','admit_policy']
