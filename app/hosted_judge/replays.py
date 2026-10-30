"""Pinned readonly historical responses; cannot dispatch or alter scored evidence."""
import hashlib,json,re
from pathlib import Path
from .canonical import bounded
IDS={'first-linear/0','successor/linear-correction/0','successor/linear-correction/1','successor/mixed-business/0'}

def load_replays(path,pin):
    if path is None and pin is None:return {'schema':'se6-frozen-offline-replays-v8','cases':[]}
    if path is None or not isinstance(pin,str) or re.fullmatch('[0-9a-f]{64}',pin) is None:raise ValueError('Pinned frozen replay projection required')
    with Path(path).open('rb') as f:raw=f.read(512*1024+1)
    if len(raw)>512*1024 or hashlib.sha256(raw).hexdigest()!=pin:raise ValueError('Frozen replay pin/size mismatch')
    value=json.loads(raw);bounded(value)
    if set(value)!={'schema','cases','source_evidence_sha256','scorer_sha256'} or value['schema']!='se6-frozen-offline-replays-v8':raise ValueError('Frozen replay schema required')
    if not isinstance(value['cases'],list) or len(value['cases'])!=4 or {c['id'] for c in value['cases']}!=IDS:raise ValueError('Exact complete historical case set required')
    for key in ('source_evidence_sha256','scorer_sha256'):
        if not isinstance(value[key],str) or re.fullmatch('[0-9a-f]{64}',value[key]) is None:raise ValueError('Replay source anchor required')
    for row in value['cases']:
        if set(row)!={'id','label','question','se6_answer','baseline_answer','scores','evidence','resources','scope'}:raise ValueError('Private/unknown replay field')
        for key in ('id','label','question','se6_answer','baseline_answer','scope'):
            if not isinstance(row[key],str):raise ValueError('Replay text required')
        scores=row['scores'];se6=scores['lanes']['se6']['score'];base=scores['lanes']['baseline']['score']
        expected={'first-linear/0':(None,0,None),'successor/linear-correction/0':(3,3,'TIE'),
            'successor/linear-correction/1':(3,3,'TIE'),'successor/mixed-business/0':(16,3,'se6')}[row['id']]
        if (se6,base,scores['arithmetic_winner'])!=expected:raise ValueError('Historical score changed')
        if row['evidence']['new_provider_calls']!=0 or row['evidence']['current_problem_comparison'] is not False:raise ValueError('Historical replay scope changed')
        if not row['scope'].startswith('FROZEN_OFFLINE_REPLAY'):raise ValueError('Replay must be explicit offline history')
    return value
