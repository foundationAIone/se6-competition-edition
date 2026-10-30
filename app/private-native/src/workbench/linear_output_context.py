"""Future-only provider projection; never rewrite frozen native evidence.

Integrate only under a NEW preregistered campaign revision. The original V1
campaign and scorer remain unchanged, including its strict coefficient map.
"""
from copy import deepcopy
import json

OUTPUT_SCHEMA_NOTICE = (
    'Output schema version: se6-linear-certificate-output-v2. Return exactly one '
    'JSON object with relation, steps, execution_receipts, unique_solution, and '
    'world_facts_verified. Equation objects have exactly coefficients and rhs. '
    'coefficients MUST be a JSON OBJECT mapping each variable name to an integer '
    'or rational fraction string; an array of pairs is invalid. Shape example '
    '(illustrative only, not a problem answer): '
    '{"coefficients":{"example_variable":1},"rhs":0}. '
    'Each step has exactly id, weights, conclusion; weights is a JSON OBJECT '
    'mapping supplied public equation labels or earlier step ids to integers or '
    'rational fraction strings. Supply 1 to 8 steps. Each conclusion must equal '
    'the exact weighted sum of its named premises. execution_receipts is an '
    'array of hashes actually supplied to your lane, or empty; the final two '
    'fields are booleans. Native journal schemas are internal evidence schemas, '
    'not the required answer schema. No tools or external actions are available.'
)


def provider_linear_context(native_context):
    """Convert only affine equation coefficient records in a copied context.

    Proof weights and premise references retain canonical serialization. No
    scorer, rubric, private answer, provider, or mutable runtime is accessed.
    """
    source = json.loads(native_context)
    projected = deepcopy(source)

    def visit(value):
        if isinstance(value, dict):
            if set(value) == {'coefficients', 'rhs'}:
                terms = value['coefficients']
                if isinstance(terms, list):
                    if not terms or any(not isinstance(t, list) or len(t) != 2 or
                            not isinstance(t[0], str) for t in terms):
                        raise ValueError('Malformed internal affine equation')
                    if len({t[0] for t in terms}) != len(terms):
                        raise ValueError('Duplicate internal affine variable')
                    value['coefficients'] = dict(terms)
                elif not isinstance(terms, dict):
                    raise ValueError('Unsupported internal affine coefficients')
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(projected)
    return json.dumps({'provider_projection_schema':'se6-linear-provider-context-v2',
                      'equation_encoding':'coefficient_map',
                      'native_evidence_schema':'Canonical journal pair arrays are retained unchanged outside this provider projection.',
                      'evidence':projected}, ensure_ascii=False, allow_nan=False)
