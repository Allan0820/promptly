# Uppercase Language

A small reference compiler and virtual machine for an experimental, statically typed programming language. The language uses uppercase keywords and identifiers, significant indentation, and explicit function signatures. The current implementation is a language prototype: it emits typed JSON IR and can execute that IR in a reference VM. It does not yet compile to native code or WebAssembly.

## Quick start

Requires Python 3.10 or newer. No third-party packages are needed.

```sh
python3 examples.py
python3 langc.py examples_data.lang --run
```

Compile a source file to typed JSON IR:

```sh
python3 langc.py program.lang
```

Compile and run its zero-argument `MAIN` function:

```sh
python3 langc.py program.lang --run
```

Choose another zero-argument entry point or change the VM step limit with `--entry NAME` and `--steps N`.

## A small program

```text
FN COUNT_TO(LIMIT: INT) -> INT:
    VAR COUNT: INT = 0
    WHILE COUNT < LIMIT:
        COUNT = COUNT + 1
    RETURN COUNT

FN MAIN() -> INT:
    RETURN COUNT_TO(10)
```

Save it as `program.lang`, then run `python3 langc.py program.lang --run`. The VM prints a JSON result. See [LANGUAGE.md](LANGUAGE.md) for syntax, typing, runtime rules, built-ins, and current limits.

## Numerical arrays and dataframes

The language includes an initial eager library for one-dimensional integer arrays and integer-column dataframes:

```text
FN MAIN() -> INT:
    LET IDS = ARANGE(1, 5)
    LET SCORES = ARRAY([12, 25, 18, 40])
    LET ROWS = DATAFRAME("ID", IDS, "SCORE", SCORES)
    LET PASSING = FILTER_GT(ROWS, "SCORE", 20)
    RETURN SUM(COLUMN(PASSING, "SCORE"))
```

The sample returns `65`. The available functions include array construction and arithmetic, dataframe selection and filtering, sorting, grouped sums, and inner joins. This is a small language-native subset inspired by NumPy and pandas, not a compatibility layer for either Python package.

## Tests

Run the unit suite with:

```sh
python3 -m unittest discover -s tests -v
```

## Project files

- `langc.py` contains the lexer, parser, type checker, typed IR emitter, VM, and command-line interface.
- `dataframe_lib.py` implements the eager array and dataframe runtime values and built-ins.
- `examples.py` demonstrates compilation and execution through the Python API.
- `examples_data.lang` demonstrates the array and dataframe APIs in the language.
- `LANGUAGE.md` describes the implemented language and its provisional library semantics.
- `LANGUAGE_DRAFT.md` retains the broader design proposal for future language features.
# promptly
