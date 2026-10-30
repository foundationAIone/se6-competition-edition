"""Read-only admission of a pinned, explicit public canonical-evidence projection."""
import hashlib
import json
import math
from pathlib import Path
import re
from .dynamic import FORBIDDEN, fields, strings, hashes, primitive

TOP={'schema','name','equation','operators','cases','conditions','limits','provenance'}
EQ={'contract','source_document','source_document_sha256','operational_latex','recursive_latex',
    'official_reference_latex','owner_latest_latex','reconciliation','source_status','display_normalization',
    'owner_older_latex','primary_reference','transcription_status'}
CANONICAL={'contract','coverage','admission','admitted_nodes','skips','mapper','qpre',
    'returned_center_changed','independent_checkpoint_replay','selection_policy','scope','resources','plan_graph'}
RESOURCES={'bridge_and_native_window_seconds','bridge_and_native_window_cpu_seconds',
    'whole_execute_native_wall_seconds','whole_execute_native_cpu_seconds','provider_calls',
    'provider_tokens','provider_cost_usd','local_monetary_cost_usd','driver_subprocess_wall_seconds'}

def scalar_map(value, allowed):
    fields(value,allowed)
    for v in value.values():primitive(v)

def bounded(value,depth=0):
    if depth>24:raise ValueError('Canonical projection depth exceeded')
    if isinstance(value,dict):
        if FORBIDDEN.intersection(value):raise ValueError('Private canonical fields prohibited')
        for item in value.values():bounded(item,depth+1)
    elif isinstance(value,list):
        if len(value)>512:raise ValueError('Canonical projection list bound exceeded')
        for item in value:bounded(item,depth+1)
    elif isinstance(value,str):
        if len(value)>32768 or re.search(r'(?i)[A-Z]:[\\/](?:Users|Windows|Program Files)|/(?:Users|home)/|Bearer\s+[A-Za-z0-9._-]{16,}',value):
            raise ValueError('Private path, credential or excessive text prohibited')
    elif type(value) is float and not math.isfinite(value):raise ValueError('Nonfinite projection value')
    elif value is not None and type(value) not in (int,float,bool):raise ValueError('Invalid projection value')

def validate(value):
    bounded(value);fields(value,TOP)
    if value.get('schema')!='se6-canonical-public-projection-v7':raise ValueError('Canonical projection schema required')
    strings(value,('schema','name'));eq=value['equation'];fields(eq,EQ)
    strings(eq,EQ-{'reconciliation'});hashes(eq,('source_document_sha256',))
    if not isinstance(eq.get('reconciliation'),list) or any(not isinstance(v,str) for v in eq['reconciliation']):raise ValueError('Equation reconciliation text required')
    if not isinstance(value.get('operators'),list) or len(value['operators'])>40:raise ValueError('Bounded operator coverage required')
    for op in value['operators']:
        fields(op,{'id','status','source','description','skip_reason'});strings(op,op)
        if op.get('status') not in {'NATIVE_EXECUTED','HOST_VERIFIED','MODEL_ASSISTED','CONCEPTUAL','UNAVAILABLE'}:raise ValueError('Canonical evidence status required')
    scalar_map(value.get('conditions',{}),{'A_direct_Nemotron','B_conventional_stateful_model_agent','C_SE6_model_system','deterministic_control','fixture_outcome','new_provider_calls'})
    if not isinstance(value.get('limits'),list) or any(not isinstance(v,str) for v in value['limits']):raise ValueError('Explicit limitations required')
    scalar_map(value.get('provenance',{}),{'source_manifest_sha256','capture_manifest_sha256','scoring_status','scope'})
    cases=value.get('cases',[])
    if not isinstance(cases,list) or len(cases)>16:raise ValueError('Bounded canonical cases required')
    for case in cases:
        fields(case,{'id','domain','rounds'});strings(case,('id','domain'))
        if not isinstance(case.get('rounds'),list) or len(case['rounds'])>8:raise ValueError('Bounded canonical rounds required')
        for row in case['rounds']:
            fields(row,{'phase','question','outputs','resources','skips','before','after','correction','transfer','checks','receipts','traces'})
            strings(row,('phase','question','before','after','correction','transfer'))
            scalar_map(row.get('resources',{}),RESOURCES)
            if any(not isinstance(s,str) for s in row.get('skips',[])):raise ValueError('Canonical skip text required')
            scalar_map(row.get('checks',{}),{'native_proofs_replayed','actual_center_changed','old_dependency_invalidated','independent_knowledge_preserved','same_public_history','new_target_verified'})
            out=row['outputs'];fields(out,{'answer','canonical'});strings(out,('answer',))
            canon=out.get('canonical')
            if canon is not None:
                fields(canon,CANONICAL);strings(canon,('contract','coverage','admission','selection_policy','scope'))
                if any(not isinstance(s,str) for s in canon.get('admitted_nodes',[])):raise ValueError('Admitted identifiers required')
                for skip in canon.get('skips',[]):fields(skip,{'id','route','reason'});strings(skip,skip)
                if canon.get('mapper') is not None:scalar_map(canon['mapper'],{'vertices','relations','dimensions','perspectives','flower_centers','invariants','dependency_relations','hyperedges','recentered_topologically','scope'})
                scalar_map(canon.get('qpre',{}),{'rendered','actuality','authority'})
                for k in ('returned_center_changed','independent_checkpoint_replay'):
                    if type(canon.get(k)) is not bool:raise ValueError('Canonical verification bool required')
                scalar_map(canon.get('resources',{}),RESOURCES)
                graph=canon.get('plan_graph')
                if graph is not None:
                    fields(graph,{'nodes','flower_recentered_terminal','scope'});strings(graph,('flower_recentered_terminal','scope'))
                    if not isinstance(graph.get('nodes'),list) or len(graph['nodes'])>12:raise ValueError('Bounded exact plan topology required')
                    known=set()
                    for n in graph['nodes']:
                        fields(n,{'id','route','depends_on','admitted'});strings(n,('id','route'))
                        if n['id'] in known or not isinstance(n.get('depends_on'),list) or len(set(n['depends_on']))!=len(n['depends_on']) or any(d not in known for d in n['depends_on']):raise ValueError('Ordered closed plan dependencies required')
                        if type(n.get('admitted')) is not bool:raise ValueError('Plan admission bool required')
                        known.add(n['id'])
                    if graph.get('flower_recentered_terminal') is not None and graph['flower_recentered_terminal'] not in known:raise ValueError('Recentered terminal absent from actual plan')
            if len(row.get('receipts',[]))>20 or len(row.get('traces',[]))>20:raise ValueError('Bounded native receipts required')
            for rec in row.get('receipts',[]):
                fields(rec,{'operation','boundary_outcome','verification_passed','hash','sequence'});strings(rec,('operation','boundary_outcome'));hashes(rec,('hash',))
                if type(rec.get('verification_passed')) is not bool or type(rec.get('sequence')) is not int:raise ValueError('Native receipt bool/sequence required')
            for trace in row.get('traces',[]):
                fields(trace,{'receipt_hash','trace_hash','stages'});hashes(trace,('receipt_hash','trace_hash'))
                if not isinstance(trace.get('stages'),list) or len(trace['stages'])>16:raise ValueError('Bounded actual trace stages required')
                for stage in trace['stages']:fields(stage,{'stage','operator','outcome'});strings(stage,stage)
    return value

def load_canonical(path,pin):
    if path is None and pin is None:return {'name':'Canonical evidence not configured','cases':[]}
    if path is None or not isinstance(pin,str) or re.fullmatch('[0-9a-f]{64}',pin) is None:raise ValueError('Pinned canonical public projection required')
    with Path(path).open('rb') as stream:raw=stream.read(2*1024*1024+1)
    if len(raw)>2*1024*1024 or hashlib.sha256(raw).hexdigest()!=pin:raise ValueError('Canonical projection size/hash differs')
    return validate(json.loads(raw))

def load_current_coverage(path,pin):
    if path is None and pin is None:return []
    if path is None or not isinstance(pin,str) or re.fullmatch('[0-9a-f]{64}',pin) is None:raise ValueError('Pinned current coverage required')
    raw=Path(path).read_bytes()
    if len(raw)>128*1024 or hashlib.sha256(raw).hexdigest()!=pin:raise ValueError('Current coverage size/hash differs')
    value=json.loads(raw);bounded(value)
    if not isinstance(value,list) or len(value)>40:raise ValueError('Bounded current operators required')
    ids=set()
    for op in value:
        fields(op,{'id','status','source','description','skip_reason'});strings(op,op)
        if op['id'] in ids or op['status'] not in {'NATIVE_EXECUTED','HOST_VERIFIED','MODEL_ASSISTED','CONCEPTUAL','UNAVAILABLE'}:raise ValueError('Unique current scoped operator required')
        ids.add(op['id'])
    return value

def load_field_controls(path,pin):
    if path is None and pin is None:return {}
    if path is None or not isinstance(pin,str) or re.fullmatch('[0-9a-f]{64}',pin) is None:raise ValueError('Pinned candidate controls required')
    raw=Path(path).read_bytes()
    if len(raw)>128*1024 or hashlib.sha256(raw).hexdigest()!=pin:raise ValueError('Candidate controls size/hash differs')
    value=json.loads(raw);bounded(value)
    if value.get('schema')!='se6-v8-candidate-field-controls' or value.get('physical_claim') is not False or value.get('canonical_equivalence') is not False:
        raise ValueError('Explicit nonphysical candidate controls required')
    if not isinstance(value.get('controls'),list) or len(value['controls'])!=5:raise ValueError('Exactly five bounded field controls required')
    return value
