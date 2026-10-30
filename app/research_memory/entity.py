"""Actual non-authoritative Entity genesis and memory event admission ports."""
from datetime import datetime,UTC
from pathlib import Path
import hashlib,sys

CORE=Path(__file__).resolve().parents[1]/'awareness_native/work/qpre-calibration-integration-20261026/dev'
sys.path.insert(0,str(CORE));sys.dont_write_bytecode=True
from se666_core.entity_store import EntityStore
from se666_core.entity_runtime import LocalEntityRuntime
from se666_core.entity_simulation import create_shadow_entity_genesis
from se666_core.entity_state import EntityIdentityReference,LifecycleView,ControllerStatus,OperationalConnectionState,EmergencyStopState
from se666_core.embodiment_lifecycle import LifecycleState
from se666_core.epistemic_status import EpistemicStatus,UncertaintyRecord
from se666_core.operational_awareness import build_operational_awareness_state,RuntimeDecision
from se666_core.canonical_contracts import BoundaryDecision
from se666_core.sphere_of_mirrors import reflect_task
from se666_core.merkabah_rotation import rotate_perspectives
from se666_core.entity_events import EntityEventDraft,EventType,LoopName,EventEndpoint,EventSourceKind,ObservationProvenance,AuthorityStatus,MemoryPayload,MemoryEventOperation

SOURCE_FILES=[CORE/'se666_core'/name for name in ('entity_store.py','entity_runtime.py','entity_state.py','entity_events.py','three_loop_entity.py')]
def source_pins():return {str(p.relative_to(CORE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in SOURCE_FILES}

def initialize(store,identity_pin):
    at=datetime.now(UTC);intention='Retain attributed historical text as provisional evidence; no World or provider authority.'
    uncertainty=UncertaintyRecord(status=EpistemicStatus.DETERMINISTIC,confidence=1.0,
        known=('This is a disposable non-authoritative research Entity store.',),
        unknown=('Historical claims are not independently verified World facts.',),assumptions=(),inferences=(),symbolic=(),evidence_references=())
    awareness=build_operational_awareness_state(stated_intention=intention,interpreted_objective=intention,
        objective_status=EpistemicStatus.DETERMINISTIC,objective_confidence=1.0,cognition_mode='offline_fallback',
        current_state_present=True,classification='historical_text_development',classification_status=EpistemicStatus.DETERMINISTIC,
        classification_confidence=1.0,uncertainty=uncertainty,mirrors=reflect_task(intention),perspectives=rotate_perspectives(intention),
        runtime_decision=RuntimeDecision.ALLOW,effective_decision=BoundaryDecision.ALLOW,observed_at_utc=at)
    identity=EntityIdentityReference(instance_id='research-memory-'+identity_pin,identity_state_id='identity_'+identity_pin,
        identity_state_hash=identity_pin,constitution_version='NONAUTHORITATIVE_RESEARCH_GENESIS',constitution_hash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        owner_identity_reference='programmerONE',identity_lineage=('identity_'+identity_pin,))
    lifecycle=LifecycleView(durable_state=LifecycleState.PAUSED,operational_state=OperationalConnectionState.DISCONNECTED_SAFE,
        controller_status=ControllerStatus.ABSENT,controller_authoritative=False,emergency_stop=EmergencyStopState.ARMED,observed_at_utc=at)
    state=create_shadow_entity_genesis(identity=identity,lifecycle=lifecycle,operational_awareness=awareness,updated_at_utc=at,event_budget=512)
    return LocalEntityRuntime(store=store,runtime_session_id='research-history-admission').initialize(state=state)

def commit_candidate(store,*,subject,text,refs,key):
    at=datetime.now(UTC);runtime=LocalEntityRuntime(store=store,runtime_session_id='research-history-admission')
    draft=EntityEventDraft(event_type=EventType.MEMORY_CANDIDATE,occurred_at_utc=at,originating_loop=LoopName.EXTERNAL,
        source=EventEndpoint(kind=EventSourceKind.EXTERNAL_SOURCE,identifier='historical-text-development-source'),
        target=EventEndpoint(kind=EventSourceKind.SE6,identifier=store.reconstruct().state.identity.instance_id),
        relation='reported_historical_evidence',provenance=ObservationProvenance.EXTERNAL_RETRIEVED,
        epistemic_status=EpistemicStatus.REPORTED,authority_status=AuthorityStatus.NOT_REQUIRED,correlation_id=key,
        payload=MemoryPayload(operation=MemoryEventOperation.CANDIDATE,subject=subject,content_summary=text,evidence_references=tuple(refs)))
    ingress=runtime.enqueue(draft=draft,ingress_key=key)
    step=runtime.process_one()
    if step is None or step.ingress.ingress_id!=ingress.ingress_id:raise ValueError('HISTORY_FIFO_OR_COMMIT_UNCERTAIN')
    return step
