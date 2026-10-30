"""Owner priority must not silently acquire normative source dependencies."""
from hosted_judge.canonical import validate
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]

def test_primary_owner_and_normative_source_remain_distinct():
    value=validate(json.loads((ROOT/'canonical/public-evidence.json').read_bytes()))
    eq=value['equation'];owner=eq['owner_older_latex'];source=eq['operational_latex']
    assert eq['primary_reference']=='OWNER_OLDER_ACTION_DEPENDENT_COMPOSITION'
    assert r'\Delta V(X_t,a)' in owner and r'\Delta V(X_t,\Theta_t,a)' not in owner
    assert r'a\in A_B}' in owner and r'A_B(X_t,\Theta_t)' not in owner
    assert r'\Delta V(X_t,\Theta_t,a)' in source and r'\mathcal A_B(X_t,\Theta_t)' in source
    assert r'\Bigg]\Bigg),\n' not in owner
    assert 'E_t,M_t,\\Theta_t\\Bigg]' in owner
    assert 'not asserted character-identical' in eq['transcription_status']
