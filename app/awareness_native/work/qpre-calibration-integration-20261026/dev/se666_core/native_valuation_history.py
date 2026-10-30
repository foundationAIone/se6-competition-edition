"""Frozen historical mathematics is explanatory, never fresh action authority.

Only the actual Native receipt and externally pinned retained state bind the
consumption time. A caller-supplied past timestamp alone proves no consumption.
New selections cannot receive this historical replay port.
"""
from copy import deepcopy
from pathlib import Path
import hashlib,json
from .observation_grounding import digest,require
from .qpre_calibration_v1 import QPREProbabilityRender
from . import typed_valuation_policy as policies

VERSION='se6-native-typed-history-v1'
# Reviewed additive, disabled-by-default awareness input. Only this exact pair
# is admitted, and only records without that new input can use compatibility.
# Exact emitted bytes, original calculation and final receipt are still checked.
_OPTIONAL_AWARENESS_COMPATIBILITY={(
    '3a8eb1a5af1565575c9c4194cc75a1e99031e06293108b378a11f943de06a8fe',
    'd1f88d61f9294b88178a270020811a1b147307a7b8798226b2fea9f972b41845')}


def capture(decision,authority):
    observation=decision['selection'].get('native_typed_valuation',{})
    if observation.get('typed_expectations') is None:return None
    port=getattr(authority,'typed_owner_policy_port',None)
    require(type(port) is policies.ExistingOwnerPolicyPort,'NATIVE_HISTORY_ACTUAL_OWNER_PORT')
    owner=observation['producer']['owner_authorization']
    require(owner['status'] in ('TEST_ONLY_MATH_ADMITTED','OWNER_ADMITTED'),'NATIVE_HISTORY_EXACT_ADOPTION_REQUIRED')
    from .typed_valuation_history import capture as freeze_math
    render=QPREProbabilityRender.model_validate_json(json.dumps(decision['selection']['probability_learning']['render']))
    archive=freeze_math(observation,render=render)
    binding=dict(version=VERSION,consumed_at_utc=port.owner_service._now().isoformat(),
        archive_sha256=digest(archive),decision_sha256=digest(decision),
        native_source_sha256=hashlib.sha256(Path(__file__).with_name('grounded_native_input.py').read_bytes()).hexdigest())
    return dict(binding=binding,archive=archive,original_decision=deepcopy(decision))


def replay(decision,*,history,authority,state,core,binding,actions,boundary,graph):
    """Validate only a previously journal-bound calculation, never new use."""
    from .typed_valuation_history import verify
    from .native_expected_value import source_context
    require(type(history) is dict and set(history)=={'binding','archive','original_decision','receipt_hash'},
        'NATIVE_HISTORY_FIELDS')
    original=history['original_decision'];frozen=history['binding']
    require(frozen['version']==VERSION and frozen['archive_sha256']==digest(history['archive']) and
        frozen['decision_sha256']==digest(original),'NATIVE_HISTORY_JOURNAL_BINDING')
    current_source=hashlib.sha256(Path(__file__).with_name('grounded_native_input.py').read_bytes()).hexdigest()
    compatible=(frozen['native_source_sha256'],current_source) in _OPTIONAL_AWARENESS_COMPATIBILITY and (
        'native_situated_awareness' not in boundary['selection_policy'])
    require(frozen['native_source_sha256']==current_source or compatible,
        'NATIVE_HISTORY_UNADMITTED_NATIVE_SOURCE_VERSION')
    verified=verify(history['archive'])
    observation=original['selection']['native_typed_valuation']
    require(verified['archive_sha256']==history['archive']['archive_sha256'],'NATIVE_HISTORY_MATH_ARCHIVE')
    actual=source_context(decision,state=state,core=core,binding=binding,actions=actions,boundary=boundary,graph=graph)
    require(actual is not None,'NATIVE_HISTORY_ACTUAL_CONTEXT_REQUIRED')
    render,_,eligible,eligibility,context=actual
    require(context==observation['context'] and eligibility==observation['eligibility'] and
        history['archive']['observation']==observation,'NATIVE_HISTORY_ACTUAL_CONTEXT_CHANGED')
    before=deepcopy(original['selection']);before.pop('native_typed_valuation',None)
    require(before==decision['selection'],'NATIVE_HISTORY_PREVALUE_CONSUMER_CHANGED')
    port=getattr(authority,'typed_owner_policy_port',None)
    require(type(port) is policies.ExistingOwnerPolicyPort,'NATIVE_HISTORY_ACTUAL_OWNER_PORT')
    owner=observation['producer']['owner_authorization'];policy=observation['producer']['typed_materials']
    require(owner['review_material']['policy']==policy and owner['permission']=='MATHEMATICAL_READ_ONLY' and
        owner['world_execution_approval']=='NOT_GRANTED','NATIVE_HISTORY_ORIGINAL_POLICY_BINDING')
    receipt=owner['adoption_receipt']
    verified_owner=port.owner_service.read_valuation_policy_history(
        adoption_id=owner['adoption_id'],policy_hash=policy['policy_hash'],revision=policy['revision'],
        scope_hash=digest(policy['scope']),action_binding_hash=policies.owner_action_binding(policy),
        review_hash=receipt['payload']['review_hash'],consumed_at_utc=frozen['consumed_at_utc'],
        expected_adoption_receipt_hash=receipt['receipt_hash'])
    require(verified_owner['status']=='HISTORICALLY_VALID' and verified_owner['review_material']==owner['review_material'] and
        verified_owner['adoption_receipt']==receipt and verified_owner['test_only'] is port.owner_service.store.testing_only,
        'NATIVE_HISTORY_INDEPENDENT_ADOPTION_INVALID')
    require((owner['status']=='TEST_ONLY_MATH_ADMITTED') is port.owner_service.store.testing_only,
        'NATIVE_HISTORY_AUTHORITY_SCOPE')
    return deepcopy(original)


def require_current_math_permission(pending,authority):
    """Historical validity never authorizes dispatch of a retained action."""
    observation=pending['prepared']['learned'].get('selection',{}).get('native_typed_valuation')
    if observation is None:return
    port=getattr(authority,'typed_owner_policy_port',None)
    require(type(port) is policies.ExistingOwnerPolicyPort,'PRE_EFFECT_CURRENT_VALUATION_AUTHORITY_REQUIRED')
    policy=observation['producer']['typed_materials']
    current=port.inspect(policy,observation['context'],port.owner_service._now())
    require(current['status']=='OWNER_ADMITTED' and current['permission']=='MATHEMATICAL_READ_ONLY',
        'PRE_EFFECT_CURRENT_VALUATION_AUTHORITY_REQUIRED')
