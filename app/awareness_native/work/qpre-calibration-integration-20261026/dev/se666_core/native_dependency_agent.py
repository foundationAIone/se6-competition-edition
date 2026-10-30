"""One bounded executable Native specialism, not a general agent nursery.

The existing Native consumer is configured with current SELF/WORLD relations.
Only an exact verified Becoming memory, cross-bound to a completed Native
renewal, can specialize its next candidate catalog. Memory never grants action
authority; the original Boundary, dispatch and independent witness remain.
"""
from copy import deepcopy
from datetime import datetime,UTC
import json

from .grounded_native_input import GroundedNativeConsumer
from .native_dependency_relation_v1 import VERSION as DOMAIN,relation_index,pin
from .observation_grounding import digest,require
from .entity_events import VerificationPayload,VerificationResult
from .entity_state import MemoryStatus

VERSION='se6-native-dependency-agent-development-v1'
CAPABILITY='SET_INTEGER_EXISTING_CONFIG_LIMIT_0_TO_100'


def verified_capability(observation,action,configuration,witness):
    """Materialize only after independently witnessing this exact execution."""
    active=relation_index(observation)[observation['manifest']['entry']]
    require(witness['goal'] is True and witness['action_sha256']==digest(action)
        and active['config']==action['payload']['path'],'CAPABILITY_EXACT_VERIFIED_ACTION')
    return dict(version=VERSION,capability=CAPABILITY,domain=DOMAIN,operator_sha256=pin(),
        world_source_sha256=observation['file_hashes']['workload.py'],
        root_sha256=digest(observation['context']['observed_root']),
        edge_id=active['edge_id'],definition_sha256=active['definition_sha256'],
        path=active['config'],configuration_sha256=digest(configuration),
        witness_sha256=digest(witness),observation_sha256=digest(observation),authority_effect='NONE')


def applicable_memory(state,events,expected,observation,*,at=None):
    """Read exact active Entity truth; source bytes/history are checked by caller."""
    at=at or datetime.now(UTC)
    eligible=[]
    for record in state.memory.active_at(at):
        if record.status is not MemoryStatus.VERIFIED:continue
        try:material=json.loads(record.content_summary)
        except (TypeError,ValueError):continue
        if material!=expected:continue
        source=[e for e in events if e.event_id in record.source_event_ids]
        if not any(isinstance(e.payload,VerificationPayload)
            and e.payload.result is VerificationResult.PASSED
            and e.payload.independently_verified
            and e.payload.summary==record.content_summary
            and {digest(expected),expected['witness_sha256'],expected['configuration_sha256']}<=set(e.payload.evidence_references)
            for e in source):continue
        if not {digest(expected),expected['witness_sha256'],expected['configuration_sha256']}<=set(record.evidence_references):continue
        active=relation_index(observation)[observation['manifest']['entry']]
        if (expected['operator_sha256']==pin() and expected['domain']==DOMAIN
            and expected['world_source_sha256']==observation['file_hashes'].get('workload.py')
            and expected['root_sha256']==digest(observation['context']['observed_root'])
            and expected['edge_id']==active['edge_id']
            and expected['definition_sha256']==active['definition_sha256']
            and expected['path']==active['config']):eligible.append(record)
    return sorted(eligible,key=lambda r:(r.recorded_at_utc,r.memory_id))[-1] if eligible else None


class DependencyRepairAgent(GroundedNativeConsumer):
    """Actual Native implementation with a source-bound finite configuration.

    Construction/restoration, select, Boundary, dispatch, verification and
    renewal are the existing consumer methods, not a second agent framework.
    """
    def configure(self,observation,actions,*,prior=None,phase=1,memory_enabled=True):
        require(type(memory_enabled) is bool,'AGENT_MEMORY_FLAG')
        lineage=self.authority.store.reconstruct();state=lineage.state
        require(state.identity.instance_id==self.engine.state.identity
            and observation['context']['entity_id']==state.identity.instance_id
            and observation['context']['identity_state_id']==state.identity.identity_state_id,
            'AGENT_ENTITY_IDENTITY')
        active=relation_index(observation)[observation['manifest']['entry']]
        current=list(actions);record=None;reason='NO_VERIFIED_CAPABILITY_MEMORY'
        if prior is not None and memory_enabled:
            # Real Ports validates retained files, independent effect, complete
            # renewal and Entity receipt ancestry. A self-hashed memory alone
            # is insufficient to reach this consumer.
            expected=self.authority.read_verified_agent_capability(prior,phase-1)
            record=applicable_memory(state,lineage.historical_events,expected,observation)
            reason='MEMORY_NOT_CURRENT_OR_APPLICABLE'
            if record is not None:
                current=[a for a in actions if a['payload']['path']==active['config']]
                require(len(current)==1,'AGENT_UNAMBIGUOUS_VERIFIED_PRIMITIVE')
                reason='VERIFIED_CAPABILITY_REVALIDATED'
        elif not memory_enabled:reason='DEVELOPMENT_MEMORY_BRIDGE_DISABLED'
        configuration=dict(version=VERSION,implementation=type(self).__name__,domain=DOMAIN,
            operator_sha256=pin(),entity_id=state.identity.instance_id,
            world_source_sha256=observation['file_hashes'].get('workload.py'),
            identity_state_id=state.identity.identity_state_id,input_entity_state_id=state.entity_state_id,
            self_root_sha256=digest(observation['context']['observed_root']),
            world_observation_sha256=digest(observation),active_relation=deepcopy(active),
            need='CURRENT_PUBLIC_GOAL_NOT_MET',uncertainty='CONDITIONAL_PUBLIC_CONTRACT_NOT_WORLD_TRUTH',
            capability=CAPABILITY,capability_status='VERIFIED_IN_EXACT_APPLICABILITY' if record else 'IMPLEMENTED_REQUIRES_CONSEQUENCE_VERIFICATION',
            configuration_mode='REVALIDATED_RETAINED_SPECIALISM' if record else 'CURRENT_SOURCE_DERIVATION',
            reason=reason,verified_memory_id=record.memory_id if record else None,
            verified_memory_sources=list(record.source_event_ids) if record else [],
            available_candidates=[a['id'] for a in actions],configured_candidates=[a['id'] for a in current],
            authority_effect='NONE',general_agent_nursery=False)
        self.agent_configuration=configuration
        return deepcopy(current),deepcopy(configuration),record is not None
