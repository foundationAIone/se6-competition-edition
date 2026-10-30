"""Competition adapter for the exact verified native mathematical SE Core.

The dependency snapshot is byte-identical to SE6Triad's tested source. Existing
structured-core sessions keep their older pinned dependency. No evaluator,
answer key, production Entity, transport or model is imported here.
"""
from copy import deepcopy
from dataclasses import asdict
import hashlib
import importlib
import json
from pathlib import Path
import re
import time

from .native_core import _pairs
from .core_revisions import LEGACY, CANONICAL, SOURCE_HASHES as CANONICAL_PINS, validate_revision, load_core, check_sources, verify_traces

CONTRACT = 'se6-native-mathematics-competition-v1'
TASK_SCHEMA = 'se6-native-math-task-v1'
END_TO_END = 'math_end_to_end_v1'
CONTROLLED = 'math_mechanism_controlled_v1'
COMPACT = 'math_compact_end_to_end_v1'
SOURCE_HASHES = {
    'kernel.py': '36772351d6fda48dab1d7d9470c9a080c91f9fc401bba667d0d7ca53fb533bf4',
    'mathematics.py': '8e7ad101a65a43040c3f7e65c12ddbeeccfb6e947329e2f0940a75d60f57ff56',
    '__init__.py': 'be25b3311502fce970f13f7a936af672f7b754a104336dcb2d2a49c6f3f9a3c5',
}
PUBLIC_HASH = '47ae5e313a3cf9a5bf5cd04186118c8e8cd6a0c778e9bbc24fddb0ff076bcde7'
PREFIX = 'EXECUTED SE6 NATIVE MATHEMATICS V1\n'
CHECKING_PREFIX = 'SHARED STATELESS MATHEMATICAL CHECKING RESULTS\n'
COMMON_NOTICE = ('Both lanes have the identical public problem and their own answer history. '
    'No interactive tools, web, external computation, hidden answer or evaluator is available to the model. '
    'The original problem\'s no-tools sentence describes model permissions; the host may supply explicitly disclosed '
    'local mathematical preprocessing. End-to-end comparison gives this preprocessing only to LEFT. '
    'Mechanism-controlled comparison gives equivalent stateless mathematical checks to RIGHT. '
    'An end-to-end tooling benefit is not automatically superior intrinsic model reasoning.')


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


class NativeMathematics:
    def __init__(self, *, source_root=None, public_path=None, revision=LEGACY):
        self.revision = validate_revision(revision)
        self.source_hashes = dict(CANONICAL_PINS if revision == CANONICAL else SOURCE_HASHES)
        self.contract = "se6-canonical-mathematics-competition-v1" if revision == CANONICAL else CONTRACT
        root = Path(__file__).resolve().parents[2]
        self.source_root = Path(source_root) if source_root else Path(__file__).parent / ('canonical_core_vendor/se_core' if revision == CANONICAL else 'math_core_vendor/se_core')
        self.public_path = Path(public_path) if public_path else root / 'benchmarks/math_constraints_v1/public/problem.json'
        self.api = None
        self.blocker = None
        self.public = None
        try:
            self._check_sources()
            self.api = load_core() if self.revision == CANONICAL else importlib.import_module('src.workbench.math_core_vendor.se_core')
            self.public = json.loads(self.public_path.read_bytes())
            self.inputs = [encode({'schema': TASK_SCHEMA, 'round': step, 'problem': statement})
                           for step, statement in enumerate(self.public['statements'])]
        except (OSError, ValueError, ImportError, SyntaxError, KeyError) as error:
            self.blocker = 'Native mathematics unavailable (' + type(error).__name__ + '); no fallback.'

    def _check_sources(self):
        if self.revision == CANONICAL:
            check_sources(self.source_root)
        for name, expected in self.source_hashes.items():
            if hashlib.sha256((self.source_root / name).read_bytes()).hexdigest() != expected:
                raise ValueError('Native mathematical source mismatch: ' + name)
        if hashlib.sha256(self.public_path.read_bytes()).hexdigest() != PUBLIC_HASH:
            raise ValueError('Public mathematical fixture mismatch')

    def capability(self):
        return {'id': 'native_mathematics', 'label': 'SE6 NATIVE MATHEMATICS V1',
                'connected': self.blocker is None, 'blocker': self.blocker,
                'entrypoint': 'se_core.kernel.SE.realize' if self.revision == CANONICAL else 'se_core.kernel.SE.transition', 'source_hashes': deepcopy(self.source_hashes),
                'source': 'EXACT_VERIFIED_SE6TRIAD_DEPENDENCY_SNAPSHOT', 'production_connected': False,
                'operators': ['MAP', 'MIRROR', 'TRANSFORM', 'BOUNDARY', 'ASSIMILATE', 'PROJECT'] + (['FEEDBACK'] if self.revision == CANONICAL else []),
                'scope': 'Bounded linear deductions and dependency-aware correction; not a full mathematical solver.',
                'limitations': ['Modular/inequality givens remain model inputs; not evaluated by the native core',
                                'Model responses never certify or mutate retained deductions',
                                'End-to-end advantage includes local tooling; intrinsic model reasoning is not isolated'],
                'inputs': [] if self.blocker else list(self.inputs),
                'comparisons': [END_TO_END, CONTROLLED]}

    def validate_task(self, text, checkpoint=None):
        if self.blocker:
            raise ValueError(self.blocker)
        self._check_sources()
        if not isinstance(text, str) or not 0 < len(text.encode()) <= 65536:
            raise ValueError('Bounded native mathematics fixture input required')
        data = json.loads(text, object_pairs_hook=_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite input')))
        if (not isinstance(data, dict) or set(data) != {'schema', 'round', 'problem'}
                or data['schema'] != TASK_SCHEMA or type(data['round']) is not int
                or data['round'] not in (0, 1) or data['problem'] != self.public['statements'][data['round']]):
            raise ValueError('Only the unchanged prepared public mathematical challenge is supported')
        expected = 0 if checkpoint is None else checkpoint['step'] + 1
        if data['round'] != expected:
            raise ValueError('Native math requires step 0, then exactly step 1; no replay or skipping')
        return data

    def validate_checkpoint(self, checkpoint, task_id):
        if checkpoint is None:
            return None
        fields = {'schema', 'task_id', 'step', 'source_hashes', 'public_sha256', 'core_checkpoint', 'core_head', 'checkpoint_hash'}
        if self.revision == CANONICAL:
            fields |= {'core_revision', 'realization_traces', 'host_admissions'}
        if (not isinstance(checkpoint, dict) or set(checkpoint) != fields or checkpoint['schema'] != self.contract
                or checkpoint['task_id'] != task_id or type(checkpoint['step']) is not int
                or checkpoint['step'] not in (0, 1) or checkpoint['source_hashes'] != self.source_hashes
                or checkpoint['public_sha256'] != PUBLIC_HASH
                or digest({k: v for k, v in checkpoint.items() if k != 'checkpoint_hash'}) != checkpoint['checkpoint_hash']):
            raise ValueError('Native mathematical checkpoint binding mismatch')
        engine = self.api.SE.restore(checkpoint['core_checkpoint'], expected_head=checkpoint['core_head'])
        if engine.state.identity != 'competition-math-task:' + task_id or engine.state.actions_used != (4 if checkpoint['step'] == 0 else 7):
            raise ValueError('Native mathematical checkpoint session/state mismatch')
        if self.revision == CANONICAL:
            if checkpoint['core_revision'] != CANONICAL or checkpoint['host_admissions'] != [self._admission(task_id, step) for step in range(checkpoint['step'] + 1)]:
                raise ValueError('Canonical fixture attribution/revision mismatch')
            verify_traces(self.api, engine, checkpoint['realization_traces'])
        return engine

    def _admission(self, task_id, step):
        return {'schema': 'se6-host-admitted-fixture-v1', 'source_kind': 'HOST_ADMITTED',
            'epistemic_status': 'OWNER_SUPPLIED', 'task_id': task_id, 'step': step,
            'public_sha256': PUBLIC_HASH, 'problem_sha256': hashlib.sha256(self.inputs[step].encode()).hexdigest(),
            'world_truth_verified': False}

    def _equations(self, step):
        # Only genuinely supported non-modular equality givens enter native MAP.
        return tuple(self.api.EquationInput(row['id'], self.api.LinearEquation.from_coefficients(row['terms'], row['rhs']))
                     for row in self.public['rounds'][step]['constraints'] if row['op'] == 'eq' and 'mod' not in row)

    def advance(self, task_id, round_id, problem, checkpoint):
        if not all(isinstance(v, str) and re.fullmatch('[0-9a-f]{32}', v) for v in (task_id, round_id)):
            raise ValueError('Invalid mathematical task/round identity')
        started = time.perf_counter()
        self._check_sources()
        engine = self.validate_checkpoint(checkpoint, task_id)
        data = self.validate_task(problem, checkpoint)
        if engine is None:
            engine = self.api.SE(self.api.SEMathState('competition-math-task:' + task_id))
        before = engine.state
        traces = list(checkpoint['realization_traces']) if checkpoint and self.revision == CANONICAL else []
        admission = self._admission(task_id, data['round']) if self.revision == CANONICAL else None
        assumption_source = 'owner-task' if admission else 'public-problem'
        public_refs = ('public:' + PUBLIC_HASH + ':' + str(data['round']),)
        if admission:
            public_refs += ('host-admitted:' + digest(admission),)
        receipt_count = len(engine.receipts)
        host = dict(identity=engine.state.identity, authorized=True,
                    permissions=('MATH_MAP', 'MATH_DERIVE', 'MATH_CORRECT'), integrity_valid=True,
                    evidence_valid=True, max_actions=7, risk=0, max_risk=0, sensitive=False, human_approval_for=None)
        def run(observation):
            if self.revision == CANONICAL:
                result = engine.realize(engine.state, observation, host)
                receipt = result.receipt
                if receipt is None:
                    raise ValueError("Canonical mathematical realization rejected input")
                traces.append(json.loads(json.dumps(result.trace.to_record())))
            else:
                _, receipt = engine.transition(engine.state, observation, host)
            if receipt.boundary.outcome != 'ALLOW' or not receipt.verification.passed:
                raise ValueError('Native mathematical operation failed closed')
        if data['round'] == 0:
            public = self.public['rounds'][0]
            run(self.api.SEMathObservation('MATH_MAP', assumption_source, public_refs,
                tuple(self.api.IntegerVariable(v, *public['domain']) for v in sorted(public['variables'])), self._equations(0)))
            current = {c.label: c for c in engine.state.current_constraints}
            run(self.api.SEMathObservation('MATH_DERIVE', 'native-row-combination', ('public-C1-minus-C3',),
                proof=self.api.MathProof((current['C1'].reference, current['C3'].reference), (1, -1)), isolate_variable='b'))
        else:
            revised = next(e for e in self._equations(1) if e.label == self.public['change']['id'])
            run(self.api.SEMathObservation('MATH_CORRECT', assumption_source, public_refs, equations=(revised,)))
        # Relevant C2 consequences are recomputed after correction. Old records
        # remain in history, inactive; the independent C1/C3 relation is reused.
        current = {c.label: c for c in engine.state.current_constraints}
        run(self.api.SEMathObservation('MATH_DERIVE', 'native-row-combination', ('public-C2-isolation',),
            proof=self.api.MathProof((current['C2'].reference,), (1,)), isolate_variable='e'))
        parent = engine.state.active_deductions[-1]
        run(self.api.SEMathObservation('MATH_DERIVE', 'native-row-combination', ('public-C2-transitive',),
            proof=self.api.MathProof((parent.reference,), (2,))))
        core_checkpoint = engine.dumps()
        head = engine.receipts[-1].receipt_hash
        restored = self.api.SE.restore(core_checkpoint, expected_head=head)
        if restored.state != engine.state:
            raise ValueError('Mathematical checkpoint roundtrip failed')
        material = {'schema': self.contract, 'task_id': task_id, 'step': data['round'], 'source_hashes': deepcopy(self.source_hashes),
                    'public_sha256': PUBLIC_HASH, 'core_checkpoint': core_checkpoint, 'core_head': head}
        if self.revision == CANONICAL:
            verify_traces(self.api, engine, traces)
            material.update(core_revision=CANONICAL, realization_traces=traces,
                host_admissions=[self._admission(task_id, step) for step in range(data['round'] + 1)])
        next_checkpoint = {**material, 'checkpoint_hash': digest(material)}
        context = self._context(engine.state, data['round'])
        receipts = [r.to_record() for r in engine.receipts[receipt_count:]]
        summary = {'schema': self.contract, 'step': data['round'], 'source_hashes': deepcopy(self.source_hashes),
            'public_sha256': PUBLIC_HASH, 'state_before_hash': before.state_hash,
            'state_after_hash': engine.state.state_hash, 'core_head': head,
            'checkpoint_hash': next_checkpoint['checkpoint_hash'], 'checkpoint_roundtrip': 'PASS',
            'local_operations': len(receipts), 'local_elapsed_seconds': time.perf_counter() - started,
            'retained_deductions': [d.reference for d in engine.state.active_deductions],
            'invalidated_deductions': [d.reference for d in engine.state.invalidated_deductions],
            'context': context, 'context_sha256': hashlib.sha256(context.encode()).hexdigest(),
            'context_bytes': len(context.encode()), 'production_connected': False, 'world_truth_verified': False,
            'model_output_ingested': False, 'receipts': receipts}
        if self.revision == CANONICAL:
            summary.update(core_revision=CANONICAL, entrypoint="se_core.kernel.SE.realize",
                host_admission=admission, realization_traces=traces[receipt_count:])
        return next_checkpoint, summary

    def _context(self, state, step):
        history = {c.reference: c.label for c in state.constraint_history}
        history.update({d.reference: 'd' + str(i + 1) for i, d in enumerate(state.deduction_history)})
        deductions = []
        for deduction in state.active_deductions:
            deductions.append({'id': history[deduction.reference], 'reference': deduction.reference,
                'claim': {'terms': dict(deduction.equation.coefficients), 'op': 'eq', 'rhs': deduction.equation.rhs},
                'isolated': deduction.equation.isolate(deduction.isolate_variable) if deduction.isolate_variable else None,
                'status': 'VERIFIED_CONDITIONAL_MATHEMATICAL_DEDUCTION',
                'proof': asdict(deduction.proof), 'premise_labels': [history[ref] for ref in deduction.proof.premise_refs],
                'verification': asdict(deduction.verification),
                'projection': self.api.project_retained(state, deduction.reference)})
        result = {'schema': self.contract, 'scope': 'Mathematical entailment from versioned public task assumptions only; not physical truth.',
            'source_hashes': self.source_hashes, 'round': step, 'state_version': state.version, 'state_hash': state.state_hash,
            'current_constraints': [{'label': c.label, 'equation': asdict(c.equation), 'reference': c.reference,
                                     'previous_ref': c.previous_ref, 'status': 'OWNER_SUPPLIED'} for c in state.current_constraints],
            'deductions': deductions, 'invalidated': [{'id': history[d.reference], 'reference': d.reference,
                'premise_refs': d.proof.premise_refs, 'status': 'INVALIDATED_NOT_ACTIVE'} for d in state.invalidated_deductions],
            'unsupported_native_operations': ['modular conditions', 'inequality deduction', 'complete solution', 'uniqueness proof'],
            'complete_system_solved': False, 'model_output_assimilated': False}
        text = PREFIX + encode(result)
        if len(text.encode()) > 24576:
            raise ValueError('Bounded mathematical context exceeded; no silent truncation')
        return text

    def model_context(self, summary, task_id, checkpoint):
        engine = self._verified_model_engine(summary, task_id, checkpoint)
        if self.revision == CANONICAL:
            return self.compact_model_context(summary, task_id, checkpoint)
        return self._context(engine.state, checkpoint['step'])

    def _verified_model_engine(self, summary, task_id, checkpoint):
        self._check_sources()
        engine = self.validate_checkpoint(checkpoint, task_id)
        expected = self._context(engine.state, checkpoint['step'])
        if (summary['checkpoint_hash'] != checkpoint['checkpoint_hash'] or summary['context'] != expected
                or summary['context_sha256'] != hashlib.sha256(expected.encode()).hexdigest()):
            raise ValueError('Mathematical model-context evidence mismatch')
        return engine

    def compact_model_context(self, summary, task_id, checkpoint):
        """New-session projection only. Full original audit/checkpoint stays local."""
        engine = self._verified_model_engine(summary, task_id, checkpoint)
        state = engine.state
        evidence = {}
        aliases = {}
        def ref(identifier, label):
            if identifier not in aliases:
                alias = 'r' + str(len(aliases) + 1)
                aliases[identifier] = alias
                evidence[alias] = {'label': label, 'reference': identifier}
            return aliases[identifier]
        for index, premise in enumerate(state.constraint_history):
            ref(premise.reference, premise.label + '@' + str(index + 1))
        for index, deduction in enumerate(state.deduction_history):
            ref(deduction.reference, 'd' + str(index + 1))
        active = []
        for deduction in state.active_deductions:
            projection = self.api.project_retained(state, deduction.reference)
            bounds = {}
            for domain in projection['domains']:
                values = domain['supported_values']
                contiguous = bool(values) and tuple(range(values[0], values[-1] + 1)) == tuple(values)
                bounds[domain['variable']] = {'interval': [values[0], values[-1]]} if contiguous else {'values': list(values)}
            active.append({'ref': aliases[deduction.reference], 'equation': deduction.equation.display(),
                'isolated': deduction.equation.isolate(deduction.isolate_variable) if deduction.isolate_variable else None,
                'premises': [aliases[p] for p in deduction.proof.premise_refs], 'weights': deduction.proof.weights,
                'verified_check': ref(deduction.verification.reference, 'independent-check'),
                'checked_assignments': deduction.verification.cells_checked,
                'satisfying_assignments': deduction.verification.satisfying_assignments, 'supported_domains': bounds})
        context = {'schema': 'se6-compact-math-context-v1', 'round': checkpoint['step'],
            'scope': 'Verified conditional deductions from the shared public integer problem only; not a complete solution.',
            'inference_rule': 'INTEGER_LINEAR_COMBINATION_V1',
            'verification_method': 'INDEPENDENT_ROW_CERTIFICATE_AND_FINITE_ENTAILMENT_V1',
            'snapshot': {'version': state.version, 'hash': state.state_hash},
            'current_premises': {c.label: aliases[c.reference] for c in state.current_constraints},
            'active_deductions': active,
            'correction': {'changed_given': 'C2' if checkpoint['step'] else None,
                'current_rhs': next(c.equation.rhs for c in state.current_constraints if c.label == 'C2'),
                'invalidated_not_active': [{'ref': aliases[d.reference],
                    'premises': [aliases[p] for p in d.proof.premise_refs]}
                    for d in state.invalidated_deductions]},
            'evidence': evidence, 'complete_system_solved': False}
        if self.revision == CANONICAL:
            context.update(core_revision=CANONICAL, host_admission=self._admission(task_id, checkpoint["step"]))
        text = PREFIX + encode(context)
        if len(text.encode()) > 8192:
            raise ValueError('Compact mathematical context exceeds its bound; no truncation')
        return text

    def control_model_context(self, step, recorded):
        self._check_sources()
        expected, _ = self.stateless_checking_context(step)
        if recorded != expected:
            raise ValueError('Stateless control context mismatch; no arbitrary context or private state allowed')
        return expected

    def stateless_checking_context(self, step):
        """Mechanism control: reuse exact pure math rules/checker, no SE engine.

        Independently recomputes current facts from public givens. No retained
        LEFT state, receipt, correction history or response enters this path.
        """
        started = time.perf_counter()
        api = self.api
        public = self.public['rounds'][step]
        constraints = tuple(api.MathConstraint(e.label, e.equation, ('public-given:' + e.label,)) for e in self._equations(step))
        scratch = api.SEMathState('stateless-public-math-check', variables=tuple(api.IntegerVariable(v, *public['domain'])
                                  for v in sorted(public['variables'])), constraint_history=constraints)
        current = {c.label: c for c in constraints}
        operations = (((current['C1'], current['C3']), (1, -1), 'b'),
                      ((current['C2'],), (1,), 'e'), ((current['C2'],), (2,), None))
        facts = []
        for premises, weights, pivot in operations:
            proof = api.MathProof(tuple(p.reference for p in premises), weights)
            equation = api.transform_equations(premises, proof)
            check = api.verify_deduction(scratch, equation, proof)
            if not check.passed:
                raise ValueError('Shared stateless mathematical checking failed')
            projection = api.mathematics.project_equation(scratch.variables, equation, 'stateless-public-relation')
            facts.append({'claim': {'terms': dict(equation.coefficients), 'op': 'eq', 'rhs': equation.rhs},
                'isolated': equation.isolate(pivot) if pivot else None,
                'premises': [p.label for p in premises], 'weights': weights, 'rule': proof.rule,
                'verification_method': check.method, 'checked_assignments': check.cells_checked,
                'satisfying_assignments': check.satisfying_assignments, 'projection': projection})
        context = CHECKING_PREFIX + encode({'scope': 'Equivalent public mathematical checking resources; stateless recomputation.',
                                           'round': step, 'facts': facts, 'retained_state': False, 'complete_system_solved': False})
        return context, time.perf_counter() - started
