"""Fail-closed configuration and fixed state paths for SE6 LIVE LOOP v0.1.

Reading configuration is pure. No directory or database is created until an
authenticated, explicitly enabled controller opens the live-loop store.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from .production_state_paths import trusted_local_state_root

LIVE_LOOP_SCHEMA_VERSION = "se6-live-loop-v0.1-store-v1"
LIVE_LOOP_POLICY_VERSION = "se6-live-loop-v0.1-boundary-v1"
LIVE_LOOP_APPROVAL_POLICY_VERSION = "se6-live-loop-v0.1-approval-v1"
LIVE_LOOP_ADAPTER = "sandbox_python_repair"


class LiveLoopFeatureFlags(BaseModel):
    """Exact boolean flags; only the literal string ``1`` enables a flag."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    live_loop_enabled: bool = False
    canonical_authoritative: bool = False

    @property
    def authoritative_enabled(self) -> bool:
        return self.live_loop_enabled and self.canonical_authoritative


class LiveLoopLimits(BaseModel):
    """Hard v0.1 ceilings; the production controller binds the exact defaults."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    max_cycles: StrictInt = Field(default=3, ge=1, le=3)
    max_repairs_per_candidate: StrictInt = Field(default=2, ge=0, le=2)
    max_real_effect_adapters: StrictInt = Field(default=1, ge=0, le=1)
    max_model_calls: StrictInt = Field(default=3, ge=0, le=3)
    max_tokens: StrictInt = Field(default=12_000, ge=0, le=12_000)
    max_tool_calls: StrictInt = Field(default=4, ge=1, le=4)
    max_runtime_seconds: StrictInt = Field(default=30, ge=1, le=30)
    max_files: StrictInt = Field(default=3, ge=1, le=3)
    max_file_bytes: StrictInt = Field(default=64_000, ge=1, le=64_000)
    max_output_bytes: StrictInt = Field(default=30_000, ge=1, le=30_000)
    repeated_failure_pause_threshold: StrictInt = Field(default=2, ge=2, le=2)


def load_live_loop_feature_flags(
    environ: Mapping[str, str] | None = None,
) -> LiveLoopFeatureFlags:
    values = os.environ if environ is None else environ
    return LiveLoopFeatureFlags(
        live_loop_enabled=values.get("SE6_LIVE_LOOP_ENABLED") == "1",
        canonical_authoritative=values.get("SE6_CANONICAL_AUTHORITATIVE") == "1",
    )


_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_STATE_SUFFIX = Path("SE6Triad") / "live_loop" / "se6_live_loop_v0_1.sqlite3"


def default_live_loop_database_path(
    *,
    environ: Mapping[str, str] | None = None,
    platform_name: str | None = None,
    home: Path | None = None,
    repository_root: Path = _REPOSITORY_ROOT,
) -> Path:
    """Return the fixed OS-owned live-loop store path outside the repository."""

    root = trusted_local_state_root(
        environ=environ,
        platform_name=platform_name,
        home=home,
    )
    resolved = (root / _STATE_SUFFIX).expanduser().resolve(strict=False)
    repository = repository_root.resolve(strict=False)
    if resolved == repository or repository in resolved.parents:
        raise RuntimeError("live-loop state path must remain outside the repository")
    return resolved


__all__ = [
    "LIVE_LOOP_ADAPTER",
    "LIVE_LOOP_APPROVAL_POLICY_VERSION",
    "LIVE_LOOP_POLICY_VERSION",
    "LIVE_LOOP_SCHEMA_VERSION",
    "LiveLoopFeatureFlags",
    "LiveLoopLimits",
    "default_live_loop_database_path",
    "load_live_loop_feature_flags",
]
