"""Load only a pinned, bounded public projection. No execution or credentials."""
import hashlib,json,math,re
from pathlib import Path
FORBIDDEN={'journal','private_state','state_before','state_after','actual_pid','actual_spawned_pid','candidate_directory','owner_approval_text','authorization_record','api_key','transcript'}
TOP={'schema','name','equation','equation_status','operator_coverage','totals','model_conditions','mechanisms','scenarios','control_scenarios','provenance','scope'}
CHECKS=set('honest_unknown contradiction_not_silently_assimilated no_native_action_on_unsupported_remap independent_full_rank_truth premises_match_current_public_evidence requested_entailment delivered_math_answer_valid current_deductions_valid old_dependent_deduction_invalidated independent_deduction_preserved current_relation independent_relation contradiction_refused revenue materials_cost gross_contribution budget_variance budget_exceeded allocation quantity_proofs_reused boundary_honest model_claim_not_promoted trusted_knowledge_unchanged verified_artifact_relation actual_artifact_checked operational_self_model_matches_observed launch_identity_matches_driver no_false_provider_or_world_authority persistent_roundtrip fresh_process_handoff'.split())
METRICS=set('score maximum events native_operations native_transition_attempts executed_native_actions subprocess_wall_seconds worker_cpu_seconds peak_python_heap_bytes provider_calls provider_tokens provider_cost_usd local_monetary_cost_usd host_calculations_created checkpoint_bytes'.split())
def fields(value,allowed):
    if not isinstance(value,dict) or set(value)-set(allowed):raise ValueError('Unexpected public projection fields')
def strings(value,keys):
    if any(k in value and value[k] is not None and not isinstance(value[k],str) for k in keys):raise ValueError('Public text field required')
def primitive(value):
    if value is not None and type(value) not in (str,int,float,bool):raise ValueError('Public scalar field required')
def hashes(value,keys):
    for k in keys:
        pattern='se-realization:[0-9a-f]{64}' if k=='trace_hash' else '[0-9a-f]{64}'
        if k in value and value[k] is not None and (not isinstance(value[k],str) or re.fullmatch(pattern,value[k]) is None):raise ValueError('Public digest required')
def equation(item):
    primitive(item.get('rhs'));strings(item,('label','reference'))
    if not isinstance(item.get('coefficients'),list):raise ValueError('Coefficient list required')
    for pair in item['coefficients']:
        if not isinstance(pair,list) or len(pair)!=2 or not isinstance(pair[0],str):raise ValueError('Coefficient pair required')
        primitive(pair[1])
def validate_shape(value):
    fields(value,TOP)
    strings(value,('schema','name','equation','equation_status','scope'))
    for item in value.get('operator_coverage',[]):
        fields(item,{'operator','status','description'});strings(item,('operator','status','description'))
    fields(value.get('totals',{}),{'SE6','DROP_RETAINED_STATE'})
    for item in value.get('totals',{}).values():
        fields(item,METRICS)
        for v in item.values():primitive(v)
    fields(value.get('model_conditions',{}),{'A_direct_Nemotron','B_conventional_stateful_agent','C_Nemotron_with_SE6','native_SE6','memory_drop'})
    strings(value.get('model_conditions',{}),value.get('model_conditions',{}))
    fields(value.get('provenance',{}),{'capture_manifest_sha256','answer_key_sha256','public_spec_sha256','scorer_sha256','rows_verified_before_scoring','scope'})
    for v in value.get('provenance',{}).values():primitive(v)
    strings(value.get('provenance',{}),('scope',));hashes(value.get('provenance',{}),('capture_manifest_sha256','answer_key_sha256','public_spec_sha256','scorer_sha256'))
    mechanism=value.get('mechanisms',{});fields(mechanism,{'scope','rows','interpretation'})
    strings(mechanism,('scope','interpretation'))
    for row in mechanism.get('rows',[]):
        fields(row,{'case','entrypoint','boundary','executed_actions','receipt_hash','wall_ns','cpu_ns','journal_replay_verified','trace_replay_verified'})
        for v in row.values():primitive(v)
        strings(row,('case','entrypoint','boundary'));hashes(row,('receipt_hash',))
    for group in ('scenarios','control_scenarios'):
        scenarios=value.get(group,[])
        if not isinstance(scenarios,list) or len(scenarios)>16:raise ValueError('Bounded public scenarios required')
        for scenario in scenarios:
            fields(scenario,{'id','domain','events'})
            strings(scenario,('id','domain'))
            if not isinstance(scenario.get('events'),list) or len(scenario['events'])>16:raise ValueError('Bounded public events required')
            for event in scenario['events']:
                fields(event,{'phase','question','source','host_artifact','answer','checks','knowledge','receipts','traces','business_views','metrics','checkpoint_before','checkpoint_after','selected_routes','scope'})
                strings(event,('phase','question','source','answer','checkpoint_before','checkpoint_after','scope'))
                artifact=event.get('host_artifact')
                if artifact is not None:
                    fields(artifact,{'sha256','verified','scope'});hashes(artifact,('sha256',));strings(artifact,('scope',))
                    if type(artifact.get('verified')) is not bool:raise ValueError('Host checksum check bool required')
                hashes(event,('checkpoint_before','checkpoint_after'))
                if any(not isinstance(v,str) for v in event.get('selected_routes',[])):raise ValueError('Public route strings required')
                fields(event.get('checks',{}),CHECKS)
                if any(type(c) is not bool for c in event.get('checks',{}).values()):raise ValueError('Boolean public checks required')
                fields(event.get('metrics',{}),METRICS)
                for v in event.get('metrics',{}).values():primitive(v)
                knowledge=event.get('knowledge',{});fields(knowledge,{'constraints','active','invalidated','relations','math_head','relation_head'})
                strings(knowledge,('math_head','relation_head'))
                for c in knowledge.get('constraints',[]):fields(c,{'label','reference','coefficients','rhs'});equation(c)
                for c in knowledge.get('active',[]):fields(c,{'reference','coefficients','rhs'});equation(c)
                for r in knowledge.get('relations',[]):fields(r,{'subject','predicate','value','status'});strings(r,r)
                for k in ('invalidated',):
                    if any(not isinstance(v,str) for v in knowledge.get(k,[])):raise ValueError('Public reference strings required')
                for r in event.get('receipts',[]):
                    fields(r,{'operation','observation','boundary_outcome','verification_passed','hash','previous_hash','sequence'})
                    for v in r.values():primitive(v)
                    strings(r,('operation','observation','boundary_outcome'));hashes(r,('hash','previous_hash'))
                    if type(r.get('verification_passed')) is not bool or type(r.get('sequence')) is not int:raise ValueError('Public receipt bool/sequence required')
                for t in event.get('traces',[]):
                    fields(t,{'receipt_hash','trace_hash','source_origin','stages'})
                    strings(t,('receipt_hash','trace_hash','source_origin'));hashes(t,('receipt_hash','trace_hash'))
                    for s in t.get('stages',[]):
                        fields(s,{'stage','operator','status','state_before_hash','state_after_hash'});strings(s,s);hashes(s,('state_before_hash','state_after_hash'))
                views=event.get('business_views') or {};fields(views,{'original','corrected'})
                for v in views.values():
                    if v is None:continue
                    fields(v,{'allocations','revenue','materials_cost','gross_contribution','budget_variance','budget_exceeded'})
                    fields(v.get('allocations',{}),{'basic','deep'})
                    strings(v.get('allocations',{}),('basic','deep'))
                    for key,item in v.items():
                        if key!='allocations':primitive(item)
def load_dynamic(path,pin):
    if path is None and pin is None:return {'name':'Dynamic evidence not configured','scenarios':[]}
    if path is None or not isinstance(pin,str) or len(pin)!=64:raise ValueError('Pinned public dynamic evidence required')
    with Path(path).open('rb') as stream:data=stream.read(2*1024*1024+1)
    if len(data)>2*1024*1024 or hashlib.sha256(data).hexdigest()!=pin:raise ValueError('Dynamic projection size/hash differs')
    value=json.loads(data)
    if value.get('schema')!='se6-dynamic-public-projection-v1' or not isinstance(value.get('scenarios'),list):raise ValueError('Dynamic projection schema required')
    def check(item,depth=0):
        if depth>24:raise ValueError('Public projection depth exceeded')
        if isinstance(item,dict):
            if FORBIDDEN.intersection(item):raise ValueError('Private dynamic fields prohibited')
            for v in item.values():check(v,depth+1)
        elif isinstance(item,list):
            if len(item)>512:raise ValueError('Public list bound exceeded')
            for v in item:check(v,depth+1)
        elif isinstance(item,str) and (len(item)>32768 or re.search(r'(?i)[A-Z]:[\\/](?:Users|Windows|Program Files)|/(?:Users|home)/|Bearer\s+[A-Za-z0-9._-]{16,}',item)):raise ValueError('Private path, credential or excessive text prohibited')
        elif isinstance(item,float) and not math.isfinite(item):raise ValueError('Finite public number required')
    check(value);validate_shape(value);return value
