"""Small, deterministic NumPy/pandas-inspired runtime used by langc.

This is an intentionally compact first slice: one-dimensional integer arrays
and dataframes whose columns are one-dimensional integer arrays.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class LibraryError(ValueError):
    pass


@dataclass(frozen=True)
class NDArray:
    values: tuple[int, ...]

    def __len__(self) -> int:
        return len(self.values)


@dataclass(frozen=True)
class DataFrame:
    columns: tuple[tuple[str, NDArray], ...]

    @property
    def row_count(self) -> int:
        return len(self.columns[0][1]) if self.columns else 0

    def get(self, name: str) -> NDArray:
        for column_name, values in self.columns:
            if column_name == name:
                return values
        raise LibraryError(f"column {name!r} does not exist")


def _as_array(value: Any) -> NDArray:
    if not isinstance(value, NDArray):
        raise LibraryError("expected an ARRAY")
    return value


def _integer(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise LibraryError("expected an INT")
    return value


def call_builtin(name: str, args: list[Any]) -> Any:
    """Run a library call. Return NotImplemented for non-library names."""
    if name not in BUILTINS:
        return NotImplemented
    if name == "ARRAY":
        (values,) = args
        if not isinstance(values, (list, tuple)):
            raise LibraryError("ARRAY expects a list of INT values")
        return NDArray(tuple(_integer(value) for value in values))
    if name == "ARANGE":
        if len(args) == 1:
            start, stop, step = 0, _integer(args[0]), 1
        elif len(args) == 2:
            start, stop = map(_integer, args)
            step = 1
        else:
            start, stop, step = map(_integer, args)
        if step == 0:
            raise LibraryError("ARANGE step cannot be zero")
        return NDArray(tuple(range(start, stop, step)))
    if name in {"ZEROS", "ONES"}:
        (size,) = args
        size = _integer(size)
        if size < 0:
            raise LibraryError(f"{name} size cannot be negative")
        return NDArray((0 if name == "ZEROS" else 1,) * size)
    if name == "SHAPE":
        (array,) = args
        return [len(_as_array(array))]
    if name == "SUM":
        (array,) = args
        return sum(_as_array(array).values)
    if name in {"MIN", "MAX"}:
        (array,) = args
        values = _as_array(array).values
        if not values:
            raise LibraryError(f"{name} is undefined for an empty ARRAY")
        return min(values) if name == "MIN" else max(values)
    if name == "LENGTH":
        (value,) = args
        if isinstance(value, NDArray):
            return len(value)
        if isinstance(value, DataFrame):
            return value.row_count
        raise LibraryError("LENGTH expects an ARRAY or FRAME")
    if name == "CONCAT":
        left, right = map(_as_array, args)
        return NDArray(left.values + right.values)
    if name == "DOT":
        left, right = map(_as_array, args)
        if len(left) != len(right):
            raise LibraryError("DOT arrays must have the same length")
        return sum(a * b for a, b in zip(left.values, right.values))
    if name == "DATAFRAME":
        if len(args) % 2:
            raise LibraryError("DATAFRAME expects alternating column names and arrays")
        columns = []
        seen = set()
        for index in range(0, len(args), 2):
            name_value, array_value = args[index:index + 2]
            if not isinstance(name_value, str):
                raise LibraryError("DATAFRAME column names must be STRING values")
            if name_value in seen:
                raise LibraryError(f"duplicate dataframe column {name_value!r}")
            array = _as_array(array_value)
            if columns and len(array) != len(columns[0][1]):
                raise LibraryError("all DATAFRAME columns must have the same length")
            seen.add(name_value)
            columns.append((name_value, array))
        return DataFrame(tuple(columns))
    if name == "COLUMN":
        frame, column_name = args
        if not isinstance(frame, DataFrame) or not isinstance(column_name, str):
            raise LibraryError("COLUMN expects (FRAME, STRING)")
        return frame.get(column_name)
    if name == "SELECT":
        frame, *names = args
        if not isinstance(frame, DataFrame) or not all(isinstance(n, str) for n in names):
            raise LibraryError("SELECT expects a FRAME followed by STRING column names")
        selected = []
        for name_value in names:
            if any(name_value == existing for existing, _ in selected):
                raise LibraryError(f"duplicate selected column {name_value!r}")
            selected.append((name_value, frame.get(name_value)))
        if not selected:
            raise LibraryError("SELECT requires at least one column name")
        return DataFrame(tuple(selected))
    if name == "FILTER":
        frame, mask = args
        if not isinstance(frame, DataFrame) or not isinstance(mask, NDArray):
            raise LibraryError("FILTER expects (FRAME, boolean ARRAY)")
        if len(mask) != frame.row_count:
            raise LibraryError("FILTER mask length must match dataframe row count")
        if any(not isinstance(value, bool) for value in mask.values):
            raise LibraryError("FILTER mask must contain BOOL values")
        columns = tuple((column, NDArray(tuple(v for v, keep in zip(values.values, mask.values) if keep)))
                        for column, values in frame.columns)
        return DataFrame(columns)
    if name == "HEAD":
        frame, count = args
        if not isinstance(frame, DataFrame):
            raise LibraryError("HEAD expects a FRAME")
        count = _integer(count)
        if count < 0:
            raise LibraryError("HEAD count cannot be negative")
        return DataFrame(tuple((column, NDArray(values.values[:count])) for column, values in frame.columns))
    if name == "NROWS":
        (frame,) = args
        if not isinstance(frame, DataFrame):
            raise LibraryError("NROWS expects a FRAME")
        return frame.row_count
    if name == "SORT":
        frame, column_name, ascending = args
        if not isinstance(frame, DataFrame) or not isinstance(column_name, str):
            raise LibraryError("SORT expects (FRAME, STRING, BOOL)")
        if not isinstance(ascending, bool):
            raise LibraryError("SORT ascending argument must be BOOL")
        order = sorted(range(frame.row_count), key=lambda index: frame.get(column_name).values[index], reverse=not ascending)
        return DataFrame(tuple((name, NDArray(tuple(values.values[index] for index in order)))
                               for name, values in frame.columns))
    if name == "GROUP_SUM":
        frame, key_name, value_name = args
        if not isinstance(frame, DataFrame) or not isinstance(key_name, str) or not isinstance(value_name, str):
            raise LibraryError("GROUP_SUM expects (FRAME, key STRING, value STRING)")
        if key_name == value_name:
            raise LibraryError("GROUP_SUM key and value columns must be different")
        keys = frame.get(key_name).values
        values = frame.get(value_name).values
        grouped: dict[int, int] = {}
        for key, value in zip(keys, values):
            grouped[key] = grouped.get(key, 0) + value
        return DataFrame(((key_name, NDArray(tuple(grouped.keys()))),
                          (value_name, NDArray(tuple(grouped.values())))))
    if name == "JOIN":
        left, right, key_name = args
        if not isinstance(left, DataFrame) or not isinstance(right, DataFrame) or not isinstance(key_name, str):
            raise LibraryError("JOIN expects (left FRAME, right FRAME, key STRING)")
        left_keys = left.get(key_name).values
        right_keys = right.get(key_name).values
        right_names = [name for name, _ in right.columns if name != key_name]
        left_names = [name for name, _ in left.columns]
        collisions = set(left_names).intersection(right_names)
        if collisions:
            raise LibraryError(f"JOIN has duplicate non-key column {sorted(collisions)[0]!r}")
        right_rows: dict[int, list[int]] = {}
        for index, key in enumerate(right_keys):
            right_rows.setdefault(key, []).append(index)
        pairs = [(left_index, right_index) for left_index, key in enumerate(left_keys)
                 for right_index in right_rows.get(key, [])]
        columns = []
        for name, values in left.columns:
            columns.append((name, NDArray(tuple(values.values[left_index] for left_index, _ in pairs))))
        for name, values in right.columns:
            if name != key_name:
                columns.append((name, NDArray(tuple(values.values[right_index] for _, right_index in pairs))))
        return DataFrame(tuple(columns))
    if name == "ADD":
        left, right = args
        if isinstance(left, NDArray) and isinstance(right, NDArray):
            if len(left) != len(right):
                raise LibraryError("array operands must have the same length")
            return NDArray(tuple(a + b for a, b in zip(left.values, right.values)))
        if isinstance(left, NDArray):
            scalar = _integer(right)
            return NDArray(tuple(value + scalar for value in left.values))
        if isinstance(right, NDArray):
            scalar = _integer(left)
            return NDArray(tuple(scalar + value for value in right.values))
        return _integer(left) + _integer(right)
    if name == "FILTER_GT":
        frame, column_name, threshold = args
        if not isinstance(frame, DataFrame) or not isinstance(column_name, str):
            raise LibraryError("FILTER_GT expects (FRAME, STRING, INT)")
        threshold = _integer(threshold)
        mask = NDArray(tuple(value > threshold for value in frame.get(column_name).values))
        return call_builtin("FILTER", [frame, mask])
    if name == "FILTER_EQ":
        frame, column_name, expected = args
        if not isinstance(frame, DataFrame) or not isinstance(column_name, str):
            raise LibraryError("FILTER_EQ expects (FRAME, STRING, INT)")
        expected = _integer(expected)
        mask = NDArray(tuple(value == expected for value in frame.get(column_name).values))
        return call_builtin("FILTER", [frame, mask])
    raise AssertionError(name)


BUILTINS = {
    "ARRAY", "ARANGE", "ZEROS", "ONES", "SHAPE", "SUM", "MIN", "MAX", "LENGTH", "CONCAT", "DOT",
    "DATAFRAME", "COLUMN", "SELECT", "FILTER", "HEAD", "NROWS", "SORT", "GROUP_SUM", "JOIN", "ADD",
    "FILTER_GT", "FILTER_EQ",
}
