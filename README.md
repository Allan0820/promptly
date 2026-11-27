# Promptly

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://github.com/Allan0820/promptly/blob/main/images/promptly_logo.svg" />
  <!-- <source media="(prefers-color-scheme: light)" srcset="https://github.com/pytorch/pytorch/raw/main/docs/source/_static/img/pytorch-logo-dark.png" /> -->
  <!-- <img src="https://github.com/pytorch/pytorch/raw/main/docs/source/_static/img/pytorch-logo-dark.png" alt="PyTorch logo" /> -->
</picture>

Promptly is an experiment in a compact, readable programming language with a clear path from high-level intent to low-level execution. The goal is to make everyday programming tasks concise and predictable, while keeping the language precise enough for a compiler to check and translate.

The long-term idea is a general-purpose, Turing-complete core that can express algorithms and control flow, then connect those programs to lower-level languages and runtimes when performance or system access calls for it. Promptly is at an early prototype stage: today it has a lexer, parser, static type checker, typed JSON intermediate representation (IR), and a reference virtual machine. It does not yet generate native code or call into C, Rust, WebAssembly, or another low-level target.

## Why another language?

Programming languages often make you choose between terse notation and explicit structure. Promptly explores a middle ground:

- **Concise by design:** declarations, function signatures, and common operations use direct forms such as `LET`, `FN`, and `RETURN`.
- **Predictable syntax:** indentation defines blocks, names and keywords use uppercase spelling, and function parameters and return types are explicit.
- **Checked before execution:** the compiler checks names, calls, return paths, and types. It reports mistakes rather than guessing what a program meant.
- **A bridge to lower-level code:** a typed IR can serve as a stable boundary between Promptly source and future backends or foreign-function interfaces. That boundary is an architectural direction, not an implemented integration yet.

“Non-ambiguous” is a design goal: a given valid program should have one defined interpretation. The current implementation supports a deliberately small set of syntax and runtime rules, documented in [LANGUAGE.md](LANGUAGE.md). It is a prototype, not a formal proof that the language is ambiguity-free.

## Current status

The implemented core includes functions, immutable and mutable bindings, integer and boolean expressions, conditionals, loops, and function calls. These features are the basis for the intended Turing-complete core. The reference VM also applies a configurable step limit so that a run cannot continue indefinitely; the current runtime is therefore a bounded prototype environment.

The project also includes eager one-dimensional integer arrays and integer-column dataframes. These are small built-in libraries for trying data-oriented tasks, not replacements for NumPy or pandas.

| Available now | Planned direction |
| --- | --- |
| Lexer, parser, static type checker | Native or WebAssembly code generation |
| Deterministic typed JSON IR | Interfaces to lower-level languages and libraries |
| Reference VM with a step limit | Modules, broader types, and richer runtime facilities |
| Integer arrays and basic dataframe operations | More complete data and systems programming support |

See [LANGUAGE.md](LANGUAGE.md) for exact behavior and limitations. [LANGUAGE_DRAFT.md](LANGUAGE_DRAFT.md) contains proposals that may go beyond the current implementation.

## Install and run

Promptly currently needs Python 3.10 or newer and has no third-party dependencies.

Compile a source file to typed JSON IR:

```sh
python3 langc.py examples_data.lang
```

Compile and run its zero-argument `MAIN` function in the reference VM:

```sh
python3 langc.py examples_data.lang --run
```

By default, the compiler prints IR. `--run` executes the checked program and prints its result as JSON. Use `--entry NAME` to select a different zero-argument function and `--steps N` to set the positive VM step limit.

## One program, from source to result

This example builds a small score table, adds five points to every score, keeps scores greater than 25, and returns their sum. It is also in [`examples_data.lang`](examples_data.lang).

```text
FN MAIN() -> INT:
    LET IDS = ARANGE(1, 5)
    LET SCORES = ARRAY([12, 25, 18, 40])
    LET SCORES_WITH_BONUS = SCORES + 5
    LET ROWS = DATAFRAME("ID", IDS, "SCORE", SCORES_WITH_BONUS)
    LET PASSING = FILTER_GT(ROWS, "SCORE", 25)
    RETURN SUM(COLUMN(PASSING, "SCORE"))
```

Here is what the current compiler and VM do with it, in order:

1. **Lexing — source becomes tokens.** The lexer recognizes keywords, names, literals, operators, punctuation, and indentation. For example, the first two lines produce token sequences like:

   ```text
   FN MAIN ( ) -> INT : NEWLINE INDENT
   LET IDS = ARANGE ( 1 , 5 ) NEWLINE
   ```

   Each token also carries a source line and column so later errors can point back to the code.

2. **Parsing — tokens become program structure.** The parser groups the tokens into a `MAIN` function with an `INT` return type. Its body is an ordered list of five bindings and a return statement. Calls such as `SUM(COLUMN(...))` become nested call expressions; indentation marks the function body.

3. **Type checking — names and operations are validated.** The checker resolves each built-in, checks argument and operator types, and infers each binding's type:

   | Binding | Type | Value represented at runtime |
   | --- | --- | --- |
   | `IDS` | `ARRAY` | `[1, 2, 3, 4]` |
   | `SCORES` | `ARRAY` | `[12, 25, 18, 40]` |
   | `SCORES_WITH_BONUS` | `ARRAY` | Element-wise addition of an integer to an array |
   | `ROWS` | `FRAME` | A frame with `ID` and `SCORE` columns |
   | `PASSING` | `FRAME` | The rows whose score is greater than `25` |
   | `MAIN` result | `INT` | The sum of the passing scores |

   If, for example, the program tried to add a string to `SCORES`, compilation would stop with a type error instead of passing that operation to the VM.

4. **IR emission — checked structure becomes typed JSON.** The compiler emits a deterministic JSON representation. Every expression and binding includes its inferred type. A shortened excerpt for the bonus calculation looks like this:

   ```json
   {
     "kind": "binding",
     "name": "SCORES_WITH_BONUS",
     "type": "ARRAY",
     "value": {
       "kind": "binary",
       "op": "+",
       "left": { "kind": "name", "name": "SCORES", "type": "ARRAY" },
       "right": { "kind": "integer", "value": "5", "type": "INT" },
       "type": "ARRAY"
     }
   }
   ```

   The complete IR also preserves source locations and the remaining statements. Integer literals are encoded as decimal strings so large integers are not rounded by JSON consumers with limited numeric precision.

5. **VM execution — built-ins transform the data.** The reference VM evaluates the checked IR. The intermediate values for this example are:

   ```text
   ARANGE(1, 5)                         -> [1, 2, 3, 4]
   ARRAY([12, 25, 18, 40])              -> [12, 25, 18, 40]
   SCORES + 5                           -> [17, 30, 23, 45]
   DATAFRAME("ID", IDS, "SCORE", ...)  -> rows (1,17), (2,30), (3,23), (4,45)
   FILTER_GT(ROWS, "SCORE", 25)         -> rows (2,30), (4,45)
   COLUMN(PASSING, "SCORE")             -> [30, 45]
   SUM(...)                             -> 75
   ```

6. **Final output.** Run `python3 langc.py examples_data.lang --run` to get:

   ```json
   {"result":{"type":"INT","value":"75"}}
   ```

This shows the current end-to-end path: Promptly source → tokens → parsed structure → type-checked IR → reference VM → JSON result. A future backend could use the typed IR to target lower-level code, while preserving the source-level checks and semantics.

## Project files

- [`langc.py`](langc.py) contains the lexer, parser, type checker, typed IR emitter, VM, and command-line interface.
- [`dataframe_lib.py`](dataframe_lib.py) implements the eager array and dataframe values and built-ins.
- [`examples.py`](examples.py) demonstrates compilation and execution through the Python API.
- [`examples_data.lang`](examples_data.lang) contains the array and dataframe pipeline shown above.
- [`LANGUAGE.md`](LANGUAGE.md) documents implemented syntax, types, runtime rules, and current limits.
- [`LANGUAGE_DRAFT.md`](LANGUAGE_DRAFT.md) describes broader proposals that are not necessarily implemented.

## Learn more

Start with the pipeline example above, then read the [language reference](LANGUAGE.md) for supported constructs and precise semantics. To explore the Python API example, run:

```sh
python3 examples.py
```
