# Language reference

This document describes the behavior implemented by `langc.py` and `dataframe_lib.py`. The language and library are experimental. The separate [design draft](LANGUAGE_DRAFT.md) contains broader ideas that are not all implemented.

## Source format

- Source files are UTF-8 text, one statement per nonblank line.
- Indentation uses groups of four spaces. A nested block adds exactly four spaces. Tabs in indentation are rejected.
- Blank lines and lines whose first non-space character is `#` are ignored. A `#` outside a string starts a comment through the end of the line.
- Keywords, built-in type names, boolean literals, and identifiers are uppercase. Identifiers begin with `A`–`Z` and may continue with uppercase letters, decimal digits, or `_`. Lowercase identifiers are rejected.
- Strings use double quotes and JSON-style escapes. Their contents are case-sensitive and may be lowercase.
- Integer literals are decimal, signed by the unary `-` operator, and unbounded by the abstract language semantics.

## Types

The implemented type names are:

| Type | Meaning |
| --- | --- |
| `INT` | Arbitrary precision signed integer. |
| `BOOL` | `TRUE` or `FALSE`. |
| `STRING` | Immutable string value. |
| `UNIT` | No meaningful value; used for procedures. |
| `ARRAY` | One-dimensional immutable array of `INT`. |
| `FRAME` | Immutable table with named `ARRAY` columns of equal length. |

The checker infers local binding types from initializers. An annotation, when supplied, must match exactly; there are no implicit conversions. Array comparison expressions have an internal boolean-mask type that can be passed to `FILTER`, but it is not a source-level annotation type. List literals currently exist to construct arrays and are not general mutable collections.

## Functions and statements

Every program contains at least one function. Function parameters and return types are explicit. Functions can call functions declared anywhere in the program.

```text
FN DOUBLE(VALUE: INT) -> INT:
    LET RESULT = VALUE * 2
    RETURN RESULT

FN MAIN() -> INT:
    RETURN DOUBLE(21)
```

Supported statements:

- `LET NAME = EXPRESSION` creates an immutable binding.
- `VAR NAME = EXPRESSION` creates a mutable binding.
- An optional `: TYPE` annotation can follow a binding name, as in `LET COUNT: INT = 0`.
- `NAME = EXPRESSION` assigns to an existing `VAR` binding of the same type.
- `RETURN EXPRESSION` returns a value. `RETURN` by itself is allowed only in a `UNIT` function.
- `IF CONDITION:` and optional `ELSE:` choose a branch. Conditions must be `BOOL`.
- `WHILE CONDITION:` repeats a block while its condition is `TRUE`.
- A function call may be used as a standalone statement; other expression statements are rejected.

Each function has a scope shared by its parameters and top-level local bindings. Each `IF` branch and each `WHILE` iteration creates a nested scope. Nested scopes may shadow outer names; a name cannot be redeclared in the same scope. A non-`UNIT` function must return on every statically recognized path. The checker does not assume a loop executes, even if its condition is `TRUE`.

Blocks must contain at least one statement. There are no `ELIF`, `BREAK`, or `CONTINUE` statements in this version.

## Expressions and operators

Expressions include integer, boolean, and string literals; names; function calls; parenthesized expressions; and homogeneous list literals. Lists may contain `INT`, `BOOL`, or `STRING` values, but only integer lists can currently be passed to `ARRAY`.

Operator precedence from highest to lowest:

| Operators | Behavior |
| --- | --- |
| unary `-`, `NOT` | Integer negation; boolean negation. |
| `*`, `/`, `%` | Integer multiply, divide, remainder. Arrays also support element-wise operations. |
| `+`, `-` | Integer addition/subtraction. Arrays support element-wise operations and scalar integer operands. |
| `==`, `<`, `<=`, `>`, `>=` | Scalar comparisons return `BOOL`; array comparisons return a boolean mask. |

Comparisons do not chain: `A < B < C` is an error. There is no `!=`, `AND`, or `OR` operator yet. Use `NOT` and nested `IF` statements for boolean logic.

`INT / INT` truncates toward zero. `%` is defined as `A - (A / B) * B`, so a nonzero remainder has the sign of `A`. Division and remainder by zero are runtime errors. These rules also apply element by element to array division and remainder.

Array-to-array operators require equal lengths. Array-to-scalar operators apply the integer operation to every element; there is no general broadcasting. Array comparisons produce a boolean mask. Scalar `==` requires equal operand types.

## Array library

Library functions are built in; the language does not have import syntax yet.

| Call | Result and behavior |
| --- | --- |
| `ARRAY([1, 2, 3])` | Creates an integer `ARRAY`. The literal must contain only integers. |
| `ARANGE(STOP)` | Values from `0` up to, but excluding, `STOP`. |
| `ARANGE(START, STOP)` | Values from `START` up to, but excluding, `STOP`, with step `1`. |
| `ARANGE(START, STOP, STEP)` | Values from `START` toward `STOP` using `STEP`; zero step is an error. |
| `ZEROS(SIZE)` / `ONES(SIZE)` | Creates an array of the requested nonnegative length. |
| `SHAPE(ARRAY)` | Returns a one-item integer list containing the array length. |
| `LENGTH(ARRAY)` | Returns the number of array elements. |
| `SUM(ARRAY)` | Returns the integer sum; the empty array sums to `0`. |
| `MIN(ARRAY)` / `MAX(ARRAY)` | Returns the smallest/largest value; empty arrays are runtime errors. |
| `CONCAT(LEFT, RIGHT)` | Concatenates two arrays. |
| `DOT(LEFT, RIGHT)` | Returns the integer dot product; lengths must match. |
| `ADD(ARRAY, INT)`, `ADD(INT, ARRAY)`, `ADD(ARRAY, ARRAY)` | Convenience addition operation; array lengths must match when both operands are arrays. |

Example:

```text
FN MAIN() -> INT:
    LET VALUES = ARANGE(1, 5)
    LET DOUBLED = VALUES * 2
    RETURN DOT(VALUES, DOUBLED)
```

## Dataframe library

`DATAFRAME` builds an immutable frame from alternating string names and arrays. At least one column is required. All columns must have equal lengths and unique names. Column labels are checked at runtime, because the current type system does not encode a frame's schema.

| Call | Behavior |
| --- | --- |
| `DATAFRAME("ID", IDS, "SCORE", SCORES)` | Builds a frame from named integer arrays. |
| `COLUMN(FRAME, "SCORE")` | Returns one column as an array. Unknown columns are runtime errors. |
| `SELECT(FRAME, "ID", "SCORE")` | Returns a frame with the requested columns in the given order. Requires at least one column. |
| `FILTER(FRAME, MASK)` | Keeps rows whose boolean mask value is `TRUE`. The mask length must match the row count. |
| `FILTER_GT(FRAME, "SCORE", 20)` | Keeps rows where the integer column is greater than the threshold. |
| `FILTER_EQ(FRAME, "SCORE", 20)` | Keeps rows where the integer column equals the threshold. |
| `HEAD(FRAME, COUNT)` | Returns up to the first `COUNT` rows; negative counts are errors. |
| `NROWS(FRAME)` / `LENGTH(FRAME)` | Returns the row count. |
| `SORT(FRAME, "SCORE", TRUE)` | Sorts ascending by the named integer column. Use `FALSE` for descending order. Sorting is stable. |
| `GROUP_SUM(FRAME, "TEAM", "SCORE")` | Returns a two-column frame containing each first-seen key and the sum of its values. Key and value columns must differ. |
| `JOIN(LEFT, RIGHT, "ID")` | Inner joins on the named key. Duplicate non-key column names are runtime errors. Duplicate keys produce all matching row pairs. |

Example:

```text
FN MAIN() -> INT:
    LET IDS = ARANGE(1, 5)
    LET SCORES = ARRAY([12, 25, 18, 40])
    LET ROWS = DATAFRAME("ID", IDS, "SCORE", SCORES)
    LET PASSING = FILTER_GT(ROWS, "SCORE", 20)
    RETURN SUM(COLUMN(PASSING, "SCORE"))
```

## Compiler and virtual machine

Compile to deterministic typed JSON IR:

```sh
python3 langc.py program.lang
```

Run the zero-argument `MAIN` function:

```sh
python3 langc.py program.lang --run
```

Use `--entry NAME` to select a different zero-argument function and `--steps N` to set the positive VM step limit. The VM counts evaluated statements, expressions, and loop iterations. Long-running loops stop with a resource-limit error when they exceed the limit. The implementation is a front end and reference VM, not a native-code compiler.

Integer values in typed JSON IR are decimal strings, preserving arbitrary precision in consumers with limited numeric precision. Runtime scalar results are printed as JSON objects with a `type` field. Array results contain a `values` list; frame results contain ordered `columns` and a `rows` count.

Syntax and type errors include a source line, column, and caret. Runtime errors from the array/dataframe built-ins use the call site's source location.

## Current limitations

This is not a full NumPy or pandas port. The array and dataframe runtime supports only eager one-dimensional integer data. There is no floating point, missing values, multidimensional arrays, dataframe columns of strings or booleans, lazy evaluation, indexing syntax, CSV or other file I/O, grouped aggregate beyond sum, outer join, or schema-aware compile-time column checking. The core also lacks modules, generic types, exceptions, and native/WebAssembly backends. The examples and tests describe the currently implemented subset; broader ideas in `LANGUAGE_DRAFT.md` are proposals, not supported syntax.
