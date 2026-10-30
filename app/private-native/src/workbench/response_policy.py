"""Prepared bounded response policy; unsupported remote controls fail closed.

Nebius's generic API documents a combined completion cap. It does not establish
a separate reasoning limit or reserved final-content budget for this model.
This module never substitutes prompt instructions for an enforced token limit.
"""
from copy import deepcopy

POLICY_ID = 'nebius_math_bounded_v1'
MODEL = 'nvidia/nemotron-3-super-120b-a12b'
REASONING_LIMIT = 512
FINAL_ALLOWANCE = 2400
TOTAL_COMPLETION_LIMIT = REASONING_LIMIT + FINAL_ALLOWANCE
API_REFERENCE = 'https://docs.tokenfactory.nebius.com/api-reference/inference/create-chat-completion'
JSON_REFERENCE = 'https://docs.tokenfactory.nebius.com/ai-models-inference/json'

_CONTRACT = {
    'id': POLICY_ID, 'model': MODEL, 'new_sessions_only': True,
    'proposed_max_reasoning_tokens': REASONING_LIMIT,
    'proposed_final_answer_allowance': FINAL_ALLOWANCE,
    'proposed_total_completion_cap': TOTAL_COMPLETION_LIMIT,
    'reasoning_control': 'UNVERIFIED', 'provider_acceptance': 'NOT_TESTED',
    'capabilities': {'combined_completion_cap': 'DOCUMENTED', 'low_effort_reasoning': 'UNVERIFIED',
        'explicit_reasoning_budget': 'UNVERIFIED', 'reasoning_disabled': 'UNVERIFIED',
        'reserved_final_answer_tokens': 'UNVERIFIED', 'model_specific_json_enforcement': 'UNVERIFIED',
        'host_requires_nonempty_terminal_final_content': 'IMPLEMENTED'},
    'provider_parameter_mapping': None, 'ready_for_inference': False,
    'documentation': [API_REFERENCE, JSON_REFERENCE],
    'blocker': 'NEBIUS_REASONING_CONTROL_UNVERIFIED: model-specific budget/final-reservation mapping required',
}


def response_policy_contract():
    return deepcopy(_CONTRACT)


def validate_response_policy(settings, *, require_provider_support):
    if settings.response_policy is None:
        return
    if settings.response_policy != POLICY_ID or settings.model != MODEL:
        raise ValueError('Unsupported bounded response policy/model; no fallback')
    if settings.reasoning_effort is not None or settings.max_output_tokens != TOTAL_COMPLETION_LIMIT:
        raise ValueError('Bounded policy requires its exact combined cap and no conflicting effort control')
    if require_provider_support:
        # No documented model-specific mapping exists. Do not send guessed NIM
        # kwargs, silently ignore a limit, or manufacture provider acceptance.
        raise ValueError(_CONTRACT['blocker'])
