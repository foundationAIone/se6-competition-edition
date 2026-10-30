"""Additive DEVELOPMENT consumer: raw-history grounding precedes Native choice.

Caller supplies the existing pinned Native/mapper/composer and independent
authority ports. This module creates no Entity, execution permission or trusted
issuer. Source/action admission and durable compare-and-swap remain host-owned.
"""
from copy import deepcopy
from dataclasses import dataclass, replace
from itertools import product
import json
import hashlib
from pathlib import Path

from .observation_grounding import VERSION, digest, fit, predict, require, verify_prediction


NATIVE_MATERIAL_CAP_V2 = 1024 * 1024
NATIVE_MATERIAL_CAP_CONTRACT_V2 = 'se6-native-material-exact-encoder-v2-development'


def encode_native_material(material, *, enforce_development_cap=False):
    """Preserve the actual producer's bytes; optionally enforce a new cap.

    Prefix/suffix at this producer: none. The opt-in 1 MiB bound is NEW, not
    historical Native capacity or complete eventual post-state proof.
    """
    require(type(enforce_development_cap) is bool, 'NATIVE_MATERIAL_CAP_FLAG')
    emitted=json.dumps(material,sort_keys=True)
    if enforce_development_cap:
        require(len(emitted.encode('utf-8')) <= NATIVE_MATERIAL_CAP_V2,
                'NATIVE_MATERIAL_DEVELOPMENT_BYTE_CAP')
    return emitted


@dataclass(frozen=True)
class GroundingObservation:
    """Explicit DEVELOPMENT operation, never disguised as owner ASSERT."""
    material_json: str
    source: str
    evidence_refs: tuple
    kind: str = 'GROUNDING_EVALUATE'

    @property
    def observation_id(self):
        return digest({'material': self.material_json, 'source': self.source, 'refs': self.evidence_refs})


class GroundingTranscriptAuthority:
    """Extend the existing batch-authentication port with committed chronology.

    Pins must be admitted by the independent host. A learner-created registry
    has no authenticity. DEV fixtures must declare SIMULATED_DEV_OBSERVER.
    """
    def __init__(self, existing_authority, chronologies, externally_admitted_pins):
        require(existing_authority is not None and chronologies
                and set(chronologies) == set(externally_admitted_pins), 'ADMITTED_CHRONOLOGY_REQUIRED')
        self.existing = existing_authority
        self.records = deepcopy(chronologies); self.pins = deepcopy(externally_admitted_pins)
        for key, value in self.records.items():
            require(digest(value) == self.pins[key], 'EXTERNAL_CHRONOLOGY_PIN')

    def authenticate_rows(self, *args):
        return self.existing.authenticate_rows(*args)

    def authenticate_cycle(self, committed, released, key):
        row = self.records[key]
        require(digest(row) == self.pins[key] and set(row) == {'origin', 'source', 'epoch', 'events'}
                and row['origin'] in ('SIMULATED_DEV_OBSERVER', 'INDEPENDENT_PUBLIC_OBSERVER'), 'CHRONOLOGY_SOURCE')
        events = row['events']
        require(len(events) >= 2 and all(e['sequence'] == i for i, e in enumerate(events)), 'CHRONOLOGY_SEQUENCE')
        commits = [e for e in events if e['kind'] == 'COMMIT' and e.get('sha256') == digest(committed)]
        releases = [e for e in events if e['kind'] == 'READBACK' and e.get('sha256') == digest(released)]
        require(len(commits) == len(releases) == 1 and commits[0]['sequence'] < releases[0]['sequence'], 'COMMIT_BEFORE_OBSERVATION')
        require(row['source'] == committed['binding']['source'] and row['epoch'] == committed['binding']['epoch'], 'CHRONOLOGY_SCOPE')
        return True


def certificate(proposal, rows, committed, released, *, training_key, release_key, chronology_key):
    """Untrusted candidate material; validate_certificate must run on consumption."""
    material = dict(version=VERSION, proposal=deepcopy(proposal), training=deepcopy(rows),
                    committed=deepcopy(committed), released=deepcopy(released),
                    training_key=training_key, release_key=release_key, chronology_key=chronology_key)
    return {**material, 'certificate_sha256': digest(material)}


def validate_certificate(value, authority):
    from .native_dependency_relation_v1 import is_certificate,validate
    if is_certificate(value):return validate(value,authority)
    require(authority is not None, 'NO_GROUNDING_AUTHORITY')
    require(digest({k: v for k, v in value.items() if k != 'certificate_sha256'})
            == value['certificate_sha256'], 'CERTIFICATE_CONTENT')
    proposal = value['proposal']
    require(value['version'] == VERSION and proposal['status'] == 'BOUNDED_CONSISTENT', 'CURRENT_LEARNER_VERSION')
    require(authority.authenticate_rows(value['training'], proposal['epoch'], value['training_key']), 'AUTHENTIC_TRAINING')
    require(fit(value['training'], proposal['actions'], limits=proposal['limits']) == proposal, 'REBUILD_LEARNED_INTERPRETATION')
    require(authority.authenticate_cycle(value['committed'], value['released'], value['chronology_key']), 'PROSPECTIVE_CHRONOLOGY')
    verified = verify_prediction(proposal, value['committed'], value['released'], authority, value['release_key'])
    require(verified['passed'], 'CONTRADICTED_GROUNDING')
    # A previously observed history is regression evidence, never fresh holdback.
    hold_history = value['committed']['history'] + value['released']
    episodes = {}
    for row in value['training']:
        episodes.setdefault(row['episode'], []).append(row)
    shape = lambda history: [(r['action'], r['raw']) for r in history]
    require(all(shape(hold_history) != shape(e) for e in episodes.values()), 'HOLDBACK_HISTORY_NOT_FRESH')
    return verified


def prepare_native_input(value, history, binding, admitted_actions, authority):
    """The missing upstream port. No caller-supplied semantic feature exists."""
    from .native_dependency_relation_v1 import is_certificate,prepare
    if is_certificate(value):return prepare(value,history,binding,admitted_actions,authority)
    verify = validate_certificate(value, authority)
    require(authority.authenticate_rows(history,binding['epoch'],digest(history)),'AUTHENTIC_CURRENT_HISTORY')
    expected = value['committed']['binding']
    require(binding['entity_id'] == expected['entity_id'] and binding['source'] == expected['source']
            and binding['epoch'] == expected['epoch'], 'CURRENT_ENTITY_SOURCE_SCOPE')
    require(set(binding) == set(expected) and binding['entity_state'] and binding['memory_head'], 'CURRENT_STATE_MEMORY_BINDING')
    require(admitted_actions and len({a['id'] for a in admitted_actions}) == len(admitted_actions)
            and all(set(a) == {'id', 'payload', 'cost'} and type(a['cost']) is int and a['cost'] >= 0
                    for a in admitted_actions), 'ADMITTED_ACTION_DEFINITIONS')
    ordered = sorted(admitted_actions, key=lambda a: (a['cost'], a['id']))
    predictions=[]
    for length in range(1,value['proposal']['limits']['max_plan_depth']+1):
        for word in product([a['id'] for a in ordered],repeat=length):
            require(len(predictions)<96,'MAPPED_CANDIDATE_BOUND')
            predictions.append(predict(value['proposal'],history,list(word)))
    return dict(status='MAPPED_CANDIDATE_PREDICTIONS', predictions=predictions, certificate_sha256=value['certificate_sha256'],
                verification=verify, binding=deepcopy(binding), history_sha256=digest(history),
                history=deepcopy(history),
                definitions_sha256=digest(admitted_actions), semantics='goal-success conditioned on learned observation history',
                authority_effect='NONE')


class GroundedNativeConsumer:
    def __init__(self, reference, native, authority, composer_type):
        self.c = reference.canonical
        self.native_base = deepcopy(native)
        self.engine = self.c.core.SE.restore(native['core_journal'], expected_head=native['core_head'])
        self.grounding_records = []
        self.authority = authority; self.composer_type = composer_type; self.pending = None
        self.invalidated = set(); self.used_attempts = set()
        self.dispatched = set(); self.renewals = []; self.current_certificate = None
        self.semantic_states = []  # opt-in candidate; absent from legacy exports
        self.probability_state = None; self.probability_events = []

    def _mapped_resource(self,prepared,binding, *, native_context=None):
        observation=self.c.frames.create_source_observation(source_reference='grounding:'+prepared['certificate_sha256'],
            summary='Authenticated finite raw-history predictions before candidate selection.',
            epistemic_status=self.c.E.REPORTED,evidence_references=('readback:'+prepared['verification']['readback_sha256'],))
        mapper=self.c.mapper
        center=mapper.create_mapper_node(kind=mapper.NodeKind.THING,label=binding['entity_id'],
            description=('Current research Entity' if native_context is None else
                         json.dumps(native_context,sort_keys=True,separators=(',',':'))),
            epistemic_status=self.c.E.REPORTED,source_observations=(observation,))
        nodes=[center];relations=[]
        for prediction in prepared['predictions']:
            node=mapper.create_mapper_node(kind=mapper.NodeKind.THING,label='continuation:'+digest(prediction),
                description=json.dumps(prediction,sort_keys=True,separators=(',',':')),
                epistemic_status=self.c.E.INFERRED,source_observations=(observation,))
            nodes.append(node)
            relations.append(mapper.create_mapper_relation(kind=mapper.RelationKind.RELATES_TO,
                label='action-conditioned-prediction',source_nodes=(center,),target_nodes=(node,),
                epistemic_status=self.c.E.INFERRED,source_observations=(observation,)))
        return mapper.create_universal_map(vertices=nodes,relations=relations).model_dump(mode='json')

    def _map_current(self,prepared,binding,boundary):
        policy=boundary.get('selection_policy',{})
        context=None
        if 'native_correspondence' in policy:
            from .grounded_canonical_context import native_context
            context=native_context(self.c,self.native_base,self.engine,representation_seed=policy.get('representation_seed'))
        if context is not None:
            from .grounded_canonical_context import center_view
            context=center_view(context)
        mapped=self._mapped_resource(prepared,binding,native_context=context)
        if prepared.get('domain')=='se6-native-dependency-relation-development-v1':
            from .native_dependency_relation_v1 import augment
            mapped=augment(mapped,prepared,self.c)
        if 'native_situated_awareness' in policy:
            from .native_situated_awareness import augment_graph
            mapped=augment_graph(mapped,policy['native_situated_awareness'],self.authority,binding)
        if 'reflection_consequences' in policy:
            from .native_reflection_consequences import authenticate, augment_graph
            rows=authenticate(policy['reflection_consequences'],self.authority,binding,
                prepared['history'],boundary['_reflection_admitted_actions'],policy['frame'])
            mapped=augment_graph(mapped,rows)
        return mapped

    @staticmethod
    def _choose_from_map(graph,admitted,budget,binding=None,semantic=None,probability_state=None):
        if budget.get('selection_policy'):
            from .grounded_canonical_selection import select_mapped
            return select_mapped(graph,admitted,budget,binding,semantic=semantic,probability_state=probability_state)
        # Candidate evaluation consumes mapped relationship targets, never the
        # earlier HOST plan or an unconsumed graph annotation.
        prices={a['id']:a['cost'] for a in admitted};candidates=[]
        for node in graph['vertices'][1:]:
            if not node['label'].startswith('continuation:'):continue
            prediction=json.loads(node['description']);word=prediction['continuation']
            if (prediction['outcomes'] and prediction['outcomes'][-1][1] is True and len(word)<=budget['remaining_actions']
                    and len(word)<=budget['remaining_effects'] and sum(prices[a] for a in word)<=budget['remaining_cost']):
                candidates.append((sum(prices[a] for a in word),len(word),tuple(word),prediction))
        if not candidates:return {'status':'UNKNOWN','actions':[]}
        _,_,word,prediction=min(candidates,key=lambda row:row[:3])
        return {'status':'GOAL_PATH_PREDICTED','actions':list(word),'prediction':prediction}

    def _native_evaluate(self, value, history, binding, admitted, boundary, mapped, *, semantic_override=None, decision_input=None, probability_override=None, historical_valuation=None):
        """Small typed input extension, using original state/receipt/boundary.

        The original ASSERT realization refuses unknown-origin observations.
        Do not bypass that refusal or relabel empirical predictions as owner
        assertions. This new operation evaluates an authenticated conditional
        model, adds no factual SERelation, and declares no World truth.
        """
        k = self.c.core
        prepared = prepare_native_input(value, history, binding, admitted, self.authority)
        require(self._map_current(prepared,binding,boundary)==mapped,'ACTUAL_MAPPER_INPUT_BINDING')
        semantic = None
        policy=boundary.get('selection_policy',{})
        if 'state_semantics' in policy:
            from . import candidate_state_transition as state_ops
            config=policy['state_semantics']; state_ops.validate_config(config)
            packet=semantic_override or (self.semantic_states[-1] if self.semantic_states else None)
            if packet is None:
                z=state_ops.initial_state(config,policy['frame'],value,history,binding)
                packet=state_ops.pack(z,state_ops.state_context(z))
            z=state_ops.recover(packet,packet['context'])
            if not state_ops.same(z['M'][-1]['history'],history):
                require(semantic_override is None,'REPLAY_HISTORY_REBIND_REFUSED')
                z=state_ops.refresh_observation(z,history,binding)
                packet=state_ops.pack(z,state_ops.state_context(z))
            require(state_ops.same(z['source_pins'],config['source_pins']) and
                    state_ops.same([g['definition'] for g in z['Theta']['governing']],config['governing']) and
                    state_ops.same(z['M'][0]['model_requires'],config['model_requires']) and
                    state_ops.same(state_ops.base_frame(z['Theta']['frame']),policy['frame']), 'RETAINED_SEMANTIC_CONFIG')
            semantic=dict(packet=packet,eligible=state_ops.eligible(z,value,history,binding),
                          proposal=value['proposal'],history=history)
            if 'decision_inputs_version' in policy:
                require(decision_input is not None,'TYPED_DECISION_INPUT_REQUIRED')
                p={**policy,'admitted_prices':{a['id']:a for a in admitted}}
                semantic['decision_inputs']=state_ops.decision_inputs(z,decision_input,mapped,p,binding,history)
            else:require(decision_input is None,'UNADMITTED_DECISION_INPUT')
            if 'native_correspondence' in policy:
                from .grounded_canonical_context import native_context
                semantic['native_context']=native_context(self.c,self.native_base,self.engine,
                    representation_seed=policy.get('representation_seed'))
        else:
            require(semantic_override is None and not self.semantic_states,'SEMANTIC_DOWNGRADE_REFUSED')
        probability=None
        if 'probability_learning' in policy:
            from . import qpre_native_learning as calibration
            frame=policy['frame']  # stable semantics; actual expanded frame remains bound in QPRE
            scope=calibration.scope_for(value,history,binding,admitted,frame)
            probability=deepcopy(probability_override or self.probability_state or calibration.initial(scope))
            require(probability['scope']==scope,'NATIVE_CALIBRATION_CONTEXT_CHANGED')
            calibration.snapshot(probability)
        else:require(probability_override is None and self.probability_state is None,'NATIVE_PROBABILITY_DOWNGRADE_REFUSED')
        if 'reflection_consequences' in policy:
            from .native_reflection_consequences import authenticate
            require(semantic is not None,'REFLECTION_TYPED_SEMANTICS_REQUIRED')
            semantic['reflection_evidence']=authenticate(policy['reflection_consequences'],self.authority,
                binding,history,admitted,policy['frame'])
        selected=self._choose_from_map(mapped,admitted,boundary,binding,semantic,probability)
        from .native_reflection_consequences import apply_boundary
        selected=apply_boundary(selected,self.engine.state,k,binding,admitted,boundary)
        from .native_situated_awareness import apply as apply_situated
        selected=apply_situated(selected,state=self.engine.state,core=k,authority=self.authority,
            binding=binding,actions=admitted,boundary=boundary,graph=mapped)
        from .native_expected_value import observe as observe_value
        if historical_valuation is None:
            selected=observe_value(selected,state=self.engine.state,core=k,authority=self.authority,
                binding=binding,actions=admitted,boundary=boundary,graph=mapped)
        else:
            from .native_valuation_history import replay
            selected=replay(selected,history=historical_valuation,state=self.engine.state,core=k,authority=self.authority,
                binding=binding,actions=admitted,boundary=boundary,graph=mapped)
        material = dict(certificate=value, history=history, binding=binding, actions=admitted,mapped=mapped)
        if probability is not None:material['probability_state']=deepcopy(probability)
        if decision_input is not None:material['decision_input']=deepcopy(decision_input)
        if semantic is not None: material['semantic_packet']=deepcopy(semantic['packet'])
        valuation_history=None
        if policy.get('native_typed_valuation',{}).get('history_contract') is not None:
            from .native_valuation_history import capture
            valuation_history=historical_valuation or capture(selected,self.authority)
            if valuation_history is not None:
                material['valuation_history_binding']=deepcopy(valuation_history['binding'])
        else:require(historical_valuation is None,'NATIVE_HISTORY_OPT_IN_REQUIRED')
        enforce_cap=policy.get('native_material_contract')==NATIVE_MATERIAL_CAP_CONTRACT_V2
        emitted=encode_native_material(material,enforce_development_cap=enforce_cap)
        capacity=None
        if enforce_cap:
            raw=emitted.encode('utf-8')
            capacity=dict(version=NATIVE_MATERIAL_CAP_CONTRACT_V2,bytes=len(raw),limit=NATIVE_MATERIAL_CAP_V2,
                emitted_sha256=hashlib.sha256(raw).hexdigest(),encoder='json.dumps(sort_keys=True); UTF8; default ASCII escaping and separators',
                encoder_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),enforced=True,
                scope='ACTUAL_CURRENT_NATIVE_INPUT_ONLY_NOT_FUTURE_FULL_WRAPPER')
            if historical_valuation is not None:
                # The byte codec is verified below. Original source/version
                # attribution is retained, never replaced by today's source.
                capacity['encoder_source_sha256']=historical_valuation['binding']['native_source_sha256']
            selected.setdefault('selection',{})['native_material_capacity']=capacity
        obs = GroundingObservation(emitted, 'authenticated-grounding',
                                   ('grounding:'+value['certificate_sha256'],))
        expected = json.dumps({'decision':selected, 'mapping_input_sha256':digest(mapped),
                              'world_truth_verified':False},sort_keys=True,separators=(',',':'))
        action = k.SEAction('GROUNDING_EVALUATE',obs.material_json)
        candidate = k.SECandidateTransition(self.engine.state.state_hash,obs.observation_id,None,(),False,action,expected)
        # External host permissions for actual World actions remain separate.
        native_limit=boundary['max_native_actions']
        if semantic is not None and 'native_context' in semantic:
            from .grounded_canonical_context import effective_native_limit
            native_limit=effective_native_limit(semantic['native_context'],native_limit)
        ctx = k._context(dict(identity=binding['entity_id'],authorized=boundary['authorized'],
            permissions=boundary['native_permissions'],integrity_valid=True,evidence_valid=True,
            max_actions=native_limit,risk=0,max_risk=0,sensitive=False,human_approval_for=None))
        bound = k._bound(self.engine.state,obs,candidate,ctx)
        require(bound.outcome == 'ALLOW','NATIVE_GROUNDING_BOUNDARY_REFUSED')
        # Registered evaluator recomputes from authenticated raw records, never
        # echoes an ASSERT or a caller-supplied predicted value.
        actual = prepare_native_input(value,history,binding,admitted,self.authority)
        recomputed_map=self._map_current(actual,binding,boundary)
        recomputed=self._choose_from_map(recomputed_map,admitted,boundary,binding,semantic,probability)
        recomputed=apply_boundary(recomputed,self.engine.state,k,binding,admitted,boundary)
        recomputed=apply_situated(recomputed,state=self.engine.state,core=k,authority=self.authority,
            binding=binding,actions=admitted,boundary=boundary,graph=recomputed_map)
        if historical_valuation is None:
            recomputed=observe_value(recomputed,state=self.engine.state,core=k,authority=self.authority,
                binding=binding,actions=admitted,boundary=boundary,graph=recomputed_map)
        else:
            recomputed=replay(recomputed,history=historical_valuation,state=self.engine.state,core=k,authority=self.authority,
                binding=binding,actions=admitted,boundary=boundary,graph=recomputed_map)
        if enforce_cap:
            recomputed_material={**material,'mapped':recomputed_map}
            require(encode_native_material(recomputed_material,enforce_development_cap=True)==emitted,
                'NATIVE_ACTUAL_ENCODER_RECOMPUTATION')
            recomputed.setdefault('selection',{})['native_material_capacity']=deepcopy(capacity)
        observed = json.dumps({'decision':recomputed,'mapping_input_sha256':digest(recomputed_map),
                              'world_truth_verified':False},sort_keys=True,separators=(',',':'))
        consequence = k.SEConsequence(action.action_id,True,observed,obs.evidence_refs)
        verification = k.SEVerification(observed == expected,('AUTHENTIC_CONDITIONAL_MODEL_RECOMPUTED',),obs.evidence_refs)
        require(verification.passed,'ACTUAL_NATIVE_CONSUMPTION_FAILED')
        before = self.engine.state; after = replace(before,version=before.version+1,actions_used=before.actions_used+1)
        receipt = k.SETransitionReceipt(before,obs,(),candidate,bound,json.dumps(ctx,sort_keys=True),action,
            expected,consequence,verification,(),after,self.engine.receipts[-1].receipt_hash if self.engine.receipts else None)
        k._validate_state(after)
        self.engine._receipts += (receipt,);self.engine._state = after
        record=dict(material=deepcopy(material),boundary=deepcopy(boundary),receipt=receipt.to_record())
        if valuation_history is not None:
            record['valuation_history']={**deepcopy(valuation_history),'receipt_hash':receipt.receipt_hash}
        self.grounding_records.append(record)
        if semantic is not None and (not self.semantic_states or
                digest(semantic['packet'])!=digest(self.semantic_states[-1])):
            self.semantic_states.append(deepcopy(semantic['packet']))
        if probability is not None: self.probability_state=deepcopy(probability)
        return receipt

    def select(self, value, history, binding, actions, boundary, attempt_id, *, mapping_enabled=True, decision_input=None):
        require(attempt_id not in self.used_attempts and self.pending is None, 'DUPLICATE_OR_PENDING_ATTEMPT')
        require(binding['entity_id'] == self.engine.state.identity and binding['entity_state'] == self.engine.state.state_hash,
                'ACTUAL_NATIVE_STATE_BINDING')
        require((binding['source'], binding['epoch']) not in self.invalidated, 'INVALIDATED_SOURCE_EPOCH')
        require(boundary['authorized'] is True and boundary['identity'] == binding['entity_id'], 'CURRENT_HOST_AUTHORITY')
        require(all(type(boundary[k]) is int and boundary[k]>=0 for k in ('remaining_actions','remaining_effects','remaining_cost')),
                'CURRENT_RESOURCE_LIMITS')
        require({'READ_CURRENT','ARCHIVE_RETAIN'}<=set(boundary['retention_permissions']),'EXPLICIT_MODEL_RETENTION_RIGHTS')
        admitted = [a for a in actions if a['id'] in boundary['permissions']]
        require(admitted, 'NO_PERMITTED_ACTION')
        if 'reflection_consequences' in boundary.get('selection_policy',{}):
            boundary=deepcopy(boundary)
            boundary['_reflection_admitted_actions']=deepcopy(admitted)
        if not mapping_enabled:
            return {'status': 'UNKNOWN', 'reason': 'LEARNED_MAPPING_DISABLED', 'effect': False}
        # Exact selected typed primitives are checked and actually consumed.
        node = lambda i, ins, outs: dict(id=i, inputs=ins, outputs=outs, permissions=[],
            evidence=['AUTHENTIC_GROUNDING'], current_epoch=True, cost=1, source_id=VERSION,
            verifier='Source-bound authenticated observation-grounding')
        composer = self.composer_type([
            node('map_grounded_history', ['CERTIFIED_RAW_HISTORY'], ['MAPPED_PREDICTION']),
            node('consume_native_prediction', ['MAPPED_PREDICTION'], ['NATIVE_RECALLED_PATH']),
            node('bind_admitted_action', ['NATIVE_RECALLED_PATH'], ['EXACT_PENDING_ACTION'])])
        context = dict(permissions=[], evidence=['AUTHENTIC_GROUNDING'], epoch=1, evidence_epoch=1,
                       source_fingerprint=composer.source_fingerprint, authority_scope='DEVELOPMENT_GROUNDING')
        composed = composer.plan(['EXACT_PENDING_ACTION'], ['CERTIFIED_RAW_HISTORY'], context)
        require(composed['status']=='VIABLE_PATHS','CURRENT_COMPOSER_PATH')
        path=min(composed['plans'],key=lambda p:(len(p),p))
        require(path==['map_grounded_history','consume_native_prediction','bind_admitted_action'],'UNSUPPORTED_REGISTERED_PATH')
        self.used_attempts.add(attempt_id)
        self.current_certificate = deepcopy(value)
        resources={'CERTIFIED_RAW_HISTORY':value};trace=[]
        for primitive in path:
            node=next(n for n in composer.catalog if n['id']==primitive)
            require(set(node['inputs'])<=set(resources),'REGISTERED_INPUT_TAG_FLOW')
            if primitive=='map_grounded_history':
                prepared=prepare_native_input(value,history,binding,admitted,self.authority)
                graph=self._map_current(prepared,binding,boundary)
                produced={'MAPPED_PREDICTION':graph}
            elif primitive=='consume_native_prediction':
                receipt=self._native_evaluate(value,history,binding,admitted,boundary,resources['MAPPED_PREDICTION'],decision_input=decision_input)
                require(receipt.verification.passed,'ACTUAL_NATIVE_CONSUMPTION_FAILED')
                decision=json.loads(receipt.observed_consequence.result)['decision']
                if decision['status']=='UNKNOWN':return {'status':'UNKNOWN','effect':False,'native_receipts':[receipt.to_record()], 'decision':decision}
                produced={'NATIVE_RECALLED_PATH':decision}
            else:
                decision=resources['NATIVE_RECALLED_PATH']
                selected_action=next(a for a in admitted if a['id']==decision['actions'][0])
                if prepared.get('domain')=='se6-native-dependency-relation-development-v1':
                    from .native_dependency_relation_v1 import instantiate
                    selected_action=instantiate(selected_action,decision['prediction'])
                produced={'EXACT_PENDING_ACTION':selected_action}
            require(set(produced)==set(node['outputs']),'REGISTERED_OUTPUT_TAG_FLOW')
            trace.append(dict(primitive=primitive,input_sha256=digest({k:resources[k] for k in node['inputs']}),output_sha256=digest(produced)))
            resources.update(produced)
        recalled=resources['NATIVE_RECALLED_PATH']['actions']
        prepared['learned']=resources['NATIVE_RECALLED_PATH']
        action = resources['EXACT_PENDING_ACTION']
        self.pending = dict(attempt_id=attempt_id, action=deepcopy(action), prepared=prepared,
                            mapping_hash=graph['map_hash'], core_head=receipt.receipt_hash)
        if 'retention_limits' in boundary.get('selection_policy',{}):
            self.pending['retention_limits']=deepcopy(boundary['selection_policy']['retention_limits'])
        return dict(status='SELECTED_PENDING_EXECUTION', pending=deepcopy(self.pending),
                    native_receipts=[receipt.to_record()], mapper=graph,
                    consumed_path=path,primitive_trace=trace, effect=False)

    def dispatch(self, *, current_head, current_permission_verifier, existing_dispatcher, durable_attempts,
                 durable_prior_head):
        require(self.pending is not None and current_head == self.pending['prepared']['binding']['memory_head'], 'ATOMIC_CURRENT_HEAD')
        require(self.pending['attempt_id'] not in self.dispatched, 'EFFECT_ALREADY_DISPATCHED_NO_RETRY')
        from .native_valuation_history import require_current_math_permission
        require_current_math_permission(self.pending,self.authority)
        representation=self.grounding_records[-1]['boundary'].get('selection_policy',{}).get('representation_seed')
        if representation is not None:
            from .grounded_canonical_context import native_context
            # Native computation may have advanced counters since C. Check its
            # actual successor representation before admitting a World effect.
            native_context(self.c,self.native_base,self.engine,representation_seed=representation)
        if self.semantic_states:
            from . import grounded_canonical_context as canonical_state
            from . import candidate_state_transition as state_ops
            require('retention_limits' in self.pending, 'PRE_EFFECT_RETENTION_CONTRACT_REQUIRED')
            packet=self.semantic_states[-1]
            z=state_ops.recover(packet,packet['context'])
            retained_before=self.export()
            retained_before['pending'].pop('retention_reservation',None)
            reservation=canonical_state.reserve(z,self.pending,self.pending['retention_limits'],
                                                self.current_certificate['proposal'],retained_before)
            self.pending['retention_reservation']=reservation
        # Only the admitted existing host dispatcher may perform the effect.
        # This callback must verify current exact-source permission, not return
        # a learner/producer supplied Boolean.
        current_permission_verifier(deepcopy(self.pending))
        attempt = self.pending['attempt_id']
        # Reuse the existing nonrefundable claim and unresolved-partial guard.
        # It persists duplicate protection across a replacement process.
        durable_attempts.begin(attempt, self.pending, durable_prior_head)
        self.dispatched.add(attempt)
        try:
            result = existing_dispatcher(deepcopy(self.pending))
            durable_attempts.complete({'core_head': self.pending['core_head'], 'pending': self.pending})
        except BaseException as error:
            durable_attempts.failed(str(error), {'attempt_id': attempt})
            raise
        finally:
            durable_attempts.close()
        return result

    def verify_cycle(self, witness, *, independent_effect_verifier, durable_renewal_writer,
                     independent_renewal_verifier):
        require(self.pending is not None and self.pending['attempt_id'] in self.dispatched, 'DISPATCHED_PENDING_REQUIRED')
        pending = deepcopy(self.pending)
        # Purpose-specific existing host ports must authenticate the exact
        # independent bytes, issuer and scope. No producer verified flag is used.
        effect_verified=independent_effect_verifier(witness, pending)
        dependency_domain=self.current_certificate.get('version')=='se6-native-dependency-relation-development-v1'
        if dependency_domain:require(effect_verified is True,'DEPENDENCY_INDEPENDENT_WORLD_EFFECT_REQUIRED')
        if self.probability_state is not None:
            require(effect_verified is True,
                'NATIVE_CALIBRATION_INDEPENDENT_EFFECT_REQUIRED')
            native_receipt=next((r for r in self.engine.receipts if r.receipt_hash==pending['core_head']),None)
            require(native_receipt is not None and native_receipt.verification.passed and
                json.loads(native_receipt.observed_consequence.result)['decision']==pending['prepared']['learned'],
                'NATIVE_CALIBRATION_CONSUMED_DECISION')
        if self.semantic_states and 'retention_reservation' in pending:
            from . import grounded_canonical_context as canonical_state
            from . import candidate_state_transition as state_ops
            packet=self.semantic_states[-1]
            before=self.export()
            before['pending'].pop('retention_reservation')
            before['dispatched'].remove(pending['attempt_id'])
            canonical_state.validate_reservation(state_ops.recover(packet,packet['context']),pending,
                pending['retention_reservation'],self.current_certificate['proposal'],before)
            canonical_state.verify_envelope(witness,pending['retention_reservation'])
        binding = pending['prepared']['binding']
        require(witness['purpose'] == 'GROUNDING_WORLD_EFFECT' and witness['entity_id'] == binding['entity_id']
                and witness['attempt_id'] == pending['attempt_id'] and witness['source'] == binding['source']
                and witness['epoch'] == binding['epoch'] and witness['action_sha256'] == digest(pending['action'])
                and witness['before_head'] == binding['memory_head'], 'EXACT_WORLD_WITNESS_BINDING')
        from .observation_grounding import raw_id
        predicted = pending['prepared']['learned']['prediction']['outcomes'][0]
        require(type(witness['goal']) is bool, 'WORLD_GOAL_BOOLEAN')
        passed = predicted == [raw_id(witness['raw']), witness['goal']]
        prior_pending = deepcopy(self.pending)
        record = dict(status='VERIFIED_PREDICTION' if passed else 'CONTRADICTED', witness_sha256=digest(witness),
                      source=binding['source'], epoch=binding['epoch'], attempt_id=pending['attempt_id'],
                      before_head=binding['memory_head'], goal=witness['goal'], passed=passed)
        require('observation_row' in witness and witness['observation_row']['raw']==witness['raw']
                and witness['observation_row']['goal']==witness['goal']
                and witness['observation_row']['action']==pending['action']['id'], 'ACTUAL_OBSERVATION_HISTORY_BINDING')
        from .observation_grounding import beliefs
        next_history=deepcopy(pending['prepared'].get('history',[]))
        require(next_history,'PENDING_CURRENT_HISTORY_REQUIRED')
        next_history.append(deepcopy(witness['observation_row']))
        record['history_after']=next_history
        record['remaining_path']=pending['prepared']['learned']['actions'][1:]
        record['belief_after']=([dict(domain='se6-native-dependency-relation-development-v1',observed_raw=witness['raw'])] if passed else []) if dependency_domain else ([state for _,state in beliefs(self.current_certificate['proposal'],next_history)] if passed else [])
        next_packet=None
        if self.semantic_states:
            from . import candidate_state_transition as state_ops
            previous=self.semantic_states[-1]
            z=state_ops.recover(previous,previous['context'])
            successor=state_ops.advance(z,witness,pending,self.engine.state.state_hash,next_history,passed)
            next_packet=state_ops.pack(successor,state_ops.state_context(successor))
            state_ops.recover(next_packet,state_ops.state_context(successor))
            record['semantic_successor_sha256']=digest(next_packet)
        old_probability=deepcopy(self.probability_state)
        if self.probability_state is not None:
            from .qpre_native_learning import feedback
            after_probability, probability_event=feedback(self.probability_state,pending,witness,verified_effect=effect_verified)
            self.probability_state=after_probability
            self.probability_events.append(probability_event)
            record['probability_event_sha256']=probability_event['record_sha256']
        if not passed:
            self.contradict(binding['source'], binding['epoch'])
        # State retained after observation; no answer or private World rule is
        # supplied to the restored learner. Renewal must be independently read.
        self.pending = None
        self.renewals.append(record)
        if next_packet is not None: self.semantic_states.append(next_packet)
        state = self.export()
        try:
            receipt = durable_renewal_writer(state, binding['memory_head'])
            renewal_verified=independent_renewal_verifier(receipt, state, binding['memory_head'])
            if dependency_domain:require(renewal_verified is True,'DEPENDENCY_INDEPENDENT_RENEWAL_REQUIRED')
            if old_probability is not None:
                require(renewal_verified is True,'NATIVE_CALIBRATION_INDEPENDENT_RENEWAL_REQUIRED')
            require(receipt['purpose'] == 'GROUNDING_DURABLE_RENEWAL'
                    and receipt['state_sha256'] == digest(state) and receipt['previous_head'] == binding['memory_head'], 'EXACT_RENEWAL_BINDING')
        except BaseException:
            self.pending = prior_pending
            self.probability_state=old_probability
            if old_probability is not None:self.probability_events.pop()
            self.renewals.pop()
            if next_packet is not None: self.semantic_states.pop()
            raise
        return {**record, 'renewal_receipt': receipt}

    def retain_decision(self, *, durable_renewal_writer, independent_renewal_verifier):
        """Use the existing durable ports for a consumed no-World decision.

        No effect receipt is fabricated; the external observation stays exact.
        Head/source/authority/CAS remain the existing host's responsibility.
        """
        from . import candidate_state_transition as state_ops
        require(self.pending is None and self.semantic_states and self.grounding_records,'LOCAL_DECISION_STATE')
        native=self.grounding_records[-1];binding=native['material']['binding']
        require(native['receipt']['receipt_hash']==self.engine.receipts[-1].receipt_hash,'LOCAL_DECISION_NATIVE_HEAD')
        old=self.semantic_states[-1];z=state_ops.recover(old,old['context'])
        successor=state_ops.advance_decision(z,native,self.engine.state.state_hash)
        packet=state_ops.pack(successor,state_ops.state_context(successor))
        record=dict(status='VERIFIED_LOCAL_DECISION',local_decision_receipt=native['receipt']['receipt_hash'],
            semantic_successor_sha256=digest(packet),before_head=binding['memory_head'],world_effects=0)
        self.semantic_states.append(packet);self.renewals.append(record);state=self.export()
        try:
            receipt=durable_renewal_writer(state,binding['memory_head'])
            require(independent_renewal_verifier(receipt,state,binding['memory_head']) is True,
                    'LOCAL_DECISION_INDEPENDENT_RENEWAL_REQUIRED')
            require(receipt['purpose']=='GROUNDING_DURABLE_RENEWAL' and receipt['state_sha256']==digest(state)
                and receipt['previous_head']==binding['memory_head'],'EXACT_RENEWAL_BINDING')
        except BaseException:
            self.semantic_states.pop();self.renewals.pop();raise
        return {**record,'renewal_receipt':receipt}

    def export(self):
        result = dict(version=VERSION, entity_id=self.engine.state.identity,
                    native=deepcopy(self.native_base), grounding_records=deepcopy(self.grounding_records),
                    current_core_head=self.engine.receipts[-1].receipt_hash if self.engine.receipts else None,
                    certificate=deepcopy(self.current_certificate), invalidated=[list(x) for x in sorted(self.invalidated)],
                    used_attempts=sorted(self.used_attempts), dispatched=sorted(self.dispatched),
                    pending=deepcopy(self.pending), renewals=deepcopy(self.renewals))
        if self.probability_state is not None:
            result['probability_state']=deepcopy(self.probability_state)
            result['probability_events']=deepcopy(self.probability_events)
        if self.semantic_states: result['semantic_states']=deepcopy(self.semantic_states)
        if any('retention_limits' in r['boundary'].get('selection_policy',{}) for r in self.grounding_records):
            from .grounded_canonical_context import CODEC
            result['retention_codec']=CODEC
        return result

    @classmethod
    def restore(cls, reference, state, authority, composer_type, *, expected_sha256, independent_learning_verifier=None):
        require(digest(state) == expected_sha256 and state['version'] == VERSION, 'EXTERNAL_RETAINED_STATE_PIN')
        if state['certificate'] is not None:
            validate_certificate(state['certificate'], authority)
        result = cls(reference, state['native'], authority, composer_type)
        probability=state.get('probability_state')
        events=state.get('probability_events',[])
        from .qpre_native_learning import verify_history, initial
        verify_history(probability,events,independent_learning_verifier)
        replay_probability=initial(probability['scope']) if probability is not None else None
        event_index=0
        require(len(events)==len({e['pending']['core_head'] for e in events}), 'NATIVE_CALIBRATION_DUPLICATE_NATIVE_HEAD')
        require([r.get('probability_event_sha256') for r in state['renewals'] if 'probability_event_sha256' in r]==
                [e['record_sha256'] for e in events], 'NATIVE_CALIBRATION_RENEWAL_LINEAGE')
        packets=state.get('semantic_states',[])
        if packets:
            from . import candidate_state_transition as state_ops
            state_ops.verify_lineage(packets,state['grounding_records'],state['renewals'],native_state_hash=result.c.core._hash)
        for record in state['grounding_records']:
            material=record['material']
            require(material['binding']['entity_state']==result.engine.state.state_hash,'RESTORED_NATIVE_STATE_ANCESTRY')
            recorded_probability=material.get('probability_state')
            if recorded_probability is not None:
                require(recorded_probability==replay_probability,'NATIVE_PROBABILITY_REPLAY_CHRONOLOGY')
            packet=material.get('semantic_packet')
            if packet is not None: require(any(digest(packet)==digest(p) for p in packets),'REPLAY_RETAINED_STATE_MEMBERSHIP')
            historical=record.get('valuation_history')
            if historical is not None:
                require(historical['receipt_hash']==record['receipt']['receipt_hash'] and
                    material.get('valuation_history_binding')==historical['binding'],'NATIVE_HISTORY_ORIGINAL_RECEIPT_BINDING')
            else:require('valuation_history_binding' not in material,'NATIVE_HISTORY_ARCHIVE_REQUIRED')
            receipt=result._native_evaluate(material['certificate'],material['history'],material['binding'],material['actions'],record['boundary'],material['mapped'],semantic_override=packet,decision_input=material.get('decision_input'),probability_override=recorded_probability,historical_valuation=historical)
            require(digest(receipt.to_record())==digest(record['receipt']),'GROUNDED_NATIVE_REPLAY_MISMATCH')
            if event_index<len(events) and events[event_index]['pending']['core_head']==receipt.receipt_hash:
                require(events[event_index]['before']==recorded_probability,'NATIVE_CALIBRATION_EVENT_ORDER')
                retained_pending=events[event_index]['pending']
                require(retained_pending['prepared']['binding']==material['binding'] and
                    retained_pending['prepared']['learned']==json.loads(receipt.observed_consequence.result)['decision'],
                    'NATIVE_CALIBRATION_RESTORED_CONSUMED_DECISION')
                replay_probability=deepcopy(events[event_index]['after']);event_index+=1
        require((result.engine.receipts[-1].receipt_hash if result.engine.receipts else None)==state['current_core_head'],'GROUNDED_NATIVE_HEAD')
        require(result.engine.state.identity == state['entity_id'], 'RESTORED_ENTITY_IDENTITY')
        require(event_index==len(events) and replay_probability==probability,'NATIVE_CALIBRATION_UNCONSUMED_EVENT')
        result.current_certificate = deepcopy(state['certificate'])
        result.invalidated = {tuple(x) for x in state['invalidated']}
        result.used_attempts = set(state['used_attempts']); result.dispatched = set(state['dispatched'])
        result.pending = deepcopy(state['pending']); result.renewals = deepcopy(state['renewals'])
        result.semantic_states=deepcopy(packets)
        result.probability_state=deepcopy(probability);result.probability_events=deepcopy(events)
        return result

    def contradict(self, source, epoch):
        self.invalidated.add((source, epoch))
        if self.pending and self.pending['prepared']['binding']['source'] == source and self.pending['prepared']['binding']['epoch'] == epoch:
            self.pending = None
