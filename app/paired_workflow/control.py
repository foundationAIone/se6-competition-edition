"""Ordinary verified notes, no SE6 mechanism and no automatic task solver."""
from copy import deepcopy
from pathlib import Path
import json
from .protocol import digest,encode,require
from .tasks import exclusive

class ConventionalNotes:
    def __init__(self,directory,project_id):
        self.root=Path(directory).resolve(strict=False);self.project_id=project_id

    def load(self,*,stage):
        if stage==1:return dict(status='NO_PRIOR_NOTES',verified_observations=[])
        path=self.root/'verified-notes-stage1.json'
        if not path.exists():return dict(status='NO_VERIFIED_PREDECESSOR',verified_observations=[])
        record=json.loads(path.read_bytes())
        require(record['record_sha256']==digest({k:v for k,v in record.items() if k!='record_sha256'})
            and record['project_id']==self.project_id and record['stage']==1
            and record['independent_verdict']['goal'] is True,'PILOT_CONVENTIONAL_NOTE_LINEAGE')
        return dict(status='COLD_ORDINARY_VERIFIED_NOTES',verified_observations=[deepcopy(record)])

    def retain(self,*,stage,public_observation,proposal,independent_verdict):
        if independent_verdict['goal'] is not True:
            return dict(status='NOT_RETAINED_UNVERIFIED_OUTCOME',cold_continuation=False)
        record=dict(project_id=self.project_id,stage=stage,public_observation=deepcopy(public_observation),
            proposal=deepcopy(proposal),independent_verdict=deepcopy(independent_verdict),
            scope='OWN_VERIFIED_PUBLIC_OBSERVATIONS_NOT_EVALUATOR_ANSWERS')
        record['record_sha256']=digest(record)
        exclusive(self.root/f'verified-notes-stage{stage}.json',record)
        return dict(status='ORDINARY_VERIFIED_NOTES_RETAINED',record_sha256=record['record_sha256'],
            cold_continuation=stage==2,source='THIS_ARM_ONLY')


def native_model_notes(notes_directory,project_id,*,stage):
    """Normal model notes from its OWN prior committed result, not a new store.

    Actual SE6 relationship retention remains in its existing Native/Entity
    journals. This supplies the same model an ordinary verified work record.
    """
    if stage==1:return dict(status='NO_PRIOR_NOTES',verified_observations=[])
    path=Path(notes_directory).parent/'stage1'/'result.json'
    if not path.is_file():return dict(status='NO_VERIFIED_PREDECESSOR',verified_observations=[])
    record=json.loads(path.read_bytes())
    require(record['project_id']==project_id and record['arm']=='se6' and record['stage']==1,
            'PILOT_NATIVE_MODEL_NOTE_SCOPE')
    verdict=record.get('independent_verdict') or {}
    if verdict.get('goal') is not True:return dict(status='NO_VERIFIED_PREDECESSOR',verified_observations=[])
    return dict(status='COLD_OWN_VERIFIED_MODEL_NOTES',verified_observations=[dict(
        model_proposals=record['model_proposals'],tool_events=record['tool_events'],
        independent_verdict=verdict,scope='OWN_PRIOR_PUBLIC_TOOL_OBSERVATIONS_ONLY')])
