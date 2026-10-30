"""Shared, local-only configuration. Saving settings never contacts a provider."""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import re
import tempfile

UPDATE_VERSION = "shared-model-controls-v1"
# Documented IDs, not a claim that this user's API project can access each model.
# Do not substitute a model silently when access or parameter validation fails.
PROFILES = (
    {"id": "gpt-6-astra", "label": "GPT-6 Astra", "efforts": ["low", "medium", "high", "xhigh", "max"], "temperature": False},
    {"id": "gpt-6.1-sol", "label": "GPT-6.1 Sol", "efforts": ["low", "medium", "high", "xhigh", "max"], "temperature": False},
    {"id": "gpt-6-luna", "label": "GPT-6 Luna", "efforts": ["none", "low", "medium", "high"], "temperature": True},
    {"id": "gpt-4.1-2025-04-14", "label": "GPT-4.1 (dated)", "efforts": [], "temperature": True},
    {"id": "gpt-4.1-mini-2025-04-14", "label": "GPT-4.1 mini (existing test model)", "efforts": [], "temperature": True},
)


def profile_for(model: str) -> dict:
    for row in PROFILES:
        if model == row["id"]:
            return row
    raise ValueError("Choose one of the documented models in this dashboard. No fallback was used.")


@dataclass(frozen=True)
class ModelSettings:
    model: str = "gpt-4.1-mini-2025-04-14"
    temperature: float | None = 0
    max_output_tokens: int = 512
    reasoning_effort: str | None = None

    def __post_init__(self):
        if not isinstance(self.model, str):
            raise ValueError("Model must be text.")
        profile = profile_for(self.model)
        if type(self.max_output_tokens) is not int or not 256 <= self.max_output_tokens <= 32768:
            raise ValueError("Choose a maximum output token limit from 256 to 32768.")
        if profile["efforts"]:
            if self.reasoning_effort not in profile["efforts"]:
                raise ValueError("Select a supported reasoning effort for this model.")
        elif self.reasoning_effort is not None:
            raise ValueError("This model profile does not accept a reasoning effort.")
        allow_temperature = profile["temperature"] and self.reasoning_effort in (None, "none")
        if self.temperature is not None:
            if not allow_temperature:
                raise ValueError("Omit temperature when using this reasoning configuration.")
            if isinstance(self.temperature, bool) or not isinstance(self.temperature, (int, float)):
                raise ValueError("Temperature must be a number or omitted.")
            if not math.isfinite(self.temperature) or not 0 <= self.temperature <= 2:
                raise ValueError("Temperature must be finite and between 0 and 2.")

    def request_fields(self) -> dict:
        fields = {"model": self.model, "max_output_tokens": self.max_output_tokens}
        if self.temperature is not None:
            fields["temperature"] = self.temperature
        if self.reasoning_effort is not None:
            fields["reasoning"] = {"effort": self.reasoning_effort}
        return fields

    def public(self) -> dict:
        return {"model": self.model, "temperature": self.temperature,
                "max_output_tokens": self.max_output_tokens, "provider": "OpenAI",
                "reasoning": ({"effort": self.reasoning_effort} if self.reasoning_effort else None),
                "tools": [], "store": False, "automatic_retries": 0}

    def stored(self) -> dict:
        return {"model": self.model, "temperature": self.temperature,
                "max_output_tokens": self.max_output_tokens, "reasoning_effort": self.reasoning_effort}

    @classmethod
    def from_change(cls, value):
        required = {"model", "temperature", "max_output_tokens", "reasoning_effort"}
        if not isinstance(value, dict) or set(value) != required:
            raise ValueError("Only shared model, temperature, token limit and reasoning effort may be changed.")
        return cls(**value)


def settings_path(storage: Path) -> Path:
    return Path(storage).parent / "comparison-settings.json"


def load_settings(path: Path) -> ModelSettings:
    if not path.exists():
        return ModelSettings()  # Preserve original defaults until the owner changes them.
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or set(data) != {"schema", "settings"} or data["schema"] != UPDATE_VERSION:
            raise ValueError("Unknown settings file format.")
        return ModelSettings.from_change(data["settings"])
    except (OSError, ValueError, TypeError) as exc:
        raise ValueError("Saved comparison settings could not be loaded; no defaults were substituted. " + str(exc)) from exc


def save_settings(path: Path, settings: ModelSettings) -> None:
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


def model_identity_matches(requested: str, returned: object) -> bool:
    if not isinstance(returned, str):
        return False
    if requested == returned:
        return True
    # Accept a dated resolution of a documented alias, not another model family.
    if requested in ("gpt-6-astra", "gpt-6.1-sol", "gpt-6-luna"):
        return re.fullmatch(re.escape(requested) + r"-\d{4}-\d{2}-\d{2}", returned) is not None
    return False
