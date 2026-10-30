"""Fixed session directives; message delivery is not provider enforcement proof."""
from .provider_router import NEBIUS_MODEL

DEFAULT = "DEFAULT"
NEMOTRON_NO_THINK = "NEMOTRON_NO_THINK"
PRESETS = (DEFAULT, NEMOTRON_NO_THINK)


def validate_preset(preset, pair):
    if not isinstance(preset, str) or preset not in PRESETS:
        raise ValueError("Unknown reasoning directive preset; arbitrary system instructions are forbidden.")
    if preset == NEMOTRON_NO_THINK and (
        pair.mode != "matched" or pair.se6 != pair.baseline or
        any(model.model != NEBIUS_MODEL or model.provider != "Nebius Token Factory"
            for model in (pair.se6, pair.baseline))
    ):
        raise ValueError("NEMOTRON_NO_THINK requires matched Nemotron 3 Super settings on the Nebius adapter.")


def system_messages(preset, pair):
    validate_preset(preset, pair)
    return [] if preset == DEFAULT else [{"role": "system", "content": "/no_think"}]


def preset_contract():
    return {"presets": list(PRESETS), "new_sessions_only": True,
            "message_role": "system", "supported_model": NEBIUS_MODEL,
            "supported_adapter": "Nebius Token Factory",
            "arbitrary_system_instructions": False,
            "provider_enforcement": "UNVERIFIED", "separate_reasoning_budget": "UNVERIFIED"}
