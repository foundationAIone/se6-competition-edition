"""Write-once local journal with separately pinned development grants.

The grant issuer is the trusted local host in this development protocol. A
checksum authenticates bytes relative to that issuer's supplied pin; it is not
a signature and cannot authenticate a hostile issuer or establish real-world
truth. Imported checkpoints require the same exact grants and source bytes.
"""
from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path

from . import canonical
from .codec import (byte_hash, decode, digest, encode, exact, read_bytes, read_json,
                    require, uint)
from .engine import reduce

GRANT_KEYS = {"schema", "scope", "entity_id", "sequence", "expected_head",
              "request_sha256", "operation", "task_id", "permissions", "now_tick",
              "max_age_ticks", "allowed_actions", "task_action_limit", "max_action_cost", "sources"}
SCOPE = ("LOCAL_DEVELOPMENT_ONLY: actual supplied Native and canonical representation code; "
         "declared affine reference across tasks; canonical acceptance NOT_EVALUATED")


class FileWitness:
    """Read actual allowlisted bytes, never a producer's 'verified' Boolean."""
    def __init__(self, authority_file, grant, store):
        self.root = Path(authority_file).resolve().parent
        self.store = Path(store).resolve()
        self.sources = deepcopy(grant["sources"])
        require(type(self.sources) is dict and len(self.sources) <= 16, "SOURCE_REGISTRY_BOUND")
        self.used = []

    def read(self, token):
        require(type(token) is str and token in self.sources, "SOURCE_NOT_GRANTED")
        row = self.sources[token]
        exact(row, {"path", "sha256"}, "SOURCE_ENTRY_SCHEMA")
        require(type(row["path"]) is str and not Path(row["path"]).is_absolute(), "RELATIVE_SOURCE_REQUIRED")
        path = self.root / row["path"]
        require(path.resolve().is_relative_to(self.root) and
                not path.resolve().is_relative_to(self.store), "SOURCE_READ_BOUNDARY")
        # Checking every path component prevents a declared source directory from
        # redirecting to state files or an unrelated private file through a link.
        for component in (path, *path.parents):
            if component == self.root.parent:
                break
            require(not component.is_symlink(), "SOURCE_SYMLINK_DENIED")
        raw = read_bytes(path, 1024 * 1024)
        actual = byte_hash(raw)
        require(actual == row["sha256"], "SOURCE_BYTES_CHANGED")
        reference = "file:" + actual
        if reference not in self.used:
            self.used.append(reference)
        return decode(raw), actual


def _grant(path, pin, request, sequence, head, store):
    path = Path(path)
    require(not path.is_symlink() and not path.resolve().is_relative_to(Path(store).resolve()),
            "AUTHORITY_MUST_BE_SEPARATE_FROM_ENTITY_STORE")
    raw = read_bytes(path, 1024 * 1024)
    require(byte_hash(raw) == pin, "OUT_OF_BAND_GRANT_PIN_MISMATCH")
    grant = decode(raw)
    exact(grant, GRANT_KEYS, "GRANT_SCHEMA")
    require(grant["schema"] == "se6-reference-grant-v1" and
            grant["scope"] == "LOCAL_DEVELOPMENT_ONLY", "DEVELOPMENT_SCOPE_REQUIRED")
    uint(grant["sequence"], 63)
    require(grant["sequence"] == sequence and grant["expected_head"] == head,
            "EXTERNAL_HEAD_OR_SEQUENCE_MISMATCH")
    require(grant["request_sha256"] == digest(request), "GRANTED_REQUEST_BYTES_MISMATCH")
    for field in ("permissions", "allowed_actions"):
        value = grant[field]
        require(type(value) is list and len(value) <= 64 and all(type(v) is str for v in value)
                and len(value) == len(set(value)), "GRANT_LIST_SCHEMA")
    return grant


def _load(store):
    store = Path(store)
    require(not store.is_symlink(), "STORE_SYMLINK_DENIED")
    if not store.exists():
        return None, None, 0
    require(store.is_dir(), "STORE_DIRECTORY_REQUIRED")
    require(not (store / "LOCK").exists(), "STORE_HAS_UNRESOLVED_OWNED_OPERATION")
    require(not (store / "CURRENT.json").is_symlink(), "CURRENT_SYMLINK_DENIED")
    require((store / "CURRENT.json").is_file(), "STORE_CURRENT_MISSING")
    current = read_json(store / "CURRENT.json", 1024)
    exact(current, {"sequence", "head"}, "CURRENT_SCHEMA")
    uint(current["sequence"], 63)
    directory = store / "events"
    require(directory.is_dir() and not directory.is_symlink(), "EVENT_DIRECTORY_REQUIRED")
    files = sorted(directory.iterdir())
    require([p.name for p in files] == [f"{i:06d}.json" for i in range(current["sequence"] + 1)],
            "EVENT_SEQUENCE_GAP_OR_UNCOMMITTED_TAIL")
    previous = None
    head = None
    for sequence, path in enumerate(files):
        event = read_json(path, 16 * 1024 * 1024)
        exact(event, {"schema", "sequence", "previous", "authority_file", "authority_sha256",
                      "request", "state", "result", "seal"}, "EVENT_SCHEMA")
        material = {k: v for k, v in event.items() if k != "seal"}
        require(event["schema"] == "se6-reference-event-v1" and event["sequence"] == sequence
                and event["previous"] == head and digest(material) == event["seal"],
                "EVENT_LINEAGE_OR_CONTENT_MISMATCH")
        grant = _grant(event["authority_file"], event["authority_sha256"], event["request"],
                       sequence, head, store)
        witness = FileWitness(event["authority_file"], grant, store)
        old_receipts = decode(previous["core_journal"])["receipts"] if previous else []
        saved_receipts = decode(event["state"]["core_journal"])["receipts"]
        require(saved_receipts[:len(old_receipts)] == old_receipts, "NATIVE_IMMUTABLE_RECEIPT_PREFIX")
        with canonical.replay_receipts(saved_receipts[len(old_receipts):]):
            rebuilt, result = reduce(previous, event["request"], grant, event["authority_sha256"], witness)
        require(rebuilt == event["state"] and result == event["result"],
                "FULL_REFERENCE_REPLAY_MISMATCH")
        previous, head = rebuilt, event["seal"]
    require(head == current["head"], "CURRENT_HEAD_MISMATCH")
    return previous, head, len(files)


def inspect(store, *, expected_head):
    canonical.check_sources()
    state, head, count = _load(Path(store))
    require(head == expected_head, "EXTERNAL_HEAD_MISMATCH")
    require(state is not None, "REFERENCE_NOT_CREATED")
    return {"event_head": head, "state": state, "event_count": count, "scope": SCOPE}


def _write_once(path, value):
    with Path(path).open("xb") as stream:
        stream.write(encode(value))
        stream.flush()
        os.fsync(stream.fileno())


def _fsync_directory(path):
    # Windows does not provide a portable directory fsync through this API.
    if os.name == "posix":
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def apply_request(store, authority_file, authority_sha, request):
    canonical.check_sources()
    store = Path(store).absolute()
    authority_file = Path(authority_file).absolute()
    prior, head, sequence = _load(store)
    grant = _grant(authority_file, authority_sha, request, sequence, head, store)
    witness = FileWitness(authority_file, grant, store)
    # All deterministic validation precedes store mutation. A rejected request
    # cannot erase a pending operation, reset a budget or edit prior evidence.
    state, result = reduce(prior, request, grant, authority_sha, witness)
    require(byte_hash(read_bytes(authority_file)) == authority_sha, "GRANT_CHANGED_DURING_OPERATION")
    if prior is None:
        store.mkdir(parents=True, exist_ok=False)
        (store / "events").mkdir()
    lock = store / "LOCK"
    wrote_event = False
    _write_once(lock, {"pid": os.getpid(), "expected_head": head,
                       "sequence": sequence, "authority_sha256": authority_sha})
    try:
        # A concurrent writer that completed during validation is detected here.
        if prior is not None:
            current = read_json(store / "CURRENT.json")
            require(current == {"sequence": sequence - 1, "head": head}, "CONCURRENT_HEAD_CHANGE")
        material = {"schema": "se6-reference-event-v1", "sequence": sequence, "previous": head,
                    "authority_file": str(authority_file.resolve()), "authority_sha256": authority_sha,
                    "request": deepcopy(request), "state": state, "result": result}
        new_head = digest(material)
        event = {**material, "seal": new_head}
        event_path = store / "events" / f"{sequence:06d}.json"
        # From this point, uncertainty retains LOCK for explicit reconciliation.
        wrote_event = True
        _write_once(event_path, event)
        _fsync_directory(event_path.parent)
        temporary = store / ("CURRENT." + new_head + ".tmp")
        _write_once(temporary, {"sequence": sequence, "head": new_head})
        os.replace(temporary, store / "CURRENT.json")
        _fsync_directory(store)
        require(read_json(store / "CURRENT.json") == {"sequence": sequence, "head": new_head}
                and read_json(event_path, 16 * 1024 * 1024) == event,
                "DURABLE_READBACK_MISMATCH")
    except BaseException:
        if not wrote_event:
            lock.unlink()
        raise
    lock.unlink()
    return {"event_head": new_head, "state": state, "result": result, "scope": SCOPE}
