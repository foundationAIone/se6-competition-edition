"""Exact, bounded geometry for explicitly declared affine length frames.

The declared conversion is ``base_point = matrix * local_point + origin``.
Base coordinates are meters; vectors use the same matrix without the origin.
``unit`` is a label supplied by the frame declaration, not a unit inference
service: the matrix must include the complete conversion to meters.

This module performs no semantic discovery, task inference, persistence, or
action execution.  It supports only finite, declared 1--3 dimensional affine
length frames and exact integer/rational scalar data.
"""

from __future__ import annotations

import re
from fractions import Fraction
from typing import Any


class GeometryError(ValueError):
    """A declared coordinate, frame, or pointer violates the contract."""


_MAX_TEXT = 64
_MAX_BITS = 128
_MAX_ABS = 10**12
_MAX_POINTER = 512
_MAX_OBJECTS = 16
_RATIONAL = re.compile(r"([+-]?[0-9]+)(?:/([0-9]+))?\Z", re.ASCII)
_OBJECT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z", re.ASCII)
_INDEX = re.compile(r"(?:0|[1-9][0-9]*)\Z", re.ASCII)
_BAD_ESCAPE = re.compile(r"~(?:[^01]|$)")


def _checked(value: Fraction) -> Fraction:
    if (
        abs(value.numerator).bit_length() > _MAX_BITS
        or value.denominator.bit_length() > _MAX_BITS
        or abs(value) > _MAX_ABS
        or len(str(value)) > _MAX_TEXT
    ):
        raise GeometryError("RATIONAL_BOUND: scalar exceeds the exact numeric bounds")
    return value


def rational(value: Any) -> Fraction:
    """Parse an exact integer or integer/fraction string within numeric bounds.

    Text is at most 64 characters, with no whitespace, decimal notation,
    exponents, or unit suffix.  A leading sign and unreduced fractions are
    accepted.  Raw and reduced components are at most 128 bits; magnitude
    is at most 10**12.  Booleans, floats, and Fraction objects are not input
    encodings.  Serialized results are normalized by ``str(Fraction(...))``.
    """
    if type(value) is int:
        if abs(value).bit_length() > _MAX_BITS:
            raise GeometryError("RATIONAL_BOUND: integer component exceeds 128 bits")
        return _checked(Fraction(value))
    if type(value) is not str or not 1 <= len(value) <= _MAX_TEXT:
        raise GeometryError("RATIONAL_TYPE: expected an integer or bounded rational string")
    match = _RATIONAL.fullmatch(value)
    if match is None:
        raise GeometryError("RATIONAL_SYNTAX: expected an integer or numerator/denominator")
    numerator = int(match.group(1))
    denominator = int(match.group(2)) if match.group(2) is not None else 1
    if denominator == 0:
        raise GeometryError("RATIONAL_ZERO_DIVISOR: denominator must be positive")
    if abs(numerator).bit_length() > _MAX_BITS or denominator.bit_length() > _MAX_BITS:
        raise GeometryError("RATIONAL_BOUND: raw component exceeds 128 bits")
    return _checked(Fraction(numerator, denominator))


def _label(value: Any, name: str) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= 128
        or value.strip() != value
        or not value.isprintable()
    ):
        raise GeometryError(f"FRAME_LABEL: {name} must be a nonempty printable label")
    return value


def _values(values: Any, size: int | None = None, name: str = "coordinates") -> list[Fraction]:
    if type(values) is not list or not 1 <= len(values) <= 3:
        raise GeometryError(f"COORDINATE_SHAPE: {name} must be a list of 1 to 3 scalars")
    if size is not None and len(values) != size:
        raise GeometryError(f"DIMENSION_MISMATCH: {name} does not match the frame")
    return [rational(value) for value in values]


def _solve(matrix: list[list[Fraction]], rhs: list[Fraction]) -> list[Fraction]:
    """Small exact Gaussian elimination; singular matrices fail explicitly."""
    size = len(matrix)
    rows = [list(row) + [rhs[index]] for index, row in enumerate(matrix)]
    for column in range(size):
        pivot = next((i for i in range(column, size) if rows[i][column] != 0), None)
        if pivot is None:
            raise GeometryError("SINGULAR_FRAME: frame matrix must be invertible")
        rows[column], rows[pivot] = rows[pivot], rows[column]
        divisor = rows[column][column]
        rows[column] = [value / divisor for value in rows[column]]
        for index in range(size):
            if index == column:
                continue
            factor = rows[index][column]
            rows[index] = [
                value - factor * pivot_value
                for value, pivot_value in zip(rows[index], rows[column])
            ]
    return [rows[index][-1] for index in range(size)]


def _frame_parts(frame: Any) -> tuple[dict[str, Any], list[list[Fraction]], list[Fraction]]:
    if type(frame) is not dict or set(frame) != {"id", "dimension", "unit", "matrix", "origin"}:
        raise GeometryError("FRAME_SCHEMA: frame must have exactly id, dimension, unit, matrix, origin")
    frame_id = _label(frame["id"], "id")
    unit = _label(frame["unit"], "unit")
    if frame["dimension"] != "length":
        raise GeometryError("FRAME_DIMENSION: only declared length frames are supported")
    raw_matrix = frame["matrix"]
    if type(raw_matrix) is not list or not 1 <= len(raw_matrix) <= 3:
        raise GeometryError("FRAME_MATRIX: expected a square matrix of size 1 to 3")
    size = len(raw_matrix)
    matrix = [_values(row, size, "matrix row") for row in raw_matrix]
    origin = _values(frame["origin"], size, "origin")
    _solve(matrix, [Fraction(0) for _ in range(size)])
    normalized = {
        "id": frame_id,
        "dimension": "length",
        "unit": unit,
        "matrix": [[str(value) for value in row] for row in matrix],
        "origin": [str(value) for value in origin],
    }
    return normalized, matrix, origin


def validate_frame(frame: Any) -> dict[str, Any]:
    """Validate and copy a frame, normalizing its rational entries."""
    return _frame_parts(frame)[0]


def _serialized(values: list[Fraction]) -> list[str]:
    return [str(_checked(value)) for value in values]


def point_to_base(values: Any, frame: Any) -> list[str]:
    """Transform a local point to base meters, including the origin."""
    _, matrix, origin = _frame_parts(frame)
    point = _values(values, len(matrix))
    return _serialized([
        sum((entry * coordinate for entry, coordinate in zip(row, point)), Fraction(0)) + offset
        for row, offset in zip(matrix, origin)
    ])


def vector_to_base(values: Any, frame: Any) -> list[str]:
    """Transform a displacement to base meters, excluding the origin."""
    _, matrix, _ = _frame_parts(frame)
    vector = _values(values, len(matrix))
    return _serialized([
        sum((entry * coordinate for entry, coordinate in zip(row, vector)), Fraction(0))
        for row in matrix
    ])


def point_from_base(values: Any, frame: Any) -> list[str]:
    """Transform a point from base meters into the declared local frame."""
    _, matrix, origin = _frame_parts(frame)
    point = _values(values, len(matrix))
    rhs = [coordinate - offset for coordinate, offset in zip(point, origin)]
    return _serialized(_solve(matrix, rhs))


def _pointer_tokens(pointer: Any) -> list[str]:
    if type(pointer) is not str or len(pointer) > _MAX_POINTER:
        raise GeometryError("POINTER_TYPE: expected a JSON pointer of at most 512 characters")
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise GeometryError("POINTER_SYNTAX: nonempty JSON pointers must begin with /")
    tokens = pointer[1:].split("/")
    if any(_BAD_ESCAPE.search(token) is not None for token in tokens):
        raise GeometryError("POINTER_ESCAPE: only ~0 and ~1 escapes are permitted")
    return [token.replace("~1", "/").replace("~0", "~") for token in tokens]


def resolve_pointer(document: Any, pointer: Any) -> Any:
    """Resolve one exact JSON pointer through dicts/lists; never guess keys.

    The empty pointer selects the document.  List indices are canonical
    nonnegative decimal indices, with no leading zero except index zero.
    Coordinate scalar validation is performed by :func:`observe_points`.
    """
    if type(document) not in (dict, list):
        raise GeometryError("DOCUMENT_TYPE: the document root must be a dict or list")
    current = document
    for token in _pointer_tokens(pointer):
        if type(current) is dict:
            if token not in current:
                raise GeometryError("POINTER_MISSING: the exact object key is absent")
            current = current[token]
        elif type(current) is list:
            if _INDEX.fullmatch(token) is None:
                raise GeometryError("POINTER_INDEX: array indices must be canonical nonnegative integers")
            index = int(token)
            if index >= len(current):
                raise GeometryError("POINTER_MISSING: array index is outside the document")
            current = current[index]
        else:
            raise GeometryError("POINTER_CONTAINER: traversal encountered a scalar")
    return current


def observe_points(document: Any, schema: Any, frame: Any) -> dict[str, list[str]]:
    """Bind declared object IDs to base-meter points from arbitrary JSON layouts.

    At most 16 object bindings are supported.  Object IDs and complete pointer
    tuples must be unique; object ID comparisons additionally reject case-fold
    aliases.  IDs are preserved in the result.  The schema supplies all meaning:
    this function does not infer task semantics or inspect undeclared fields.
    """
    normalized = validate_frame(frame)
    size = len(normalized["matrix"])
    if type(document) not in (dict, list):
        raise GeometryError("DOCUMENT_TYPE: the document root must be a dict or list")
    if type(schema) is not dict or set(schema) != {"bindings"}:
        raise GeometryError("OBSERVATION_SCHEMA: expected exactly the bindings key")
    bindings = schema["bindings"]
    if type(bindings) is not list or len(bindings) > _MAX_OBJECTS:
        raise GeometryError("OBSERVATION_BOUND: bindings must be a list of at most 16 entries")
    seen_ids: set[str] = set()
    seen_pointers: set[tuple[str, ...]] = set()
    result: dict[str, list[str]] = {}
    for binding in bindings:
        if type(binding) is not dict or set(binding) != {"object_id", "coordinates"}:
            raise GeometryError("BINDING_SCHEMA: expected exactly object_id and coordinates")
        object_id = binding["object_id"]
        if type(object_id) is not str or _OBJECT_ID.fullmatch(object_id) is None:
            raise GeometryError("OBJECT_ID: expected a bounded ASCII identifier")
        folded = object_id.casefold()
        if folded in seen_ids:
            raise GeometryError("OBJECT_ALIAS: duplicate object IDs or case-fold aliases")
        pointers = binding["coordinates"]
        if type(pointers) is not list or len(pointers) != size:
            raise GeometryError("DIMENSION_MISMATCH: coordinate pointer count must match the frame")
        for pointer in pointers:
            _pointer_tokens(pointer)
        pointer_tuple = tuple(pointers)
        if pointer_tuple in seen_pointers:
            raise GeometryError("POINTER_ALIAS: multiple objects cannot bind the same pointer tuple")
        selected = [resolve_pointer(document, pointer) for pointer in pointers]
        result[object_id] = point_to_base(selected, normalized)
        seen_ids.add(folded)
        seen_pointers.add(pointer_tuple)
    return result


def distance_squared(a: Any, b: Any) -> Fraction:
    """Return exact squared Euclidean distance between equal-sized base points."""
    left = _values(a)
    right = _values(b, len(left))
    return _checked(sum(((x - y) ** 2 for x, y in zip(left, right)), Fraction(0)))


def add_vectors(a: Any, b: Any) -> list[str]:
    """Add two equal-sized coordinate vectors without truncating dimensions."""
    left = _values(a)
    right = _values(b, len(left))
    return _serialized([x + y for x, y in zip(left, right)])
