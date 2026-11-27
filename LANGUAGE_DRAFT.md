# Programming Language Design Draft

Status: initial design proposal. The language name and several semantics are still open.

For implemented syntax, runtime behavior, built-ins, and commands, see the [language reference](LANGUAGE.md) and [README](README.md). Examples in this draft that use modules, capabilities, generic result types, or other features beyond that reference are proposals only.

## Goal

Create one general-purpose programming language that people can learn once and use across web, data, systems, and embedded work. It has one syntax and one programming model. Platform libraries and available capabilities may differ by target.

AI tools may help write programs and connect platform APIs, but program meaning must come from a deterministic specification and compiler/runtime, not from an AI guessing intent.

## Design commitments

- Significant indentation defines blocks, following the broad style of Python.
- Keywords, built-in type names, boolean literals, and identifiers are uppercase. Lowercase spellings are rejected by the lexer.
- Text inside string literals keeps its authored case; comments are prose and may use either case.
- The grammar and runtime rules must be precise enough for independent implementations to agree.
- The core language is statically typed and Turing complete.
- Types are checked at compile time, with type inference to reduce annotation overhead.
- Platform-specific features are explicit capabilities provided by libraries or the target runtime.
- Unsupported capabilities produce a clear compile-time or deployment error.
- No implicit conversions or unspecified evaluation order in the core.

## Provisional syntax

```text
FN COUNT_TO(LIMIT: INT) -> INT:
    VAR COUNT: INT = 0
    WHILE COUNT < LIMIT:
        COUNT = COUNT + 1
    RETURN COUNT

FN MAIN() -> INT:
    RETURN COUNT_TO(10)
```

Proposed rules:

- A block starts after `:` and includes subsequent lines indented by exactly one indentation level.
- Indentation uses groups of four spaces; a nested block indents exactly four spaces more than its parent. Tabs are rejected.
- Every nonblank, noncomment source line ends one statement. Expressions cannot span lines in this initial version.
- `LET` introduces an immutable binding; `VAR` introduces a mutable binding.
- Function parameter types are written explicitly.
- Local binding types can be inferred from their initializer when unambiguous.
- Public function return types should be explicit; private function return inference is a possible convenience.
- Numeric conversions are explicit; there are no implicit conversions between numeric types.

These are starting conventions, not final syntax decisions.

## Provisional type-system direction

The language is statically typed: a program that fails type checking does not run. Type inference fills in local types where there is one clear answer, but does not change a value's type or insert conversions. The same source program must receive the same type-checking result across implementations.

```text
FN DOUBLE(VALUE: INT) -> INT:
    LET RESULT = VALUE * 2  # inferred as INT
    RETURN RESULT
```

Still to specify: the full type grammar, generic functions, inference boundaries, and whether private function return types may be omitted.

## Core grammar sketch

This grammar covers only the first executable slice. `NEWLINE`, `INDENT`, and `DEDENT` are tokens emitted by the indentation-aware lexer. Indentation uses groups of four spaces; each nested block must add exactly four spaces, and tabs are errors. Blank lines and comment-only lines do not change the indentation stack.

```ebnf
program       = { function } ;
function      = "FN", identifier, "(", [ parameters ], ")", "->", type, ":", NEWLINE,
                INDENT, statement, { statement }, DEDENT ;
parameters    = parameter, { ",", parameter } ;
parameter     = identifier, ":", type ;
type          = "INT" | "BOOL" | "UNIT" | "STRING" | "FRAME" | "ARRAY" ;

statement     = binding | assignment | call_stmt | return_stmt | if_stmt | while_stmt ;
binding       = ("LET" | "VAR"), identifier, [ ":", type ], "=", expression, NEWLINE ;
assignment    = identifier, "=", expression, NEWLINE ;
call_stmt     = call, NEWLINE ;
return_stmt   = "RETURN", [ expression ], NEWLINE ;
if_stmt       = "IF", expression, ":", NEWLINE, INDENT, statement, { statement }, DEDENT,
                [ "ELSE", ":", NEWLINE, INDENT, statement, { statement }, DEDENT ] ;
while_stmt    = "WHILE", expression, ":", NEWLINE, INDENT, statement, { statement }, DEDENT ;

expression    = comparison ;
comparison    = sum, [ ("==" | "<" | "<=" | ">" | ">="), sum ] ;
sum           = product, { ("+" | "-"), product } ;
product       = unary, { ("*" | "/" | "%"), unary } ;
unary         = ( "-" | "NOT" ), unary | primary ;
primary       = integer | string | boolean | identifier | call | list | "(", expression, ")" ;
list          = "[", [ expression, { ",", expression }, [ "," ] ], "]" ;
call          = identifier, "(", [ arguments ], ")" ;
arguments     = expression, { ",", expression } ;
boolean       = "TRUE" | "FALSE" ;
string        = '"', { string_character | escape }, '"' ;
identifier    = letter, { letter | digit | "_" } ;
letter        = "A" | "B" | ... | "Z" ;
digit         = "0" | "1" | ... | "9" ;
```

`identifier` begins with `A`–`Z` and continues with `A`–`Z`, `0`–`9`, or `_`. Lowercase letters are not permitted in identifiers in this initial version.

Operator precedence is fixed by the grammar: unary, multiplication/division/remainder, addition/subtraction, then one comparison. Chained comparisons are rejected in this initial slice. Function calls are restricted to named functions. Lists are currently accepted as literals for array construction; general collection types, modules, and capability declarations remain future work.

## Core type-checking rules (proposal)

- Each name resolves to exactly one declaration in its lexical scope; using an undeclared name is an error.
- A binding with an annotation must have an initializer of that type. Without an annotation, its type is inferred from the initializer.
- `LET` cannot be reassigned; `VAR` can be reassigned only with a value of the same type.
- Conditions for `IF` and `WHILE` must have type `BOOL`.
- Arithmetic operators require `INT`; comparisons of `INT` produce `BOOL`; equality requires equal operand types and produces `BOOL`.
- Function arguments must match the declared parameter types and arity.
- A standalone expression statement must be a function call; its return value, if any, is discarded.
- Every function returns a value matching its declared return type; a function declared `UNIT` may use a bare `RETURN` or reach its end.
- `INT` is provisionally an unbounded signed integer in the abstract language semantics. Implementations may report a defined resource-exhaustion error on finite targets.

These rules need a more formal typing judgment before the draft is considered a language specification.

## Runtime rules in the reference compiler

- Expressions are evaluated left to right. Function arguments are evaluated left to right.
- `INT` is mathematical signed integer arithmetic with no fixed-width overflow.
- `/` divides integers with the quotient truncated toward zero. `%` returns the remainder `A - (A / B) * B`, so a nonzero remainder has the sign of `A`.
- Division or remainder by zero is a runtime error.
- `IF` evaluates exactly one branch. `WHILE` evaluates its condition before each iteration.
- A function's parameters and top-level local bindings share a scope. Each `IF` branch and each `WHILE` iteration has a fresh nested scope. Inner scopes may shadow outer names; redeclaring a name in the same scope is an error.
- A non-`UNIT` function must return on every path. The checker does not assume a loop executes, even when its condition is `TRUE`.

## Reference compiler

`langc.py` is the initial compiler implementation. It parses and type-checks the supported core, then emits deterministic JSON typed IR. Integer literals in the JSON IR are decimal strings, preserving exact values in consumers with limited numeric precision. `--run` executes that checked IR in a reference virtual machine. The VM has a configurable step limit, so a run may stop with a resource-limit error even though the abstract language is Turing complete. The compiler currently does not implement modules, general collection types, capability declarations, native machine-code output, or multiline expressions.

Syntax and semantic errors are reported in plain language with the source line and a caret showing the location. The parser and type checker should report what was expected or what types conflicted, rather than exposing parser internals or compiler stack traces.

```sh
python3 langc.py program.lang
python3 langc.py program.lang --run
```

`--entry NAME` selects a zero-argument entry function, and `--steps N` changes the execution step limit for `--run`.

The compiler makes the meaning of a valid source program explicit. In source code, `1 + 1 + 1` is integer arithmetic because each unquoted numeric literal has type `INT`; the compiler should not ask whether those literals were meant as text. String literals use double quotes, so `"1"` is text while `1` is an integer.

## Initial NumPy and pandas-style library slice

The reference compiler also includes a small eager numerical and tabular library. Library calls are built in for now; there is no import syntax yet. `ARRAY` is a one-dimensional integer array, and `FRAME` is a table with named integer columns. These values are immutable: operations create new arrays or frames.

```text
FN MAIN() -> INT:
    LET IDS = ARANGE(1, 5)
    LET SCORES = ARRAY([12, 25, 18, 40])
    LET ROWS = DATAFRAME("ID", IDS, "SCORE", SCORES)
    LET PASSING = FILTER_GT(ROWS, "SCORE", 20)
    RETURN SUM(COLUMN(PASSING, "SCORE"))
```

Available NumPy-inspired calls are `ARRAY`, `ARANGE`, `ZEROS`, `ONES`, `SHAPE`, `SUM`, `MIN`, `MAX`, `LENGTH`, `CONCAT`, and `DOT`. Integer arrays support element-wise `+`, `-`, `*`, `/`, `%`, and comparisons with another equal-length array or an integer scalar. Comparisons produce a boolean mask.

Available pandas-inspired calls are `DATAFRAME` (alternating string names and arrays), `COLUMN`, `SELECT`, `FILTER`, `FILTER_GT`, `FILTER_EQ`, `HEAD`, `NROWS`, `SORT`, `GROUP_SUM`, and `JOIN`. `FILTER` accepts a boolean mask, including one produced by comparing a column array. `JOIN` is an inner join. Column names are checked at runtime because the current type system does not carry dataframe schemas.

Run the included example with `python3 langc.py examples_data.lang --run`.

This is an initial subset, not a port of all pandas or NumPy. It currently supports one-dimensional integer arrays, integer dataframe columns, eager execution, and no missing values, floating-point dtype, broadcasting, multidimensional arrays, indexing syntax, outer joins, or file I/O. Those need additional type-system and library design work before they can have well-defined cross-target semantics.

An AI layer still has to translate a user's natural-language request into source code. If the request leaves a meaningful choice unclear, that layer should ask a short clarification before generating code. The compiler handles syntax and type errors in code and can explain likely fixes, but it cannot recover intent absent from the source.

## Shared core and platform capabilities

Programs use the same core syntax on every target. Platform APIs are imported as libraries and declare the capabilities they need. For example, a web program may use `Network` and `HttpServer`; an embedded program may use `GPIO` and `Timer`. A target must provide the requested capability, or the build reports that it is unavailable.

```text
USE DEVICE.GPIO

FN MAIN() -> RESULT[UNIT, ERROR] REQUIRES GPIO:
    LET LED = GPIO.PIN(13)
    LED.WRITE(TRUE)
    RETURN OK(UNIT)
```

The capability declaration and API above are illustrative; their exact syntax and behavior remain to be specified.

## Turing completeness

The core will provide conditional execution, mutable state, and an unbounded loop (or equivalent general recursion). Its abstract machine has access to unbounded memory. Real targets have finite resources, so execution can still fail with a specified resource-exhaustion error.

## Open design decisions

1. Exact type system, including integer sizes, collections, and nullability.
2. Error handling and resource cleanup.
3. Concurrency and asynchronous execution semantics.
4. Capability declaration and library packaging syntax.
5. Memory model and how the language maps to small embedded targets.
6. Initial implementation strategy and first supported targets.

## Next milestone

Turn the implemented core into a frozen versioned specification, then add modules and capability declarations before building a target backend. The current compiler is a front end plus typed IR and reference VM; it is not yet a native or WebAssembly code generator.
