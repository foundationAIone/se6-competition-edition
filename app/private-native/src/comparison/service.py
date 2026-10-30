"""Freeze one input and dispatch two independent lanes; never auto-run or retry."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from threading import Lock
from uuid import uuid4

from .adapters import ModelFailure, ModelSettings, OpenAIResponses
from .model_controls import PROFILES, UPDATE_VERSION, load_settings, save_settings, settings_path


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ComparisonService:
    def __init__(self, integration, storage: Path, settings=None, *, adapter_factory=None):
        self.integration = integration
        self.storage = Path(storage)
        self.settings = settings or load_settings(settings_path(self.storage))
        self.adapter_factory = adapter_factory or (lambda: OpenAIResponses(self.settings))
        self._lock = Lock()
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="comparison")
        self._runs = {}

    def configuration(self):
        with self._lock:
            settings = self.settings
            busy = any(not row["complete"] for row in self._runs.values())
        blocker = self.integration.blocker
        if not blocker and not OpenAIResponses.credential_present():
            blocker = "OPENAI_API_KEY is not available to the local server."
        return {"ready": not blocker, "blocker": blocker, "model": settings.model,
                "settings": settings.public(), "se6_mode": self.integration.mode,
                "se6_description": self.integration.description,
                "model_controls": {"version": UPDATE_VERSION, "busy": busy,
                                   "profiles": deepcopy(PROFILES), "api_access_verified": False}}

    def update_settings(self, value):
        settings = ModelSettings.from_change(value)
        with self._lock:
            if any(not row["complete"] for row in self._runs.values()):
                raise ValueError("Both lanes must finish before shared settings can change.")
            try:
                save_settings(settings_path(self.storage), settings)
            except OSError as exc:
                raise ValueError("Settings could not be saved; current in-memory settings were not changed.") from exc
            self.settings = settings
        return self.configuration()

    def start(self, problem):
        if not isinstance(problem, str) or not problem.strip():
            raise ValueError("Paste a nonempty test problem.")
        if len(problem.encode("utf-8")) > 65536:
            raise ValueError("The shared problem exceeds 64 KiB.")
        config = self.configuration()
        if not config["ready"]:
            raise ValueError(config["blocker"])
        # Validate both lanes before any dispatch. Do not normalize the string.
        self.integration.validate_problem(problem)
        with self._lock:
            if any(not row["complete"] for row in self._runs.values()):
                raise ValueError("A comparison is already running; it will not be submitted again.")
            token = uuid4().hex
            folder = self.storage / token
            folder.mkdir(parents=True, exist_ok=False)
            with (folder / "problem.txt").open("xb") as stream:
                stream.write(problem.encode("utf-8"))
            run = {"id": token, "problem_sha256": sha(problem), "model": self.settings.model,
                   "settings": self.settings.public(), "complete": False,
                   "lanes": {name: {"status": "RUNNING", "response": "", "error": None}
                             for name in ("se6", "baseline")}}
            self._runs[token] = run
            with (folder / "settings.json").open("x", encoding="utf-8") as stream:
                json.dump({"model": self.settings.model, "settings": self.settings.public(),
                           "problem_sha256": sha(problem), "se6_mode": self.integration.mode}, stream, indent=2)
            # Each lane receives its own provider adapter and output directory.
            # No run object, peer output, prior run or shared history is passed.
            for lane in ("se6", "baseline"):
                adapter = self.adapter_factory()
                self._pool.submit(self._execute, token, lane, problem, adapter, folder / lane)
        return token

    def _execute(self, token, lane, problem, adapter, folder):
        folder.mkdir(exist_ok=False)
        try:
            result = self.integration.run(problem, lane, adapter, folder)
            text = result["text"]
            if not isinstance(text, str):
                raise ModelFailure("The lane did not return raw text.")
            with (folder / "response.txt").open("xb") as stream:
                stream.write(text.encode("utf-8"))
            value = {"status": "COMPLETE", "response": text, "response_sha256": sha(text),
                     "error": None, "model": result["model"], "usage": result.get("usage")}
        except Exception as exc:
            message = str(exc) if isinstance(exc, (ModelFailure, ValueError)) else "Local execution failed (" + type(exc).__name__ + ")."
            value = {"status": "ERROR", "response": "", "error": message}
        with (folder / "result.json").open("x", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
        with self._lock:
            self._runs[token]["lanes"][lane] = value
            self._runs[token]["complete"] = all(
                row["status"] in ("COMPLETE", "ERROR") for row in self._runs[token]["lanes"].values())
            run = self._runs[token]
            if run["complete"]:
                rows = list(run["lanes"].values())
                both_ok = all(row["status"] == "COMPLETE" for row in rows)
                same_actual_model = both_ok and len({row.get("model") for row in rows}) == 1
                run["comparison_eligible"] = bool(same_actual_model)
                run["comparison_blocker"] = (
                    "" if same_actual_model else
                    "Comparison is not eligible: a lane failed or the returned model IDs differ. Raw responses were preserved; no retry was made."
                )
                summary = {"requested_model": run["model"],
                           "returned_models": {name: row.get("model") for name, row in run["lanes"].items()},
                           "comparison_eligible": run["comparison_eligible"],
                           "comparison_blocker": run["comparison_blocker"]}
                try:
                    with (folder.parent / "comparison.json").open("x", encoding="utf-8") as stream:
                        json.dump(summary, stream, indent=2)
                except OSError:
                    run["comparison_eligible"] = False
                    run["comparison_blocker"] = "Comparison summary could not be saved. Raw response files were not replaced; no retry was made."

    def get(self, token):
        with self._lock:
            if token not in self._runs:
                raise KeyError("Unknown comparison.")
            return deepcopy(self._runs[token])

    def close(self):
        self._pool.shutdown(wait=True, cancel_futures=False)
