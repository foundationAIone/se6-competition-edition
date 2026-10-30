"""Pure, lossless public history contract for the custom LongMemEval-S pilot.

The trusted evaluator removes labels before this boundary; this validator also
rejects them recursively. It never silently drops messages or source fields.
"""
import hashlib,json

VERSION='se6-source-reported-session-collection-v1'
MAX_HISTORY_BYTES=16*1024*1024
MAX_SESSIONS=512
FORBIDDEN={'answer','answer_session_ids','has_answer','question_type','question_id',
    'eval_function','reference_answer','gold','gold_answer','scoring','evaluator_metadata'}

def require(value,code):
    if not value:raise ValueError(code)

def canonicalbytes(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')

def history_sha256(history):return hashlib.sha256(canonicalbytes(history)).hexdigest()
def session_sha256(session):return hashlib.sha256(canonicalbytes(session)).hexdigest()

def _private_keys(value):
    if type(value) is dict:
        require(not ({str(k).casefold() for k in value}&FORBIDDEN),'SESSION_PRIVATE_LABEL_REJECTED')
        for child in value.values():_private_keys(child)
    elif type(value) is list:
        for child in value:_private_keys(child)

def validate_history(history):
    require(type(history) is dict and {'source_id','sessions'}<=set(history)<=
        {'source_id','sessions','provenance'},'SESSION_HISTORY_SCHEMA')
    _private_keys(history)
    require(type(history['source_id']) is str and 1<=len(history['source_id'])<=256,'SESSION_SOURCE_ID')
    require(type(history['sessions']) is list and 1<=len(history['sessions'])<=MAX_SESSIONS,'SESSION_COUNT_BOUND')
    require(len(canonicalbytes(history))<=MAX_HISTORY_BYTES,'SESSION_HISTORY_BYTE_BOUND')
    if 'provenance' in history:
        require(type(history['provenance']) is dict and len(canonicalbytes(history['provenance']))<=4096,'SESSION_PROVENANCE_BOUND')
    for session in history['sessions']:
        require(type(session) is dict and set(session)=={'session_id','timestamp','turns'},'SESSION_SCHEMA')
        # The external source can repeat a logical ID with a distinct date.
        # Preserve every occurrence; deduplication belongs to returned evidence.
        sid=session['session_id'];require(type(sid) is str and 1<=len(sid)<=256,'SESSION_ID')
        require(type(session['timestamp']) is str and len(session['timestamp'])<=256,'SESSION_TIMESTAMP')
        require(type(session['turns']) is list and 1<=len(session['turns'])<=4096,'SESSION_TURN_BOUND')
        for turn in session['turns']:
            require(type(turn) is dict and set(turn)=={'role','content'},'SESSION_TURN_SCHEMA')
            require(type(turn['role']) is str and 1<=len(turn['role'])<=64 and type(turn['content']) is str,'SESSION_TEXT_TURN_REQUIRED')
    return history

def render_session(session):
    """Same legitimate information for both arms, in exact original order."""
    return ('Session '+session['session_id']+'\nDate: '+session['timestamp']+'\n'+
        '\n'.join(turn['role']+': '+turn['content'] for turn in session['turns']))

def history_spans(history):
    """Exact UTF-8 offsets in the canonical public projection, not raw gold JSON."""
    validate_history(history);raw=canonicalbytes(history)
    prefix=(b'{"provenance":'+canonicalbytes(history['provenance'])+b',"sessions":['
        if 'provenance' in history else b'{"sessions":[')
    require(raw.startswith(prefix),'SESSION_SOURCE_PREFIX');offset=len(prefix);out=[]
    for index,session in enumerate(history['sessions']):
        encoded=canonicalbytes(session);require(raw[offset:offset+len(encoded)]==encoded,'SESSION_SOURCE_OFFSET')
        turn_prefix=b'{"session_id":'+canonicalbytes(session['session_id'])+b',"timestamp":'+canonicalbytes(session['timestamp'])+b',"turns":['
        require(encoded.startswith(turn_prefix),'SESSION_TURN_SOURCE_PREFIX');turn_offset=offset+len(turn_prefix);turns=[]
        for ti,turn in enumerate(session['turns']):
            piece=canonicalbytes(turn);require(raw[turn_offset:turn_offset+len(piece)]==piece,'SESSION_TURN_SOURCE_OFFSET')
            turns.append(dict(turn_index=ti,byte_start=turn_offset,byte_end=turn_offset+len(piece),sha256=hashlib.sha256(piece).hexdigest()))
            turn_offset+=len(piece)+1
        out.append(dict(session_index=index,byte_start=offset,byte_end=offset+len(encoded),sha256=session_sha256(session),turns=turns))
        offset+=len(encoded)+1
    return out
