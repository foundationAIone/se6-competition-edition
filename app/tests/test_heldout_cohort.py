"""Fixed distinct cohort and answer-key firewall, independent of outcomes."""
import json,hashlib,sys
from collections import Counter
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from hosted_judge import benchmark_campaign,benchmark_controls

def test_thirty_unique_frozen_sequences_six_categories_fortythree_phases():
    raw=(ROOT/'heldout/public-tasks.json').read_bytes()
    assert hashlib.sha256(raw).hexdigest()=='b727439ab17de60650a5cabd19b729bf95753e40a689bf07e7de14ed1f09dd33'
    tasks=json.loads(raw)['tasks'];assert len(tasks)==30
    assert Counter(t['category'] for t in tasks)=={'businessoptimization':6,'correction_deps':6,'fieldnav_relations':6,'retained_transfer':6,'act_observe':6}
    assert len({tuple((p['public_question'],p['authorized']) for p in t['phases']) for t in tasks})==30
    assert sum(len(t['phases']) for t in tasks)==43
    assert all(len(t['phases'])<=4 and t['max_actions']<=20 for t in tasks)
    for task in tasks:benchmark_controls.valid(task,'C')

def test_original_archive_byte_preservation_and_runtime_key_exclusion():
    archive=ROOT/'tests/fixtures/heldout-archive-v1'
    assert hashlib.sha256((archive/'public-tasks.json').read_bytes()).hexdigest()=='b294bbc42a7d8ac6fa4bc76b92998f6a387ba45210e6aa10f3e44e5aa5417762'
    assert hashlib.sha256((archive/'oracles-offline-only.json').read_bytes()).hexdigest()=='ea72d7245a0773358347aa722d57bf79dc397d9e6fc995ea4b4b515be1662f7a'
    for dockerfile in ('Dockerfile','Dockerfile.native'):
        copied=[line.split()[1:-1] for line in (ROOT/dockerfile).read_text().splitlines() if line.startswith('COPY ')]
        assert not any(s in ('.','tests','tests/') for sources in copied for s in sources)
    assert not any('oracle' in p.name.lower() or 'key_private' in p.name.lower() for p in (ROOT/'heldout').rglob('*'))

def test_no_oracle_fields_in_public_controller_or_provider_packet_inputs():
    task={'id':'development','category':'development','phases':[{'id':'p1','public_question':'Insufficient facts.'}],'expected_answer':'PRIVATE_ORACLE_SENTINEL'}
    with pytest.raises(ValueError):benchmark_controls.valid(task,'C')
    # The public task blueprint has no key/rubric parameter, and tool context
    # projects actual public outputs only, excluding producer-private fields.
    context=benchmark_campaign.compact_context({'status':'UNRESOLVED','response':'Actual public partial output',
        'public':{},'answer_key':'PRIVATE_ORACLE_SENTINEL','private_path':'PRIVATE_PATH_SENTINEL'})
    text=json.dumps(context);assert 'PRIVATE_ORACLE_SENTINEL' not in text and 'PRIVATE_PATH_SENTINEL' not in text
