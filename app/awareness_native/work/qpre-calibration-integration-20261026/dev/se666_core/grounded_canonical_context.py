"""Existing Native state correspondence and pre-effect retention admission.

No Entity/seed constructor, persistence service, authority or effects.  The
Native initializer/recorded restore owns its schema.  A missing generative
reference is explicit; initial_state is never relabelled as that reference.
"""
from copy import deepcopy
import base64
import hashlib
import json
import zlib

from .observation_grounding import digest, require
from . import candidate_state_transition as state_ops

VERSION = 'grounded-canonical-correspondence-v1'
LIMIT_VERSION = 'grounded-retention-reservation-v1'
CODEC = 'grounded-retention-field-flush-v1'
ENCODER_VERSION = 'grounded-retention-component-coalesced-v3'
REPRESENTATION_VERSION = 'se6-representation-construction-v1'
REPRESENTATION_DEFINITION = dict(version=REPRESENTATION_VERSION,emblem='([{01*}])',
    carrier='typed-tree-v1',terminal_encoding='utf8',composition='typed-construction',
    boundary_symbols=['(',')','[',']','{','}'],repetition='finite-composition',
    runtime_nodes=32768,runtime_depth=32)


def native_context(canonical, base, engine, *, representation_seed=None):
    """Consume the complete actual saved Native schema, including math fields.

    restore is recorded replay.  The current extension receipts are separately
    replayed by GroundedNativeConsumer.restore, never by a new initializer.
    """
    restored = canonical.core.SE.restore(base['core_journal'], expected_head=base['core_head'])
    original = json.loads(restored.dumps())
    current = json.loads(engine.dumps())
    compatible_schema = original['schema'] == current['schema'] or (
        original['schema'] == 'se-core-math-v1' and current['schema'] == 'se-core-math-relational-v1')
    require(state_ops.exact(original['initial_state'], current['initial_state'])
            and compatible_schema, 'NATIVE_INITIAL_SCHEMA_BINDING')
    require(original['state']['identity'] == current['state']['identity'], 'NATIVE_CONTEXT_IDENTITY')
    receipts=original['receipts']
    require(base['core_head'] == (receipts[-1]['receipt_hash'] if receipts else None), 'NATIVE_BASE_HEAD')
    require(len(current['receipts']) >= len(receipts)
            and state_ops.exact(current['receipts'][:len(receipts)],receipts), 'NATIVE_BASE_RECEIPT_PREFIX')
    require(canonical.core._hash(current['state']) == engine.state.state_hash,'NATIVE_CURRENT_SERIALIZATION')
    canonical.core._validate_state(engine.state)
    if 'native_identity' in base:
        require(base['native_identity'] == engine.state.identity
                and base['native_actions_used'] == restored.state.actions_used,
                'NATIVE_BASE_METADATA')
    result = dict(schema=VERSION, kernel_schema=current['schema'],
                initial_state=original['initial_state'], current_state=current['state'],
                base_journal_sha256=digest(original), base_head=base['core_head'],
                initial_state_sha256=canonical.core._hash(original['initial_state']),
                current_state_sha256=engine.state.state_hash,
                native_limit=base.get('native_limit'),
                generative_reference_status='NOT_BOUND_BY_NATIVE_SCHEMA')
    if representation_seed is not None:
        require(representation_seed==REPRESENTATION_VERSION,'REPRESENTATION_VERSION')
        # Reuse the adopted constructors, not a new bracket parser. Actual
        # Native payload is decoded BEFORE its values reach C/FoL/selection.
        result['representation_seed']=dict(definition=deepcopy(REPRESENTATION_DEFINITION),
            term=state_ops.tree(dict(kernel_schema=result['kernel_schema'],
                initial_state=result['initial_state'],current_state=result['current_state'])))
        decoded=require_generative_reference(result)
        decoded['current_state'],result['representation_flower']=_represented_current(canonical,decoded,result)
        result.update(decoded)
        result['generative_reference_status']='REPRESENTATION_CONSTRUCTION_BOUND'
    return result


def _represented_current(canonical, decoded, context):
    """Resolve actual Native fields through existing typed Flower constructors.

    This is a registered structural interpretation, not a hypothesis search.
    Source values remain in the lossless carrier; mapped field paths resolve
    those values. No assertion about external World truth is created.
    """
    m=canonical.mapper
    source=canonical.frames.create_source_observation(source_reference='native:'+context['current_state_sha256'],
        summary='Typed Native journal interpretation under '+REPRESENTATION_VERSION,
        epistemic_status=canonical.E.REPORTED,evidence_references=('journal:'+context['base_journal_sha256'],))
    node=lambda label,path:m.create_mapper_node(kind=m.NodeKind.THING,label=label,
        description=json.dumps(dict(path=path),sort_keys=True),epistemic_status=canonical.E.REPORTED,
        source_observations=(source,))
    root=node('represented-native',[])
    parts=[node(name,[name]) for name in sorted(decoded)]
    fields=[node('current:'+name,['current_state',name]) for name in sorted(decoded['current_state'])]
    first=m.create_flower_center(root,terminals=parts)
    current=next(n for n in parts if json.loads(n.description)['path']==['current_state'])
    second=m.recenter_flower(first,current,terminals=fields)
    by_ref={n.node_id:n for n in fields}
    interpreted={}
    for ref in second.terminals:
        path=json.loads(by_ref[ref.node_id].description)['path']
        require(len(path)==2 and path[0]=='current_state','REPRESENTATION_FIELD_PATH')
        interpreted[path[1]]=deepcopy(state_ops.at(decoded,path))
    require(state_ops.exact(interpreted,decoded['current_state']),'REPRESENTATION_FLOWER_COVERAGE')
    relations=[m.create_mapper_relation(kind=m.RelationKind.CONTAINS,label='native-components',
        source_nodes=(root,),target_nodes=parts,epistemic_status=canonical.E.REPORTED,source_observations=(source,)),
        m.create_mapper_relation(kind=m.RelationKind.CONTAINS,label='current-native-fields',
        source_nodes=(current,),target_nodes=fields,epistemic_status=canonical.E.REPORTED,source_observations=(source,))]
    graph=m.create_universal_map(vertices=[root,*parts,*fields],relations=relations,flower_lineage=[first,second])
    return interpreted,graph.model_dump(mode='json')


def effective_native_limit(context, requested):
    require(type(requested) is int and requested >= 0, 'NATIVE_REQUESTED_LIMIT')
    saved = context['native_limit']
    require(saved is None or (type(saved) is int and saved >= 0), 'NATIVE_SAVED_LIMIT')
    return requested if saved is None else min(saved, requested)


def center_view(context):
    """Bounded mapper view; full payload travels on the typed Native port."""
    result = dict(schema=context['schema'],kernel_schema=context['kernel_schema'],
                initial_state_sha256=context['initial_state_sha256'],
                current_state_sha256=context['current_state_sha256'],
                actions_used=context['current_state']['actions_used'])
    if 'representation_seed' in context:
        # The digest binds the small view; the decoded payload, not this hash,
        # supplies the actual Native counters/content consumed by selection.
        require_generative_reference(context)
        result['representation_version']=REPRESENTATION_VERSION
        result['representation_sha256']=digest(context['representation_seed'])
        result['representation_flower_hash']=context['representation_flower']['map_hash']
    return result


def require_generative_reference(context):
    """No invention, cross-Entity seed substitution, or opaque success flag."""
    require(type(context) is dict and 'representation_seed' in context,
            'CANONICAL_GENERATIVE_REFERENCE_NOT_DEFINED_FOR_NATIVE_SCHEMA')
    seed=context['representation_seed']
    require(type(seed) is dict and set(seed)=={'definition','term'} and
            state_ops.exact(seed['definition'],REPRESENTATION_DEFINITION),'REPRESENTATION_DEFINITION_BINDING')
    decoded=state_ops.un_tree(seed['term'])
    require(state_ops.exact(decoded,dict(kernel_schema=context['kernel_schema'],
            initial_state=context['initial_state'],current_state=context['current_state'])),
            'REPRESENTATION_NATIVE_PAYLOAD_BINDING')
    return decoded


def limits(value):
    require(type(value) is dict and set(value) == {'version','witness_nodes','witness_depth','witness_bytes'}
            and value['version'] == LIMIT_VERSION, 'RETENTION_LIMIT_SCHEMA')
    require(type(value['witness_nodes']) is int and 1 <= value['witness_nodes'] <= 4096
            and type(value['witness_depth']) is int and 1 <= value['witness_depth'] <= 16,
            'RETENTION_LIMIT_RANGE')
    require(type(value['witness_bytes']) is int and 1 <= value['witness_bytes'] <= 65536,
            'RETENTION_WITNESS_BYTE_LIMIT')
    return value


class _Envelope:
    def __init__(self, nodes, depth, byte_bound):
        self.nodes, self.depth, self.byte_bound = nodes, depth, byte_bound


def _json_bytes(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf8')


def _byte_bound(value, *, typed=False):
    """Exact known JSON sizes; conservative unknown typed-tree envelope sizes.

    At most64 extra ASCII bytes per source node cover every supported tag,
    pair/container punctuation and binary64 hex versus decimal representation.
    String escaping is identical to the original source JSON byte contract.
    """
    if isinstance(value,_Envelope):
        return value.byte_bound + (64*value.nodes if typed else 0)
    if typed:
        if type(value) is dict:
            pairs=[3+_byte_bound(k,typed=True)+_byte_bound(v,typed=True) for k,v in value.items()]
            return len(b'["dict",[]]') + sum(pairs) + max(0,len(pairs)-1)
        if type(value) in (list,tuple):
            return len(b'["list",[]]' if type(value) is list else b'["tuple",[]]') + sum(
                _byte_bound(x,typed=True) for x in value) + max(0,len(value)-1)
        return len(_json_bytes(state_ops.tree(value)))
    if type(value) is dict:
        return 2+sum(len(_json_bytes(k))+1+_byte_bound(v) for k,v in value.items())+max(0,len(value)-1)
    if type(value) in (list,tuple):
        return 2+sum(_byte_bound(v) for v in value)+max(0,len(value)-1)
    return len(_json_bytes(value))


class _Bytes:
    def __init__(self,size):
        require(type(size) is int and size >= 0, 'RETENTION_UNKNOWN_BYTE_BOUND')
        self.size=size


class _IsolatedBytes:
    """Actual bytes corresponding to one prospectively unknown component.

    Same FULL_FLUSH boundary as the prospective _Bytes marker. Byte-for-byte
    retained-state content remains unchanged; no new logical codec is added.
    """
    def __init__(self,data):
        require(type(data) is bytes,'RETENTION_SEGMENT_BYTES')
        self.data=data


class _ProjectedPacket:
    """Size-only next-state carrier; never a retained or replayable state.

    The original actual packet always uses pack(z, context) without modification.
    Only the prospective witness-dependent subtrees are represented by bounds.
    """
    def __init__(self, context, view, state):
        self.context, self.view, self.state=context,view,state


def _packet_chunks(packet):
    """Canonical packet JSON with predictable FULL_FLUSH component boundaries.

    Previously recorded M/E entries remain *exact* known components. X, Theta,
    U, new M/E entries, view and context have independent boundaries so that
    compression of an unknown future witness cannot change later known bytes.
    There is still a single ordinary zlib stream and exact original JSON/hash.
    """
    symbolic=isinstance(packet,_ProjectedPacket)
    yield b'{"complement":'
    yield b'["dict",['
    if symbolic:
        values=packet.state
        require(type(values) is dict, 'RETENTION_SYMBOLIC_STATE')
        pairs=[(key,values[key]) for key in sorted(values)]
    else:
        require(type(packet) is dict and set(packet)=={'context','view','complement'},
                'RETENTION_PACKET_SCHEMA')
        tree=packet['complement']
        require(type(tree) is list and len(tree)==2 and tree[0]=='dict' and type(tree[1]) is list,
                'RETENTION_COMPLEMENT_TYPED_TREE')
        pairs=[]
        for pair in tree[1]:
            require(type(pair) is list and len(pair)==2 and type(pair[0]) is list
                    and pair[0][0]=='str', 'RETENTION_COMPLEMENT_FIELD')
            pairs.append((pair[0][1],pair[1]))
        require([k for k,v in pairs]==sorted(k for k,v in pairs),
                'RETENTION_COMPLEMENT_CANONICAL_ORDER')
    for index,(key,value) in enumerate(pairs):
        if index: yield b','
        yield b'['+_json_bytes(state_ops.tree(key))+b','
        if key in ('M','E'):
            if symbolic:
                require(type(value) is list, 'RETENTION_SYMBOLIC_MEMORY')
                children=value
            else:
                require(type(value) is list and len(value)==2 and value[0]=='list',
                        'RETENTION_TYPED_MEMORY')
                children=value[1]
            yield b'["list",['
            for item_index,item in enumerate(children):
                if item_index: yield b','
                if item_index==len(children)-1:
                    if symbolic:
                        yield _Bytes(_byte_bound(item,typed=True))
                    else:
                        yield _IsolatedBytes(_json_bytes(item))
                else:
                    yield _json_bytes(state_ops.tree(item)) if symbolic else _json_bytes(item)
            yield b']]'
        elif key in ('X','Theta','U','predecessor'):
            # Actual/prospective streams agree on their flush boundaries.
            if symbolic:
                yield _Bytes(_byte_bound(value,typed=True))
            else:
                yield _IsolatedBytes(_json_bytes(value))
        else:
            yield _json_bytes(state_ops.tree(value)) if symbolic else _json_bytes(value)
        yield b']'
    yield b']]'
    yield b',"context":'
    if symbolic:
        # Only predecessor/frame/governing are new hashes, all fixed 64 ASCII;
        # every other field is source-bound and unchanged by the World witness.
        yield _Bytes(len(_json_bytes(packet.context)))
        yield b',"view":'
        yield _Bytes(_byte_bound(packet.view,typed=True))
    else:
        yield _IsolatedBytes(_json_bytes(packet['context']))
        yield b',"view":'
        yield _IsolatedBytes(_json_bytes(packet['view']))
    yield b'}'


def _raw_chunks(state):
    """Canonical JSON pieces with fixed boundaries for uncertain fields.

    Ordinary bytes are known. _IsolatedBytes appear at matching fields where
    a prospective reservation would have an unknown-size _Bytes marker.
    """
    codec=state.get('retention_codec')
    require(codec == CODEC, 'RETENTION_CODEC_BINDING')
    yield b'{'
    for index,key in enumerate(sorted(state)):
        if index: yield b','
        yield _json_bytes(key)+b':'
        value=state[key]
        if type(value) is list:
            yield b'['
            for i,item in enumerate(value):
                if i: yield b','
                if key=='semantic_states' and i==len(value)-1:
                    yield from _packet_chunks(item)
                elif key=='renewals' and i==len(value)-1:
                    yield item if isinstance(item,_Bytes) else _IsolatedBytes(_json_bytes(item))
                else:
                    yield item if isinstance(item,_Bytes) else _json_bytes(item)
            yield b']'
        else:
            yield value if isinstance(value,_Bytes) else _json_bytes(value)
    yield b'}'


def _chunks(state):
    """Losslessly coalesce adjacent known JSON between uncertain fields.

    V2 flushed after tiny punctuation chunks, multiplying flush overhead and
    preventing compression across repeated *known* history. V3 coalesces only
    known fragments while keeping every unknown field isolated under the same
    reservation boundary. The logical state, reader and state hash are unchanged.
    """
    adjacent=[]
    for chunk in _raw_chunks(state):
        if isinstance(chunk,(_Bytes,_IsolatedBytes)):
            if adjacent:
                yield b''.join(adjacent)
                adjacent=[]
            yield chunk.data if isinstance(chunk,_IsolatedBytes) else chunk
        else:
            require(type(chunk) is bytes,'RETENTION_UNKNOWN_STREAM_CHUNK')
            adjacent.append(chunk)
    if adjacent:
        yield b''.join(adjacent)


def retained_envelope(state):
    """Same existing envelope/schema/reader and byte caps, explicit new encoder."""
    require(state.get('retention_codec')==CODEC,'RETENTION_CODEC_BINDING')
    compressor=zlib.compressobj(9)
    compressed=[];hash_value=hashlib.sha256();size=0
    for chunk in _chunks(state):
        size+=len(chunk);require(size<=8*1024*1024,'RETAINED_STATE_BYTE_BOUND')
        hash_value.update(chunk)
        compressed.extend((compressor.compress(chunk),compressor.flush(zlib.Z_FULL_FLUSH)))
    compressed.append(compressor.flush(zlib.Z_FINISH))
    result=dict(schema='se6-grounding-retained-state-zlib-v1',state_sha256=hash_value.hexdigest(),
                state_bytes=size,payload_b64=base64.b64encode(b''.join(compressed)).decode('ascii'))
    require(len(_json_bytes(result))<=1024*1024,'RETAINED_ENVELOPE_BYTE_BOUND')
    return result


def _measure(value):
    """Same source-tree node/depth convention as the adopted tree encoder.

    Dict key leaves count too. Envelope depths are from their own root (zero
    for a scalar). Independent occurrences count independently, as in tree().
    """
    if isinstance(value, _Envelope):
        return value.nodes, value.depth
    if type(value) is dict:
        children = [item for pair in value.items() for item in pair]
    elif type(value) in (tuple,list):
        children = value
    else:
        return 1, 0
    sizes = [_measure(x) for x in children]
    return 1 + sum(n for n,d in sizes), max((d+1 for n,d in sizes), default=0)


def reserve(z, pending, contract, proposal, retained_state):
    """Upper bound the *whole next state* before an irreversible dispatch.

    The future witness, its contained row and raw value are EACH conservatively
    bounded by the entire source-bound witness envelope. This over-reserves;
    it never relies on guessing the future observation. All original M/E stay.
    """
    state_ops.validate_state(z); limits(contract)
    max_rows=proposal['limits']['max_rows']
    require(type(max_rows) is int and len(z['M'][-1]['history']) < max_rows,
            'PRE_EFFECT_HISTORY_CAPACITY')
    envelope = _Envelope(contract['witness_nodes'], contract['witness_depth'],contract['witness_bytes'])
    bound = deepcopy(z)
    bound['version'] += 1
    bound['predecessor'] = '0'*64
    b = pending['prepared']['binding']
    row = dict(kind='VERIFIED_OBSERVATION_TRANSITION', predecessor='0'*64,
               evidence=envelope, before_head=b['memory_head'], action=pending['action'],
               history=deepcopy(z['M'][-1]['history'])+[envelope],
               native_state='0'*64, native_receipt_hash='0'*64, prediction_passed=False,
               suspended_ids=[g['id'] for g in z['Theta']['governing']])
    bound['M'].append(row)
    bound['E'].append(envelope)
    bound['X'].update(native_state='0'*64, observation=envelope, goal=False, memory_ref='0'*64)
    bound['Theta'].update(x_binding='0'*64, previous_theta='0'*64, transition='0'*64)
    inputs=pending['prepared'].get('learned',{}).get('selection',{}).get('decision_inputs')
    if inputs is not None:
        frame,unknown=state_ops.renewed_inputs(z,bound['M'][-1],inputs)
        bound['Theta']['frame']=state_ops._frame_successor(frame,'0'*64,'0'*64,'VERIFIED_OBSERVATION_TRANSITION')
        bound['U']=deepcopy(unknown)
    for g in bound['Theta']['governing']:
        # Every domain predicate may fail.  Six additional causes cover both
        # unknown declarations, freshness, old prediction, contradiction,
        # prior suspension.  This dominates both successor outcome branches.
        # APPLICABLE is the longer status; this is an abstract size carrier,
        # not a claimed governing decision. Reserve the longest actual cause.
        g.update(status='APPLICABLE', reasons=['PRIOR_SUSPENSION_REVALIDATION_REQUIRED']*(len(g['definition']['domain'])+6),
                 successor_binding=dict(x='0'*64, transition='0'*64, support=g['support']))
    nodes, depth = _measure(bound)
    require(nodes <= 32768 and depth <= 32, 'PRE_EFFECT_RETENTION_CAPACITY')
    context=state_ops.state_context(z)
    context.update(predecessor='0'*64,governing='0'*64)
    view=dict(X=bound['X'],frame=bound['Theta']['frame'],active=[g['id'] for g in bound['Theta']['governing']])
    renewal=dict(status='VERIFIED_PREDICTION',witness_sha256='0'*64,source=b['source'],epoch=b['epoch'],
        attempt_id=pending['attempt_id'],before_head=b['memory_head'],goal=False,passed=False,
        history_after=row['history'],remaining_path=pending['prepared']['learned']['actions'][1:],
        belief_after=[proposal['limits']['max_states']]*len(proposal['models']),semantic_successor_sha256='0'*64)
    require(retained_state.get('retention_codec')==CODEC,'PRE_EFFECT_CODEC_REQUIRED')
    future=deepcopy(retained_state)
    future['pending']=None
    future['dispatched']=sorted(set(future['dispatched'])|{pending['attempt_id']})
    # A correct predicted consequence retains the source epoch; a contradiction
    # invalidates it. The World has not decided which branch is actual yet.
    # Measure BOTH futures: compression is not monotone in known input bytes.
    scope=[b['source'],b['epoch']]
    future['renewals'].append(_Bytes(_byte_bound(renewal)))
    future['semantic_states'].append(_ProjectedPacket(context,view,bound))
    def size_for_branch(candidate):
        chunks=list(_chunks(candidate))
        raw=sum(c.size if isinstance(c,_Bytes) else len(c) for c in chunks)
        # Each FULL_FLUSH resets the compression dictionary. Known chunks have
        # their exact isolated bytes; for unknown fields use zlib compressBound,
        # plus the flush/header/trailer allowance. Future witness bytes never
        # enter a known chunk, by construction of matching segment boundaries.
        compressed=16
        for chunk in chunks:
            if isinstance(chunk,_Bytes):
                n=chunk.size
                compressed+=n+(n>>12)+(n>>14)+(n>>25)+13+16
            else:
                compressed+=len(zlib.compress(chunk,9))+16
        payload=4*((compressed+2)//3)
        encoded=len(_json_bytes(dict(schema='se6-grounding-retained-state-zlib-v1',
            state_sha256='0'*64,state_bytes=raw,payload_b64='')))+payload
        return raw,encoded
    upper=[size_for_branch(future)]
    if scope not in future['invalidated']:
        contradicted=deepcopy(future)
        contradicted['invalidated'].append(scope)
        upper.append(size_for_branch(contradicted))
    raw_bytes=max(n for n,_ in upper)
    envelope_bytes=max(n for _,n in upper)
    require(raw_bytes <= 8*1024*1024,'PRE_EFFECT_RETAINED_BYTE_CAPACITY')
    require(envelope_bytes <= 1024*1024,'PRE_EFFECT_ENVELOPE_BYTE_CAPACITY')
    return dict(version=LIMIT_VERSION, predecessor_sha256=state_ops.seal(z),
                action_sha256=digest(pending['action']), contract=deepcopy(contract),
                upper_nodes=nodes, upper_depth=depth, max_rows=max_rows,
                retained_before_sha256=digest(retained_state), upper_retained_bytes=raw_bytes,
                upper_envelope_bytes=envelope_bytes)


def verify_envelope(witness, reservation):
    """Called after independent authenticity verification, before assimilation.

    An out-of-contract supplier failure retains the pending effect and evidence;
    it never truncates the observation or permits an automatic retry.
    """
    contract=limits(reservation['contract'])
    state_ops.tree(witness)
    nodes,depth=_measure(witness)
    require(nodes <= contract['witness_nodes'] and depth <= contract['witness_depth'],
            'INDEPENDENT_WITNESS_EXCEEDS_ADMITTED_ENVELOPE')
    require(len(_json_bytes(witness)) <= contract['witness_bytes'],'INDEPENDENT_WITNESS_BYTE_ENVELOPE')
    require(type(witness['observation_row']) is dict, 'WITNESS_ROW_REQUIRED')
    return nodes,depth


def validate_reservation(z,pending,reservation,proposal,retained_state):
    require(state_ops.exact(reservation, reserve(z,pending,reservation['contract'],proposal,retained_state)),
            'RETENTION_RESERVATION_BINDING')
