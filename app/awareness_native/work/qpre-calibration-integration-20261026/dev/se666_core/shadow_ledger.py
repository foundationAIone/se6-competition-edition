"""In-memory physics checks for neural code and command proposals.

The Shadow Ledger never executes, imports, compiles to bytecode, writes, or
spawns a process.  It only parses Python source and tokenizes command text.
"""

from __future__ import annotations

import ast
import shlex
from pathlib import PurePath
from typing import Literal

from pydantic import BaseModel, Field

ShadowDecision = Literal["allow", "repair", "refuse"]

BANNED_EXECUTABLES = frozenset({
    "rm", "sudo", "mkfs", "fdisk", "format", "diskpart",
    "shutdown", "reboot", "halt", "poweroff",
})


class ShadowLedgerResult(BaseModel):
    decision: ShadowDecision = "allow"
    artifact_type: Literal["none", "python", "terminal"] = "none"
    checks: list[str] = Field(default_factory=list)
    reason: str = "No virtual artifact required validation."
    repair_prompt: str | None = None
    syntax_message: str | None = None
    syntax_lineno: int | None = None
    banned_tokens: list[str] = Field(default_factory=list)


def _executable_name(token: str) -> str:
    name = PurePath(token.strip("'\"")).name.lower()
    return name.removesuffix(".exe")


def inspect_python(source: str) -> ShadowLedgerResult:
    """Parse Python source into an AST without evaluating it."""
    if not isinstance(source, str):
        raise TypeError("source must be str")
    try:
        ast.parse(source, filename="<se6-shadow-ledger>", mode="exec")
    except SyntaxError as exc:
        message = exc.msg or "invalid syntax"
        line = int(exc.lineno or 1)
        return ShadowLedgerResult(
            decision="repair",
            artifact_type="python",
            checks=["ast.parse"],
            reason=f"Python proposal failed virtual parsing at line {line}: {message}",
            repair_prompt=f"[SE6 REPAIR]: SyntaxError at line {line}: {message}",
            syntax_message=message,
            syntax_lineno=line,
        )
    return ShadowLedgerResult(
        decision="allow",
        artifact_type="python",
        checks=["ast.parse"],
        reason="Python proposal passed virtual AST parsing; it was not executed.",
    )


def inspect_terminal(command: str) -> ShadowLedgerResult:
    """Tokenize a command and hard-refuse banned executable tokens."""
    if not isinstance(command, str):
        raise TypeError("command must be str")
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError as exc:
        message = str(exc) or "malformed command quoting"
        return ShadowLedgerResult(
            decision="repair",
            artifact_type="terminal",
            checks=["shlex.split"],
            reason=f"Terminal proposal could not be tokenized: {message}",
            repair_prompt=f"[SE6 REPAIR]: Command parse error: {message}",
        )
    banned = sorted({
        _executable_name(token)
        for token in tokens
        if _executable_name(token) in BANNED_EXECUTABLES
    })
    if banned:
        return ShadowLedgerResult(
            decision="refuse",
            artifact_type="terminal",
            checks=["shlex.split", "banned_executable_set"],
            reason="Terminal proposal contains a banned executable token.",
            banned_tokens=banned,
        )
    return ShadowLedgerResult(
        decision="allow",
        artifact_type="terminal",
        checks=["shlex.split", "banned_executable_set"],
        reason="Terminal proposal passed token inspection; it was not executed.",
    )


def inspect_proposal(
    *,
    elements: list[str],
    proposed_python: str | None = None,
    proposed_terminal_command: str | None = None,
) -> ShadowLedgerResult:
    """Apply Iron hard-refusal before Silicon syntax repair."""
    selected = set(elements)
    terminal: ShadowLedgerResult | None = None
    if "Iron" in selected and proposed_terminal_command is not None:
        terminal = inspect_terminal(proposed_terminal_command)
        if terminal.decision != "allow":
            return terminal
    if "Silicon" in selected and proposed_python is not None:
        return inspect_python(proposed_python)
    if terminal is not None:
        return terminal
    return ShadowLedgerResult()


__all__ = [
    "BANNED_EXECUTABLES", "ShadowDecision", "ShadowLedgerResult",
    "inspect_proposal", "inspect_python", "inspect_terminal",
]
