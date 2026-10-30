"""Pinned dependency selection and receipt/trace validation; no cognition engine."""
from dataclasses import fields
import ast
import hashlib
import importlib
import json
from pathlib import Path

LEGACY = 'legacy'
CANONICAL = 'canonical-realization-v1'
SOURCE_HASHES = {'__init__.py': 'be25b3311502fce970f13f7a936af672f7b754a104336dcb2d2a49c6f3f9a3c5', 'kernel.py': '7c6b48b11dcffb1a2524f5475167768a438af03245ad57cf58b52db05a643674', 'mathematics.py': '853bf994f5db6f61f20381a39dcef9f3db81be1f3eeedab029e2df3a7d7c7f14', 'realization.py': '265f0b0173b8e5b2f7bdd8aca8b9cb9577aebe6f50eabae77e34318999754a64'}

def validate_revision(revision, integration=None):
    if revision not in (LEGACY, CANONICAL):
        raise ValueError('Unknown core revision; no fallback')
    if revision == CANONICAL and integration is not None and integration not in ('native_mathematics', 'executable_se6', 'auto'):
        raise ValueError('Canonical revision requires an executable core integration')
    return revision

def check_sources(source_root=None):
    root = Path(source_root) if source_root else Path(__file__).parent / 'canonical_core_vendor/se_core'
    manifest = json.loads((root.parent / 'source-pins.json').read_bytes())
    if manifest != {'schema':'se6-competition-core-pins-v1', 'revision':CANONICAL, 'files':SOURCE_HASHES}:
        raise ValueError('Canonical source pin manifest mismatch')
    for name, expected in SOURCE_HASHES.items():
        data = (root / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError('Canonical source mismatch: ' + name)
        for node in ast.walk(ast.parse(data)):
            if isinstance(node, ast.ImportFrom) and node.level:
                if node.level != 1 or node.module not in ('kernel', 'mathematics', 'realization'):
                    raise ValueError('Unpinned canonical dependency')
    return root.resolve()

def load_core():
    root = check_sources()
    api = importlib.import_module('src.workbench.canonical_core_vendor.se_core')
    for module in ('kernel', 'mathematics', 'realization'):
        loaded = importlib.import_module(api.__name__ + '.' + module)
        if Path(loaded.__file__).resolve() != root / (module + '.py'):
            raise ValueError('Canonical import escaped pinned namespace')
    if Path(api.__file__).resolve() != root / '__init__.py':
        raise ValueError('Canonical package import mismatch')
    return api

def verify_traces(api, engine, records):
    """Rebuild immutable traces; the core independently replays each receipt."""
    realization = importlib.import_module(api.__name__ + '.realization')
    if not isinstance(records, list) or len(records) != len(engine.receipts):
        raise ValueError('Canonical trace/receipt count mismatch')
    for record, receipt in zip(records, engine.receipts):
        try:
            stages = []
            for row in record['stages']:
                values = {f.name: row[f.name] for f in fields(realization.RealizationStage)}
                values['evidence_refs'] = tuple(values['evidence_refs'])
                stages.append(realization.RealizationStage(**values))
            values = {f.name: record[f.name] for f in fields(realization.RealizationTrace)}
            values['stages'] = tuple(stages)
            trace = realization.RealizationTrace(**values)
            # Includes hashes, stage links, decoded projections and exact field set.
            if json.loads(json.dumps(trace.to_record())) != record or trace.receipt_hash != receipt.receipt_hash:
                raise ValueError('Canonical trace binding mismatch')
            if not realization.verify_realization(engine, trace):
                raise ValueError('Canonical trace replay mismatch')
        except (KeyError, TypeError) as exc:
            raise ValueError('Malformed canonical trace') from exc
