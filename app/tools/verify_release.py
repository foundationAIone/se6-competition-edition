"""Read-only private/public candidate integrity and exact frozen arithmetic replay."""
import hashlib,importlib.util,json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
private=root/'COMPLETE_SOURCE_MANIFEST_PRIVATE.json'
path=private if private.is_file() else root/'PUBLIC_RELEASE_MANIFEST.json'
manifest=json.loads(path.read_bytes());wanted=manifest['files']
assert not any(p.is_symlink() for p in root.rglob('*')),'Linked candidate member'
actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
assert actual==set(wanted)|{path.name},'Unexpected candidate files'
for name,pin in wanted.items():
    p=(root/name).resolve()
    assert not Path(name).is_absolute() and p.is_relative_to(root) and not p.is_symlink()
    assert hashlib.sha256(p.read_bytes()).hexdigest()==pin,(name,'changed')
spec=importlib.util.spec_from_file_location('public_scorer',root/'benchmark/public_scorer.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
score=m.verify_bundle(root/'benchmark')
assert score==json.loads((root/'benchmark/PUBLIC_SCORECARD.json').read_bytes())
print(json.dumps({'package_hashes_verified':len(wanted),'frozen_pairs_replayed':len(score['pairs']),
    'provider_calls':0,'source_scope':'PRIVATE_OWNER_REVIEW' if path==private else 'PUBLIC_CANDIDATE',
    'license':'PROJECT_LICENSE_PRESENT' if (root.parent/'LICENSE').is_file() else 'PENDING_OWNER_ACTIVATION','public_release':'REQUIRES_OWNER_AUTHORITY'}))
