"""Admission/privacy and genuine prepared-pair fairness regressions; no model calls."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import pytest
from hosted_judge.canonical import load_canonical, validate

ROOT=Path(__file__).resolve().parents[1]

def public():return json.loads((ROOT/'canonical/public-evidence.json').read_bytes())

def test_actual_projection_source_and_real_counts_admitted():
    path=ROOT/'canonical/public-evidence.json'
    value=load_canonical(path,hashlib.sha256(path.read_bytes()).hexdigest())
    assert value['equation']['source_document_sha256']=='c777248a57902008ac943aa5dde941005a5709f66bc13f7a63a785fb68c649be'
    assert sum(len(c['rounds']) for c in value['cases'])==24
    assert value['conditions']['new_provider_calls']==0
    corrected=value['cases'][0]['rounds'][4]
    assert corrected['checks']['old_dependency_invalidated'] and corrected['checks']['independent_knowledge_preserved']
    assert corrected['outputs']['canonical']['returned_center_changed']

@pytest.mark.parametrize('mutation',[
    lambda d:d.update(owner_approval_text='private owner record'),
    lambda d:d['cases'][0]['rounds'][0]['outputs'].update(journal='private'),
    lambda d:d['cases'][0]['rounds'][1]['outputs']['canonical']['mapper'].update(credential='private'),
    lambda d:d['equation'].update(operational_latex='C'+':/'+'Users/private/secret.txt'),
    lambda d:d['cases'][0]['rounds'][1]['outputs']['canonical']['plan_graph']['nodes'][0]['depends_on'].append('absent'),
    lambda d:d['cases'][0]['rounds'][1]['outputs']['canonical']['plan_graph']['nodes'][0].update(admitted='true'),
])
def test_private_or_malformed_nested_projection_refused(mutation):
    value=public();mutation(value)
    with pytest.raises(ValueError):validate(value)

def test_incorrect_pin_or_oversized_file_rejected_before_decode(tmp_path):
    path=ROOT/'canonical/public-evidence.json'
    with pytest.raises(ValueError):load_canonical(path,'0'*64)
    large=tmp_path/'large.json';large.write_bytes(b' '* (2*1024*1024+1))
    with pytest.raises(ValueError):load_canonical(large,hashlib.sha256(large.read_bytes()).hexdigest())

def test_full_public_history_in_both_prepared_lanes_and_no_authority():
    sys.path.insert(0,str(ROOT/'private-native'))
    from hosted_judge.paired_review import prepare,with_public_history,encoded
    packet,_=prepare('Derive a relation involving a,c.','n1: a = -c + 17')
    history=['E1: a+b=14','E2: b=2','E3: c=5','Derive a.','Correct E2 to b=3.','Recall c.']
    packet,shown=with_public_history(packet,history)
    for lane in ('se6','baseline'):
        users=[m['content'] for m in packet['payloads'][lane]['messages'] if m['role']=='user']
        assert len(users)==7 and all(text in users[i] for i,text in enumerate(history))
    assert not any('a = -c + 17' in m['content'] for m in packet['payloads']['baseline']['messages'])
    assert packet['authorization']=='NOT_AUTHORIZED' and shown['provider_calls']==0
    assert shown['pair_limits']['paid_budget_authorized_usd']==0 and shown['equivalent_public_history_rounds']==6
    assert all(packet['payloads'][lane]['model']=='nvidia/nemotron-3-super-120b-a12b' for lane in ('se6','baseline'))
    assert packet['payloads']['se6']['max_tokens']==packet['payloads']['baseline']['max_tokens']==1024
    digest=packet.pop('pair_sha256')
    assert hashlib.sha256(encoded(packet)).hexdigest()==digest

def test_public_replay_excludes_private_process_observations():
    raw=(ROOT/'canonical/functional-public.json').read_text(encoding='utf-8')
    assert all(name not in raw for name in ('raw_checkpoint','actual_pid','owner_approval','prepared_pair','private_state'))
    assert 'OWNER_SUPPLIED' in raw
