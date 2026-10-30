"""Narrow public frozen-score projection; never archive replay/provider access."""
import hashlib,json,math,re
from pathlib import Path


def load_review(path,expected):
    if path is None:return {'schema':'se6-public-frozen-score-review-v1','records':[],
        'scope':'No frozen score projection supplied. This hosted session does not run a baseline.'}
    raw=Path(path).read_bytes()
    if len(raw)>32768 or hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('Reviewed score projection pin mismatch')
    value=json.loads(raw)
    if not isinstance(value,dict) or set(value)!={'schema','records'} or value['schema']!='se6-public-frozen-score-review-v1' or not isinstance(value['records'],list) or len(value['records'])>8:
        raise ValueError('Public score projection schema mismatch')
    seen_campaigns=set()
    for record in value['records']:
        if not isinstance(record,dict) or set(record)!={'campaign','scorer_sha256','public_evidence_manifest_sha256','scores','measurements'}:
            raise ValueError('Raw or unknown score fields cannot enter public projection')
        if record['campaign'] not in ('mission-first-linear-v1','mission-successor-v2'):raise ValueError('Unknown frozen campaign')
        if record['campaign'] in seen_campaigns:raise ValueError('Duplicate frozen campaign')
        seen_campaigns.add(record['campaign'])
        for name in ('scorer_sha256','public_evidence_manifest_sha256'):
            if not isinstance(record[name],str) or not re.fullmatch('[0-9a-f]{64}',record[name]):raise ValueError('Frozen score digest required')
        if not isinstance(record['scores'],list) or len(record['scores'])>4:raise ValueError('Bounded frozen cases required')
        seen_cases=set()
        expected_cases={'first-linear'} if record['campaign']=='mission-first-linear-v1' else {'linear-correction/0','linear-correction/1','mixed-business/0'}
        for score in record['scores']:
            if not isinstance(score,dict) or set(score)!={'case','se6','baseline','maximum','winner','correction_retention'}:
                raise ValueError('Only independent score dimensions may be published')
            if not isinstance(score['case'],str) or score['case'] not in ('first-linear','linear-correction/0','linear-correction/1','mixed-business/0'):
                raise ValueError('Unknown score case')
            if score['case'] not in expected_cases or score['case'] in seen_cases:raise ValueError('Campaign/case projection mismatch')
            seen_cases.add(score['case'])
            if type(score['maximum']) is not int or score['maximum'] not in (3,16):raise ValueError('Unexpected score maximum')
            if score['maximum']!=(16 if score['case']=='mixed-business/0' else 3):raise ValueError('Case score maximum mismatch')
            if any(v is not None and (type(v) is not int or not 0<=v<=score['maximum']) for v in (score['se6'],score['baseline'])):
                raise ValueError('Invalid frozen scores')
            if score['winner'] not in (None,'TIE','se6','baseline'):raise ValueError('Invalid scoped winner')
            expected_winner=None if score['se6'] is None or score['baseline'] is None else 'TIE' if score['se6']==score['baseline'] else 'se6' if score['se6']>score['baseline'] else 'baseline'
            if score['winner']!=expected_winner:raise ValueError('Winner contradicts score dimensions')
            if score['correction_retention'] is not None and score['correction_retention']!={'se6':True,'baseline':True}:
                raise ValueError('Unreviewed correction field')
            if (score['case']=='linear-correction/1')!=(score['correction_retention'] is not None):raise ValueError('Correction retention case mismatch')
        if seen_cases!=expected_cases:raise ValueError('Complete frozen campaign projection required')
        metrics=record['measurements']
        if not isinstance(metrics,dict) or set(metrics)!={'captured_requests','tariff_estimate_usd','actual_billed_usd'}:
            raise ValueError('Only bounded aggregate public measurements are allowed')
        if type(metrics['captured_requests']) is not int or metrics['captured_requests'] not in (2,6):raise ValueError('Unexpected capture count')
        if metrics['captured_requests']!=(2 if record['campaign']=='mission-first-linear-v1' else 6):raise ValueError('Campaign capture count mismatch')
        if metrics['actual_billed_usd'] is not None:raise ValueError('Invoice not verified for these frozen campaigns')
        estimate=metrics['tariff_estimate_usd']
        if type(estimate) not in (float,int) or not math.isfinite(estimate) or not 0<=estimate<=0.5:raise ValueError('Invalid tariff estimate')
    value['scope']='Sanitized projection of previously frozen independent scoring, not live inference or a baseline for your current question. Raw archives, private rubrics and authorization text are not served.'
    value['projection_sha256']=hashlib.sha256(raw).hexdigest()
    return value
