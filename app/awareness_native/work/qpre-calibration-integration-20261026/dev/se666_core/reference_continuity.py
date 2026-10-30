"""Source-bound reference continuity in the canonical DEVELOPMENT checkout.

Reuse the supplied implementation. Load the actual current canonical modules
under private namespaces, without importing a production service initializer.
Development grant pins remain development authority; no canonical action
admission, dispatcher registration or Alpha acceptance is created here.
"""
from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
import sys
import types


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _regular(root, relative):
    candidate = root / relative
    if not candidate.resolve(strict=True).is_relative_to(root):
        raise ValueError("REFERENCE_DEPENDENCY_ESCAPE")
    for item in (candidate, *candidate.parents):
        if item == root.parent:
            break
        if item.is_symlink():
            raise ValueError("REFERENCE_DEPENDENCY_SYMLINK")
    if not candidate.is_file():
        raise ValueError("REFERENCE_DEPENDENCY_NOT_FILE")
    return candidate


def _namespace(name, directory):
    existing = sys.modules.get(name)
    if existing is not None:
        if list(existing.__path__) != [str(directory)]:
            raise ValueError("REFERENCE_NAMESPACE_COLLISION")
        return
    module = types.ModuleType(name)
    module.__path__ = [str(directory)]
    module.__package__ = name
    sys.modules[name] = module


class DevelopmentReference:
    """One explicitly pinned package/current-Core connection per process.

    inspect() is recorded-consequence replay, never a new live dispatch.
    apply_development() retains the package's exact development grant, source
    allowlist, pending-write blocking, reservations and atomic head checks.
    It is deliberately not a canonical-authority or World-dispatch API.
    """

    def __init__(self, *, package_root, package_manifest_sha256, canonical_root):
        self.package = Path(package_root).resolve(strict=True)
        self.core_root = Path(canonical_root).resolve(strict=True)
        self.manifest_sha = package_manifest_sha256
        self._verify_sources()
        # This process owns these private namespace bindings. Never substitute
        # a caller's already imported se6_reference package silently.
        for suffix in ("", ".canonical", ".storage", ".engine", ".geometry", ".codec"):
            existing = sys.modules.get("se6_reference" + suffix)
            relative = "__init__.py" if not suffix else suffix[1:] + ".py"
            expected = self.package / "se6_reference" / relative
            if existing is not None and Path(existing.__file__).resolve() != expected:
                raise ValueError("REFERENCE_PACKAGE_COLLISION")
        if not sys.path or sys.path[0] != str(self.package):
            sys.path.insert(0, str(self.package))
        self.canonical = importlib.import_module("se6_reference.canonical")
        self.storage = importlib.import_module("se6_reference.storage")
        binding = (str(self.package), self.manifest_sha, str(self.core_root))
        previous = getattr(self.canonical, "_development_connection", None)
        if previous is not None and previous != binding:
            raise ValueError("REFERENCE_PROCESS_ALREADY_BOUND_TO_OTHER_SOURCE")
        for module, name in ((self.canonical, "canonical.py"), (self.storage, "storage.py")):
            if Path(module.__file__).resolve() != self.package / "se6_reference" / name:
                raise ValueError("REFERENCE_IMPORTED_MODULE_COLLISION")
        token = hashlib.sha256(str(self.core_root).encode()).hexdigest()[:16]
        native_name = "_current_reference_native_" + token
        representation_name = "_current_reference_representation_" + token
        _namespace(native_name, self.core_root / "se_core")
        _namespace(representation_name, self.core_root / "se666_core")
        self.canonical.core = importlib.import_module(native_name + ".kernel")
        self.canonical.frames = importlib.import_module(representation_name + ".realization_frame")
        self.canonical.mapper = importlib.import_module(representation_name + ".universal_mapper")
        self.canonical.E = importlib.import_module(representation_name + ".epistemic_status").EpistemicStatus
        self.canonical._development_connection = binding

    def _verify_sources(self):
        manifest_path = _regular(self.package, "PACKAGE_MANIFEST.json")
        if _sha(manifest_path) != self.manifest_sha:
            raise ValueError("REFERENCE_PACKAGE_MANIFEST_PIN")
        manifest = json.loads(manifest_path.read_bytes())
        for name, pin in manifest["files"].items():
            if _sha(_regular(self.package, name)) != pin:
                raise ValueError("REFERENCE_PACKAGE_SOURCE_PIN:" + name)
        pins = json.loads(_regular(self.package, "SOURCE_PINS.json").read_bytes())["files"]
        self.component_files = {}
        for vendor_name, pin in pins.items():
            if not vendor_name.startswith("vendor/"):
                raise ValueError("REFERENCE_UPSTREAM_PREFIX")
            name = vendor_name[len("vendor/"):]
            source = _regular(self.core_root, name)
            if _sha(source) != pin:
                raise ValueError("CURRENT_CANONICAL_SOURCE_DIFFERS:" + name)
            self.component_files[name] = {"path": str(source), "sha256": pin}

    def inspect(self, store, *, expected_head):
        self._verify_sources()
        result = self.storage.inspect(store, expected_head=expected_head)
        self.canonical.verify_projection(result["state"])
        result["connection"] = {
            "status": "CURRENT_CANONICAL_COMPONENTS_CONSUMED_DEVELOPMENT_ONLY",
            "canonical_components": self.component_files,
            "kernel_loaded_from": self.canonical.core.__file__,
            "frame_loaded_from": self.canonical.frames.__file__,
            "mapper_loaded_from": self.canonical.mapper.__file__,
            "source_admission": "NOT_GRANTED_BY_THIS_ADAPTER",
            "canonical_dispatcher": "REGISTERED_REQUIRES_SEPARATE_EXECUTION_AUTHORITY",
            "canonical_acceptance": "NOT_EVALUATED",
            "new_native_actions": 0,
            "new_world_effects": 0,
        }
        return result

    def apply_development(self, store, authority_file, authority_sha256, request):
        self._verify_sources()
        # The supplied storage layer independently checks the exact grant
        # bytes, DEVELOPMENT scope, current head, budget and observer sources.
        # No conversion from these grants into canonical authority occurs.
        return self.storage.apply_request(store, authority_file, authority_sha256, request)

    def dispatch_selected(self, *, spec_path, expected_spec_sha256, permission_id, expected_head):
        """Carry a durable pending selection to the separately authorized handler."""
        self._verify_sources()
        from .local_executor import dispatch_reference_effect
        return dispatch_reference_effect("reference.affine-step.v1", spec_path=spec_path,
                                         expected_spec_sha256=expected_spec_sha256,
                                         permission_id=permission_id, expected_head=expected_head)
