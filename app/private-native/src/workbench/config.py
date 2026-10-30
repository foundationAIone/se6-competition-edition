"""Work is bounded and configuration changes never submit provider requests."""
from __future__ import annotations
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from . import VERSION
from .models import ModelSettings, PairSettings, load_settings
from .storage import atomic_json
from .context import DEFAULT_POLICY, POLICIES
from .reasoning_directive import DEFAULT, validate_preset
from .provider_reasoning_control import validate_session
from .core_revisions import LEGACY, CANONICAL, validate_revision


@dataclass(frozen=True)
class Limits:
    active_tasks: int = 2
    active_workers: int = 4
    queued_tasks: int = 12
    rounds_per_task: int = 6
    calls_per_task: int = 24
    output_reservation_per_task: int = 393216
    input_bytes_per_task: int = 2097152
    timeout_seconds: int = 120
    round_deadline_seconds: int = 600

    def __post_init__(self):
        ranges = {"active_tasks": (1, 4), "active_workers": (1, 8), "queued_tasks": (1, 50),
                  "rounds_per_task": (1, 20), "calls_per_task": (2, 120),
                  "output_reservation_per_task": (512, 4000000),
                  "input_bytes_per_task": (4096, 16777216), "timeout_seconds": (5, 600),
                  "round_deadline_seconds": (10, 3600)}
        for key, (low, high) in ranges.items():
            value = getattr(self, key)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{key} must be an integer from {low} to {high}.")
        if self.timeout_seconds > self.round_deadline_seconds:
            raise ValueError("Provider timeout cannot exceed the round scheduling deadline.")


@dataclass(frozen=True)
class Settings:
    pair: PairSettings
    limits: Limits = Limits()
    workflow: str = "single"
    baseline_workflow: str = "direct"
    integration: str = "evidence_projection"
    context_policy: str = DEFAULT_POLICY
    reasoning_directive_preset: str = DEFAULT
    core_revision: str = LEGACY

    def __post_init__(self):
        validate_preset(self.reasoning_directive_preset, self.pair)
        validate_session(self)
        validate_revision(self.core_revision, self.integration)
        if self.workflow not in ("single", "team"):
            raise ValueError("LEFT workflow must be single or team.")
        if self.baseline_workflow not in ("direct", "team"):
            raise ValueError("Baseline must be direct or the explicitly selected ordinary team.")
        if self.integration not in ("evidence_projection", "executable_se6", "verified_mirror", "native_mathematics", "auto"):
            raise ValueError("Unknown integration; no fallback.")
        if self.context_policy not in POLICIES:
            raise ValueError("Unknown context policy; no fallback.")
        math_policies = ("math_end_to_end_v1", "math_mechanism_controlled_v1", "math_compact_end_to_end_v1")
        if (self.integration == "native_mathematics") != (self.context_policy in math_policies):
            raise ValueError("Native mathematics requires its explicit end-to-end or mechanism-controlled policy.")
        from .response_policy import POLICY_ID, validate_response_policy
        if self.context_policy == "math_compact_end_to_end_v1" and any(model.response_policy != POLICY_ID for model in (self.pair.se6, self.pair.baseline)):
            raise ValueError("New compact bounded sessions require the explicit matched response policy")
        for model in (self.pair.se6, self.pair.baseline):
            validate_response_policy(model, require_provider_support=True)
        if self.integration == "native_mathematics" and (self.pair.mode != "matched" or self.limits.rounds_per_task < 2 or self.limits.calls_per_task < 4
                or self.limits.output_reservation_per_task < 2 * self.required_output()):
            raise ValueError("Native mathematics requires matched settings and quotas for two rounds/four calls.")
        if self.context_policy == "compact_v1" and self.integration not in ("executable_se6", "verified_mirror"):
            raise ValueError("compact_v1 requires the isolated structured SE Core or Verified Mirror fixture.")
        if self.integration == "verified_mirror" and self.context_policy != "compact_v1":
            raise ValueError("Verified Mirror V1 requires bounded compact_v1 context.")
        if self.integration in ("executable_se6", "verified_mirror", "native_mathematics") and (self.workflow != "single" or self.baseline_workflow != "direct"):
            raise ValueError("Structured SE Core currently supports one model call per lane. Native multi-agent planning is not implemented.")
        if self.integration == "auto" and (self.pair.mode != "matched" or self.workflow != "single" or self.baseline_workflow != "direct" or self.core_revision != CANONICAL or self.context_policy != "audit_v3"):
            raise ValueError("AUTO requires matched single/direct canonical sessions with audit_v3; no settings escalation.")
        # The quota must cover a full initial pair before either lane is admitted.
        required = self.required_calls()
        if required > self.limits.calls_per_task:
            raise ValueError("Call limit cannot cover the selected workflows for both lanes.")
        if self.required_output() > self.limits.output_reservation_per_task:
            raise ValueError("Output reservation limit cannot cover one complete pair. Increase it explicitly.")

    def required_calls(self):
        return (3 if self.workflow == "team" else 1) + (3 if self.baseline_workflow == "team" else 1)

    def required_output(self):
        return ((3 if self.workflow == "team" else 1) * self.pair.se6.max_output_tokens +
                (3 if self.baseline_workflow == "team" else 1) * self.pair.baseline.max_output_tokens)

    def stored(self):
        result = {"pair": self.pair.stored(), "limits": asdict(self.limits), "workflow": self.workflow,
                "baseline_workflow": self.baseline_workflow, "integration": self.integration,
                "context_policy": self.context_policy}
        # Preserve default/legacy settings serialization. New task snapshots also
        # freeze the explicit default; existing snapshots are never migrated.
        if self.reasoning_directive_preset != DEFAULT:
            result["reasoning_directive_preset"] = self.reasoning_directive_preset
        if self.core_revision != LEGACY:
            result["core_revision"] = self.core_revision
        return result

    @classmethod
    def parse(cls, data):
        fields = {"pair", "limits", "workflow", "baseline_workflow", "integration"}
        optional = {"context_policy", "reasoning_directive_preset", "core_revision"}
        if not isinstance(data, dict) or not fields <= set(data) or set(data) - fields - optional:
            raise ValueError("Provide only the documented workbench settings.")
        if not isinstance(data["limits"], dict) or set(data["limits"]) != set(asdict(Limits())):
            raise ValueError("Provide the complete documented limit set.")
        return cls(PairSettings.from_change(data["pair"]), Limits(**data["limits"]),
                   data["workflow"], data["baseline_workflow"], data["integration"],
                   data.get("context_policy", DEFAULT_POLICY),
                   data.get("reasoning_directive_preset", DEFAULT), data.get("core_revision", LEGACY))


def read_settings(storage):
    path = Path(storage).parent / "workbench-settings.json"
    if path.exists():
        value = json.loads(path.read_text(encoding="utf-8"))
        if set(value) != {"schema", "settings"} or value["schema"] not in (VERSION, "se6-workbench-v3.0.0", "se6-workbench-v3.0.1", "se6-workbench-v3.1.0", "se6-workbench-v3.1.1"):
            raise ValueError("Unknown workbench settings file; defaults were not substituted.")
        return Settings.parse(value["settings"])
    # Import old choices without rewriting the original file or changing their cost allowance.
    return Settings(load_settings(Path(storage).parent / "comparison-settings.json"))


def write_settings(storage, settings):
    atomic_json(Path(storage).parent / "workbench-settings.json",
                {"schema": VERSION, "settings": settings.stored()})
