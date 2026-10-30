"""Actual Entity/sensor -> mapped evidence -> reflected Native narrowing.

This port reads existing stores and sensors. It cannot authorize an effect,
invent current runtime liveness, or identify finite scan features with the
owner's still-undefined numerical rho*R_self.
"""
from copy import deepcopy
from dataclasses import asdict
import json
from .canonical_contracts import canonical_sha256
from .observation_grounding import digest,require
from .entity_store import EntityStore
from .situated_entity import SituatedEntitySnapshot,RepositoryObservationPort,verify_situated_entity
from .native_self_features import derive_repository_features

VERSION='se6-native-situated-awareness-v1'
EVIDENCE_LABEL='situated-environment-evidence'


def validate_config(config):
    require(type(config) is dict and set(config)=={'version','snapshot','require_complete_environment'} and
        config['version']==VERSION and type(config['require_complete_environment']) is bool,'NATIVE_SITUATED_CONFIG')
    SituatedEntitySnapshot.model_validate_json(json.dumps(config['snapshot']))


class NativeSituatedPort:
    def __init__(self,entity_store,observation_port,*,runtime_ledger=None):
        require(type(entity_store) is EntityStore and type(observation_port) is RepositoryObservationPort,
            'NATIVE_SITUATED_ACTUAL_PORTS')
        self.entity_store=entity_store;self.observation_port=observation_port;self.runtime_ledger=runtime_ledger

    def read(self,config,binding):
        validate_config(config)
        supplied=SituatedEntitySnapshot.model_validate_json(json.dumps(config['snapshot']))
        require(supplied.entity_id==binding['entity_id'],'NATIVE_SITUATED_ENTITY_BINDING')
        remeasured=verify_situated_entity(self.entity_store,supplied,observation_port=self.observation_port,
            runtime_ledger=self.runtime_ledger)
        # The input keeps its original as-of meaning. Verification above reads
        # current sources and rejects semantic changes; its newer witness time
        # is not a new environmental fact or part of a deterministic input.
        actual=supplied
        measured=self.observation_port.read_snapshot(observed_at_utc=actual.observed_at_utc)
        observed=next(o for o in actual.observations if o.kind=='LOCAL_REPOSITORY_METADATA')
        expected=json.loads(observed.value_json)
        require(measured.tree_hash==expected['tree_hash'] and measured.entry_count==expected['entry_count'] and
            measured.truncated==expected['truncated'] and
            canonical_sha256(self.observation_port.policy.model_dump(mode='python'))==expected['policy_hash'],
            'NATIVE_SITUATED_CONCURRENT_SENSOR_CHANGE')
        _,current,lineage=self.entity_store.inspect_read_only()
        require(current is not None and current.state.entity_state_id==actual.entity_state_id and
            current.latest_receipt.receipt_id==actual.receipt_id,'NATIVE_SITUATED_CONCURRENT_ENTITY_CHANGE')
        before=lineage.states[-2] if len(lineage.states)>1 else lineage.states[-1]
        after=lineage.states[-1]
        old={r.relation_id:r.model_dump(mode='json') for r in before.environment.relations}
        new={r.relation_id:r.model_dump(mode='json') for r in after.environment.relations}
        delta=dict(version='se6-audited-environment-state-difference-v1',
            before_state_id=before.entity_state_id,after_state_id=after.entity_state_id,
            before_version=before.state_version,after_version=after.state_version,
            receipt_id=lineage.receipts[-1].receipt_id,
            added=[new[k] for k in sorted(set(new)-set(old))],
            removed=[old[k] for k in sorted(set(old)-set(new))],
            changed=[dict(before=old[k],after=new[k]) for k in sorted(set(old)&set(new)) if old[k]!=new[k]],
            claim='AUDITED_REDUCER_CHANGE_NOT_INDEPENDENT_WORLD_SEMANTIC_TRUTH')
        delta['difference_sha256']=digest(delta)
        context=dict(entity_id=actual.entity_id,identity_state_id=actual.identity_state_id,
            entity_state_id=actual.entity_state_id,entity_receipt_id=actual.receipt_id,
            situated_frame_hash=actual.frame_hash,native_state_hash=binding['entity_state'],
            native_source=binding['source'],native_epoch=binding['epoch'],native_memory_head=binding['memory_head'])
        features=derive_repository_features(measured,self.observation_port.policy,context=context)
        material=dict(version=VERSION,snapshot_id=actual.snapshot_id,snapshot_hash=actual.snapshot_hash,
            context=context,source_observation=observed.model_dump(mode='json'),features=features,entity_difference=delta,
            qualified_observations=[o.model_dump(mode='json') for o in actual.observations],
            situated_difference=actual.difference.model_dump(mode='json'),
            presence=actual.presence.model_dump(mode='json'),origin=actual.origin.model_dump(mode='json'),
            boundary=actual.boundary.model_dump(mode='json'),
            source_revalidation='CURRENT_SOURCE_REREAD_OF_STABLE_AS_OF_INPUT_NOT_A_NEW_OBSERVATION',
            authority_effect='NONE',world_execution_approval='NOT_GRANTED')
        return {**material,'projection_sha256':digest(material)}


def _port(authority):
    port=getattr(authority,'native_situated_port',None)
    require(type(port) is NativeSituatedPort,'NATIVE_SITUATED_ACTUAL_SOURCE_REQUIRED')
    return port


def _mapped_view(material):
    """Bounded exact references; never silently truncate source evidence.

    Full qualified observations remain in the verified Native result. The
    mapper's established 4000-character node domain carries their exact hash,
    cardinality, source/head/frame and the relevant scan features instead.
    """
    feature=material['features'];delta=material['entity_difference']
    return dict(version=VERSION,projection_sha256=material['projection_sha256'],
        snapshot_id=material['snapshot_id'],context=material['context'],
        features_sha256=feature['features_sha256'],entry_count=feature['entry_count'],
        entry_limit=feature['entry_limit'],is_complete=feature['is_complete'],
        observed_source=material['source_observation']['source_reference'],
        observation_id=material['source_observation']['observation_id'],
        qualified_observations_sha256=digest(material['qualified_observations']),
        qualified_observations_count=len(material['qualified_observations']),
        entity_difference_sha256=delta['difference_sha256'],
        changed_relation_count=len(delta['added'])+len(delta['removed'])+len(delta['changed']),
        evidence_scope='CONTENT_ADDRESSED_FULL_PROJECTION_NOT_A_PARTIAL_CATALOG',authority_effect='NONE')


def augment_graph(graph,config,authority,binding):
    from . import universal_mapper as mapper
    from .realization_frame import create_source_observation
    from .epistemic_status import EpistemicStatus as E
    material=_port(authority).read(config,binding)
    graph=mapper.UniversalMap.model_validate_json(json.dumps(graph))
    nodes=list(graph.vertices);relations=list(graph.relations);center=nodes[0]
    terminals={ref.node_id for r in graph.relations if r.label=='action-conditioned-prediction' and
        r.source_nodes==(center.reference,) for ref in r.target_nodes}
    observation=create_source_observation(source_reference='situated:'+material['projection_sha256'],
        summary='Direct bounded local metadata and audited Entity environment transition; no new World authority.',
        epistemic_status=E.MEASURED,evidence_references=(material['snapshot_id'],material['context']['entity_receipt_id']))
    for terminal in graph.vertices:
        if terminal.node_id not in terminals:continue
        node=mapper.create_mapper_node(kind=mapper.NodeKind.THING,label='situated:'+terminal.node_id,
            description=json.dumps(_mapped_view(material),sort_keys=True,separators=(',',':')),
            epistemic_status=E.MEASURED,source_observations=(observation,))
        nodes.append(node)
        relations.append(mapper.create_mapper_relation(kind=mapper.RelationKind.RELATES_TO,label=EVIDENCE_LABEL,
            source_nodes=(terminal,),target_nodes=(node,),epistemic_status=E.MEASURED,source_observations=(observation,)))
    require(terminals,'NATIVE_SITUATED_PREDICTION_RELATION_REQUIRED')
    return mapper.create_universal_map(vertices=nodes,relations=relations).model_dump(mode='json')


def apply(decision,*,state,core,authority,binding,actions,boundary,graph):
    config=boundary['selection_policy'].get('native_situated_awareness')
    if config is None:return decision
    material=_port(authority).read(config,binding)
    nodes={n['node_id']:n for n in graph['vertices']}
    evidence=[r for r in graph['relations'] if r['label']==EVIDENCE_LABEL]
    require(evidence and all(json.loads(nodes[r['target_nodes'][0]['node_id']]['description'])==_mapped_view(material) for r in evidence),
        'NATIVE_SITUATED_EXACT_MAPPED_EVIDENCE')
    audit=decision.setdefault('selection',{});sphere=audit.get('continuous_sphere')
    visible=[] if sphere is None else [r['relation_id'] for r in evidence
        if any(r['relation_id'] in view['visible_relations'] for view in sphere['views'])]
    observation=dict(projection=material,mapped_relation_ids=sorted(r['relation_id'] for r in evidence),
        visible_relation_ids=sorted(visible),constraint_consumed='REQUIRE_COMPLETE_POLICY_FILTERED_METADATA' if config['require_complete_environment'] else 'DESCRIPTIVE_ONLY',
        features_consumed=material['features']['features_sha256'],authority_effect='NONE',world_effects=0)
    observation['awareness_sha256']=digest(observation)
    audit['situated_awareness']=observation
    if decision['status']=='UNKNOWN':return decision
    if not config['require_complete_environment']:return decision
    complete=material['features']['is_complete'] and len(visible)==len(evidence)
    if complete:return decision
    action=next(a for a in actions if a['id']==decision['actions'][0])
    sensed=core.SEObservation('SITUATED_EVIDENCE_CHECK',binding['entity_id'],'complete-policy-filtered-metadata',
        source=binding['source'],evidence_refs=(material['snapshot_id'],material['context']['entity_receipt_id']))
    proposed=core.SECandidateTransition(state.state_hash,sensed.observation_id,None,(),False,
        core.SEAction(action['id'],json.dumps(action['payload'],sort_keys=True)),'Require complete, reflected local evidence')
    context=core._context(dict(identity=binding['entity_id'],authorized=boundary['authorized'],permissions=boundary['permissions'],
        integrity_valid=True,evidence_valid=False,max_actions=boundary['max_native_actions'],risk=0,max_risk=0,
        sensitive=False,human_approval_for=None))
    result=core._bound(state,sensed,proposed,context)
    require(result.outcome=='REFUSE','NATIVE_SITUATED_MASTER_BOUNDARY_REQUIRED')
    audit['situated_boundary']=dict(decision=asdict(result),context=context,source_native_state=state.state_hash,
        evidence=observation['awareness_sha256'],world_effects=0)
    return dict(status='UNKNOWN',actions=[],reason='SITUATED_ENVIRONMENT_INCOMPLETE_OR_UNREFLECTED',selection=audit)
