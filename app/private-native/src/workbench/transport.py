"""Fixed-endpoint stateless transport. No tools, redirects, retries or requests on construction."""
from __future__ import annotations
import json
import os
from pathlib import Path
import ssl
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler, HTTPSHandler
from urllib.error import HTTPError, URLError
from .models import model_identity_matches


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class ProviderFailure(RuntimeError):
    def __init__(self, message, *, text="", usage=None, returned_model=None, uncertain=True):
        super().__init__(message)
        self.text, self.usage, self.returned_model, self.uncertain = text, usage, returned_model, uncertain


class ResponsesTransport:
    endpoint = "https://api.openai.com/v1/responses"

    @staticmethod
    def credential_present():
        return bool(os.environ.get("OPENAI_API_KEY"))

    def __init__(self, settings, *, opener=None):
        self.settings, self.opener = settings, opener

    def request(self, body, directory, timeout):
        if set(body) != {"input"}:
            raise ValueError("Only isolated input messages are accepted. No tools or shared conversations.")
        if not self.credential_present():
            raise ProviderFailure("OPENAI_API_KEY is not present in the server process.", uncertain=False)
        payload = {"input": body["input"], **self.settings.request_fields(), "store": False}
        raw_request = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        if len(raw_request) > 2097152:
            raise ProviderFailure("Request exceeds the local 2 MiB limit.", uncertain=False)
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        # A saved intent is not proof that a remote call did/didn't execute.
        # Never automatically repeat an existing intent after an uncertain outcome.
        with (directory / "request.json").open("xb") as stream:
            stream.write(raw_request)
        request = Request(self.endpoint, data=raw_request, method="POST", headers={
            "Authorization": "Bearer " + os.environ["OPENAI_API_KEY"], "Content-Type": "application/json"})
        opener = self.opener or build_opener(ProxyHandler({}), NoRedirect(),
                                             HTTPSHandler(context=ssl.create_default_context()))
        try:
            with opener.open(request, timeout=timeout) as response:
                raw = response.read(4194305)
        except HTTPError as exc:
            raise ProviderFailure(f"Provider HTTP {exc.code}; no automatic retry. Account access and billing are not inferred.") from exc
        except (URLError, OSError, TimeoutError) as exc:
            raise ProviderFailure("Provider outcome is uncertain (" + type(exc).__name__ + "). No retry was made.") from exc
        with (directory / "provider.json").open("xb") as stream:
            stream.write(raw)
        if len(raw) > 4194304:
            raise ProviderFailure("Provider response exceeds 4 MiB; available raw bytes retained.")
        try:
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError("object required")
            parts = [part["text"] for item in result.get("output", [])
                     for part in item.get("content", []) if part.get("type") == "output_text" and isinstance(part.get("text"), str)]
            text = "\n\n".join(parts)
            refusals = [part["refusal"] for item in result.get("output", [])
                        for part in item.get("content", []) if part.get("type") == "refusal" and isinstance(part.get("refusal"), str)]
            if not text and refusals:
                text = "\n\n".join(refusals)
        except (ValueError, TypeError, AttributeError, KeyError) as exc:
            raise ProviderFailure("Unrecognized provider payload; raw response retained.") from exc
        with (directory / "returned-text.txt").open("xb") as stream:
            stream.write(text.encode("utf-8"))
        fields = {"text": text, "usage": result.get("usage"), "returned_model": result.get("model")}
        if not model_identity_matches(self.settings.model, result.get("model")):
            raise ProviderFailure("Returned model identity does not match the selection; raw result retained.", **fields, uncertain=False)
        if result.get("status") != "completed":
            raise ProviderFailure("Provider response incomplete; partial text retained. No retry.", **fields, uncertain=False)
        if refusals and not parts:
            raise ProviderFailure("Provider refusal retained for review.", **fields, uncertain=False)
        if not parts:
            raise ProviderFailure("No response text returned; raw result retained.", **fields, uncertain=False)
        return {"text": text, "model": result.get("model"), "usage": result.get("usage"),
                "response_id": result.get("id"), "text_parts": len(parts)}
