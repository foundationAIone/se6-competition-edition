"""Fail-closed adapter for sanitized public SE6Triad state packets."""

from __future__ import annotations

import re
from typing import Any

from .se6triad_kernel import SE6StatePacket, SE6TriadResult


class PublicPacketError(ValueError):
    pass


PUBLIC_PACKET_FIELDS = (
    "realObjective", "flowerMap", "merkabahRotation", "mirrorReflection",
    "classification", "boundaryDecision", "nextLawfulAction", "toolRequest",
    "approvalRequired", "memoryUpdate", "expectedStateChange", "motionState",
    "auditEntry",
)

_FORBIDDEN_PATTERNS = (
    re.compile(r"[A-Za-z]:\\(?:Users|Documents|Desktop|AppData)\\", re.IGNORECASE),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{12,}=*\b", re.IGNORECASE),
    re.compile(r"\b(?:api[_ -]?key|password|private[_ -]?key|seed phrase)\s*[:=]", re.IGNORECASE),
    re.compile(r"\bmemory[/\\](?:audit_log|qfs|serplus|sources|approvals)", re.IGNORECASE),
)


def _scan(value: Any, path: str = "packet") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _scan(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _scan(item, f"{path}[{index}]")
    elif isinstance(value, str) and any(
        pattern.search(value) for pattern in _FORBIDDEN_PATTERNS
    ):
        raise PublicPacketError(f"sensitive content rejected at {path}")


def build_public_packet(source: SE6TriadResult | SE6StatePacket) -> dict[str, Any]:
    """Return only canonical public fields, rejecting sensitive content.

    Unknown internal fields cannot pass through because the output is rebuilt
    from :data:`PUBLIC_PACKET_FIELDS`. Content scanning is fail-closed rather
    than silently redacting data and pretending the packet is complete.
    """
    packet = source.state_packet if isinstance(source, SE6TriadResult) else source
    raw = packet.model_dump()
    public = {field: raw[field] for field in PUBLIC_PACKET_FIELDS}
    _scan(public)
    return public


__all__ = ["PUBLIC_PACKET_FIELDS", "PublicPacketError", "build_public_packet"]
