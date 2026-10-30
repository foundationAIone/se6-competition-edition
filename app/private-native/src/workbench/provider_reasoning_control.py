"""Fixed explicit Nebius reasoning profiles; provider enforcement is not established.

This is the documented generic Nebius Chat Completions field, not NVIDIA NIM
template kwargs. Historical diagnostic/evaluation controls retain their scopes.
The new complete pair also uses documented generic JSON-object formatting;
model-specific enforcement needs a separately authorized response. No calls run here.
"""
MODEL = 'nvidia/nemotron-3-super-120b-a12b'
PROVIDER = 'Nebius Token Factory'
NONE_PROBE = 'NEBIUS_NEMOTRON_NONE_PROBE_V1'
COMPLETE_PAIR = 'NEBIUS_NEMOTRON_V11_COMPLETE_PAIR_V1'
COMPLETE_PAIR_TOKENS = 2048
MAX_COMPLETION_TOKENS = 384
API_REFERENCE = 'https://docs.tokenfactory.nebius.com/api-reference/inference/create-chat-completion'
NVIDIA_REFERENCE = 'https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3-super-120b-a12b-infer'


def complete_pair_contract():
    return {'id': COMPLETE_PAIR, 'new_sessions_only': True,
            'provider': PROVIDER, 'model': MODEL, 'temperature': 0,
            'maximum_completion_tokens': COMPLETE_PAIR_TOKENS,
            'maximum_final_content_bytes': 32768,
            'provider_fields': {'reasoning_effort': 'none', 'response_format': {'type': 'json_object'}},
            'serialization': 'DOCUMENTED_GENERIC_API_FIELDS',
            'model_specific_support': 'LIVE_UNVERIFIED', 'live_enforcement': 'UNVERIFIED',
            'acceptance': 'STOP_SINGLE_FINAL_JSON_OBJECT; reported reasoning must be zero, missing remains unknown',
            'separate_reasoning_budget': 'NOT_REQUESTED',
            'final_token_reservation': 'NOT_GUARANTEED',
            'scope': 'ONE_NEW_MATCHED_PAIR_ONLY; separate exact capped authorization required',
            'documentation': [API_REFERENCE, NVIDIA_REFERENCE]}


def probe_contract():
    return {'id': NONE_PROBE, 'new_sessions_only': True,
            'provider': PROVIDER, 'model': MODEL,
            'provider_fields': {'reasoning_effort': 'none'},
            'serialization': 'DOCUMENTED_GENERIC_API_FIELD',
            'model_specific_support': 'PROBE_REQUIRED',
            'live_enforcement': 'UNVERIFIED',
            'maximum_completion_tokens': MAX_COMPLETION_TOKENS,
            'scope': 'ONE_SHORT_PAIRED_COMPLETION_DIAGNOSTIC_ONLY',
            'separate_reasoning_budget': 'UNVERIFIED',
            'final_token_reservation': 'UNVERIFIED',
            'documentation': [API_REFERENCE, NVIDIA_REFERENCE]}


def provider_fields(settings):
    """No arbitrary provider options or silently ignored incompatible control."""
    control = settings.provider_reasoning_control
    if control is None:
        return {}
    from .linear_evaluation_profile import CONTROL as LINEAR_EVAL
    from .successor_evaluation_profile import CONTROL as SUCCESSOR, MAX_COMPLETION_TOKENS as SUCCESSOR_TOKENS
    if not isinstance(control, str) or control not in (NONE_PROBE, LINEAR_EVAL, SUCCESSOR, COMPLETE_PAIR):
        raise ValueError('Unknown provider reasoning control; no fallback')
    if settings.model != MODEL or settings.provider != PROVIDER:
        raise ValueError('None probe requires Nemotron 3 Super on the Nebius adapter')
    if control == COMPLETE_PAIR:
        if (settings.temperature != 0 or settings.temperature is None or
                isinstance(settings.temperature, bool) or
                settings.max_output_tokens != COMPLETE_PAIR_TOKENS or
                settings.reasoning_effort is not None or settings.response_policy is not None):
            raise ValueError('Complete pair requires exact Nebius Super temperature 0, 2048 completion tokens and no conflicting policy')
        return {'reasoning_effort': 'none', 'response_format': {'type': 'json_object'}}
    required_tokens = SUCCESSOR_TOKENS if control == SUCCESSOR else MAX_COMPLETION_TOKENS
    if (settings.max_output_tokens != required_tokens or
            settings.reasoning_effort is not None or settings.response_policy is not None):
        if control == SUCCESSOR:
            raise ValueError('Successor requires exactly 1024 completion tokens and no conflicting effort/budget policy')
        raise ValueError('None probe requires exactly 384 completion tokens and no conflicting effort/budget policy')
    return {'reasoning_effort': 'none'}


def validate_session(settings):
    controls = [model.provider_reasoning_control for model in (settings.pair.se6, settings.pair.baseline)]
    if not any(control is not None for control in controls):
        return
    from .linear_evaluation_profile import CONTROL as LINEAR_EVAL, INPUT_BYTES
    from .successor_evaluation_profile import CONTROL as SUCCESSOR
    if COMPLETE_PAIR in controls:
        if (controls != [COMPLETE_PAIR, COMPLETE_PAIR] or settings.pair.mode != 'matched' or
                settings.pair.se6 != settings.pair.baseline or settings.reasoning_directive_preset != 'DEFAULT' or
                settings.integration != 'auto' or settings.core_revision != 'canonical-realization-v1' or
                settings.context_policy != 'audit_v3' or settings.workflow != 'single' or
                settings.baseline_workflow != 'direct' or settings.limits.rounds_per_task != 1 or
                settings.limits.calls_per_task != 2 or settings.limits.output_reservation_per_task != 4096 or
                settings.limits.input_bytes_per_task != 49152 or settings.limits.active_tasks != 1 or
                settings.limits.active_workers != 2):
            raise ValueError('Complete pair requires exact matched canonical AUTO one-pair budgets; dedicated authorization remains mandatory')
        for model in (settings.pair.se6, settings.pair.baseline):
            provider_fields(model)
        return
    if SUCCESSOR in controls:
        # Dashboard setting never grants campaign readiness. Dedicated runner
        # admission and durable six-call reservations are separately required.
        if (controls != [SUCCESSOR,SUCCESSOR] or settings.pair.mode != 'matched' or
                settings.pair.se6 != settings.pair.baseline or settings.pair.se6.temperature is not None or
                settings.reasoning_directive_preset != 'DEFAULT' or settings.integration != 'auto' or
                settings.core_revision != 'canonical-realization-v1' or settings.context_policy != 'audit_v3' or
                settings.workflow != 'single' or settings.baseline_workflow != 'direct' or
                settings.limits.rounds_per_task != 2 or settings.limits.calls_per_task != 4 or
                settings.limits.output_reservation_per_task != 4096 or
                settings.limits.input_bytes_per_task != 32768 or
                settings.limits.active_tasks != 1 or settings.limits.active_workers != 2):
            raise ValueError('Successor requires exact matched canonical AUTO task budgets; dedicated campaign gate remains mandatory')
        for model in (settings.pair.se6,settings.pair.baseline):
            provider_fields(model)
        return
    if controls == [LINEAR_EVAL, LINEAR_EVAL]:
        if (settings.pair.mode != 'matched' or settings.pair.se6 != settings.pair.baseline or
                settings.pair.se6.temperature is not None or
                settings.reasoning_directive_preset != 'DEFAULT' or settings.integration != 'auto' or
                settings.core_revision != 'canonical-realization-v1' or settings.context_policy != 'audit_v3' or
                settings.workflow != 'single' or settings.baseline_workflow != 'direct' or
                settings.limits.rounds_per_task != 1 or settings.limits.calls_per_task != 2 or
                settings.limits.output_reservation_per_task != 768 or
                settings.limits.input_bytes_per_task != INPUT_BYTES or
                settings.limits.active_tasks != 1 or settings.limits.active_workers != 2):
            raise ValueError('Linear evaluation requires its exact matched canonical AUTO one-round budgets')
        for model in (settings.pair.se6, settings.pair.baseline):
            provider_fields(model)
        return
    if (settings.pair.mode != 'matched' or settings.pair.se6 != settings.pair.baseline or
            controls != [NONE_PROBE, NONE_PROBE]):
        raise ValueError('None probe requires identical matched controls in both lanes')
    if (settings.reasoning_directive_preset != 'DEFAULT' or settings.integration != 'executable_se6' or
            settings.workflow != 'single' or settings.baseline_workflow != 'direct' or
            settings.limits.rounds_per_task != 1 or settings.limits.calls_per_task != 2):
        raise ValueError('None probe is one short structured paired diagnostic only; no math rounds, teams or combined directive')
    for model in (settings.pair.se6, settings.pair.baseline):
        provider_fields(model)


def control_contract(control):
    if control == COMPLETE_PAIR:
        return complete_pair_contract()
    from .successor_evaluation_profile import CONTROL as SUCCESSOR, contract as successor_contract
    if control == SUCCESSOR:
        return successor_contract()
    from .linear_evaluation_profile import CONTROL, contract
    return contract() if control == CONTROL else probe_contract()
