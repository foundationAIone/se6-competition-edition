"""Pinned read-only exports from real disposable Entity/Mirror stores.

Runtime execution replays the admitted fixture's canonical snapshots. It does
not import SE6Triad, open its files, run its loops or ingest model responses.
"""
from __future__ import annotations
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from .mirror_source_contract import SelfModelFact, EpistemicStatus
from .native_core import _pairs

EXPORT_SHA256 = '23842136e8c411c646276f77cd02a9d795c390e1f14bf1aa8ce43f34c857d5c8'
CONTRACT_VERSION = 'se6-competition-verified-mirror-v1'
TASK_SCHEMA = 'se6-mirror-fixture-task-v1'
PREFIX = ('VERIFIED MIRROR V1 — ISOLATED CANONICAL TEST FIXTURE. '
          'This read-only projection comes from audited disposable SE6 Entity/cognition stores. '
          'VERIFIED means scoped fixture evidence, not external world truth. '
          'Snapshots do not grant action authority or establish a currently running process. '
          'Generated answers cannot certify themselves or change these records. '
          'No production Entity, active reasoning loops, external action or autonomous planner is connected.\n')


def encode(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def sha(value):
    return hashlib.sha256(encode(value).encode('utf-8')).hexdigest()


class MirrorFixtureAdapter:
    contract_version = CONTRACT_VERSION

    def __init__(self, *, export_bytes=None):
        self.blocker = None
        self._bundle = None
        try:
            data = export_bytes if export_bytes is not None else (Path(__file__).parent/'mirror_fixtures/verified_mirror_v1.json').read_bytes()
            self.validate_source_evidence(data)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            self.blocker = 'Verified Mirror fixture unavailable ('+type(exc).__name__+'); no fallback or production access.'

    def validate_source_evidence(self, evidence):
        if type(evidence) is not bytes or hashlib.sha256(evidence).hexdigest() != EXPORT_SHA256:
            raise ValueError('MIRROR_PINNED_TEST_SOURCE_REQUIRED')
        bundle = json.loads(evidence)
        contract_bytes = (Path(__file__).parent/'mirror_source_contract.py').read_bytes()
        if hashlib.sha256(contract_bytes).hexdigest() != bundle['source_contract_subset_sha256']:
            raise ValueError('MIRROR_SOURCE_CONTRACT_MISMATCH')
        if not bundle['test_stores_only'] or bundle['model_calls'] != 0 or bundle['network_calls'] != 0:
            raise ValueError('MIRROR_OFFLINE_FIXTURE_REQUIRED')
        for case in bundle['cases']:
            for row in case['rounds']:
                export = row['export']
                if sha(export) != row['export_sha256'] or hashlib.sha256(row['input'].encode()).hexdigest() != row['input_sha256']:
                    raise ValueError('MIRROR_EXPORT_BINDING_MISMATCH')
                facts = {f['key']:SelfModelFact.model_validate_json(json.dumps(f)) for f in export['facts']}
                if (export['state_id'] != 'entity_state_'+export['state_hash']
                    or export['ancestry_state_ids'][-1] != export['state_id']
                    or json.loads(facts['self.entity_id'].value_json) != export['entity_id']
                    or json.loads(facts['self.identity_state_id'].value_json) != export['identity_state_id']
                    or json.loads(facts['self.persisted_runtime_binding'].value_json) == export['entity_id']
                    or json.loads(facts['self.entity_is_runtime'].value_json) is not False
                    or json.loads(facts['self.network_authority'].value_json) != 'NONE'
                    or json.loads(facts['self.external_requests'].value_json) != 'BLOCKED'
                    or export['production_connected'] or export['world_truth_verified']):
                    raise ValueError('MIRROR_CANONICAL_FIXTURE_MISMATCH')
                for memory in export['memory']:
                    if memory['status'] == EpistemicStatus.VERIFIED.value and not any(
                        e['independently_verified'] and e['source_kind'] != 'MODEL_OUTPUT' and e['verification_reference']
                        for e in memory['evidence']):
                        raise ValueError('MIRROR_MEMORY_INDEPENDENT_EVIDENCE_REQUIRED')
        # The digest pin authenticates an audited development fixture, not any
        # caller-supplied hash or model-proposed facts. Return independent copies.
        self._bundle = bundle

    def capabilities(self):
        return {'id':'verified_mirror','mode':'VERIFIED_MIRROR_V1',
                'label':'Verified Mirror V1 — isolated verified self/state grounding',
                'connected':self.blocker is None,'blocker':self.blocker,
                'entrypoint':'MirrorFixtureAdapter.read_verified_snapshot',
                'source':'PINNED_SANITIZED_DISPOSABLE_ENTITY_EXPORT',
                'source_contract':'se6-verified-entity-mirror-v1','export_sha256':EXPORT_SHA256,
                'production_connected':False,'active_reasoning_loops':False,
                'scope':'Canonical isolated fixture snapshots, memory classes, contradiction/correction ancestry and boundaries. '
                        'No production Entity, autonomous planner, external action or world-truth guarantee.',
                'fixtures':([] if self.blocker else [{'id':c['id'],'title':c['title'],'inputs':[r['input'] for r in c['rounds']]} for c in self._bundle['cases']])}

    def _row(self, case_id, step):
        if self.blocker: raise ValueError(self.blocker)
        case = next((c for c in self._bundle['cases'] if c['id'] == case_id), None)
        if case is None or type(step) is not int or not 0 <= step < len(case['rounds']):
            raise ValueError('Unknown Mirror fixture or step; no arbitrary evidence ingestion.')
        return deepcopy(case['rounds'][step])

    def validate_task(self, problem, checkpoint=None):
        if not isinstance(problem,str) or not 0 < len(problem.encode('utf-8')) <= 65536:
            raise ValueError('Mirror tasks require a bounded shared JSON message.')
        data = json.loads(problem, object_pairs_hook=_pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON value')))
        if (not isinstance(data,dict) or set(data) != {'schema','case_id','step','question'} or data['schema'] != TASK_SCHEMA
            or not isinstance(data['question'],str) or not data['question'].strip() or len(data['question']) > 6000):
            raise ValueError('Use the documented Mirror fixture task fields only; caller facts/status are not accepted.')
        row = self._row(data['case_id'],data['step'])
        if checkpoint is None:
            if data['step'] != 0: raise ValueError('A new fixture task must begin at step 0.')
        elif checkpoint['case_id'] != data['case_id'] or checkpoint['step']+1 != data['step']:
            raise ValueError('Mirror continuity requires the next step of the same fixture; no skipping or replay.')
        return data, row

    def read_verified_snapshot(self, isolated_session):
        return self._row(isolated_session['case_id'],isolated_session['step'])['export']

    def _validate_checkpoint(self, checkpoint, task_id):
        if checkpoint is None: return
        fields={'schema','task_id','case_id','step','round_id','export_sha256','entity_id','identity_state_id','previous_checkpoint_hash','checkpoint_hash'}
        if set(checkpoint) != fields or checkpoint['schema'] != CONTRACT_VERSION or checkpoint['task_id'] != task_id:
            raise ValueError('MIRROR_CHECKPOINT_SESSION_MISMATCH')
        material={k:v for k,v in checkpoint.items() if k!='checkpoint_hash'}
        row=self._row(checkpoint['case_id'],checkpoint['step'])
        if (sha(material)!=checkpoint['checkpoint_hash'] or row['export_sha256']!=checkpoint['export_sha256']
            or row['export']['entity_id']!=checkpoint['entity_id'] or row['export']['identity_state_id']!=checkpoint['identity_state_id']):
            raise ValueError('MIRROR_CHECKPOINT_EVIDENCE_MISMATCH')

    def advance(self, task_id, round_id, problem, checkpoint):
        self._validate_checkpoint(checkpoint,task_id)
        data,row=self.validate_task(problem,checkpoint)
        export=self.read_verified_snapshot(data)
        prior=self.read_verified_snapshot(checkpoint) if checkpoint else None
        if prior and (export['entity_id']!=prior['entity_id'] or export['identity_state_id']!=prior['identity_state_id']
                      or export['ancestry_state_ids'][:len(prior['ancestry_state_ids'])]!=prior['ancestry_state_ids']
                      or export['ancestry_receipt_ids'][:len(prior['ancestry_receipt_ids'])]!=prior['ancestry_receipt_ids']):
            raise ValueError('MIRROR_ANCESTRY_MISMATCH')
        material={'schema':CONTRACT_VERSION,'task_id':task_id,'case_id':data['case_id'],'step':data['step'],'round_id':round_id,
                  'export_sha256':row['export_sha256'],'entity_id':export['entity_id'],'identity_state_id':export['identity_state_id'],
                  'previous_checkpoint_hash':checkpoint['checkpoint_hash'] if checkpoint else None}
        next_checkpoint={**material,'checkpoint_hash':sha(material)}
        context=self._context(export,prior,task_id,row['export_sha256'])
        return next_checkpoint, {'schema':CONTRACT_VERSION,'fixture_case':data['case_id'],'fixture_step':data['step'],
            'source_export_sha256':row['export_sha256'],'checkpoint_hash':next_checkpoint['checkpoint_hash'],
            'previous_checkpoint_hash':material['previous_checkpoint_hash'],'entity_continuity':'VERIFIED',
            'entity_is_runtime':False,'production_connected':False,'active_reasoning_loops':False,
            'source':'AUDITED_DISPOSABLE_TEST_ENTITY_EXPORT_REPLAY','authority_effect':'NONE',
            'model_output_ingested':False,'world_truth_verified':False,'context':context,
            'context_sha256':hashlib.sha256(context.encode()).hexdigest(),'context_bytes':len(context.encode()),
            'evaluation':{'rubric':row['rubric'],'status':'NOT_SCORED','measurements':{
                key:None for key in ('answer_correctness','identity_continuity_accuracy','contradiction_detection',
                    'false_verification_acceptance','unknown_hallucination_rate','correction_ancestry_accuracy','relevant_memory_recall')},
                'winner':None}}

    def _context(self, export, prior, task_id, export_hash):
        references={}
        def ref(value):
            if value not in references: references[value]='e'+str(len(references))
            return references[value]
        facts=[]
        for fact in export['facts']:
            facts.append({'key':fact['key'],'value':json.loads(fact['value_json']),'status':fact['status'],
                          'evidence':[ref(v) for v in fact['evidence_references'][:1]]})
        memory=[]
        for record in export['memory']:
            memory.append({k:record[k] for k in ('memory_id','subject','value','status','recorded_status','previous_memory_id',
                           'supersedes_memory_id','contradicted_by_evidence_id','transition_reason')})
            memory[-1]['independent_evidence']=[{'reference':ref(e['evidence_id']),'kind':e['source_kind'],
                'content_hash':e['content_hash'],'verification_reference':e['verification_reference'],
                'independently_verified':e['independently_verified']} for e in record['evidence']]
            memory[-1]['claim_provenance']=[{'reference':ref(e['evidence_id']),'kind':e['source_kind'],
                                           'independently_verified':e['independently_verified']} for e in record['provenance']]
        result={'schema':CONTRACT_VERSION,'task_session':task_id,'source':'ISOLATED_CANONICAL_TEST_FIXTURE',
            'source_export_sha256':export_hash,'source_mirror_hash':export['source_mirror_hash'],
            'verified_scope':'Independent fixture evidence only; not real-world truth.',
            'entity':export['entity_id'],'identity_state':export['identity_state_id'],'state_id':export['state_id'],
            'state_version':export['state_version'],'cognition_snapshot_hash':export['cognition_snapshot_hash'],
            'facts':facts,'relevant_memory':memory,'self_claim_findings':export['findings'],
            'continuity':{'previous_projection_export':sha(prior) if prior else None,
                'previous_state':prior['state_id'] if prior else None,'current_state':export['state_id'],
                'canonical_predecessor':export['ancestry_state_ids'][-2] if len(export['ancestry_state_ids'])>1 else None,
                'latest_receipt':export['ancestry_receipt_ids'][-1]},
            'evidence_references':{alias:original for original,alias in references.items()},
            'production_connected':False,'external_actions':'NONE','world_truth_verified':False,
            'model_self_verification':'DISALLOWED','active_reasoning_loops':False}
        return PREFIX+encode(result)

    def model_context(self, summary, task_id):
        # Stored summaries are checked against the admitted pinned export again;
        # arbitrary replacement of context cannot silently reach a model.
        export=self._row(summary['fixture_case'],summary['fixture_step'])['export']
        step=summary['fixture_step']
        prior=self._row(summary['fixture_case'],step-1)['export'] if step else None
        expected=self._context(export,prior,task_id,sha(export))
        if (sha(export)!=summary['source_export_sha256'] or summary['context']!=expected
            or hashlib.sha256(summary['context'].encode()).hexdigest()!=summary['context_sha256']):
            raise ValueError('MIRROR_MODEL_CONTEXT_MISMATCH')
        return summary['context']
