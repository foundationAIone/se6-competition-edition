"""Reproducible packaging of the dependency-awareness runtime's actual imports.

This packaging utility never runs a task, initializes a store or calls a model.
The original runtime, validators and pinned package are copied byte-for-byte.
"""
from pathlib import Path
import argparse, ast, hashlib, json, shutil

SEEDS = (
    'scripts.run_dependency_awareness', 'scripts.run_native_qpre_learning',
    'tests.test_entity_cognition_layer', 'tests.test_local_entity_runtime',
    'se666_core.reference_continuity', 'se666_core.grounded_native_input',
    'se666_core.grounded_canonical_context', 'se666_core.candidate_state_transition',
    'se666_core.qpre_native_learning', 'se666_core.native_reflection_consequences',
    'se666_core.native_situated_awareness', 'se666_core.native_expected_value',
    'se666_core.native_valuation_history', 'se666_core.grounded_canonical_selection',
    'se666_core.native_dependency_relation_v1',
    'se_core.kernel', 'se_core.mathematics', 'se_core.realization',
)


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def curate(mission, original):
    destination = Path(__file__).resolve().parent
    mission, original = Path(mission).resolve(strict=True), Path(original).resolve(strict=True)
    core = mission/'work/qpre-calibration-integration-20261026/dev'
    target = destination/'work/qpre-calibration-integration-20261026/dev'
    copied, pending, seen = {}, list(SEEDS), set()

    def local(module):
        if module.split('.')[0] not in {'se666_core', 'se_core', 'scripts', 'tests'}: return None
        plain = core.joinpath(*module.split('.')).with_suffix('.py')
        package = core.joinpath(*module.split('.'))/'__init__.py'
        return plain if plain.is_file() else package if package.is_file() else None

    def copy(source, relative, reason):
        source = source.resolve(strict=True)
        if source.is_symlink(): raise ValueError('SOURCE_SYMLINK')
        output = destination/relative
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists() and sha(output) != sha(source): raise ValueError('EXISTING_BUNDLE_DIFFERS:'+relative)
        shutil.copyfile(source, output)
        copied[relative] = dict(sha256=sha(output), source_sha256=sha(source), reason=reason)

    def imports(node):
        # Lazy branches for unused production/admission operations are not a
        # dependency of this fixed development scenario. Its actual Native
        # lifecycle lazy modules are explicitly declared above.
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)): return
        if isinstance(node, (ast.Import, ast.ImportFrom)): yield node
        for child in ast.iter_child_nodes(node): yield from imports(child)

    while pending:
        module = pending.pop()
        if module in seen: continue
        seen.add(module)
        source = local(module)
        if source is None: continue
        relative = source.relative_to(mission).as_posix()
        copy(source, relative, 'Actual runtime import dependency')
        for depth in range(1, len(module.split('.'))):
            package = '.'.join(module.split('.')[:depth])
            init = local(package)
            if init is not None: pending.append(package)
        package = module.split('.') if source.name == '__init__.py' else module.split('.')[:-1]
        for item in imports(ast.parse(source.read_text(encoding='utf-8-sig'))):
            if isinstance(item, ast.Import): pending.extend(alias.name for alias in item.names)
            else:
                base = package[:len(package)-item.level+1] if item.level else []
                base += item.module.split('.') if item.module else []
                name = '.'.join(base)
                if name: pending.append(name)
                for alias in item.names:
                    if alias.name != '*': pending.append('.'.join(base+[alias.name]))
    # These bytes are an explicit input to the unchanged source-pin function.
    copy(core/'tests/test_native_dependency_relation_v1.py',
        'work/qpre-calibration-integration-20261026/dev/tests/test_native_dependency_relation_v1.py',
        'Unchanged runner source identity contract (not executed as a test)')
    for package in ('scripts', 'tests'):
        init = target/package/'__init__.py'
        if not init.exists():
            init.write_text('"""Packaged dependency-awareness development namespace."""\n', encoding='utf-8')
            copied[init.relative_to(destination).as_posix()] = dict(sha256=sha(init), reason='Generated namespace only')
    for relative in (
        'work/codex-vscode-research/operational-realization/engine/typed_composer.py',
        'work/codex-vscode-research/alpha-continuation/engine/durable_attempts.py',
    ): copy(mission/relative, relative, 'Exact original independently pinned Native lifecycle dependency')
    package_relative = 'work/se6-reference-continuity-v010-448349319aa1/SE6_Reference_Continuity_v0.1.0'
    package = mission/package_relative
    manifest = json.loads((package/'PACKAGE_MANIFEST.json').read_bytes())
    for name in ['PACKAGE_MANIFEST.json', *manifest['files']]:
        copy(package/name, package_relative+'/'+name, 'Required by unchanged reference package integrity validator')
    archive = original/'SE6_AWARENESS_RESULT.zip'
    expected = 'ff712b8072d193a3761089da682bb10b53b6b844373642858a34b24ce8d140ed'
    if sha(archive) != expected: raise ValueError('FROZEN_AWARENESS_ARCHIVE_HASH')
    evidence = json.loads((original/'RESULT.json').read_bytes())
    comparisons = evidence['comparisons']
    counts = {key: sum(row.get('goal') is True for row in comparisons[key]) for key in comparisons}
    if any(counts.get(name) != 3 for name in ('retained', 'memory-ablated', 'conventional')):
        raise ValueError('FROZEN_AWARENESS_COUNTS')
    summary = dict(status='RECORDED_VERIFIED', mode='FROZEN_HISTORICAL_EVIDENCE',
        result=dict(retained=3, memory_ablated=3, conventional=3, total_per_arm=3,
            comparative_result='NOT_ESTABLISHED'), archive_sha256=expected,
        result_sha256=sha(original/'RESULT.json'),
        scope='Original frozen dependency-awareness development evidence; never a new live request.',
        limitations=['Three successful phases per arm tie; no measured SE6 advantage.',
            'Bounded authored dependency operator; not full equation, consciousness or general learning.',
            'Worker CPU/heap excludes child processes; total monetary cost is unknown.'])
    (destination/'frozen_evidence.json').write_text(json.dumps(summary, sort_keys=True, indent=2)+'\n', encoding='utf-8')
    result = dict(schema='se6-awareness-runtime-bundle-v1',
        roots_relative=True, source_revision='Installed October28 dependency-awareness development source',
        dependencies=['Python>=3.11', 'pydantic>=2,<3', 'pytest (unchanged test-helper genesis imports)'],
        lazy_import_seeds=list(SEEDS), files=copied,
        source_scope='Actual import closure plus files required by unchanged integrity validators; no production stores or credentials.',
        original_frozen_archive_sha256=expected)
    (destination/'BUNDLE_MANIFEST.json').write_text(json.dumps(result, sort_keys=True, indent=2)+'\n', encoding='utf-8')
    return dict(files=len(copied), bytes=sum((destination/name).stat().st_size for name in copied), archive_sha256=expected)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--mission', required=True); parser.add_argument('--original', required=True)
    values=parser.parse_args(); print(json.dumps(curate(values.mission, values.original), sort_keys=True))
