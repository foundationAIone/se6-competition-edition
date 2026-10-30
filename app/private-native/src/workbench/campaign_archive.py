"""Read-only startup archive review. Paths and raw approval/requests stay private."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re


def verified_summary(ident,archive,replay):
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}',ident):raise ValueError('Invalid campaign display id')
    archive=Path(archive).resolve()
    if not archive.is_dir():raise ValueError('Explicit campaign archive directory missing')
    manifest=(archive/'archive-manifest.json').read_bytes()
    hashes=json.loads(manifest)
    if not isinstance(hashes,dict) or not hashes:raise ValueError('Empty verified archive manifest')
    for name in hashes:
        path=(archive/name).resolve()
        if Path(name).is_absolute() or not path.is_relative_to(archive):raise ValueError('Archive manifest path escapes allowlisted root')
    # Callback supplied by trusted launcher, never HTTP input. Replay must be
    # offline and complete before any score is exposed.
    score=replay(archive)
    if not isinstance(score,dict):raise ValueError('Campaign replay did not return a record')
    if (archive/'archive-manifest.json').read_bytes()!=manifest or any(
            hashlib.sha256((archive/name).read_bytes()).hexdigest()!=expected for name,expected in hashes.items()):
        raise ValueError('Campaign archive changed during startup verification')
    measurements=deepcopy(score.get('measurements',{}))
    if not measurements and 'measurements.json' in hashes:
        saved=json.loads((archive/'measurements.json').read_bytes())
        measurements={k:deepcopy(saved[k]) for k in ('lanes','tariff','total_tariff_estimate_usd','actual_billed_usd') if k in saved}
        for row in measurements.get('lanes',{}).values():
            if isinstance(row,dict) and isinstance(row.get('provider_usage'),dict):
                row['provider_usage']={k:v for k,v in row['provider_usage'].items() if k in
                    ('prompt_tokens','completion_tokens','total_tokens','completion_tokens_details')}
                details=row['provider_usage'].get('completion_tokens_details')
                if isinstance(details,dict):row['provider_usage']['completion_tokens_details']={
                    k:v for k,v in details.items() if k=='reasoning_tokens'}
    result={'campaign':ident,'status':'FROZEN_ARCHIVE_REPLAY_VERIFIED','verification':'OFFLINE_REPLAY_VERIFIED_AT_START',
            'archive_manifest_sha256':hashlib.sha256(manifest).hexdigest(),
            'artifact_count':len(hashes),'provider_calls_from_http':0,
            'score':deepcopy(score),'measurements':measurements,
            'scope':'Replay checks frozen evidence; no campaign dispatch or provider call from HTTP.'}
    # Freeze a manifest hash/status getter, without exposing filesystem paths.
    def view():
        value=deepcopy(result)
        try:value['archive_unchanged_since_verification']=hashlib.sha256((archive/'archive-manifest.json').read_bytes()).hexdigest()==result['archive_manifest_sha256'] and all(
            hashlib.sha256((archive/name).read_bytes()).hexdigest()==expected for name,expected in hashes.items())
        except OSError:value['archive_unchanged_since_verification']=False
        if not value['archive_unchanged_since_verification']:
            value['score']={};value['measurements']={};value['verification']='CHANGED_SINCE_START_NO_SCORE_DISPLAY'
        return value
    return view
