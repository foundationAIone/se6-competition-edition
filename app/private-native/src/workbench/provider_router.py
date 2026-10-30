"""Fixed provider routing; each model maps to one provider, never a fallback.

Nebius documentation checked 2026-10-05. No network operation on construction,
configuration, save or installation. Only explicit task submission sends calls.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import ssl
from urllib.request import Request, build_opener, ProxyHandler, HTTPSHandler
from urllib.error import HTTPError, URLError
from .transport import ResponsesTransport, ProviderFailure, NoRedirect
from .models import model_identity_matches
from .response_policy import validate_response_policy
from .provider_reasoning_control import provider_fields

NEBIUS_MODEL = 'nvidia/nemotron-3-super-120b-a12b'
NEBIUS_ENDPOINT = 'https://api.tokenfactory.nebius.com/v1/chat/completions'


def credential_status(settings):
    key = 'NEBIUS_API_KEY' if settings.model == NEBIUS_MODEL else 'OPENAI_API_KEY'
    return bool(os.environ.get(key))


def payload_for(settings, body):
    validate_response_policy(settings, require_provider_support=True)
    if not isinstance(body, dict) or set(body) != {'input'}:
        raise ValueError('Only isolated input messages are accepted.')
    if settings.model != NEBIUS_MODEL:
        return {'input': body['input'], **settings.request_fields(), 'store': False}
    if not isinstance(body['input'], list) or not body['input']:
        raise ValueError('Nebius input must be a nonempty message list.')
    messages = []
    for item in body['input']:
        if (not isinstance(item, dict) or set(item) != {'role', 'content'} or
            item['role'] not in ('developer', 'system', 'user', 'assistant') or not isinstance(item['content'], str)):
            raise ValueError('Unsupported message shape; tools and shared conversations are disabled.')
        messages.append({'role': 'system' if item['role'] == 'developer' else item['role'], 'content': item['content']})
    result = {'model': NEBIUS_MODEL, 'messages': messages, 'max_tokens': settings.max_output_tokens, 'stream': False}
    if settings.temperature is not None:
        result['temperature'] = settings.temperature
    result.update(provider_fields(settings))
    # No OpenAI-specific reasoning/store fields or guessed template kwargs.
    # An explicit none probe requests a generic documented field; enforcement is unverified.
    return result


def payload_bytes(settings, body):
    return json.dumps(payload_for(settings, body), ensure_ascii=False, allow_nan=False).encode('utf-8')


class NebiusTransport:
    endpoint = NEBIUS_ENDPOINT

    def __init__(self, settings, *, opener=None):
        if settings.model != NEBIUS_MODEL:
            raise ValueError('Model is not mapped to this provider.')
        self.settings, self.opener = settings, opener

    def request(self, body, directory, timeout):
        raw_request = payload_bytes(self.settings, body)
        if not credential_status(self.settings):
            raise ProviderFailure('NEBIUS_API_KEY is not present in the server process.', uncertain=False)
        if len(raw_request) > 2097152:
            raise ProviderFailure('Request exceeds the local 2 MiB limit.', uncertain=False)
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / 'request.json').open('xb') as stream:
            stream.write(raw_request)
        # Intent captured before send. Existing intents are never overwritten/retried.
        req = Request(self.endpoint, data=raw_request, method='POST', headers={
            'Authorization': 'Bearer ' + os.environ['NEBIUS_API_KEY'], 'Content-Type': 'application/json'})
        opener = self.opener or build_opener(ProxyHandler({}), NoRedirect(), HTTPSHandler(context=ssl.create_default_context()))
        try:
            with opener.open(req, timeout=timeout) as response:
                raw = response.read(4194305)
        except HTTPError as exc:
            raise ProviderFailure(f'Nebius HTTP {exc.code}; no retry or provider fallback. Access/billing not inferred.') from exc
        except (URLError, OSError, TimeoutError) as exc:
            raise ProviderFailure('Nebius outcome uncertain (' + type(exc).__name__ + '); no retry.') from exc
        with (directory / 'provider.json').open('xb') as stream:
            stream.write(raw)
        if len(raw) > 4194304:
            raise ProviderFailure('Provider payload exceeds 4 MiB; available bytes retained.')
        try:
            result = parse_nebius_completion(raw, self.settings.model,
                provider_reasoning_control=self.settings.provider_reasoning_control)
        except ProviderFailure as error:
            if error.text:
                with (directory / 'returned-text.txt').open('xb') as stream:
                    stream.write(error.text.encode('utf-8'))
            raise
        with (directory / 'returned-text.txt').open('xb') as stream:
            stream.write(result['text'].encode('utf-8'))
        return result


def completion_token_counts(usage):
    """Provider-reported counts only; unavailable/mismatched values stay null."""
    completion = usage.get('completion_tokens') if isinstance(usage, dict) else None
    details = usage.get('completion_tokens_details') if isinstance(usage, dict) else None
    reasoning = details.get('reasoning_tokens') if isinstance(details, dict) else None
    if type(completion) is not int or completion < 0:
        completion = None
    if type(reasoning) is not int or reasoning < 0 or completion is not None and reasoning > completion:
        reasoning = None
    return {'completion_tokens': completion, 'reasoning_tokens': reasoning,
            'reported_non_reasoning_completion_tokens': completion - reasoning
                if completion is not None and reasoning is not None else None}


def parse_nebius_completion(raw, expected_model, *, provider_reasoning_control=None):
    """Pure parser. Reasoning fields can never substitute for final content."""
    from .provider_reasoning_control import COMPLETE_PAIR, NONE_PROBE
    from .linear_evaluation_profile import CONTROL as LINEAR_EVAL
    from .successor_evaluation_profile import CONTROL as SUCCESSOR
    if provider_reasoning_control not in (None, NONE_PROBE, LINEAR_EVAL, SUCCESSOR, COMPLETE_PAIR):
        raise ProviderFailure('Unknown provider completion profile; no fallback.', uncertain=False)
    text, usage, model = '', None, None
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError('Expected object')
        usage, model = data.get('usage'), data.get('model')
        choices = data.get('choices')
        if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
            raise ValueError('Expected exactly one choice')
        choice = choices[0]; message = choice['message']
        if not isinstance(message, dict):
            raise ValueError('Expected message')
        content = message.get('content')
        refusal = message.get('refusal')
        if isinstance(content, str):
            text = content
        elif content is None and isinstance(refusal, str):
            text = refusal
        elif content is not None:
            raise ValueError('Expected string or absent final content')
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ProviderFailure('Unrecognized Nebius payload; raw bytes retained.', usage=usage, returned_model=model, uncertain=False) from exc
    fields = {'text': text, 'usage': usage, 'returned_model': model, 'uncertain': False}
    if not model_identity_matches(expected_model, model):
        raise ProviderFailure('Returned Nebius model does not match selection; no fallback.', **fields)
    if message.get('tool_calls') or message.get('function_call'):
        raise ProviderFailure('Model proposed a tool call; no tool executed.', **fields)
    if refusal:
        raise ProviderFailure('Provider refusal retained for review.', **fields)
    if choice.get('finish_reason') == 'length':
        counts = completion_token_counts(usage)
        if not text.strip() and counts['reasoning_tokens'] == counts['completion_tokens'] and (counts['completion_tokens'] or 0) > 0:
            reason = 'REASONING_EXHAUSTION_NO_FINAL_CONTENT'
        else:
            reason = 'COMPLETION_LIMIT_REACHED_PARTIAL_OR_MISSING_FINAL_CONTENT'
        raise ProviderFailure(reason + '; raw response retained; no retry.', **fields)
    if choice.get('finish_reason') != 'stop':
        raise ProviderFailure('Nebius completion is partial or nonterminal; text retained without retry.', **fields)
    if not text.strip():
        raise ProviderFailure('NO_FINAL_CONTENT; reasoning is not an answer; raw response retained.', **fields)
    accounting = completion_token_counts(usage)
    final_json = None
    if provider_reasoning_control == COMPLETE_PAIR:
        if expected_model != NEBIUS_MODEL:
            raise ProviderFailure('Complete pair requires the exact Nebius Super model; no fallback.', **fields)
        if len(text.encode('utf-8')) > 32768:
            raise ProviderFailure('COMPLETE_PAIR_FINAL_CONTENT_BYTE_CAP; raw bytes retained; no retry.', **fields)
        details = usage.get('completion_tokens_details') if isinstance(usage, dict) else None
        reported_reasoning = details.get('reasoning_tokens') if isinstance(details, dict) else None
        if details is not None and not isinstance(details, dict):
            raise ProviderFailure('COMPLETE_PAIR_REASONING_ACCOUNTING_INVALID; no continuation or retry.', **fields)
        if reported_reasoning is not None and (
                type(reported_reasoning) is not int or reported_reasoning < 0 or
                type(accounting['completion_tokens']) is not int or
                reported_reasoning > accounting['completion_tokens'] or reported_reasoning != 0):
            raise ProviderFailure('COMPLETE_PAIR_REASONING_ACCOUNTING_NOT_ZERO; no continuation or retry.', **fields)
        def unique(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise ValueError('Duplicate final JSON member')
                result[key] = value
            return result
        try:
            final_json = json.loads(text, object_pairs_hook=unique,
                parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite final JSON')))
            if not isinstance(final_json, dict):
                raise ValueError('Final JSON must be one object')
        except (ValueError, TypeError, RecursionError) as error:
            raise ProviderFailure('COMPLETE_PAIR_FINAL_JSON_INVALID; raw final content retained; no retry.', **fields) from error
    result = {'text': text, 'usage': usage, 'model': model, 'response_id': data.get('id'), 'text_parts': 1,
            'provider': 'Nebius Token Factory', 'completion_accounting': accounting}
    if provider_reasoning_control == COMPLETE_PAIR:
        result['complete_final_json'] = final_json
        result['reasoning_suppression'] = ('PROVIDER_REPORTED_ZERO_REASONING_TOKENS'
            if accounting['reasoning_tokens'] == 0 else 'UNKNOWN_NOT_REPORTED')
    return result


def make_transport(settings):
    return NebiusTransport(settings) if settings.model == NEBIUS_MODEL else ResponsesTransport(settings)
