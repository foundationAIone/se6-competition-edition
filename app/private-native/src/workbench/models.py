"""Matched by default, independently selectable on request; no network on save."""
from __future__ import annotations
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
from .provider_reasoning_control import provider_fields, probe_contract
import re
import tempfile

UPDATE_VERSION = "paired-model-controls-v2"
LEGACY_VERSION = "shared-model-controls-v1"
PROFILES = (
    {"id": "nvidia/nemotron-3-super-120b-a12b", "label": "NVIDIA Nemotron 3 Super (Nebius)", "efforts": [], "temperature": True, "max_output_tokens": 32768,
     "provider": "Nebius Token Factory", "reasoning_policy": "Provider default; separate reasoning controls UNVERIFIED", "output_cap_scope": "Combined reasoning and final-output cap; no final-token reservation", "provider_reasoning_probe": probe_contract()},
    {"id": "gpt-6-astra", "label": "GPT-6 Astra", "efforts": ["low", "medium", "high", "xhigh", "max"], "temperature": False, "max_output_tokens": 128000},
    {"id": "gpt-6.1-sol", "label": "GPT-6.1 Sol", "efforts": ["low", "medium", "high", "xhigh", "max"], "temperature": False, "max_output_tokens": 128000},
    {"id": "gpt-6-luna", "label": "GPT-6 Luna", "efforts": ["none", "low", "medium", "high", "xhigh", "max"], "temperature": True, "max_output_tokens": 128000},
    {"id": "gpt-4.1-2025-04-14", "label": "GPT-4.1 (dated)", "efforts": [], "temperature": True, "max_output_tokens": 32768},
    {"id": "gpt-4.1-mini-2025-04-14", "label": "GPT-4.1 mini (dated)", "efforts": [], "temperature": True, "max_output_tokens": 32768},
)


def profile_for(model: str) -> dict:
    for row in PROFILES:
        if model == row["id"]:
            return row
    raise ValueError("Select a listed model; no fallback was used.")


@dataclass(frozen=True)
class ModelSettings:
    model: str = "gpt-4.1-mini-2025-04-14"
    temperature: float | None = 0
    max_output_tokens: int = 512
    reasoning_effort: str | None = None
    response_policy: str | None = None
    provider_reasoning_control: str | None = None

    def __post_init__(self):
        if not isinstance(self.model, str):
            raise ValueError("Model must be text.")
        profile = profile_for(self.model)
        if type(self.max_output_tokens) is not int or not 256 <= self.max_output_tokens <= profile["max_output_tokens"]:
            raise ValueError("Output token limit must be from 256 to " + str(profile["max_output_tokens"]) + " for this model.")
        if profile["efforts"]:
            if self.reasoning_effort not in profile["efforts"]:
                raise ValueError("Select a supported reasoning effort.")
        elif self.reasoning_effort is not None:
            raise ValueError("Reasoning effort is unsupported by this adapter for this model.")
        allow_temperature = profile["temperature"] and self.reasoning_effort in (None, "none")
        if self.temperature is not None:
            if not allow_temperature:
                raise ValueError("Omit temperature for this reasoning setting.")
            if isinstance(self.temperature, bool) or not isinstance(self.temperature, (int, float)):
                raise ValueError("Temperature must be a number or omitted.")
            if not math.isfinite(self.temperature) or not 0 <= self.temperature <= 2:
                raise ValueError("Temperature must be finite and between 0 and 2.")
        from .response_policy import validate_response_policy
        validate_response_policy(self, require_provider_support=False)
        provider_fields(self)

    @property
    def provider(self):
        return profile_for(self.model).get("provider", "OpenAI")

    def request_fields(self):
        from .response_policy import validate_response_policy
        validate_response_policy(self, require_provider_support=True)
        if self.provider_reasoning_control is not None:
            raise ValueError("Nebius none probe requires its Chat Completions serializer")
        value = {"model": self.model, "max_output_tokens": self.max_output_tokens}
        if self.temperature is not None:
            value["temperature"] = self.temperature
        if self.reasoning_effort is not None:
            value["reasoning"] = {"effort": self.reasoning_effort}
        return value

    def public(self):
        result = {"model": self.model, "temperature": self.temperature,
                "max_output_tokens": self.max_output_tokens, "provider": self.provider,
                "reasoning": {"effort": self.reasoning_effort} if self.reasoning_effort else None,
                "tools": [], "store": None if self.provider == "Nebius Token Factory" else False,
                "reasoning_policy": "Provider default (not overridden)" if self.provider == "Nebius Token Factory" else "Selected configuration",
                "automatic_retries": 0}
        if self.provider_reasoning_control is not None:
            from .provider_reasoning_control import control_contract
            result["provider_reasoning_control"] = control_contract(self.provider_reasoning_control)
            result["reasoning_policy"] = "Explicit reasoning_effort=none probe; model support PROBE_REQUIRED"
            from .linear_evaluation_profile import CONTROL
            if self.provider_reasoning_control == CONTROL:
                result["reasoning_policy"] = "Scoped effort-none evaluation; task reliability UNVERIFIED; general AUTO remains PROBE_REQUIRED"
            from .provider_reasoning_control import COMPLETE_PAIR
            if self.provider_reasoning_control == COMPLETE_PAIR:
                result["reasoning_policy"] = "New scoped effort-none JSON pair; request documented, actual enforcement UNVERIFIED until response accounting"
        if self.response_policy is not None:
            from .response_policy import response_policy_contract
            result["bounded_response_policy"] = response_policy_contract()
        return result

    def stored(self):
        result = {"model": self.model, "temperature": self.temperature,
                "max_output_tokens": self.max_output_tokens, "reasoning_effort": self.reasoning_effort}
        if self.response_policy is not None:
            result["response_policy"] = self.response_policy
        if self.provider_reasoning_control is not None:
            result["provider_reasoning_control"] = self.provider_reasoning_control
        return result

    @classmethod
    def from_change(cls, value):
        fields = {"model", "temperature", "max_output_tokens", "reasoning_effort"}
        if not isinstance(value, dict) or not fields <= set(value) or set(value) - fields - {"response_policy", "provider_reasoning_control"}:
            raise ValueError("Each lane accepts only model, temperature, output limit and reasoning effort.")
        return cls(**value)


@dataclass(frozen=True)
class PairSettings:
    mode: str
    se6: ModelSettings
    baseline: ModelSettings

    def __post_init__(self):
        if self.mode not in ("matched", "independent"):
            raise ValueError("Mode must be matched or independent.")
        if not isinstance(self.se6, ModelSettings) or not isinstance(self.baseline, ModelSettings):
            raise ValueError("Both lanes require validated settings.")
        if self.mode == "matched" and self.se6 != self.baseline:
            raise ValueError("Matched mode requires identical models AND generation settings.")

    @classmethod
    def from_change(cls, value):
        if not isinstance(value, dict) or set(value) != {"mode", "se6", "baseline"}:
            raise ValueError("Submit mode and the settings for both named lanes.")
        return cls(value["mode"], ModelSettings.from_change(value["se6"]), ModelSettings.from_change(value["baseline"]))

    def stored(self):
        return {"mode": self.mode, "se6": self.se6.stored(), "baseline": self.baseline.stored()}

    def public(self):
        return {"mode": self.mode, "se6": self.se6.public(), "baseline": self.baseline.public(),
                "same_requested_model": self.se6.model == self.baseline.model,
                "same_requested_settings": self.se6 == self.baseline}


def settings_path(storage: Path):
    return Path(storage).parent / "comparison-settings.json"


def load_settings(path: Path) -> PairSettings:
    if not path.exists():
        legacy = ModelSettings()  # Do not silently increase cost allowances.
        return PairSettings("matched", legacy, legacy)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or set(data) != {"schema", "settings"}:
            raise ValueError("Unknown settings file format.")
        if data["schema"] == LEGACY_VERSION:
            legacy = ModelSettings.from_change(data["settings"])
            return PairSettings("matched", legacy, legacy)
        if data["schema"] == UPDATE_VERSION:
            return PairSettings.from_change(data["settings"])
        raise ValueError("Unknown settings schema.")
    except (OSError, ValueError, TypeError) as exc:
        raise ValueError("Saved settings could not be loaded; no defaults substituted: " + str(exc)) from exc


def save_settings(path: Path, settings: PairSettings):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".comparison-settings-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump({"schema": UPDATE_VERSION, "settings": settings.stored()}, stream, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def model_identity_matches(requested, returned):
    if not isinstance(returned, str):
        return False
    if requested == returned:
        return True
    if requested in ("gpt-6-astra", "gpt-6.1-sol", "gpt-6-luna"):
        return re.fullmatch(re.escape(requested) + r"-\d{4}-\d{2}-\d{2}", returned) is not None
    return False
