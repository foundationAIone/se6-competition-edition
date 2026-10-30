"""Compatibility equation metadata and the canonical V6 contract pointer.

The short and compressed forms retained here support older CLI and kernel
surfaces.  They do not replace the normative notation and causal ordering in
``docs/SYMBOLIC_EQUATION_V6.md``.
"""

from __future__ import annotations

from typing import Any

CANONICAL_EQUATION_CONTRACT = "se6-symbolic-equation-v6.1.0"
CANONICAL_TOTAL_STATE = "Z_t = (X_t, Theta_t, M_t, E_t)"
CANONICAL_FULL_SIGNATURE = (
    "SE6_Triad(X_t, Theta_t, M_t, E_t, U_t, [{01*}]) "
    "-> (X_t+1, Theta_t+1, M_t+1)"
)
CANONICAL_RECURSIVE_CLOSURE = (
    "(X_t+1, Theta_t+1, M_t+1) -> "
    "SE6_Triad(X_t+1, Theta_t+1, M_t+1, E_t+1, U_t+1, [{01*}]) -> ..."
)
CANONICAL_FULL_OPERATOR_ORDER: tuple[str, ...] = (
    "C",
    "F_FoL",
    "D_substrate",
    "K_Merkabah",
    "T",
    "Q_QPRE",
    "S",
    "P",
    "Pi_B",
    "argmax_A_B",
    "World",
    "VerifyAssimilate",
    "I^-1_return",
    "R_renew",
)
CANONICAL_CONDUCT_PILLARS: tuple[str, ...] = (
    "AUTHENTICITY",
    "INTEGRITY",
    "RESPONSIBILITY",
    "ENRICHMENT",
)
CANONICAL_CONDUCT_INVARIANT = (
    "Conduct(a) = AUTHENTICITY and INTEGRITY and RESPONSIBILITY and ENRICHMENT"
)
CANONICAL_CAUSAL_DECOMPOSITION: tuple[str, ...] = (
    "C_t = Center(I_t, Z_t)",
    "Q_t, U_t = Classify(C_t, E_t, U_t-1)",
    "G_t = UniversalMap(C_t, Q_t)",
    "D_t = Unfold(G_t)",
    "H_t = PerspectiveMirrorInvert(D_t, Theta_t, E_t)",
    "R_t^poss = QPRE(H_t, U_t)",
    (
        "A_t^B = {a in Eligible(B_t, Z_t, R_t^poss, E_t, U_t) | "
        "Pi_B^eligibility(a)=ALLOW and Conduct(a)}"
    ),
    "a_t* = DeterministicSelect(A_t^B)",
    "O_t+1 = Observe(Execute(Pi_B^pre(a_t*))) or NO_OBSERVATION",
    "M~_t+1 = Retain(M_t) + VerifyAssimilate(O_t+1, E_t) - Revoked(M_t)",
    "Z~_t+1 = Update(Z_t, a_t*, O_t+1, M~_t+1, Theta~_t+1)",
    "Z_t+1 = Pi_B^commit(Z~_t+1)",
)

SE666_EQUATION: dict[str, Any] = {
    "name": "SE6Triad compatibility state transformation",
    "status": "COMPATIBILITY_NON_NORMATIVE",
    "canonical_contract": CANONICAL_EQUATION_CONTRACT,
    "form": (
        "SE6(I_t, X_t, M_t, E_t, R_t, B, V) → (A_t, O_t+1, M_t+1, X_t+1); "
        "SE6(I, X, B) → A + X′; "
        "X[t+1] = Π_B[X[t] ⊕ Assimilate(Classify(Mirror(Rotate(Map(Intention))))) ⊕ R[t]]"
    ),
    "where": {
        "I":      "Centered intention",
        "X":      "Current state",
        "B":      "Active boundary",
        "A":      "Authorized action",
        "X′":     "Proposed next coherent state",
        "Map":    "Flower-of-Life relationship mapping",
        "Rotate": "Merkabah perspective transformation",
        "Mirror": "Sphere-of-Mirrors reflection",
        "Classify": "Periodic classification",
        "R[t]":   "World feedback or result at time t",
        "M":      "Classified memory",
        "E":      "Available evidence and context",
        "R":      "Available resources, models, tools, accounts, and permissions",
        "V":      "Value function over benefit, cost, risk, dependency, and irreversibility",
        "Π_B":    "Master Boundary (truth + safety + law + consent + "
                  "privacy + authorization + coherence + responsibility + "
                  "future_benefit)",
    },
    "triad": {
        "inner": ["intention", "identity", "desire", "fear", "memory", "question"],
        "mirror": ["pattern", "opposite", "shadow", "risk", "value", "hidden_truth"],
        "world": ["truth", "law", "safety", "consent", "action", "feedback"],
    },
    "canonical_decisions": ["ALLOW", "PAUSE", "REPAIR", "REFUSE"],
    "runtime_decisions": ["allow", "pause", "needs_human_approval", "refuse"],
    "assimilation_principle": (
        "R(x) + U(x) + M(x,T_t) + ΔT(x) = A_revelation(x,t)"
    ),
}


def describe_equation() -> dict[str, object]:
    """Return compatibility metadata plus the normative contract pointer."""
    return {
        "name": SE666_EQUATION["name"],
        "status": SE666_EQUATION["status"],
        "canonical_contract": SE666_EQUATION["canonical_contract"],
        "canonical_total_state": CANONICAL_TOTAL_STATE,
        "canonical_full_signature": CANONICAL_FULL_SIGNATURE,
        "canonical_recursive_closure": CANONICAL_RECURSIVE_CLOSURE,
        "canonical_full_operator_order": list(CANONICAL_FULL_OPERATOR_ORDER),
        "canonical_conduct_pillars": list(CANONICAL_CONDUCT_PILLARS),
        "canonical_conduct_invariant": CANONICAL_CONDUCT_INVARIANT,
        "canonical_causal_decomposition": list(CANONICAL_CAUSAL_DECOMPOSITION),
        "form": SE666_EQUATION["form"],
        "where": dict(SE666_EQUATION["where"]),
        "triad": {k: list(v) for k, v in SE666_EQUATION["triad"].items()},
        "canonical_decisions": list(SE666_EQUATION["canonical_decisions"]),
        "runtime_decisions": list(SE666_EQUATION["runtime_decisions"]),
        "assimilation_principle": SE666_EQUATION["assimilation_principle"],
    }
