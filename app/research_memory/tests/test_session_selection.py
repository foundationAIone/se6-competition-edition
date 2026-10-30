"""Task-scoped development contracts; no external case labels or inference."""
import copy,json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
from research_memory.sessions import SessionMemory
from research_memory import session_selection as selection

def fixture():
    return dict(source_id='SYNTHETIC_TASK_CONTRACT_FIXTURE_NOT_BENCHMARK',
        provenance=dict(dataset_revision=selection.read_admitted_development_report()['dataset_revision']),sessions=[
        dict(session_id='long',timestamp='2024-01-01',turns=[dict(role='user',content='needle export '+'ordinary '*3000)]),
        dict(session_id='short',timestamp='2024-01-02',turns=[dict(role='user',content='needle export '*4)]),
        *[dict(session_id=f'other-{i}',timestamp='2024-01-03',turns=[dict(role='user',content='unrelated bicycle wheels')]) for i in range(3)]])

class SelectionTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory(prefix='SE6-METHOD-DEV-');self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def memory(self):
        m=SessionMemory(self.root/'memory');m.ingest(fixture());return m
    def test_actual_retained_report_changes_generator_and_cold_next_use(self):
        m=self.memory();old=m.retrieve('needle export',k=1)
        self.assertEqual(old['trace']['method'],selection.LEGACY);self.assertEqual(old['sessions'][0]['session_id'],'long')
        receipt=m.admit_method_report(selection.read_admitted_development_report());self.assertIn('receipt_id',receipt)
        now=m.retrieve('needle export',k=1)
        self.assertEqual(now['trace']['method'],selection.BM25);self.assertEqual(now['sessions'][0]['session_id'],'short')
        self.assertNotEqual(now['trace']['method_policy']['memory_id'],now['trace']['selected'][0]['memory_id'])
        m.save(m.root/'snapshot')
        script='from research_memory.sessions import SessionMemory;import sys,json;m=SessionMemory(sys.argv[1]);m.load(sys.argv[2]);r=m.retrieve("needle export",k=1);print(json.dumps({"method":r["trace"]["method"],"selected":r["sessions"][0]["session_id"],"policy":r["trace"]["method_policy"],"pid":r["trace"]["process_id"]}))'
        deps=Path(__file__).resolve().parents[3]/'linux-deps';app=Path(__file__).resolve().parents[2]
        environment={'PATH':os.defpath,'PYTHONPATH':str(app)+os.pathsep+str(deps),'PYTHONDONTWRITEBYTECODE':'1'}
        completed=subprocess.run([sys.executable,'-B','-c',script,str(m.root),str(m.root/'snapshot')],env=environment,capture_output=True,text=True,check=True)
        cold=json.loads(completed.stdout);self.assertEqual((cold['method'],cold['selected']),(selection.BM25,'short'))
        self.assertNotEqual(cold['pid'],now['trace']['process_id']);self.assertEqual(cold['policy']['memory_id'],now['trace']['method_policy']['memory_id'])
    def test_forged_report_cannot_be_retained(self):
        m=self.memory();before=m.store.reconstruct().state.entity_state_id;bad=copy.deepcopy(selection.read_admitted_development_report())
        bad['recommended_method']=selection.LEGACY
        with self.assertRaisesRegex(ValueError,'CALLER_ECHO_REJECTED'):m.admit_method_report(bad)
        self.assertEqual(m.store.reconstruct().state.entity_state_id,before)
        self.assertEqual(m.retrieve('needle export',k=1)['trace']['method'],selection.LEGACY)
    def test_retained_preference_does_not_apply_to_undeclared_source_task(self):
        h=fixture();h.pop('provenance');m=SessionMemory(self.root/'memory');m.ingest(h)
        m.admit_method_report(selection.read_admitted_development_report());r=m.retrieve('needle export',k=1)
        self.assertEqual(r['trace']['method'],selection.LEGACY)
        self.assertEqual(r['trace']['method_policy']['status'],'RETAINED_POLICY_INAPPLICABLE_SOURCE_TASK_LEGACY_EXPLICIT')
    def test_prior_result_metrics_are_not_mutated_by_later_query(self):
        m=self.memory();before=m.retrieve('needle export');frozen=copy.deepcopy(before['trace']['phase_metrics'])
        m.retrieve('needle export');self.assertEqual(before['trace']['phase_metrics'],frozen)
    def test_static_readport_rejects_changed_report_bytes(self):
        original=selection.ROOT;fake=self.root/'readport';fake.mkdir()
        for name in ['development_method_report.json','selection_read_contract.json']:(fake/name).write_bytes((original/name).read_bytes())
        try:
            selection.ROOT=fake;self.assertTrue(selection.read_admitted_development_report())
            path=fake/'development_method_report.json';path.write_bytes(path.read_bytes()+b' ')
            with self.assertRaisesRegex(ValueError,'PIN_MISMATCH'):selection.read_admitted_development_report()
        finally:selection.ROOT=original
    def test_policy_withdrawal_changes_method_without_deleting_source(self):
        m=self.memory();m.admit_method_report(selection.read_admitted_development_report());r=m.retrieve('needle export',k=1)
        m.mark_inactive(r['trace']['method_policy']['memory_id'])
        changed=m.retrieve('needle export',k=1);self.assertEqual(changed['trace']['method'],selection.LEGACY)
        self.assertEqual(changed['sessions'][0]['session_id'],'long')
    def test_collection_withdrawal_blocks_shared_capability(self):
        m=self.memory();m.admit_method_report(selection.read_admitted_development_report());r=m.retrieve('needle export',k=1)
        m.mark_inactive(r['trace']['selected'][0]['memory_id']);blocked=m.retrieve('needle export')
        self.assertEqual(blocked['sessions'],[]);self.assertEqual(blocked['trace']['candidate_occurrence_count'],0)
    def test_cached_validation_still_freshly_hashes_tampered_same_size_bytes(self):
        m=self.memory();m.retrieve('needle export');part=next(m.payload_root.rglob('*.chunk'));saved=part.stat();raw=part.read_bytes()
        part.write_bytes(bytes([raw[0]^1])+raw[1:]);os.utime(part,ns=(saved.st_atime_ns,saved.st_mtime_ns))
        with self.assertRaisesRegex(ValueError,'CHUNK_CONTENT_PIN'):m.retrieve('needle export')
    def test_fresh_storage_scan_matches_existing_accounting(self):
        m=self.memory()
        from research_memory.adapter import Memory
        self.assertEqual(m._bytes(),Memory._bytes(m))

if __name__=='__main__':unittest.main()
