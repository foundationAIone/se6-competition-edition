"""Focused synthetic-input/disposable-Entity tests, never World/model evidence."""
from pathlib import Path
from datetime import datetime,UTC,timedelta
from types import SimpleNamespace
from copy import deepcopy
import json,sys
import pytest

CORE=Path(__file__).resolve().parents[1]/'awareness_native/work/qpre-calibration-integration-20261026/dev'
sys.path.insert(0,str(CORE))
from se666_core.native_dependency_agent import DependencyRepairAgent,verified_capability,applicable_memory
from se666_core.native_dependency_relation_v1 import VERSION
from se666_core.observation_grounding import digest
from se666_core.entity_events import EntityEventDraft,EventType,LoopName,EventEndpoint,EventSourceKind,ObservationProvenance,AuthorityStatus,ObservationPayload,VerificationPayload,VerificationResult
from se666_core.epistemic_status import EpistemicStatus
from scripts.run_dependency_awareness import commit_draft
from tests.test_entity_cognition_layer import _entity_store


def material(store):
    state=store.reconstruct().state
    observation=dict(manifest={'entry':'one','profiles':{'one':{'config':'a.json','gain':2,'offset':1},'two':{'config':'b.json','gain':3,'offset':0}}},
        schema={'version':VERSION,'goal':11,'setting_bounds':[0,100],'operation':'gain*limit+offset'},
        configs={'a.json':{'limit':0},'b.json':{'limit':0}},failure={'output':1,'returncode':3},file_hashes={'workload.py':'a'*64},
        context={'cwd':'synthetic-root-A','observed_root':'synthetic-root-A','entity_id':state.identity.instance_id,'identity_state_id':state.identity.identity_state_id})
    actions=[dict(id='set:'+n,payload={'op':'SET_INTEGER','path':n,'field':'limit'},cost=1) for n in observation['configs']]
    selected=deepcopy(actions[0]);selected['payload']['value']=5
    configuration={'unit_fixture':'EXPLICITLY_SIMULATED_CONFIG_NOT_EXECUTION'}
    witness={'goal':True,'action_sha256':digest(selected),'unit_fixture':'SIMULATED_WITNESS_NOT_WORLD'}
    capability=verified_capability(observation,selected,configuration,witness)
    return observation,actions,capability


def assimilate(store,capability,*,at=None,independent=True):
    at=at or datetime.now(UTC);state=store.reconstruct().state
    endpoint=lambda kind,ident:EventEndpoint(kind=kind,identifier=ident)
    common=dict(occurred_at_utc=at,originating_loop=LoopName.EXTERNAL,
        source=endpoint(EventSourceKind.COMPONENT,'SIMULATED_UNIT_WITNESS'),target=endpoint(EventSourceKind.SE6,state.identity.instance_id),
        provenance=ObservationProvenance.INDEPENDENTLY_VERIFIED,epistemic_status=EpistemicStatus.VERIFIED,authority_status=AuthorityStatus.NOT_REQUIRED,
        correlation_id='explicit-synthetic-unit')
    draft=EntityEventDraft(**common,event_type=EventType.OBSERVATION,relation='unit-capability-source',
        payload=ObservationPayload(world_node='unit',relation='unit',value_summary='No World action executed',
            provenance=ObservationProvenance.INDEPENDENTLY_VERIFIED,observed_at_utc=at,evidence_references=('unit-synthetic',),confidence_basis_points=10000))
    commit_draft(store,draft,'unit-source',at)
    event=next(e for e in reversed(store.reconstruct().historical_events) if isinstance(e.payload,ObservationPayload))
    draft=EntityEventDraft(**common,event_type=EventType.VERIFICATION,relation='verified_native_dependency_capability',
        payload=VerificationPayload(subject_event_id=event.event_id,result=VerificationResult.PASSED,independently_verified=independent,
            evidence_references=(digest(capability),capability['witness_sha256'],capability['configuration_sha256']),
            summary=json.dumps(capability,sort_keys=True,separators=(',',':'))))
    commit_draft(store,draft,'unit-verification',at)


def configured(store,observation,actions,capability,**options):
    # Exercise configure independently of the expensive Native reference setup;
    # actual construction/selection/effect is reserved for coordinator proof.
    agent=object.__new__(DependencyRepairAgent)
    agent.authority=SimpleNamespace(store=store,read_verified_agent_capability=lambda prior,phase:capability)
    agent.engine=SimpleNamespace(state=SimpleNamespace(identity=store.reconstruct().state.identity.instance_id))
    return agent.configure(observation,actions,prior={'synthetic_prior':True},phase=2,**options)


def test_real_becoming_memory_changes_actual_candidate_configuration_after_cold_read(tmp_path):
    store=_entity_store(tmp_path);observation,actions,capability=material(store)
    before=configured(store,observation,actions,capability)
    assert before[2] is False and len(before[0])==2
    assimilate(store,capability)
    from se666_core.entity_store import EntityStore
    cold=EntityStore.for_testing(tmp_path/'entity.sqlite3')
    observation['schema']['goal']=15  # same structural capability, new unsolved goal
    after=configured(cold,observation,actions,capability)
    assert after[2] is True and [a['id'] for a in after[0]]==['set:a.json']
    assert after[1]['verified_memory_id'] and after[1]['configuration_mode']=='REVALIDATED_RETAINED_SPECIALISM'
    assert after[1]['authority_effect']=='NONE' and not after[1]['general_agent_nursery']
    assert after[0][0]['payload']==actions[0]['payload']  # no expected patch supplied


@pytest.mark.parametrize('change',['root','relation','entry','source','bridge','expired','unverified'])
def test_stale_wrong_scope_or_unverified_memory_cannot_specialize(tmp_path,change):
    store=_entity_store(tmp_path);observation,actions,capability=material(store)
    assimilate(store,capability,at=datetime.now(UTC)-timedelta(days=2) if change=='expired' else None,
        independent=change!='unverified')
    if change=='root':observation['context'].update(cwd='synthetic-root-B',observed_root='synthetic-root-B')
    if change=='relation':observation['manifest']['profiles']['one']['gain']=4
    if change=='entry':observation['manifest']['entry']='two'
    if change=='source':observation['file_hashes']['workload.py']='b'*64
    selected,configuration,reused=configured(store,observation,actions,capability,memory_enabled=change!='bridge')
    assert reused is False and len(selected)==2 and configuration['verified_memory_id'] is None


def test_wrong_entity_rejected_before_configuration(tmp_path):
    store=_entity_store(tmp_path);observation,actions,capability=material(store)
    observation['context']['entity_id']='wrong'
    with pytest.raises(ValueError,match='AGENT_ENTITY_IDENTITY'):configured(store,observation,actions,capability)


def test_failed_or_unrelated_witness_cannot_create_verified_capability(tmp_path):
    store=_entity_store(tmp_path);observation,actions,_=material(store)
    action=deepcopy(actions[0]);action['payload']['value']=5
    with pytest.raises(ValueError,match='CAPABILITY_EXACT_VERIFIED_ACTION'):
        verified_capability(observation,action,{},dict(goal=False,action_sha256=digest(action)))
