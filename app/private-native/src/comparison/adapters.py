"""One stateless Responses API transport, shared settings, no automatic retries.

The endpoint and request conventions follow the existing v0.2 benchmark adapter.
Nothing sends a request at import, construction, readiness checks, or page load.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ModelFailure(RuntimeError):
    pass


from .model_controls import ModelSettings, model_identity_matches


class OpenAIResponses:
    endpoint = "https://api.openai.com/v1/responses"

    def __init__(self, settings: ModelSettings, *, transport=None):
        self.settings = settings
        self._transport = transport or urlopen

    @staticmethod
    def credential_present():
        return bool(os.environ.get("OPENAI_API_KEY"))

    def request(self, body: dict, directory: Path, name: str):
        if not self.credential_present():
            raise ModelFailure("OPENAI_API_KEY is not available to the local server.")
        if any(key in body for key in ("previous_response_id", "conversation", "tools")):
            raise ModelFailure("Shared conversations and model tools are disabled.")
        if any(key in body for key in ("model", "temperature", "max_output_tokens", "store", "reasoning")):
            raise ModelFailure("Model settings are owned by the shared configuration.")
        payload = {**body, **self.settings.request_fields(), "store": False}
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        if len(encoded) > 262144:
            raise ModelFailure("Model request exceeds the local size limit.")
        directory.mkdir(parents=True, exist_ok=True)
        # Exclusive request file doubles as an ambiguous-send guard. Never retry
        # this call automatically, including after a timeout or process failure.
        with (directory / (name + ".request.json")).open("xb") as stream:
            stream.write(encoded)
        req = Request(self.endpoint, data=encoded, method="POST", headers={
            "Authorization": "Bearer " + os.environ["OPENAI_API_KEY"],
            "Content-Type": "application/json",
        })
        try:
            with self._transport(req, timeout=60) as stream:
                raw = stream.read(1048577)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            # Provider bodies and request headers may contain sensitive data.
            raise ModelFailure("Provider call failed or is ambiguous; no retry performed (" + type(exc).__name__ + ").") from exc
        with (directory / (name + ".provider.json")).open("xb") as stream:
            stream.write(raw)
        if len(raw) > 1048576:
            raise ModelFailure("Provider response exceeds the local size limit; raw bytes saved.")
        try:
            result = json.loads(raw)
        except (ValueError, UnicodeError) as exc:
            raise ModelFailure("Provider returned invalid JSON; raw bytes saved.") from exc
        parts = [item["text"] for output in result.get("output", [])
                 for item in output.get("content", []) if item.get("type") == "output_text"]
        if len(parts) == 1 and isinstance(parts[0], str):
            with (directory / (name + ".txt")).open("xb") as stream:
                stream.write(parts[0].encode("utf-8"))
        if not model_identity_matches(self.settings.model, result.get("model")):
            raise ModelFailure("Returned model version does not match the shared pinned model; raw response saved.")
        if result.get("status") != "completed":
            raise ModelFailure("Provider response is incomplete; raw response saved. No retry performed.")
        if len(parts) != 1 or not isinstance(parts[0], str):
            raise ModelFailure("Expected one unchanged response text; raw provider response saved.")
        return {"text": parts[0], "model": result["model"], "usage": result.get("usage"),
                "response_id": result.get("id")}
