"""Capability admission. An export reader is not an executable SE6 interface."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol
from .integration_modes import contract, require_mode
from .core_revisions import LEGACY, CANONICAL, validate_revision
from .native_core import NativeCore
from .verified_mirror import MirrorFixtureAdapter
from .native_mathematics import NativeMathematics, END_TO_END, CONTROLLED, COMPACT


class ExecutableSE6Contract(Protocol):
    """Integration requirements only. No assumed production import or transport.

    A future implementation must map these requirements to an inspected genuine
    core and test it with isolated storage. This Protocol itself is not that core.
    """
    def capabilities(self) -> dict: ...
    def validate_task(self, problem: str) -> None: ...
    def create_isolated_session(self, session_id: str, storage) -> object: ...
    def execute(self, session, problem: str, bounded_model_call, emit_event) -> dict: ...
    def snapshot(self, session) -> dict: ...
    def close(self, session) -> None: ...


class ReadOnlyStateContextContract(Protocol):
    """Verified-source adapter interface; no action or production authority.

    Its implementation must independently audit identity/state/provenance and
    preserve epistemic classes. Generated model text cannot provide that proof.
    It cannot derive action authority from a read-only snapshot. No implementation
    or production connection follows from this Protocol. Phase 2 implements it
    only for pinned sanitized exports from disposable canonical test stores.
    """
    contract_version: str
    def capabilities(self) -> dict: ...
    def validate_source_evidence(self, evidence) -> None: ...
    def read_verified_snapshot(self, isolated_session) -> dict: ...


class Integrations:
    def __init__(self, projection, native_core=None, mirror_adapter=None, math_adapter=None):
        self.projection = projection
        self.native_core = native_core
        self.mirror = mirror_adapter or MirrorFixtureAdapter()
        self.mathematics = math_adapter or NativeMathematics()
        self.canonical_core = NativeCore(revision=CANONICAL)
        self.canonical_mathematics = NativeMathematics(revision=CANONICAL)

    def core_for(self, revision=LEGACY):
        validate_revision(revision)
        return self.canonical_core if revision == CANONICAL else self.native_core

    def math_for(self, revision=LEGACY):
        validate_revision(revision)
        return self.canonical_mathematics if revision == CANONICAL else self.mathematics

    def versioned_contract(self):
        # Capability declarations only; no production import, endpoint or adapter.
        return contract()

    def mode_for(self, integration, policy):
        if integration == "auto":
            return "UNIVERSAL_AUTO_V1"
        if integration == "native_mathematics" and policy == COMPACT:
            return require_mode("NATIVE_MATHEMATICS_COMPACT_BOUNDED_V1").id
        if integration == "native_mathematics" and policy in (END_TO_END, CONTROLLED):
            return require_mode("NATIVE_MATHEMATICS_V1" if policy == END_TO_END else "NATIVE_MATHEMATICS_V1_MECHANISM_CONTROL").id
        if integration == "verified_mirror" and policy == "compact_v1":
            return require_mode("VERIFIED_MIRROR").id
        if integration == "executable_se6":
            return require_mode("COMPACT_STRUCTURED_CORE" if policy == "compact_v1" else "LEGACY_STRUCTURED_CORE").id
        if integration == "evidence_projection" and policy == "audit_v3":
            return "LEGACY_EVIDENCE_PROJECTION"
        raise ValueError("Integration mode NOT YET ENABLED; no fallback.")

    def capabilities(self, revision=LEGACY):
        core, mathematics = self.core_for(revision), self.math_for(revision)
        return [{"id": "evidence_projection", "label": "Evidence projection — limited",
                 "connected": not bool(self.projection.blocker), "blocker": self.projection.blocker,
                 "tasks": "Original supported S1–S16 packet; follow-ups use its historical projection, not fresh SE6 assimilation."},
                core.capability() if core is not None else
                {"id": "executable_se6", "label": "Executable SE6 test instance — NOT CONNECTED",
                 "connected": False,
                 "blocker": "The supplied public review bridge and export importer are non-executing. No genuine isolated SE6 task interface was supplied.",
                 "tasks": []}, self.mirror.capabilities(), mathematics.capability(),
                {"id":"auto", "label":"Universal AUTO V1", "connected":not bool(self.canonical_core.blocker),
                 "blocker":self.canonical_core.blocker, "tasks":"Bounded deterministic intake; provider readiness separately checked."}]

    def validate(self, integration, problem, revision=LEGACY):
        validate_revision(revision, integration)
        if integration == "native_mathematics":
            self.math_for(revision).validate_task(problem)
            return ""
        if integration == "verified_mirror":
            self.mirror.validate_task(problem)
            return ""
        if integration == "executable_se6" and self.core_for(revision) is not None:
            self.core_for(revision).validate(problem)
            return ""  # No projection is built; actual transition occurs at round execution.
        if integration != "evidence_projection":
            raise ValueError("EXECUTABLE_SE6_NOT_CONNECTED. No model request or silent projection fallback.")
        if self.projection.blocker:
            raise ValueError("Existing projection is unavailable: " + str(self.projection.blocker))
        # Exact original problem, not an invented parser of arbitrary text.
        return self.projection.project(problem)

    def wrap(self, lane, message, projection, first):
        if first:
            if lane == "se6":
                return self.projection.prefix_b + projection + self.projection.separator_b + message
            return self.projection.prefix_a + message
        # Both lanes receive the identical raw follow-up. Own histories preserve
        # their original contexts; the original projection is historical only.
        return message
