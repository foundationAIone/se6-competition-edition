"""Deterministic intake over existing pinned adapters, not another SE engine.

Planning is pure admission: no transition, file write or provider construction.
Only explicit paired submission may commit task-local operations and send calls.
"""
from copy import deepcopy
from dataclasses import asdict, replace
import hashlib
import json
import re
import time

from .config import Settings
from .core_revisions import CANONICAL, SOURCE_HASHES, check_sources, load_core, verify_traces
from .native_core import SCHEMA, parse_observation
from .provider_router import NEBIUS_MODEL, credential_status
from .reasoning_directive import DEFAULT
from .verified_mirror import TASK_SCHEMA
from .linear_admission import admit as admit_linear

AUTO = 'AUTO'
CONTRACT = 'se6-universal-auto-v1'
NATIVE_CONTRACT = 'se6-native-only-v1'
NATIVE_ROUTES = ('LINEAR_MATH', 'LINEAR_DERIVATION')
MAX_ACTIONS = 20
MAX_CONTEXT_BYTES = 16384


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def question(text):
    if not isinstance(text, str) or not text.strip() or len(text.encode('utf-8')) > 65536:
        raise ValueError('Provide a nonempty question of at most 64 KiB.')
    return text  # No trim, rewrite, fixture substitution or eval.


def session_settings(config):
    if config.pair.mode != 'matched' or config.workflow != 'single' or config.baseline_workflow != 'direct':
        raise ValueError('AUTO requires the configured matched pair and one worker per lane; save a profile once.')
    # Same model, inference settings and quotas. Never increase or switch them.
    return replace(config, integration='auto', core_revision=CANONICAL, context_policy='audit_v3')


def provider_status(config, records, credentials, text=None):
    model = config.pair.se6
    from .linear_evaluation_profile import CONTROL as LINEAR_EVAL, status as evaluation_status
    if model.provider_reasoning_control == LINEAR_EVAL:
        return evaluation_status(config, records, credentials, text)
    if not credentials:
        return {'status': 'BLOCKED', 'blocker': 'Configured provider credential unavailable; no provider switch.'}
    if (model.model == NEBIUS_MODEL or model.provider_reasoning_control or
            config.reasoning_directive_preset != DEFAULT or model.response_policy):
        return {'status': 'PROBE_REQUIRED', 'blocker': 'Configured Nemotron/reasoning controls are not validated for ordinary AUTO execution. Separate completion diagnostic required; no automatic diagnostic.'}
    # A profile is reusable only after a frozen complete matched pair, with this
    # exact inference configuration, has returned the requested model and usage.
    # Caller text and model self-reports cannot register a verified profile.
    for task in records:
        try:
            saved = Settings.parse(task['settings'])
            if saved.pair != config.pair or saved.reasoning_directive_preset != DEFAULT:
                continue
            for row in task['rounds']:
                if row['status'] != 'COMPLETE':
                    continue
                good = True
                for lane in ('se6', 'baseline'):
                    result = row['lanes'][lane]
                    from .models import model_identity_matches
                    agents = result['agents']
                    good &= (result['status'] == 'COMPLETE' and bool(result['response'].strip()) and
                             hashlib.sha256(result['response'].encode()).hexdigest() == result['response_sha256'] and
                             model_identity_matches(model.model, result['model_returned']) and
                             len(agents) == 1 and agents[0]['status'] == 'COMPLETE' and
                             agents[0].get('provider_request_attempted') is True and
                             model_identity_matches(model.model, agents[0].get('model_returned')) and
                             agents[0].get('result') == result['response'] and
                             isinstance(agents[0].get('usage'), dict) and
                             type(agents[0]['usage'].get('total_tokens')) is int and
                             agents[0]['usage']['total_tokens'] > 0)
                if good:
                    return {'status': 'VERIFIED_COMPLETION_PROFILE', 'blocker': None,
                            'evidence': {'task_id': task['id'], 'round_id': row['id']},
                            'scope': 'Historical completion at these settings; not future answer correctness.'}
        except (KeyError, TypeError, ValueError):
            continue
    return {'status': 'PROBE_REQUIRED', 'blocker': 'No frozen successful matched completion evidence for this configured profile. Separate owner-authorized diagnostic required.'}


def registry(integrations):
    core = integrations.canonical_core.capability()
    mirror = integrations.mirror.capabilities()
    math = integrations.canonical_mathematics.capability()
    rows = [
        ('canonical_realize', not core['blocker'], 'Validated structured ASSERT/RECALL/correction',
         'src.workbench.native_core.NativeCore.advance -> pinned SE.realize', 'Exact source pins, owner-supplied references',
         'Task-local retention only; not verified world facts or autonomous planning'),
        ('linear_math', not core['blocker'], 'Bounded single-variable Solve; or Given equations followed by Derive relationship between named variables; explicit corrections/retained derivations',
         'pinned SE.realize + SEMathObservation + project_retained', 'Validated public bounded integer equation; independent proof check',
         'At most four affine equalities/six variables; rational coefficients normalized exactly; native proof weights at most 16. Non-vacuous bounded integer verification required; host-only probe grids are not user-domain assumptions. No nonlinear/modular/full-system solver'),
        ('relational', not core['blocker'], 'Remember/Assert/Correct: SUBJECT priority/status/owner/location is VALUE; What is SUBJECT\'s PREDICATE?; up to 4 assertion lines',
         'src.workbench.native_core.NativeCore.advance', 'Exact question digest; OWNER_SUPPLIED input, explicit corrections',
         'Bounded grammar, task-local history; no ChatGPT sync or production memory'),
        ('verified_mirror', not mirror['blocker'], 'Verified Mirror: <registered case id or title>; exact existing fixture JSON also supported',
         'src.workbench.verified_mirror.MirrorFixtureAdapter.advance', 'Pinned independently audited disposable Entity exports',
         'Read-only fixture replay; not live production, arbitrary caller identity or model certification'),
        ('evidence_projection', not integrations.projection.blocker, 'Existing supported S1â€“S16 source packet only',
         'src.comparison.projection.EvidenceProjection.project', 'Frozen exact packet and projection source pins',
         'No general evidence parser; no substitution with the registered packet'),
        ('native_math_fixture', not math['blocker'], 'Existing exact two-round mathematical fixture JSON',
         'src.workbench.native_mathematics.NativeMathematics.advance', 'Pinned public challenge, canonical proof/checkpoint',
         'Existing bounded derivations only; no hidden solution or full-system solver'),
        ('business_arithmetic', not core['blocker'], 'Exact unit-cost/quantity products, revenue, expenses, gross contribution, budget comparisons and corrections',
         'src.workbench.business_arithmetic; deterministic HOST operations, not SE operators',
         'Canonical quantity proofs + provenance-bound OWNER_SUPPLIED unit-price/budget facts',
         'Bounded exact arithmetic, compatible dimensions/currencies only; no exchange rates, world verification, recommendations or code execution'),
        ('direct_model', True, 'Other bounded ordinary text, conceptual questions, code analysis',
         'WorkbenchService._messages -> existing provider_router transport', 'Credential presence + verified configured completion profile + explicit RUN',
         'No tools, web/shell/actions; output UNVERIFIED, no native SE advantage'),
        ('deterministic_verification', True, 'Frozen one-variable assignment; existing fixture scoring',
         'auto_intake.score_frozen / workbench.math_scoring', 'Raw response hashes frozen before evaluation',
         'Only applicable mathematical rules; no general answer judge or automatic winner')]
    return [{'id': key, 'connected': bool(connected), 'supported_inputs': inputs,
             'entrypoint': entry, 'required_evidence': evidence,
             'authority': 'Explicit local task submission; never production or external-action authority',
             'limits': {'local_actions_per_task': MAX_ACTIONS, 'question_bytes': 65536,
                        'context_bytes': MAX_CONTEXT_BYTES, 'model_calls_per_round': 2, 'retries': 0},
             'cannot_do': limitation} for key, connected, inputs, entry, evidence, limitation in rows]


def linear(text):
    match = re.fullmatch(r'\s*(Solve|Correct E1 to)\s+(.+?)\s+for integer ([A-Za-z][A-Za-z0-9_]{0,31}) (?:between (-?\d+) and (-?\d+)|in \[(-?\d+),\s*(-?\d+)\])\.?\s*', text, re.I)
    if not match:
        return None
    kind, equation, name, low, high, low2, high2 = match.groups()
    low, high = int(low or low2), int(high or high2)
    if len(equation) > 256 or equation.count('=') != 1:
        return None
    def side(value):
        value = re.sub(r'\s+', '', value)
        terms = re.findall(r'[+-]?[^+-]+', value)
        if ''.join(terms) != value:
            raise ValueError('Unsupported affine expression')
        coefficient, constant = 0, 0
        for term in terms:
            term_match = re.fullmatch(r'([+-]?)(\d*)\*?' + re.escape(name), term)
            if term_match:
                sign, magnitude = term_match.groups()
                coefficient += (-1 if sign == '-' else 1) * int(magnitude or 1)
            elif re.fullmatch(r'[+-]?\d+', term):
                constant += int(term)
            else:
                raise ValueError('Only one-variable integer affine expressions are supported')
        return coefficient, constant
    try:
        left, right = map(side, equation.split('='))
        api = load_core()
        variable = api.IntegerVariable(name, low, high)
        eq = api.LinearEquation.from_coefficients({name: left[0] - right[0]}, right[1] - left[1])
        # Validation is not deduction execution. Inconsistent/unsatisfiable
        # input remains a disclosed model-only task, never vacuous verification.
        if not any(eq.holds({name: n}) for n in range(low, high + 1)):
            return None
        return {'variable': asdict(variable), 'equation': asdict(eq), 'correction': kind.lower().startswith('correct')}
    except (ValueError, OverflowError):
        return None


def relation(text):
    recall = re.fullmatch(r"\s*What is ([\w -]{1,80})'s (priority|status|owner|location)\?\s*", text, re.I)
    ref = 'question:' + hashlib.sha256(text.encode()).hexdigest()
    if recall:
        return [dict(kind='RECALL', subject=recall[1], predicate=recall[2].lower(), value=None,
                     source='owner', evidence_refs=[ref], correction=False)]
    lines = text.strip().splitlines()
    if not 1 <= len(lines) <= 4:
        return None
    rows = []
    for line in lines:
        match = re.fullmatch(r'\s*(Remember|Assert|Correct): ([\w -]{1,80}) (priority|status|owner|location) is (.{1,1000}?)\.?\s*', line, re.I)
        if not match:
            return None
        rows.append(dict(kind='ASSERT', subject=match[2], predicate=match[3].lower(), value=match[4],
                         source='owner', evidence_refs=[ref], correction=match[1].lower() == 'correct'))
    return rows


class AutoIntake:
    def __init__(self, integrations):
        self.integrations = integrations

    def classify(self, text, checkpoint=None):
        question(text)
        check_sources()
        if checkpoint is not None:
            if (not isinstance(checkpoint, dict) or checkpoint.get('schema') != CONTRACT or
                    checkpoint.get('source_hashes') != SOURCE_HASHES or
                    checkpoint.get('checkpoint_hash') != digest({k: v for k, v in checkpoint.items() if k != 'checkpoint_hash'})):
                raise ValueError('AUTO checkpoint content/source binding mismatch')
        # Text analysis is allowed; requested external effects are not. This
        # intentionally narrow deny rule is disclosed and does not grant tools.
        if re.search(r'\b(?:search|browse|research|fetch|download) (?:the (?:web|internet)|https?://)|\b(?:run|execute) (?:a )?(?:shell|powershell|command)|\b(?:delete|reset) (?:files|database|entity)|\b(?:enable|grant|renew) (?:network|authority|event budget)', text, re.I):
            return {'route': 'UNSUPPORTED', 'blocker': 'Requested internet, shell or high-authority action is unavailable. No execution or authority expansion.', 'limitations': ['Text-only model analysis is available when explicitly requested instead.']}
        # Existing structured contracts remain accepted, without rewriting the
        # public question. Internal typed observations are distinct from it.
        if text.lstrip().startswith('{'):
            try:
                data = json.loads(text)
                if data.get('schema') == SCHEMA:
                    parsed = parse_observation(text)
                    return {'route': 'RELATIONAL', 'observations': [parsed['observation']], 'limitations': ['OWNER_SUPPLIED, not world truth.']}
                if data.get('schema') == TASK_SCHEMA:
                    self.integrations.mirror.validate_task(text, (checkpoint or {}).get('mirror'))
                    return {'route': 'VERIFIED_MIRROR', 'internal_input': text, 'limitations': ['Pinned test fixture; production not connected.']}
                if data.get('schema') == 'se6-native-math-task-v1':
                    self.integrations.canonical_mathematics.validate_task(text, (checkpoint or {}).get('fixture_math'))
                    return {'route': 'NATIVE_MATH_FIXTURE', 'internal_input': text, 'limitations': ['Bounded public derivations only.']}
            except (ValueError, TypeError, AttributeError):
                return {'route': 'DIRECT_MODEL', 'limitations': ['Malformed/unsupported structured input; no native operation.']}
        parsed = linear(text)
        if parsed:
            old_math = (checkpoint or {}).get('math')
            if old_math:
                api = load_core()
                engine = api.SE.restore(old_math['journal'], expected_head=old_math['head'])
                verify_traces(api, engine, old_math['traces'])
                variable = api.IntegerVariable(**parsed['variable'])
                equation = api.LinearEquation(tuple(tuple(t) for t in parsed['equation']['coefficients']), parsed['equation']['rhs'])
                if (not parsed['correction'] or engine.state.variables != (variable,) or
                        engine.state.current_constraints[0].equation == equation):
                    return {'route': 'UNSUPPORTED', 'blocker': 'This session needs an explicit changed E1 correction with unchanged domain. No replay or automatic NEW SESSION.', 'limitations': ['Use NEW SESSION for an unrelated equation.']}
            if parsed['correction'] and not (checkpoint or {}).get('math'):
                return {'route': 'UNSUPPORTED', 'blocker': 'Correct E1 requires this session\'s prior linear premise.', 'limitations': ['Start with Solve, then continue this session.']}
            return {'route': 'LINEAR_MATH', 'math': parsed, 'limitations': ['One-variable conditional deduction; local tooling advantage, not intrinsic model intelligence.']}
        if re.search(r'\bDerive\b', text, re.I):
            api = load_core()
            old = (checkpoint or {}).get('math')
            previous = api.SE.restore(old['journal'], expected_head=old['head']) if old else None
            if previous:
                verify_traces(api, previous, old['traces'])
            admitted = admit_linear(text, api, previous.state if previous else None,
                                    old.get('linear_policy', {'domain_origin': 'PUBLIC_INTEGER_BOUNDS'}) if old else None)
            if admitted:
                if 'unsupported' in admitted:
                    return {'route': 'DIRECT_MODEL', 'limitations': ['Native linear admission unavailable: ' + admitted['unsupported'],
                        'Model-only attempt; no native derivation or verified fact is claimed.']}
                return {'route': 'LINEAR_DERIVATION', 'math': admitted, 'limitations': [
                    'Exact row-certificate entailment from public equations only; no verified world facts or complete-system solution.',
                    'Unspecified domains use auxiliary host-only integer witness grids; no integer/range restriction on the original question is inferred.',
                    'Local checking assistance is a tooling advantage, not intrinsic model intelligence.']}
        observations = relation(text)
        if observations:
            return {'route': 'RELATIONAL', 'observations': observations, 'limitations': ['Task-local owner assertions remain OWNER_SUPPLIED.']}
        requested = re.fullmatch(r'\s*Verified Mirror: (.+?)\.?\s*', text, re.I)
        if requested:
            cap = self.integrations.mirror.capabilities()
            fixture = next((c for c in cap['fixtures'] if requested[1].casefold() in (c['id'].casefold(), c['title'].casefold())), None)
            if fixture:
                old = (checkpoint or {}).get('mirror')
                step = old['step'] + 1 if old and old['case_id'] == fixture['id'] else 0
                internal = json.dumps({'schema': TASK_SCHEMA, 'case_id': fixture['id'], 'step': step, 'question': text})
                self.integrations.mirror.validate_task(internal, old)
                return {'route': 'VERIFIED_MIRROR', 'internal_input': internal, 'limitations': ['Explicit requested fixture only; not current production state.']}
            return {'route': 'UNSUPPORTED', 'blocker': 'Unknown/unavailable verified Mirror fixture.', 'limitations': ['Select a registered fixture title or ID.']}
        if 'SOURCE S1' in text and not self.integrations.projection.blocker:
            try:
                context = self.integrations.projection.project(text)
                return {'route': 'EVIDENCE_PROJECTION', 'context': context, 'limitations': ['Existing exact packet projection; no native transition.']}
            except ValueError:
                pass
        return {'route': 'DIRECT_MODEL', 'limitations': ['No supported native parser/operation applies. Model-only text attempt; no native SE advantage, tools or deterministic general judge.']}

    def plan(self, text, settings, records, credentials, checkpoint=None):
        question(text)
        try:
            route = self.classify(text, checkpoint)
            local_blocker = route.get('blocker')
            required = route['math']['required_actions'] if route['route'] == 'LINEAR_DERIVATION' else 2 if route['route'] == 'LINEAR_MATH' else len(route.get('observations', []))
            if route['route'] == 'NATIVE_MATH_FIXTURE':
                required = 3 if (checkpoint or {}).get('fixture_math') else 4
            if (checkpoint or {}).get('local_actions_used', 0) + required > MAX_ACTIONS:
                local_blocker = 'Task-local SE action allowance exhausted; no automatic increase.'
        except ValueError as exc:
            route, local_blocker = {'route': 'UNSUPPORTED', 'limitations': [str(exc)]}, str(exc)
        try:
            frozen = session_settings(settings)
            provider = provider_status(frozen, records, credentials, text)
        except ValueError as exc:
            frozen, provider = settings, {'status': 'BLOCKED', 'blocker': str(exc)}
        blocker = local_blocker or provider['blocker']
        native_blocker = (local_blocker or self.integrations.canonical_core.blocker or
            (None if route['route'] in NATIVE_ROUTES else
             'Native-only solving supports verified linear deductions only. ' + '; '.join(route.get('limitations', []))))
        result = {'schema': CONTRACT, 'original_question': text,
                  'question_sha256': hashlib.sha256(text.encode()).hexdigest(), 'selection': route,
                  'settings': frozen.stored(), 'source_hashes': dict(SOURCE_HASHES),
                  'provider_profile': provider, 'ready': not bool(blocker), 'blocker': blocker,
                  'native_execution': {'contract': NATIVE_CONTRACT, 'ready': not bool(native_blocker),
                      'blocker': native_blocker, 'provider_calls': 0, 'output_tokens_reserved': 0,
                      'local_action_limit': MAX_ACTIONS, 'production_connected': False},
                  'native_advantage_comparison': route['route'] in ('LINEAR_MATH', 'LINEAR_DERIVATION', 'RELATIONAL', 'NATIVE_MATH_FIXTURE'),
                  'grounding_advantage': route['route'] in ('VERIFIED_MIRROR', 'EVIDENCE_PROJECTION'),
                  'resources': {'model': frozen.pair.se6.model, 'calls_per_round': 2,
                      'output_cap_per_lane': frozen.pair.se6.max_output_tokens, 'limits': asdict(frozen.limits),
                      'local_action_limit': MAX_ACTIONS, 'tools': [], 'retries': 0, 'provider_switch': False,
                      'cost': 'Not available; token reservations are not actual usage or currency.'},
                  'authorization': 'Explicit RUN required; PLAN sends zero provider requests.',
                  'plan_only': True, 'operators_executed': []}
        result['plan_sha256'] = digest(result)
        return result

    def native_result(self, selection, summary, checkpoint):
        """Present the actual verified deduction; never ask a model for an answer."""
        if selection['route'] not in NATIVE_ROUTES or not summary['receipts']:
            raise ValueError('No supported native mathematical result.')
        if any(r['boundary']['outcome'] != 'ALLOW' or not r['verification']['passed']
               for r in summary['receipts']):
            raise ValueError('Native receipts did not independently verify.')
        context = json.loads(summary['context'])
        api = load_core()
        retained = checkpoint['math']
        engine = api.SE.restore(retained['journal'], expected_head=retained['head'])
        verify_traces(api, engine, retained['traces'])
        if (context['head'] != retained['head'] or summary['receipts'][-1]['receipt_hash'] != retained['head']
                or not engine.state.active_deductions):
            raise ValueError('Native presentation/checkpoint binding mismatch.')
        deduction = engine.state.active_deductions[-1]
        if not deduction.verification.passed:
            raise ValueError('No verified active mathematical deduction.')
        equation = deduction.equation
        pivot = (selection['math']['proof_candidate']['pivot'] if selection['route'] == 'LINEAR_DERIVATION'
                 else selection['math']['variable']['name'])
        answer = equation.isolate(pivot)
        proof = asdict(deduction.proof)
        premises = {c.reference: c for c in engine.state.current_constraints}
        derivation = '\n'.join(f'{premises[ref].label}: {premises[ref].equation.display()}' for ref in proof['premise_refs'])
        derivation += '\nCombine: ' + ' + '.join(f"({weight}) × {premises[reference].label}" for weight, reference in
                                                zip(proof['weights'], proof['premise_refs']))
        return {'contract': NATIVE_CONTRACT, 'answer': answer,
            'derivation': f'{derivation}\nVerified equation: {equation.display()}\nIsolate {pivot}: {answer}',
            'deduction_reference': deduction.reference, 'proof': proof,
            'verification': asdict(deduction.verification), 'receipt_hashes': [r['receipt_hash'] for r in summary['receipts']],
            'checkpoint_hash': summary['checkpoint_hash'], 'head': context['head'],
            'scope': context['scope'], 'limitations': selection['limitations'],
            'provider_calls': 0, 'model_tokens': 0, 'production_connected': False,
            'local_seconds': summary['local_seconds'], 'complete_system_solved': False}

    def advance(self, task_id, round_id, text, checkpoint, selection):
        started = time.perf_counter()
        # Reclassify against committed state; never trust caller-supplied routing.
        if self.classify(text, checkpoint) != selection:
            raise ValueError('AUTO route/source binding mismatch')
        cp = deepcopy(checkpoint or {'schema': CONTRACT, 'task_id': task_id, 'source_hashes': dict(SOURCE_HASHES)})
        if cp.get('schema') != CONTRACT or cp.get('task_id') != task_id or cp.get('source_hashes') != SOURCE_HASHES:
            raise ValueError('AUTO checkpoint identity/source mismatch')
        route = selection['route']
        summary = {'route': route, 'question_sha256': hashlib.sha256(text.encode()).hexdigest(),
                   'source_hashes': dict(SOURCE_HASHES), 'limitations': selection['limitations'],
                   'production_connected': False, 'model_output_ingested': False,
                   'receipts': [], 'realization_traces': [], 'operators_executed': [], 'context': '',
                   'world_truth_verified': False}
        if route == 'RELATIONAL':
            details = []
            for observation in selection['observations']:
                internal = json.dumps({'schema': SCHEMA, 'observation': observation, 'question': text[:6000]})
                cp['relations'], cp['relation_head'], receipt, detail = self.integrations.canonical_core.advance(
                    task_id, round_id, internal, cp.get('relations'), cp.get('relation_head'), MAX_ACTIONS)
                summary['receipts'].append(receipt)
                summary['realization_traces'].extend(detail['realization_traces'])
                details.append({k: detail[k] for k in ('boundary', 'verification', 'conflict', 'observed_consequence', 'assimilation', 'receipt_hash', 'state_after_hash')})
            # Include retained state, not prior model text. No assertion becomes a
            # world-verified fact. Complete journals/traces remain local.
            summary['context'] = json.dumps({'scope': 'Actual canonical task-local relational result; assertions OWNER_SUPPLIED, not verified world facts.', 'results': details}, ensure_ascii=False)
        elif route in ('LINEAR_MATH', 'LINEAR_DERIVATION'):
            self._math(task_id, text, selection['math'], cp, summary)
        elif route == 'VERIFIED_MIRROR':
            cp['mirror'], detail = self.integrations.mirror.advance(task_id, round_id, selection['internal_input'], cp.get('mirror'))
            summary['context'] = self.integrations.mirror.model_context(detail, task_id)
            summary['evidence'] = {'source_export_sha256': detail['source_export_sha256'], 'checkpoint_hash': detail['checkpoint_hash']}
            # Hidden fixture rubric stays local, never copied into model context.
        elif route == 'NATIVE_MATH_FIXTURE':
            cp['fixture_math'], detail = self.integrations.canonical_mathematics.advance(task_id, round_id, selection['internal_input'], cp.get('fixture_math'))
            summary['context'] = self.integrations.canonical_mathematics.model_context(detail, task_id, cp['fixture_math'])
            summary['receipts'] = detail['receipts']
            summary['realization_traces'] = detail['realization_traces']
            summary['fixture_projection'] = detail
        elif route == 'EVIDENCE_PROJECTION':
            summary['context'] = selection['context']
        elif route != 'DIRECT_MODEL':
            raise ValueError('Unsupported AUTO operation; no provider call')
        if len(summary['context'].encode()) > MAX_CONTEXT_BYTES:
            raise ValueError('AUTO context cap exceeded; no silent truncation or provider call')
        summary['operators_executed'] = [{'stage': stage['name'], 'operator': stage['operator'],
                                         'outcome': stage['outcome'], 'stage_id': stage['stage_id']}
            for trace in summary['realization_traces'] for stage in trace['stages']]
        summary['local_operations'] = len(summary['receipts'])
        charged = sum(receipt.get('action') is not None for receipt in summary['receipts'])
        cp['local_actions_used'] = cp.get('local_actions_used', 0) + charged
        if cp['local_actions_used'] > MAX_ACTIONS:
            raise ValueError('Task-local action allowance exhausted; no checkpoint commit or provider call')
        summary['local_actions_charged'] = charged
        summary['local_seconds'] = time.perf_counter() - started
        summary['context_bytes'] = len(summary['context'].encode())
        summary['context_sha256'] = hashlib.sha256(summary['context'].encode()).hexdigest()
        cp['previous_checkpoint_hash'] = (checkpoint or {}).get('checkpoint_hash')
        cp.pop('checkpoint_hash', None)
        cp['checkpoint_hash'] = digest(cp)
        summary['checkpoint_hash'] = cp['checkpoint_hash']
        summary['previous_checkpoint_hash'] = cp['previous_checkpoint_hash']
        return cp, summary

    def _math(self, task_id, text, parsed, cp, summary):
        api = load_core()
        old = cp.get('math')
        identity = 'competition-auto-math:' + task_id
        engine = api.SE.restore(old['journal'], expected_head=old['head']) if old else api.SE(api.SEMathState(identity))
        if engine.state.identity != identity:
            raise ValueError('Mathematical checkpoint belongs to another session')
        traces = deepcopy(old['traces']) if old else []
        verify_traces(api, engine, traces)
        multiple = summary['route'] == 'LINEAR_DERIVATION'
        if multiple:
            variables = tuple(api.IntegerVariable(**v) for v in parsed['variables'])
            equations = tuple(api.EquationInput(r['label'], api.LinearEquation(
                tuple(tuple(t) for t in r['equation']['coefficients']), r['equation']['rhs'])) for r in parsed['equations'])
            if old and tuple(engine.state.variables) != variables:
                raise ValueError('Mathematical correction cannot change the retained domain')
            mode = parsed['mode']
        else:
            variable = api.IntegerVariable(**parsed['variable'])
            variables = (variable,)
            eq = api.LinearEquation(tuple(tuple(t) for t in parsed['equation']['coefficients']), parsed['equation']['rhs'])
            equations = (api.EquationInput('E1', eq),)
            if old and (not parsed['correction'] or tuple(engine.state.variables) != variables):
                raise ValueError('Existing mathematical state requires an explicit correction with unchanged domain; use NEW SESSION for another problem')
            mode = 'CORRECT' if old else 'MAP'
        host = dict(identity=identity, authorized=True, permissions=('MATH_MAP', 'MATH_CORRECT', 'MATH_DERIVE'),
                    integrity_valid=True, evidence_valid=True, max_actions=MAX_ACTIONS, risk=0,
                    max_risk=0, sensitive=False, human_approval_for=None)
        ref = ('question:' + hashlib.sha256(text.encode()).hexdigest(),)
        if multiple:
            ref += ('linear-admission:' + parsed['contract'], 'verification-domain:' + parsed['domain_origin'])
        def run(obs):
            result = engine.realize(engine.state, obs, host)
            if result.receipt is None or result.receipt.boundary.outcome != 'ALLOW' or not result.receipt.verification.passed:
                raise ValueError('Mathematical realization failed closed')
            record = json.loads(json.dumps(result.trace.to_record()))
            traces.append(record)
            summary['realization_traces'].append(record)
            summary['receipts'].append(result.receipt.to_record())
        if mode != 'DERIVE':
            incoming = tuple(e for e in equations if e.label == parsed['changed_label']) if multiple and mode == 'CORRECT' else equations
            run(api.SEMathObservation('MATH_CORRECT' if mode == 'CORRECT' else 'MATH_MAP', 'owner-task', ref,
                variables=() if old else variables, equations=incoming))
        if multiple:
            current = {c.label: c for c in engine.state.current_constraints}
            selected = tuple(current[parsed['equations'][i]['label']].reference for i in parsed['proof_candidate']['indexes'])
            proof = api.MathProof(selected, tuple(parsed['proof_candidate']['weights']))
            pivot = parsed['proof_candidate']['pivot']
        else:
            premise = engine.state.current_constraints[0]
            proof, pivot = api.MathProof((premise.reference,), (1,)), variable.name
        run(api.SEMathObservation('MATH_DERIVE', 'native-row-combination', ref,
            proof=proof, isolate_variable=pivot))
        verify_traces(api, engine, traces)
        journal, head = engine.dumps(), engine.receipts[-1].receipt_hash
        if api.SE.restore(journal, expected_head=head).state != engine.state:
            raise ValueError('Mathematical replay mismatch')
        cp['math'] = {'journal': journal, 'head': head, 'traces': traces}
        active = engine.state.active_deductions
        if multiple:
            cp['math']['linear_policy'] = {k: parsed[k] for k in ('contract', 'domain_origin', 'domain_is_public_assumption')}
            summary['public_linear_derivation'] = {k: parsed[k] for k in ('contract', 'requested_variables', 'domain_origin')}
            summary['context'] = json.dumps({'scope': 'Exact row-certificate algebraic entailment from the original public equalities; independently verified canonical deductions, not world facts.',
                'public_equalities': parsed['equations'], 'domain_origin': parsed['domain_origin'],
                'domain_is_public_assumption': parsed['domain_is_public_assumption'],
                'host_verification_policy': 'Auxiliary bounded integer consistency/witness check. No solution, integer restriction or range bound is inferred for an unspecified user domain.',
                'verified_relations': [{'equation': asdict(d.equation), 'isolated_relation': d.equation.isolate(d.isolate_variable) if d.isolate_variable else None,
                    'reference': d.reference, 'proof': asdict(d.proof), 'verification': asdict(d.verification)} for d in active],
                'invalidated_references': [d.reference for d in engine.state.invalidated_deductions],
                'head': head, 'state_hash': engine.state.state_hash, 'complete_system_solved': False}, ensure_ascii=False)
            return
        summary['public_linear'] = parsed
        summary['context'] = json.dumps({'scope': 'Verified conditional mathematical deduction from the exact public question; local tooling assistance.',
            'premise': asdict(premise), 'active_deductions': [asdict(d) for d in active],
            'projection': api.project_retained(engine.state, active[-1].reference),
            'invalidated_references': [d.reference for d in engine.state.invalidated_deductions],
            'head': head, 'state_hash': engine.state.state_hash}, ensure_ascii=False)


def score_frozen(task, root=None):
    """No general judge. Narrow equation checker, after raw outputs are frozen."""
    row = task['rounds'][-1]
    summary = row['auto_execution']
    parsed = summary.get('public_linear')
    scores = {}
    for lane in ('se6', 'baseline'):
        response = row['lanes'][lane]
        raw = response['response']
        if hashlib.sha256(raw.encode()).hexdigest() != response['response_sha256']:
            raise ValueError('Frozen AUTO response hash mismatch')
        score = {'status': 'UNASSESSABLE', 'correct': None, 'winner': None,
                 'proof_validity': None, 'unsupported_claims': None, 'limitations': 'No general answer or prose-proof evaluator.'}
        if response['status'] == 'COMPLETE' and raw.strip():
            if root is not None:
                from .math_scoring import _raw
                try:
                    _raw(root, task, row, lane)
                except (OSError, ValueError, KeyError):
                    score['limitations'] = 'Frozen raw capture mismatch; not assessable.'
                    scores[lane] = score
                    continue
            score['status'] = 'UNASSESSED'
            if parsed:
                name = parsed['variable']['name']
                matches = re.findall(r'^\s*' + re.escape(name) + r'\s*=\s*(-?\d+)\s*[.;]?\s*$', raw, re.M)
                if matches and len(set(matches)) == 1:
                    value = int(matches[0]); low = parsed['variable']['lower']; high = parsed['variable']['upper']
                    coefficient = dict(parsed['equation']['coefficients'])[name]
                    score.update(status='ASSIGNMENT_CHECKED', correct=low <= value <= high and coefficient * value == parsed['equation']['rhs'])
                score['limitations'] = 'Checks explicit single integer assignment against public equation/domain; prose proof and uniqueness claims unscored.'
        scores[lane] = score
    return {'schema': CONTRACT, 'scores': scores, 'winner': None}
