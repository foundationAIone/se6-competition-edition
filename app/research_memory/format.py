"""Explicit text-only development admission; no image or metadata flattening."""
import hashlib,json,re

VERSION='se6-historical-text-development-v1'
def require(value,code):
    if not value:raise ValueError(code)
def encode(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')
def digest(value):return hashlib.sha256(encode(value)).hexdigest()
def tokens(text):return set(re.findall(r'[^\W_]+',text.casefold(),flags=re.UNICODE))

def trajectory_chunks(trajectory,*,chunk_chars=1600):
    require(type(chunk_chars) is int and 1<=chunk_chars<=1600,'HISTORY_CHUNK_BOUND')
    required={'id','goal','start_url','outcome','states'};optional={'domain','environment'}
    require(type(trajectory) is dict and required<=set(trajectory)<=required|optional,'UNSUPPORTED_TRAJECTORY_SCHEMA')
    require(all(type(trajectory[k]) is str for k in optional if k in trajectory),'HISTORY_OPTIONAL_HEADER_SCHEMA')
    require(all(type(trajectory[k]) is str and trajectory[k].strip() for k in ('id','goal','start_url'))
        and (trajectory['outcome'] is None or type(trajectory['outcome']) is str),'HISTORY_HEADER_SCHEMA')
    require(type(trajectory['states']) is list and 1<=len(trajectory['states'])<=512,'HISTORY_STATE_BOUND')
    require(len(encode(trajectory))<=512*1024,'HISTORY_INPUT_BYTE_BOUND')
    segments=[dict(historical_source_id=trajectory['id'],historical_goal=trajectory['goal'],historical_start_url=trajectory['start_url'],
        reported_outcome=trajectory['outcome'],epistemic_scope='REPORTED_HISTORICAL_SOURCE_NOT_WORLD_VERIFICATION')]
    for key in optional:
        if key in trajectory:segments[0]['historical_'+key]=trajectory[key]
    allowed={'url','action','text','accessibility_tree','thought','thoughts','step','state_index','screenshot'}
    for index,state in enumerate(trajectory['states']):
        require(type(state) is dict and set(state)<=allowed and 'url' in state,'UNSUPPORTED_HISTORY_STATE_SCHEMA')
        require(state.get('screenshot') in (None,''),'UNSUPPORTED_MODALITY_IMAGE_HISTORY')
        require(('text' in state) != ('accessibility_tree' in state),'HISTORY_EXACT_TEXT_SOURCE_REQUIRED')
        require(type(state.get('text',state.get('accessibility_tree'))) is str,'HISTORY_EXACT_TEXT_SOURCE_REQUIRED')
        for key,value in state.items():
            if key in ('step','state_index'):require(type(value) is int and value>=0,'HISTORY_STEP_SCHEMA')
            else:require(value is None or type(value) is str,'HISTORY_TEXT_FIELD_SCHEMA')
        require(type(state['url']) is str and state['url'].strip(),'HISTORY_URL_SCHEMA')
        # Preserve every admitted text field, including explicit null screenshot.
        # No URL is fetched and a reported action/outcome is never re-executed.
        segments.append(dict(historical_state_index=index,reported_state=state))
    source=digest(trajectory);chunks=[]
    for index,segment in enumerate(segments):
        text=encode(segment).decode('utf-8')
        for part,start in enumerate(range(0,len(text),chunk_chars)):
            content=text[start:start+chunk_chars];pin=digest(content)
            chunks.append(dict(text=content,segment_index=index,part_index=part,chunk_sha256=pin,
                source_ref=f'history:{source}:segment:{index}:part:{part}:sha256:{pin}'))
    require(len(chunks)<=384,'HISTORY_MEMORY_RECORD_BOUND')
    return dict(version=VERSION,trajectory_sha256=source,chunks=chunks)
