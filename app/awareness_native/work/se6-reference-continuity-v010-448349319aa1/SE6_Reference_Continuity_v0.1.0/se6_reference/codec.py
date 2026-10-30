"""Small strict JSON boundary shared by the local reference extension."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


class ReferenceError(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise ReferenceError(reason)


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(encode(value)).hexdigest()


def byte_hash(value):
    return hashlib.sha256(value).hexdigest()


def _pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, "DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def decode(raw):
    try:
        return json.loads(raw, object_pairs_hook=_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(
                              ReferenceError("NONFINITE_JSON")))
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise ReferenceError("INVALID_JSON") from error


def read_bytes(path, limit=4 * 1024 * 1024):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), "REGULAR_FILE_REQUIRED")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    require(len(raw) <= limit, "FILE_SIZE_BOUND")
    return raw


def read_json(path, limit=4 * 1024 * 1024):
    return decode(read_bytes(path, limit))


def exact(value, keys, code):
    require(type(value) is dict and set(value) == set(keys), code)


def identifier(value):
    require(type(value) is str and
            re.fullmatch(r"[a-z0-9][a-z0-9._:-]{0,127}", value) is not None,
            "LOWERCASE_IDENTIFIER_REQUIRED")
    return value


def uint(value, limit=1_000_000_000):
    require(type(value) is int and 0 <= value <= limit, "NONNEGATIVE_INTEGER_BOUND")
    return value
