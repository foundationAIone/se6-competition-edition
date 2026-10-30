"""Frozen isolated SHADOW operators plus actual native checkpoint replay.

This compatibility bridge is not the complete symbolic equation or a world
authority. Public responses omit private task hashes/journals; full owner
attestation contains the actual typed operator outputs and loaded-code hashes.
"""
from copy import deepcopy
import hashlib
import importlib.abc
import importlib.machinery
import json
import marshal
from pathlib import Path
import sys
import time

def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()

def digest(value):
    return hashlib.sha256(encode(value)).hexdigest()

class FrozenOperators(importlib.abc.MetaPathFinder):
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.sources = {str(p.resolve()): p.read_bytes() for p in self.root.rglob('*.py')}
        self.loaded = {}
        if any(name in sys.modules for name in ('native_bridge', 'operator_executor', 'component_layer', 'computational_interference_field', 'relational_field_realization', 'toroidal_field_realization', 'field_navigation', 'se666_core')):
            raise ValueError('Operator namespace was already loaded before source freeze')
    def find_spec(self, fullname, path=None, target=None):
        if fullname not in ('native_bridge', 'operator_executor', 'component_layer', 'computational_interference_field', 'relational_field_realization', 'toroidal_field_realization', 'field_navigation', 'se666_core') and not fullname.startswith('se666_core.'):
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None or spec.origin is None:
            raise ImportError('Required operator absent from reviewed source')
        origin = str(Path(spec.origin).resolve())
        if origin not in self.sources:
            raise ImportError('Operator namespace escaped frozen private copy')
        raw = self.sources[origin]; owner = self
        class Loader(importlib.machinery.SourceFileLoader):
            def get_code(self, name):
                code = compile(raw, origin, 'exec', dont_inherit=True)
                owner.loaded[name] = {'path': Path(origin).relative_to(owner.root).as_posix(),
                    'source_sha256': hashlib.sha256(raw).hexdigest(),
                    'compiled_code_sha256': hashlib.sha256(marshal.dumps(code)).hexdigest()}
                return code
        spec.loader = Loader(fullname, origin)
        return spec

def load_bridge(bundle):
    root = Path(bundle) / 'canonical_operators'
    if not root.is_dir():
        return None
    loader = FrozenOperators(root)
    sys.meta_path.insert(0, loader)
    sys.path.insert(0, str(root))
    from native_bridge import preflight, postflight
    return preflight, postflight, loader

_COMPLETED_AUDIT_ORIGIN=object()  # Worker-local capability; never serialized.
_HOST_MANIFEST=Path(__file__).resolve().parents[1]/'COMPLETE_SOURCE_MANIFEST_PRIVATE.json'

def completed_audit_manifest_pin():
    if not _HOST_MANIFEST.is_file() or _HOST_MANIFEST.is_symlink():
        raise ValueError('Completed audit requires the regular pinned HOST manifest')
    return hashlib.sha256(_HOST_MANIFEST.read_bytes()).hexdigest()

def completed_audit_binding(engine,task_id,before,checkpoint,out,answer):
    """Exact invocation inputs plus loaded HOST/Core audit implementation."""
    from .native_adapter import wrapper_signature
    from tools.code_attestation_v7 import fingerprint
    from src.workbench.core_revisions import SOURCE_HASHES
    return digest({'task_id':task_id,'before':before,'checkpoint':checkpoint,'out':out,'raw_answer':answer,
        'core_sources':SOURCE_HASHES,'loaded_host_wrapper':wrapper_signature(),
        'whole_host_manifest_sha256':completed_audit_manifest_pin(),
        'loaded_score_local':fingerprint(type(engine).score_local)})

def read_completed_audit(sink,engine,task_id,before,checkpoint,out,answer):
    if not isinstance(sink,dict) or set(sink)!={'audit','audit_sha256','binding','origin'} or sink['origin'] is not _COMPLETED_AUDIT_ORIGIN or type(sink['audit']) is not dict:
        raise ValueError('Completed native audit envelope malformed')
    if digest(sink['audit'])!=sink['audit_sha256'] or sink['binding']!=completed_audit_binding(engine,task_id,before,checkpoint,out,answer):
        raise ValueError('Completed native audit binding changed')
    if sink['audit'].get('status')!='LOCAL_CERTIFICATES_REPLAYED':raise ValueError('Completed native audit status invalid')
    return deepcopy(sink['audit'])


def verify_native_checkpoint(engine, task_id, checkpoint, out, answer, *, before=None, audit_sink=None, presentation_captures=None):
    """Reconstruct both kernel journals and compare NEW receipts, not flags.

    Journal replay authenticates conditional local state consequences. It does
    not establish that an owner-supplied premise is an external world fact.
    """
    from src.workbench.core_revisions import load_core, verify_traces, SOURCE_HASHES, CANONICAL
    if audit_sink is not None and (type(audit_sink) is not dict or audit_sink):raise ValueError('Completed audit sink must be fresh and empty')
    auto = engine._restore(checkpoint, task_id)
    if auto is None:
        return False
    if auto.get('task_id') != task_id or auto.get('source_hashes') != SOURCE_HASHES:
        raise ValueError('Native task/source identity mismatch')
    if auto.get('checkpoint_hash') != digest({k: v for k, v in auto.items() if k != 'checkpoint_hash'}):
        raise ValueError('AUTO checkpoint hash mismatch')
    previous=engine._restore(before,task_id) if before is not None else None
    if previous is not None and (previous.get('task_id')!=task_id or previous.get('source_hashes')!=SOURCE_HASHES or previous.get('checkpoint_hash')!=digest({k:v for k,v in previous.items() if k!='checkpoint_hash'})):
        raise ValueError('Prior AUTO checkpoint identity/hash mismatch')
    api = load_core(); recorded = {}; new_hashes=set(); journal_deltas={}
    presentation_receipts=[]
    for kind in ('math', 'relations'):
        retained = auto.get(kind)
        if retained is None:
            continue
        if kind == 'relations':
            if retained.get('core_revision') != CANONICAL or retained.get('source_hashes') != SOURCE_HASHES:
                raise ValueError('Relational checkpoint source mismatch')
            head = auto['relation_head']
        else:
            head = retained['head']
        restored = api.SE.restore(retained['journal'], expected_head=head)
        expected_identity = ('competition-auto-math:' if kind == 'math' else 'competition-task:') + task_id
        if restored.state.identity != expected_identity:
            raise ValueError('Restored journal belongs to another task')
        verify_traces(api, restored, retained['traces'])
        presentation_receipts.extend(restored.receipts)
        records=[json.loads(encode(r.to_record())) for r in restored.receipts]
        old_retained=(previous or {}).get(kind); old_records=[]
        if old_retained is not None:
            old_head=previous['relation_head'] if kind=='relations' else old_retained['head']
            old_engine=api.SE.restore(old_retained['journal'],expected_head=old_head)
            if old_engine.state.identity!=expected_identity:raise ValueError('Prior journal belongs to another task')
            verify_traces(api,old_engine,old_retained['traces'])
            old_records=[json.loads(encode(r.to_record())) for r in old_engine.receipts]
            if records[:len(old_records)]!=old_records:raise ValueError('Native history was replaced instead of appended')
        journal_deltas[kind]=[r['receipt_hash'] for r in records[len(old_records):]]
        new_hashes.update(journal_deltas[kind])
        for record in records:recorded[record['receipt_hash']]=record
    if previous is not None and any(previous.get(kind) and not auto.get(kind) for kind in ('math','relations')):
        raise ValueError('Previously retained independent journal was removed')
    receipts = out['receipts']
    if len({r['receipt_hash'] for r in receipts}) != len(receipts):
        raise ValueError('Duplicate consequence receipt')
    for receipt in receipts:
        if recorded.get(receipt['receipt_hash']) != json.loads(encode(receipt)):
            raise ValueError('Claimed native receipt differs from replayed consequence')
    claimed_hashes=[r['receipt_hash'] for r in receipts]
    if set(claimed_hashes)!=new_hashes or out['local_operations']!=len(receipts):
        raise ValueError('Claimed receipts must be the exact new journal delta')
    ordered=[]; per_kind={'math':[],'relations':[]}
    for node in out['nodes']:
        values=(node.get('result') or {}).get('receipt_hashes',[]) if node['status']=='COMPLETE' else []
        if not isinstance(values,list) or any(not isinstance(h,str) for h in values):raise ValueError('Native node receipt coverage malformed')
        ordered.extend(values)
        if node['route'] in ('LINEAR_MATH','LINEAR_DERIVATION'):per_kind['math'].extend(values)
        elif node['route']=='RELATIONAL':per_kind['relations'].extend(values)
        elif values:raise ValueError('Host or unsupported node cannot claim native receipts')
    if claimed_hashes!=ordered or any(per_kind[k]!=journal_deltas.get(k,[]) for k in per_kind):
        raise ValueError('Current node order and exact new journal receipts disagree')
    from .provisional_math_presentation import verify_presentations,formatter_policy
    from src.workbench.auto_intake import AutoIntake
    # Only actual original full-replay receipt objects enter this additional gate.
    verify_presentations(api,out,presentation_receipts,answer,checkpoint,formatter_policy(AutoIntake),captures=presentation_captures)
    audit = engine.score_local({'id': task_id, 'orchestration_checkpoint': checkpoint,
        'rounds': [{'auto_execution': out, 'lanes': {'se6': {'response': answer,
        'response_sha256': hashlib.sha256(answer.encode()).hexdigest()}}}]})
    if audit['status'] != 'LOCAL_CERTIFICATES_REPLAYED':
        raise ValueError('Actual consequence did not pass local proof replay')
    passed=any(r['verification']['passed'] and r['boundary']['outcome'] == 'ALLOW'
        and r.get('observed_consequence') and r['observed_consequence'].get('success') for r in receipts)
    if passed and audit_sink is not None:
        audit_sink.update(audit=deepcopy(audit),audit_sha256=digest(audit),binding=completed_audit_binding(engine,task_id,before,checkpoint,out,answer),origin=_COMPLETED_AUDIT_ORIGIN)
    return passed

def begin(bundle, question, plan, checkpoint, field_checkpoint=None, *, field_mode='enabled', toroidal_mode=None,toroidal_parameters=None):
    if field_mode not in ('enabled','neutralized','disabled'):raise ValueError('FIELD_MODE')
    toroidal_mode=field_mode if toroidal_mode is None else toroidal_mode
    if toroidal_mode not in ('enabled','neutralized','disabled'):raise ValueError('TOROIDAL_MODE')
    start = time.perf_counter(); cpu = time.process_time()
    loaded = load_bridge(bundle)
    if loaded is None:
        return None
    preflight, postflight, loader = loaded
    before = deepcopy(checkpoint)
    pre = preflight(question, plan, checkpoint)
    from component_layer import inspect_components
    components = inspect_components(question, pre['plan_mapping'], (pre['operators'] or {}).get('models', {}).get('qpre'))
    field_step=None
    legacy_checkpoint=deepcopy(field_checkpoint)
    relational_checkpoint=legacy_checkpoint.pop('relational_checkpoint',None) if legacy_checkpoint is not None else None
    toroidal_checkpoint=legacy_checkpoint.pop('toroidal_checkpoint',None) if legacy_checkpoint is not None else None
    navigation_checkpoint=legacy_checkpoint.pop('navigation_checkpoint',None) if legacy_checkpoint is not None else None
    if legacy_checkpoint=={}:legacy_checkpoint=None
    if field_mode!='disabled' and (Path(bundle)/'canonical_operators/computational_interference_field.py').exists():
        from computational_interference_field import plan_field_step
        field_step=plan_field_step(plan,question,legacy_checkpoint,budget=1)
    relational=None;pipeline=None
    if field_mode!='disabled' and (Path(bundle)/'canonical_operators/relational_field_realization.py').exists():
        from relational_field_realization import realize_field
        from .field_pipeline import prepare
        relational=realize_field(plan,pre['plan_mapping'],relational_checkpoint,enabled=field_mode=='enabled')
        pipeline=prepare(pre,relational,budget=1)
    toroidal=None
    if toroidal_mode!='disabled' and (Path(bundle)/'canonical_operators/toroidal_field_realization.py').exists():
        from .toroidal_pipeline import prepare as prepare_toroidal
        toroidal=prepare_toroidal(pre,plan,toroidal_checkpoint,enabled=toroidal_mode=='enabled',budget=1,navigation_prior=navigation_checkpoint,parameters=toroidal_parameters)
    if checkpoint != before:
        raise ValueError('Canonical preflight mutated retained state')
    permitted = {'LINEAR_MATH', 'LINEAR_DERIVATION', 'RELATIONAL', 'HOST_BUSINESS', 'HOST_BUDGET'}
    admitted = set(pre['admitted_ids'])
    for n in plan['nodes']:
        could_run = n['connected'] and n['route'] in permitted and all(d in admitted for d in n['depends_on'])
        if could_run and n['id'] not in admitted:
            raise ValueError('Native effect is not admitted by canonical preflight')
    if pre['decision'] == 'PAUSE' and admitted:
        raise ValueError('Paused preflight cannot admit an effect')
    return {'pre': pre, 'components': components, 'field_step':field_step, 'relational_field':relational,'field_pipeline':pipeline,
        'field_mode':field_mode,'toroidal':toroidal,'toroidal_mode':toroidal_mode,'postflight': postflight, 'loader': loader, 'wall_start': start,
        'cpu_start': cpu, 'before': before, 'before_sha256': digest(before),'plan':deepcopy(plan)}

def finish(context, engine, task_id, checkpoint, out, answer):
    if context is None:
        return None, None
    original = deepcopy(checkpoint)
    plan=context['plan'];pre=context['pre']
    if digest(plan)!=pre['plan_sha256'] or out['question_sha256']!=pre['question_sha256']:
        raise ValueError('Actual consequence plan/question differs from preflight')
    if checkpoint.get('previous_checkpoint_hash')!=(context['before'] or {}).get('checkpoint_hash') or out['checkpoint_hash']!=checkpoint['checkpoint_hash']:
        raise ValueError('Actual successor ancestry differs from preflight')
    nodes=out['nodes']
    if len(nodes)!=len(plan['nodes']):raise ValueError('Actual consequence graph has a different size')
    for planned,observed in zip(plan['nodes'],nodes):
        if any(observed.get(k)!=planned.get(k) for k in ('id','route','depends_on','source_spans','purpose')):
            raise ValueError('Actual node identity/route/order differs from admitted plan')
        if observed['status']=='COMPLETE' and observed['id'] not in pre['admitted_ids']:
            raise ValueError('Nonadmitted node executed an operation')
    after_hash = digest(checkpoint)
    audit_sink={}
    context.pop('completed_local_audit',None)
    def independent(request):
        if request['before_sha256'] != context['before_sha256'] or request['after_sha256'] != after_hash:
            raise ValueError('Consequence checkpoint binding mismatch')
        if request['receipts'] != out['receipts']:
            raise ValueError('Consequence receipt substitution')
        return verify_native_checkpoint(engine, task_id, checkpoint, out, answer, before=context['before'],audit_sink=audit_sink,presentation_captures=context.get('presentation_captures'))
    post = context['postflight'](context['pre'], context['before_sha256'], after_hash,
        out['receipts'], verify_native=independent)
    if post['host_independent_replay_passed'] and audit_sink:
        read_completed_audit(audit_sink,engine,task_id,context['before'],checkpoint,out,answer)
        context['completed_local_audit']=audit_sink
    relational_feedback=None
    if context.get('field_pipeline') is not None:
        from .field_pipeline import finish as finish_field_pipeline
        relational_feedback=finish_field_pipeline(context['field_pipeline'],context['relational_field'],out,
            post['host_independent_replay_passed'],pre['admitted_ids'])
    toroidal_feedback=None
    if context.get('toroidal') is not None:
        from .toroidal_pipeline import finish as finish_toroidal
        toroidal_feedback=finish_toroidal(context['toroidal'],out,post['host_independent_replay_passed'],pre['admitted_ids'])
    field_feedback=None
    if context.get('field_step') is not None:
        from computational_interference_field import advance_field_feedback
        def additional_node_audit(request):
            # Mandatory full journal replay above remains the evidence gate.
            # This selected extra audit checks actual node/receipt binding only.
            actual=next((n for n in out['nodes'] if n['id']==request['id']),None)
            if request['plan_sha256']!=context['field_step']['plan_sha256'] or request['question_sha256']!=out['question_sha256'] or actual!=request['node']:
                return False
            if actual['status']!='COMPLETE' or request['id'] not in pre['admitted_ids']:return False
            hashes=(actual.get('result') or {}).get('receipt_hashes',[])
            return bool(post['host_independent_replay_passed']) and all(h in {r['receipt_hash'] for r in out['receipts']} for h in hashes)
        field_feedback=advance_field_feedback(context['field_step'],out,independent_audit=additional_node_audit)
    if checkpoint != original:
        raise ValueError('Independent proof replay mutated successor state')
    pre = context['pre']; operators = pre['operators']
    mapping = pre['plan_mapping']['model']
    counts=pre['plan_mapping']['counts']
    qpre = operators['models']['qpre'] if operators else None
    wall = time.perf_counter() - context['wall_start']; cpu = time.process_time() - context['cpu_start']
    # No user checkpoint/source identifiers or hashes are published here.
    public = {'contract': 'se6-symbolic-equation-v6.1.0', 'coverage': 'PARTIAL_ISOLATED_COMPATIBILITY',
        'admission': pre['decision'], 'admitted_nodes': pre['admitted_ids'], 'skips': pre['skips'],
        'mapper': {'vertices': len(mapping['vertices']), 'relations': len(mapping['relations']),
            'dimensions': len(mapping['dimensions']), 'perspectives': len(mapping['perspectives']),
            'flower_centers': len(mapping['flower_lineage']), 'invariants': len(mapping['invariants']),
            'dependency_relations':counts['dependency_relations'],'hyperedges':counts['hyperedges'],
            'recentered_topologically':len(mapping['flower_lineage'])>1,
            'scope':'Exact plan topology and provenance, not numerical geometry or semantic inference'},
        'components': {'periodic_dimensions':len(context['components']['periodic_map']['dimensions']),
            'periodic_grounding':'SYMBOLIC_ONLY', 'roundtrip_verified':context['components']['roundtrip_verified'],
            'invariants':context['components']['invariants'],
            'legacy_advisory_counts':{k:len(v.get('rings',[])) if k=='flower_token_lattice' else len(v) for k,v in context['components']['legacy_advisory'].items()},
            'geometric_rotation':'UNAVAILABLE', 'scope':context['components']['scope']},
        'qpre': {'rendered': qpre is not None, 'actuality': False, 'authority': 'NONE'},
        'returned_center_changed': post['traversal']['state_changed'],
        'independent_checkpoint_replay': post['host_independent_replay_passed'],
        'selection_policy': pre['selection_policy'],
        'plan_graph':{'nodes':[{'id':n['id'],'route':n['route'],'depends_on':n['depends_on'],'admitted':n['id'] in pre['admitted_ids']} for n in context['plan']['nodes']],
            'flower_recentered_terminal':pre['admitted_ids'][0] if len(mapping['flower_lineage'])>1 else None,
            'scope':pre['plan_mapping']['recenter_scope']},
        'scope': 'Actual SHADOW typed mapping/possibility/traversal plus conditional kernel proof replay; no numerical geometry, integral execution, universal state, model or world-truth claim.',
        'resources': {'bridge_and_native_window_seconds': wall, 'bridge_and_native_window_cpu_seconds': cpu,
            'provider_calls': 0, 'provider_tokens': 0, 'provider_cost_usd': 0, 'local_monetary_cost_usd': None}}
    attestation = {'components':context['components'], 'preflight': pre, 'postflight': post, 'compiled_operator_modules': context['loader'].loaded,
        'actual_checkpoint_before_sha256': context['before_sha256'], 'actual_checkpoint_after_sha256': after_hash}
    if field_feedback is not None:
        field=context['field_step']['field'];attention=context['field_step']['projection']
        public['field_candidate']={'schema':field['schema'],'status':'CANDIDATE_COMPUTATIONAL_ONLY',
            'step':field['step'],'time':field['time'],'samples':field['samples'],
            'source_force_norms':field['source_force_norms'],'next_force_norms':field_feedback['updated_field']['next_force_norms'],
            'parameters':context['field_step']['config'],
            'next_source_forces':field_feedback['checkpoint']['field_state']['forces'],
            'candidate_transform':attention,'selected_extra_audits':field_feedback['audits'],
            'configuration_changed':context['field_step']['configuration_rebase'] is not None,
            'feedback_applied':field_feedback['feedback'] is not None,
            'units':field['units'],'mandatory_verification_skipped':False,'native_evidence_truth_changed':False,
            'scope':'Bounded candidate field directs actual optional node-binding audits and updates separate candidate source state. No physical field, canonical coupling equivalence, added solving correctness or authority.'}
        attestation['field_candidate']={'step':context['field_step'],'feedback':field_feedback}
    if relational_feedback is not None:
        from .field_pipeline import public as public_field_pipeline
        public['field_realization']=public_field_pipeline(context['relational_field'],context['field_pipeline'],relational_feedback)
        public['field_realization']['scope']+=' Legacy V8 compatibility calculation/audit also runs; both costs are included in whole execution measurements.'
        attestation['field_realization']={'field':context['relational_field'],'pipeline':context['field_pipeline'],'feedback':relational_feedback}
    if toroidal_feedback is not None:
        from .toroidal_pipeline import public as public_toroidal
        public['toroidal_realization']=public_toroidal(context['toroidal'],toroidal_feedback)
        attestation['toroidal_realization']={'prepared':context['toroidal'],'feedback':toroidal_feedback}
    public['field_mode']=context['field_mode']
    public['toroidal_mode']=context['toroidal_mode']
    return public, attestation
