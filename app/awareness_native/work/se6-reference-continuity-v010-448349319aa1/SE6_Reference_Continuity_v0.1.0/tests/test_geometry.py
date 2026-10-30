"""Independent arithmetic and rejection cases for declared affine geometry."""

import copy
import unittest
from fractions import Fraction

from se6_reference.geometry import (
    GeometryError,
    add_vectors,
    distance_squared,
    observe_points,
    point_from_base,
    point_to_base,
    rational,
    resolve_pointer,
    validate_frame,
    vector_to_base,
)


def frame(matrix=None, origin=None, unit="m"):
    return {
        "id": "work-frame",
        "dimension": "length",
        "unit": unit,
        "matrix": matrix if matrix is not None else [["1", "0"], ["0", "1"]],
        "origin": origin if origin is not None else ["0", "0"],
    }


class ExactGeometryTests(unittest.TestCase):
    def test_shifted_centimeter_frame_has_hand_calculated_result(self):
        declared = frame([["1/100", "0"], ["0", "1/100"]], ["10", "-2"], "cm")
        self.assertEqual(point_to_base(["150", "25"], declared), ["23/2", "-7/4"])
        self.assertEqual(vector_to_base(["150", "25"], declared), ["3/2", "1/4"])
        self.assertEqual(point_from_base(["23/2", "-7/4"], declared), ["150", "25"])

    def test_rotated_frame_uses_matrix_row_order_and_no_vector_origin(self):
        declared = frame([["0", "-1"], ["1", "0"]], ["3", "4"])
        self.assertEqual(point_to_base(["2", "5"], declared), ["-2", "6"])
        self.assertEqual(vector_to_base(["2", "5"], declared), ["-5", "2"])
        self.assertEqual(point_from_base(["-2", "6"], declared), ["2", "5"])

    def test_three_dimensional_shear_and_axis_swap_inverse(self):
        declared = frame(
            [["0", "2", "0"], ["1", "1", "0"], ["0", "0", "1/2"]],
            ["1", "-2", "3"],
        )
        self.assertEqual(point_to_base(["4", "5", "6"], declared), ["11", "7", "6"])
        self.assertEqual(point_from_base(["11", "7", "6"], declared), ["4", "5", "6"])

    def test_one_dimensional_reflection(self):
        declared = frame([["-2"]], ["7"])
        self.assertEqual(point_to_base(["3/2"], declared), ["4"])
        self.assertEqual(point_from_base(["4"], declared), ["3/2"])

    def test_different_declared_units_can_represent_the_same_point(self):
        meters = frame()
        centimeters = frame([["1/100", "0"], ["0", "1/100"]], ["0", "0"], "cm")
        self.assertEqual(point_to_base(["1", "2"], meters), point_to_base(["100", "200"], centimeters))

    def test_frame_normalization_copies_instead_of_mutating_input(self):
        declared = frame([["2/2", "0/3"], [0, "+1"]], ["-0", "2/4"])
        before = copy.deepcopy(declared)
        normalized = validate_frame(declared)
        self.assertEqual(normalized["matrix"], [["1", "0"], ["0", "1"]])
        self.assertEqual(normalized["origin"], ["0", "1/2"])
        normalized["matrix"][0][0] = "8"
        self.assertEqual(declared, before)

    def test_singular_unknown_keys_nonlength_and_bad_shapes_rejected(self):
        bad_frames = [
            frame([["1", "2"], ["2", "4"]]),
            frame([["0"]], ["0"]),
            dict(frame(), unknown="ignored"),
            dict(frame(), dimension="time", unit="s"),
            dict(frame(), dimension="area"),
            frame([["1", "0"], ["0"]]),
            frame(origin=["0"]),
            frame(unit=""),
            frame(unit=" m"),
            frame([["1", "0"], ["0", True]]),
            frame([["1.0", "0"], ["0", "1"]]),
        ]
        for declared in bad_frames:
            with self.subTest(declared=declared), self.assertRaises(GeometryError):
                validate_frame(declared)

    def test_dimension_checks_do_not_silently_truncate(self):
        for operation in (point_to_base, vector_to_base, point_from_base):
            for values in (["1"], ["1", "2", "3"], [], ("1", "2")):
                with self.subTest(operation=operation.__name__, values=values), self.assertRaises(GeometryError):
                    operation(values, frame())
        for operation in (distance_squared, add_vectors):
            with self.assertRaises(GeometryError):
                operation(["1", "2"], ["3"])

    def test_exact_distance_and_vector_sum(self):
        self.assertEqual(distance_squared(["-1/2", "1/3"], ["1/2", "4/3"]), Fraction(2))
        self.assertEqual(add_vectors(["1/2", "-3/4"], ["1/3", "1/4"]), ["5/6", "-1/2"])


class RationalBoundaryTests(unittest.TestCase):
    def test_exact_accepted_encodings(self):
        for value, expected in [(0, Fraction(0)), (10**12, Fraction(10**12)), ("+2/4", Fraction(1, 2)), ("-001/002", Fraction(-1, 2))]:
            with self.subTest(value=value):
                self.assertEqual(rational(value), expected)

    def test_lossy_or_ambiguous_encodings_rejected(self):
        for value in (True, False, 1.0, float("inf"), float("nan"), None, Fraction(1, 2), "", " 1", "1 ", "1.25", "1e3", "1_000", "1/0", "1/-2", "2 cm", "NaN", "１２", "1\n"):
            with self.subTest(value=repr(value)), self.assertRaises(GeometryError):
                rational(value)

    def test_numeric_and_text_bounds(self):
        for value in (10**12 + 1, -(10**12 + 1), 2**128, str(2**128), "1/" + str(2**128), "0" * 65):
            with self.subTest(value=value), self.assertRaises(GeometryError):
                rational(value)
        self.assertEqual(rational("1/" + str(2**127)), Fraction(1, 2**127))

    def test_computed_results_remain_bounded(self):
        with self.assertRaises(GeometryError):
            add_vectors([str(10**12)], ["1"])
        with self.assertRaises(GeometryError):
            point_to_base([str(10**12)], frame([["2"]], ["0"]))
        with self.assertRaises(GeometryError):
            point_from_base(["2"], frame([["1/1000000000000"]], ["0"]))


class SchemaPointerTests(unittest.TestCase):
    def test_pointer_escaping_order_empty_key_and_list_index(self):
        document = {"a/b": {"~x": ["7", {"": "9"}]}, "a~1b": "11"}
        self.assertEqual(resolve_pointer(document, "/a~1b/~0x/0"), "7")
        self.assertEqual(resolve_pointer(document, "/a~1b/~0x/1/"), "9")
        self.assertEqual(resolve_pointer(document, "/a~01b"), "11")
        self.assertIs(resolve_pointer(document, ""), document)

    def test_invalid_exact_pointers_rejected(self):
        document = {"items": ["2", "3"], "Name": "4"}
        for pointer in ("items/0", "/items/01", "/items/-", "/items/-1", "/items/+1", "/items/2", "/items/0/child", "/name", "/a~", "/a~2", "/" + "a" * 512, 1):
            with self.subTest(pointer=pointer), self.assertRaises(GeometryError):
                resolve_pointer(document, pointer)

    def test_schema_binds_different_nested_layouts_without_task_adapters(self):
        declared = frame([["0", "-1/100"], ["1/100", "0"]], ["3", "4"], "cm")
        schema_a = {"bindings": [{"object_id": "Tool-A", "coordinates": ["/arbitrary/0/p", "/arbitrary/0/q"]}]}
        schema_b = {"bindings": [{"object_id": "Tool-A", "coordinates": ["/2", "/0/deeper"]}]}
        result_a = observe_points({"arbitrary": [{"p": 200, "q": "500"}]}, schema_a, declared)
        result_b = observe_points([{"deeper": "500"}, None, "200"], schema_b, declared)
        self.assertEqual(result_a, {"Tool-A": ["-2", "6"]})
        self.assertEqual(result_b, result_a)

    def test_casefold_duplicate_ids_and_duplicate_pointer_tuples_rejected(self):
        document = {"p": ["1", "2"], "q": ["3", "4"]}
        first = {"object_id": "Object-A", "coordinates": ["/p/0", "/p/1"]}
        for second in (
            {"object_id": "object-a", "coordinates": ["/q/0", "/q/1"]},
            {"object_id": "Object-A", "coordinates": ["/q/0", "/q/1"]},
            {"object_id": "Object-B", "coordinates": ["/p/0", "/p/1"]},
        ):
            with self.subTest(second=second), self.assertRaises(GeometryError):
                observe_points(document, {"bindings": [first, second]}, frame())

    def test_malformed_schema_and_quantity_encodings_rejected(self):
        document = {"x": "1", "y": "2"}
        valid = {"object_id": "A", "coordinates": ["/x", "/y"]}
        schemas = [
            {},
            {"bindings": [], "inferred": True},
            {"bindings": None},
            {"bindings": [dict(valid, guessed=True)]},
            {"bindings": [dict(valid, object_id="../A")]},
            {"bindings": [dict(valid, object_id="Å")]},
            {"bindings": [dict(valid, coordinates=["/x"])]},
            {"bindings": [dict(valid, coordinates=[True, "/y"])]},
            {"bindings": [valid] * 17},
        ]
        for schema in schemas:
            with self.subTest(schema=schema), self.assertRaises(GeometryError):
                observe_points(document, schema, frame())
        for value in (True, 1.25, {"value": "1", "unit": "s"}, "1 cm"):
            with self.subTest(value=value), self.assertRaises(GeometryError):
                observe_points({"x": value, "y": "2"}, {"bindings": [valid]}, frame())


if __name__ == "__main__":
    unittest.main()
