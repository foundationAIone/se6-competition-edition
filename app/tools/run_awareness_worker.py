"""Run one visible, unscored development instance through the original sequence.

No solver/controller is reimplemented here. The unchanged sequence creates
independent equivalent disposable worlds for Native and conventional arms.
"""
from pathlib import Path
import argparse, hashlib, json, os, random, sys, time

APP=Path(__file__).resolve().parents[1]
BUNDLE=APP/'awareness_native'
CORE=BUNDLE/'work/qpre-calibration-integration-20261026/dev'


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_bundle():
    manifest=json.loads((BUNDLE/'BUNDLE_MANIFEST.json').read_bytes())
    hashes={}
    for name,row in manifest['files'].items():
        path=BUNDLE/name
        if not path.resolve(strict=True).is_relative_to(BUNDLE.resolve()) or path.is_symlink() or sha(path)!=row['sha256']:
            raise ValueError('AWARENESS_BUNDLED_SOURCE_MISMATCH')
        hashes[name]=row['sha256']
    return hashes


def main(out):
    out=Path(out).resolve(strict=True)
    hashes=verify_bundle()
    sys.path.insert(0,str(CORE));sys.dont_write_bytecode=True
    from scripts import run_dependency_awareness as original
    start=time.perf_counter();cpu=time.process_time()
    templates,_unused_evaluator_metadata=original.generate_templates(random.Random(int.from_bytes(os.urandom(16),'big')))
    # This is a visible authored developmental case. It is not a frozen scored
    # evaluation, a regrade, or a new claim of comparative advantage.
    results=original.sequence(out,templates,['retained','conventional'],original.source_pins())
    phases=[]
    for phase,label in enumerate(('Seed repair','Changed dependency','Changed working root'),start=1):
        arms={}
        for name,source in [('se6','retained'),('conventional','conventional')]:
            row=next((r for r in results[source] if r.get('phase')==phase),{})
            selected=row.get('selected_action',{});payload=selected.get('payload',{})
            arms[name]=dict(action=dict(id=selected.get('id'),path=payload.get('path'),value=payload.get('value')),
                goal=row.get('goal'),verification='INDEPENDENTLY_VERIFIED' if row.get('goal') is True else 'NOT_VERIFIED',
                retention=('VERIFIED_COLD_REUSE' if row.get('cold_restored') else 'VERIFIED_RETAINED') if row.get('goal') is True else 'NOT_VERIFIED',
                native_receipt=row.get('native_receipt_hash'),entity_receipt=row.get('entity_receipt_id'),
                entity_version=row.get('entity_version'),witness_sha256=row.get('witness_sha256'),
                retained_relationship_ids=row.get('maintained_edges_consumed',[]),
                retained_state_sha256=row.get('retained_state_sha256'),cold_restored=row.get('cold_restored',False),
                resources={key:row.get(key) for key in ('worker_wall_seconds','worker_cpu_seconds',
                    'peak_traced_python_bytes','child_cpu_seconds','local_monetary_cost','observed_cli_processes','model_calls')})
        def relationship(source):
            rows=results[source]
            prior=next((r for r in rows if r.get('phase')==phase-1),{})
            current=next((r for r in rows if r.get('phase')==phase),{})
            return dict(before=prior.get('selected_action',{}).get('payload',{}).get('path'),
                after=current.get('selected_action',{}).get('payload',{}).get('path'))
        phases.append(dict(phase=phase,label=label,relationship=dict(**relationship('retained'),source='PUBLIC_TASK_RELATION'),
            context=dict(root_alias='projectA' if phase<3 else 'projectB',changed=phase==3),arms=arms))
    complete=all(len(results[arm])==3 and all(row.get('goal') is True for row in results[arm]) for arm in results)
    public=dict(status='COMPLETE' if complete else 'FAILED_CLOSED',phases=phases,
        comparative_result='NOT_ESTABLISHED',development_case_visibility='VISIBLE_UNSCORED_DEVELOPMENT',
        resources=dict(worker_wall_seconds=time.perf_counter()-start,worker_cpu_seconds=time.process_time()-cpu,
            effects=sum(row.get('actual_effects',0) for rows in results.values() for row in rows),
            provider_calls=0,network_calls=0,child_cpu_seconds=None,monetary_cost=None),source_hashes=hashes,
        limitations=['Fresh disposable local development; not a new held-out benchmark.',
            'A tied completion establishes no SE6 advantage; additional verification/computation remains visible.',
            'Bounded authored dependency operator; not full mathematical equation or subjective consciousness.',
            'Worker CPU/heap excludes subprocess costs; total monetary cost is unknown.'])
    original.write_once(out/'public-result.json',public)
    print(json.dumps(dict(status=public['status'],phases=3,comparative_result='NOT_ESTABLISHED'),sort_keys=True))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',required=True)
    arguments=parser.parse_args();main(arguments.out)
