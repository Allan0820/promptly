import unittest
from pathlib import Path

from langc import LangError, VM, compile_source, encode_result


class CompilerTests(unittest.TestCase):
    def run_program(self, source: str, entry: str = "MAIN"):
        ir = compile_source(source)
        return VM(ir, step_limit=10_000).run(entry)

    def test_loop_and_function_call(self):
        source = """\
FN COUNT_TO(LIMIT: INT) -> INT:
    VAR COUNT: INT = 0
    WHILE COUNT < LIMIT:
        COUNT = COUNT + 1
    RETURN COUNT

FN MAIN() -> INT:
    RETURN COUNT_TO(10)
"""
        self.assertEqual(self.run_program(source), 10)

    def test_recursive_function_and_if_else(self):
        source = """\
FN FACT(N: INT) -> INT:
    IF N == 0:
        RETURN 1
    ELSE:
        RETURN N * FACT(N - 1)

FN MAIN() -> INT:
    RETURN FACT(5)
"""
        self.assertEqual(self.run_program(source), 120)

    def test_boolean_condition(self):
        source = """\
FN MAIN() -> INT:
    IF NOT FALSE:
        RETURN 7
    ELSE:
        RETURN 0
"""
        self.assertEqual(self.run_program(source), 7)

    def test_integer_division_truncates_toward_zero(self):
        source = """\
FN MAIN() -> INT:
    RETURN -7 / 3
"""
        self.assertEqual(self.run_program(source), -2)

    def test_remainder_has_sign_of_dividend(self):
        source = """\
FN MAIN() -> INT:
    RETURN -7 % 3
"""
        self.assertEqual(self.run_program(source), -1)

    def test_syntax_error_is_reported_in_words(self):
        source = """\
FN MAIN() -> INT
    RETURN 1
"""
        with self.assertRaisesRegex(LangError, "expected.*':'"):
            compile_source(source)

    def test_lowercase_source_is_rejected(self):
        source = """\
fn MAIN() -> INT:
    RETURN 1
"""
        with self.assertRaisesRegex(LangError, "must be uppercase"):
            compile_source(source)

    def test_type_mismatch_is_rejected(self):
        source = """\
FN MAIN() -> INT:
    LET VALUE: INT = TRUE
    RETURN VALUE
"""
        with self.assertRaisesRegex(LangError, "initializer has type BOOL, expected INT"):
            compile_source(source)

    def test_immutable_binding_cannot_be_reassigned(self):
        source = """\
FN MAIN() -> INT:
    LET VALUE = 1
    VALUE = 2
    RETURN VALUE
"""
        with self.assertRaisesRegex(LangError, "cannot assign to immutable binding VALUE"):
            compile_source(source)

    def test_non_unit_function_must_return_on_every_path(self):
        source = """\
FN MAIN() -> INT:
    IF TRUE:
        RETURN 1
"""
        with self.assertRaisesRegex(LangError, "may finish without returning INT"):
            compile_source(source)

    def test_division_by_zero_is_runtime_error(self):
        source = """\
FN MAIN() -> INT:
    RETURN 3 / 0
"""
        ir = compile_source(source)
        with self.assertRaisesRegex(LangError, "division by zero"):
            VM(ir, step_limit=100).run("MAIN")

    def test_step_limit_stops_an_infinite_loop(self):
        source = """\
FN MAIN() -> UNIT:
    WHILE TRUE:
        LET VALUE = 1
"""
        ir = compile_source(source)
        with self.assertRaisesRegex(LangError, "step limit"):
            VM(ir, step_limit=20).run("MAIN")

    def test_strings_and_homogeneous_list_literals(self):
        source = """\
FN MAIN() -> STRING:
    LET LABEL = "MiXeD \\"text\\""
    LET VALUES = ARRAY([1, 2, 3])
    RETURN LABEL
"""
        self.assertEqual(self.run_program(source), 'MiXeD "text"')

    def test_array_construction_arithmetic_and_reductions(self):
        source = """\
FN MAIN() -> INT:
    LET LEFT = ARANGE(1, 5)
    LET RIGHT = ARRAY([2, 3, 4, 5])
    LET TOTALS = LEFT * 2 + RIGHT
    RETURN SUM(TOTALS) + DOT(LEFT, RIGHT)
"""
        self.assertEqual(self.run_program(source), 74)

    def test_array_comparison_mask_filters_frame(self):
        source = """\
FN MAIN() -> INT:
    LET VALUES = ARRAY([1, 2, 3, 4])
    LET DATA = DATAFRAME("VALUE", VALUES)
    LET FILTERED = FILTER(DATA, COLUMN(DATA, "VALUE") >= 3)
    RETURN SUM(COLUMN(FILTERED, "VALUE"))
"""
        self.assertEqual(self.run_program(source), 7)

    def test_dataframe_select_sort_group_sum_and_join(self):
        source = """\
FN MAIN() -> INT:
    LET IDS = ARRAY([2, 1, 2, 1])
    LET AMOUNTS = ARRAY([5, 7, 11, 13])
    LET LEFT = DATAFRAME("ID", IDS, "AMOUNT", AMOUNTS)
    LET GROUPED = GROUP_SUM(LEFT, "ID", "AMOUNT")
    LET SORTED = SORT(GROUPED, "ID", TRUE)
    LET RIGHT = DATAFRAME("ID", ARRAY([1, 2]), "BONUS", ARRAY([100, 200]))
    LET JOINED = JOIN(SORTED, RIGHT, "ID")
    LET PICKED = SELECT(JOINED, "AMOUNT", "BONUS")
    RETURN SUM(COLUMN(PICKED, "AMOUNT")) + SUM(COLUMN(PICKED, "BONUS"))
"""
        self.assertEqual(self.run_program(source), 336)

    def test_dataframe_builtin_runtime_errors_have_locations(self):
        source = """\
FN MAIN() -> INT:
    LET DATA = DATAFRAME("A", ARRAY([1, 2]), "B", ARRAY([3]))
    RETURN NROWS(DATA)
"""
        with self.assertRaisesRegex(LangError, "all DATAFRAME columns must have the same length") as error:
            self.run_program(source)
        self.assertEqual(error.exception.line, 2)

    def test_unknown_column_is_a_runtime_error(self):
        source = """\
FN MAIN() -> INT:
    LET DATA = DATAFRAME("A", ARRAY([1]))
    RETURN SUM(COLUMN(DATA, "MISSING"))
"""
        with self.assertRaisesRegex(LangError, "column 'MISSING' does not exist") as error:
            self.run_program(source)
        self.assertEqual(error.exception.line, 3)

    def test_array_result_serialization(self):
        source = """\
FN MAIN() -> ARRAY:
    RETURN ARANGE(3)
"""
        result = self.run_program(source)
        self.assertEqual(encode_result(result), {"type": "ARRAY", "values": [0, 1, 2]})

    def test_frame_result_serialization(self):
        source = """\
FN MAIN() -> FRAME:
    RETURN DATAFRAME("ID", ARRAY([3, 4]))
"""
        result = self.run_program(source)
        self.assertEqual(encode_result(result), {
            "type": "FRAME",
            "columns": [{"name": "ID", "values": [3, 4]}],
            "rows": 2,
        })

    def test_documented_data_example(self):
        source = Path(__file__).resolve().parents[1].joinpath("examples_data.lang").read_text(encoding="utf-8")
        self.assertEqual(self.run_program(source), 75)

    def test_range_rejects_zero_step(self):
        source = """\
FN MAIN() -> INT:
    RETURN SUM(ARANGE(0, 5, 0))
"""
        with self.assertRaisesRegex(LangError, "ARANGE step cannot be zero"):
            self.run_program(source)

    def test_redefining_a_builtin_is_rejected(self):
        source = """\
FN SUM(VALUE: INT) -> INT:
    RETURN VALUE
"""
        with self.assertRaisesRegex(LangError, "SUM is a reserved library function name"):
            compile_source(source)


if __name__ == "__main__":
    unittest.main()
