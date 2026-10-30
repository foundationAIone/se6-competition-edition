"""Use the existing paired-experiment evidence projection, never a substitute.

The frozen builder is deliberately task-specific. An incompatible packet is
rejected before either model call; no generic replacement or stale projection
is silently introduced. The baseline never receives or builds a projection.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


class EvidenceProjection:
    mode = "SE6 evidence projection"
    description = (
        "Existing paired-experiment source graph, uncertainty and boundary projection. "
        "Supports the recent SOURCE S1–S16 evidence packet; other packets are rejected before either call. "
        "No production Entity, prior responses, private memory or executable SE Core is used."
    )

    def __init__(self, repository: Path):
        self.root = Path(repository) / "experiments/real-paired-004"
        self.blocker = None
        try:
            manifest = json.loads((self.root / "manifest.json").read_bytes())
            source = self.root / "se6/shadow.py"
            wrapper_source = self.root / "provenance/upstream-prepare.py"
            for path in (source, wrapper_source):
                expected = manifest["artifacts_sha256"][path.relative_to(self.root).as_posix()]
                if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                    raise ValueError("The frozen projection implementation or wrapper changed.")
            # Compile in memory to avoid creating __pycache__ in frozen inputs.
            namespace = {"__name__": "comparison_frozen_evidence_shadow", "__file__": str(source)}
            exec(compile(source.read_bytes(), str(source), "exec"), namespace)
            self.build_shadow = namespace["build_shadow"]
            self.serialize = namespace["serialize"]
            wanted = {"A_PREFIX", "B_PREFIX", "B_SEPARATOR"}
            constants = {}
            for node in ast.parse(wrapper_source.read_bytes()).body:
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id in wanted:
                            constants[target.id] = ast.literal_eval(node.value).decode("utf-8")
            if set(constants) != wanted:
                raise ValueError("The original prompt wrappers are unavailable.")
            self.prefix_a = constants["A_PREFIX"]
            self.prefix_b = constants["B_PREFIX"]
            self.separator_b = constants["B_SEPARATOR"]
        except (OSError, ValueError, KeyError, SyntaxError) as exc:
            self.blocker = "Existing evidence-projection integration unavailable: " + str(exc)

    def project(self, problem):
        if self.blocker:
            raise ValueError(self.blocker)
        try:
            stages = self.build_shadow(problem)
        except ValueError as exc:
            raise ValueError(
                "This problem is incompatible with the existing task-specific SE6 projection: "
                + str(exc) + ". Neither model was called. Use the supported recent evidence packet; "
                "supporting a different packet requires adapting its projection explicitly."
            ) from exc
        projection = stages["projection-context"]
        if projection["source_task_sha256"] != hashlib.sha256(problem.encode("utf-8")).hexdigest():
            raise ValueError("Projection does not bind the exact shared problem.")
        return self.serialize(projection)

    def validate_problem(self, problem):
        self.project(problem)

    def run(self, problem, lane, adapter, folder):
        if lane == "baseline":
            # No projection, engine, memory, peer output, or stored response.
            prompt = self.prefix_a + problem
        elif lane == "se6":
            projection = self.project(problem)
            with (folder / "projection.json").open("xb") as stream:
                stream.write(projection.encode("utf-8"))
            prompt = self.prefix_b + projection + self.separator_b + problem
        else:
            raise ValueError("Unknown comparison lane.")
        return adapter.request({"input": prompt}, folder, "answer")
