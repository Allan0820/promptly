#!/usr/bin/env python3
"""Reference compiler for the first uppercase language core.

By default, source is compiled to deterministic, typed JSON IR on stdout.
Pass --run to execute that checked IR with the reference virtual machine.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dataframe_lib import BUILTINS as LIBRARY_BUILTINS, DataFrame, LibraryError, NDArray, call_builtin


KEYWORDS = {"FN", "INT", "BOOL", "UNIT", "STRING", "FRAME", "ARRAY", "LET", "VAR", "RETURN", "IF", "ELSE", "WHILE", "NOT", "TRUE", "FALSE"}
ONE_CHAR = set("()[],:+-*/%<>=")

# Python 3.11+ limits decimal integer conversions by default. The language's
# INT values are unbounded, so the reference implementation removes that cap.
if hasattr(sys, "set_int_max_str_digits"):
    sys.set_int_max_str_digits(0)


@dataclass(frozen=True)
class Token:
    kind: str
    text: str
    line: int
    column: int


class LangError(Exception):
    def __init__(self, message: str, line: int, column: int):
        super().__init__(message)
        self.message = message
        self.line = line
        self.column = column


def fail(message: str, token: Token | dict[str, Any]) -> None:
    if isinstance(token, Token):
        raise LangError(message, token.line, token.column)
    raise LangError(message, token["line"], token["column"])


def lex(source: str) -> list[Token]:
    tokens: list[Token] = []
    indents = [0]
    for line_no, raw in enumerate(source.splitlines(), 1):
        if "\t" in raw[: len(raw) - len(raw.lstrip(" \t"))]:
            raise LangError("tabs are not allowed for indentation; use groups of four spaces", line_no, 1)
        indent = len(raw) - len(raw.lstrip(" "))
        text = raw[indent:]
        if not text or text.startswith("#"):
            continue
        if indent % 4:
            raise LangError("indentation must use multiples of four spaces", line_no, 1)
        if indent > indents[-1]:
            if indent != indents[-1] + 4:
                raise LangError("a new block must indent by exactly four spaces", line_no, 1)
            indents.append(indent)
            tokens.append(Token("INDENT", "", line_no, 1))
        elif indent < indents[-1]:
            while indent < indents[-1]:
                indents.pop()
                tokens.append(Token("DEDENT", "", line_no, indent + 1))
            if indent != indents[-1]:
                raise LangError("dedent does not match an earlier indentation level", line_no, indent + 1)

        i = indent
        while i < len(raw):
            ch = raw[i]
            if ch in " \r":
                i += 1
                continue
            if ch == "#":
                break
            if ch == '"':
                j = i + 1
                escaped = False
                while j < len(raw):
                    if raw[j] == '"' and not escaped:
                        break
                    if raw[j] == "\\" and not escaped:
                        escaped = True
                    else:
                        escaped = False
                    j += 1
                if j == len(raw):
                    raise LangError("unterminated string literal", line_no, i + 1)
                spelling = raw[i:j + 1]
                try:
                    value = json.loads(spelling)
                except json.JSONDecodeError as exc:
                    raise LangError("invalid string escape", line_no, i + 1) from exc
                tokens.append(Token("STRING", value, line_no, i + 1))
                i = j + 1
                continue
            if raw.startswith("->", i) or raw.startswith("==", i) or raw.startswith("<=", i) or raw.startswith(">=", i):
                op = raw[i : i + 2]
                tokens.append(Token(op, op, line_no, i + 1))
                i += 2
                continue
            if "0" <= ch <= "9":
                j = i + 1
                while j < len(raw) and "0" <= raw[j] <= "9":
                    j += 1
                tokens.append(Token("INTEGER", raw[i:j], line_no, i + 1))
                i = j
                continue
            if ch.isalpha() or ch == "_":
                j = i + 1
                while j < len(raw) and (raw[j].isalnum() or raw[j] == "_"):
                    j += 1
                word = raw[i:j]
                if not word.isascii():
                    raise LangError("identifiers must use ASCII characters", line_no, i + 1)
                if any(c.islower() for c in word):
                    raise LangError(f"{word!r} is lowercase; identifiers and keywords must be uppercase", line_no, i + 1)
                if word.startswith("_"):
                    raise LangError("identifiers must begin with A-Z", line_no, i + 1)
                tokens.append(Token(word if word in KEYWORDS else "IDENT", word, line_no, i + 1))
                i = j
                continue
            if ch in ONE_CHAR:
                tokens.append(Token(ch, ch, line_no, i + 1))
                i += 1
                continue
            raise LangError(f"unexpected character {ch!r}", line_no, i + 1)
        tokens.append(Token("NEWLINE", "", line_no, len(raw) + 1))

    eof_line = max(1, len(source.splitlines()) + 1)
    while len(indents) > 1:
        indents.pop()
        tokens.append(Token("DEDENT", "", eof_line, 1))
    tokens.append(Token("EOF", "", eof_line, 1))
    return tokens


class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos = 0

    @property
    def current(self) -> Token:
        return self.tokens[self.pos]

    def take(self, kind: str) -> Token:
        token = self.current
        if token.kind != kind:
            found = self.describe_token(token)
            expected = self.describe_kind(kind)
            fail(f"I expected {expected}, but found {found}.", token)
        self.pos += 1
        return token

    @staticmethod
    def describe_kind(kind: str) -> str:
        labels = {
            "IDENT": "an uppercase name", "INTEGER": "an integer number", "NEWLINE": "the end of this line",
            "INDENT": "an indented block", "DEDENT": "the end of this block", "EOF": "the end of the file",
            "INT": "the type INT", "BOOL": "the type BOOL", "UNIT": "the type UNIT",
            "STRING": "the type STRING", "FRAME": "the type FRAME", "ARRAY": "the type ARRAY",
            "FN": "FN", "LET": "LET", "VAR": "VAR", "RETURN": "RETURN", "IF": "IF",
            "ELSE": "ELSE", "WHILE": "WHILE", "NOT": "NOT", "TRUE": "TRUE", "FALSE": "FALSE",
        }
        return labels.get(kind, repr(kind))

    @classmethod
    def describe_token(cls, token: Token) -> str:
        if token.kind == "EOF":
            return "the end of the file"
        if token.kind == "NEWLINE":
            return "the end of the line"
        if token.kind in {"INDENT", "DEDENT"}:
            return "the start of an indented block" if token.kind == "INDENT" else "the end of an indented block"
        if token.kind == "IDENT":
            return f"the name {token.text}"
        if token.kind == "INTEGER":
            return f"the number {token.text}"
        return repr(token.text)

    def match(self, *kinds: str) -> Token | None:
        if self.current.kind in kinds:
            token = self.current
            self.pos += 1
            return token
        return None

    def program(self) -> list[dict[str, Any]]:
        functions = []
        while self.current.kind != "EOF":
            functions.append(self.function())
        if not functions:
            fail("a program must declare at least one function", self.current)
        return functions

    def function(self) -> dict[str, Any]:
        start = self.take("FN")
        name = self.take("IDENT")
        self.take("(")
        params = []
        if self.current.kind != ")":
            params.append(self.parameter())
            while self.match(","):
                params.append(self.parameter())
        self.take(")")
        self.take("->")
        return_type = self.type_name()
        self.take(":")
        self.take("NEWLINE")
        body = self.block()
        return {"kind": "function", "name": name.text, "params": params, "return_type": return_type,
                "body": body, "line": start.line, "column": start.column}

    def parameter(self) -> dict[str, Any]:
        name = self.take("IDENT")
        self.take(":")
        return {"name": name.text, "type": self.type_name(), "line": name.line, "column": name.column}

    def type_name(self) -> str:
        token = self.current
        if token.kind not in {"INT", "BOOL", "UNIT", "STRING", "FRAME", "ARRAY"}:
            fail("expected type INT, BOOL, UNIT, STRING, FRAME, or ARRAY", token)
        self.pos += 1
        return token.text

    def block(self) -> list[dict[str, Any]]:
        self.take("INDENT")
        statements = []
        while self.current.kind not in {"DEDENT", "EOF"}:
            statements.append(self.statement())
        if not statements:
            fail("blocks must contain at least one statement", self.current)
        self.take("DEDENT")
        return statements

    def statement(self) -> dict[str, Any]:
        token = self.current
        if token.kind in {"LET", "VAR"}:
            self.pos += 1
            name = self.take("IDENT")
            annotation = None
            if self.match(":"):
                annotation = self.type_name()
            self.take("=")
            value = self.expression()
            self.take("NEWLINE")
            return {"kind": "binding", "mutable": token.kind == "VAR", "name": name.text,
                    "annotation": annotation, "value": value, "line": token.line, "column": token.column}
        if token.kind == "IDENT" or token.kind in LIBRARY_BUILTINS:
            if self.tokens[self.pos + 1].kind == "(":
                call = self.expression()
                self.take("NEWLINE")
                return {"kind": "expression_statement", "expression": call,
                        "line": token.line, "column": token.column}
            name = self.take("IDENT")
            self.take("=")
            value = self.expression()
            self.take("NEWLINE")
            return {"kind": "assignment", "name": name.text, "value": value,
                    "line": name.line, "column": name.column}
        if token.kind == "RETURN":
            self.pos += 1
            value = None if self.current.kind == "NEWLINE" else self.expression()
            self.take("NEWLINE")
            return {"kind": "return", "value": value, "line": token.line, "column": token.column}
        if token.kind == "IF":
            self.pos += 1
            condition = self.expression()
            self.take(":")
            self.take("NEWLINE")
            then_body = self.block()
            else_body = None
            if self.match("ELSE"):
                self.take(":")
                self.take("NEWLINE")
                else_body = self.block()
            return {"kind": "if", "condition": condition, "then": then_body, "else": else_body,
                    "line": token.line, "column": token.column}
        if token.kind == "WHILE":
            self.pos += 1
            condition = self.expression()
            self.take(":")
            self.take("NEWLINE")
            body = self.block()
            return {"kind": "while", "condition": condition, "body": body,
                    "line": token.line, "column": token.column}
        fail("expected LET, VAR, assignment, RETURN, IF, or WHILE", token)

    def expression(self) -> dict[str, Any]:
        left = self.sum()
        if self.current.kind in {"==", "<", "<=", ">", ">="}:
            op = self.current
            self.pos += 1
            right = self.sum()
            left = {"kind": "binary", "op": op.text, "left": left, "right": right,
                    "line": op.line, "column": op.column}
            if self.current.kind in {"==", "<", "<=", ">", ">="}:
                fail("chained comparisons are not allowed; combine comparisons explicitly", self.current)
        return left

    def sum(self) -> dict[str, Any]:
        value = self.product()
        while self.current.kind in {"+", "-"}:
            op = self.current
            self.pos += 1
            value = {"kind": "binary", "op": op.text, "left": value, "right": self.product(),
                     "line": op.line, "column": op.column}
        return value

    def product(self) -> dict[str, Any]:
        value = self.unary()
        while self.current.kind in {"*", "/", "%"}:
            op = self.current
            self.pos += 1
            value = {"kind": "binary", "op": op.text, "left": value, "right": self.unary(),
                     "line": op.line, "column": op.column}
        return value

    def unary(self) -> dict[str, Any]:
        if self.current.kind in {"-", "NOT"}:
            op = self.current
            self.pos += 1
            return {"kind": "unary", "op": op.text, "operand": self.unary(),
                    "line": op.line, "column": op.column}
        return self.primary()

    def primary(self) -> dict[str, Any]:
        token = self.current
        if token.kind == "INTEGER":
            self.pos += 1
            return {"kind": "integer", "value": token.text, "line": token.line, "column": token.column}
        if token.kind == "STRING":
            self.pos += 1
            return {"kind": "string", "value": token.text, "line": token.line, "column": token.column}
        if token.kind in {"TRUE", "FALSE"}:
            self.pos += 1
            return {"kind": "boolean", "value": token.kind == "TRUE", "line": token.line, "column": token.column}
        if token.kind == "IDENT" or token.kind in LIBRARY_BUILTINS:
            self.pos += 1
            if self.match("("):
                args = []
                if self.current.kind != ")":
                    args.append(self.expression())
                    while self.match(","):
                        args.append(self.expression())
                self.take(")")
                return {"kind": "call", "name": token.text, "args": args, "line": token.line, "column": token.column}
            return {"kind": "name", "name": token.text, "line": token.line, "column": token.column}
        if self.match("("):
            value = self.expression()
            self.take(")")
            return value
        if self.match("["):
            values = []
            if self.current.kind != "]":
                values.append(self.expression())
                while self.match(","):
                    if self.current.kind == "]":
                        break
                    values.append(self.expression())
            self.take("]")
            return {"kind": "list", "values": values, "line": token.line, "column": token.column}
        fail("expected a literal, name, function call, list, or parenthesized expression", token)


@dataclass
class Symbol:
    type_name: str
    mutable: bool


class TypeChecker:
    def __init__(self, functions: list[dict[str, Any]]):
        self.functions = functions
        self.signatures: dict[str, tuple[list[str], str]] = {}
        for fn in functions:
            name = fn["name"]
            if name in LIBRARY_BUILTINS:
                fail(f"{name} is a reserved library function name", fn)
            if name in self.signatures:
                fail(f"function {name} is declared more than once", fn)
            arg_types = [p["type"] for p in fn["params"]]
            if len({p["name"] for p in fn["params"]}) != len(fn["params"]):
                fail(f"function {name} has duplicate parameter names", fn)
            self.signatures[name] = (arg_types, fn["return_type"])

    def check(self) -> list[dict[str, Any]]:
        typed = []
        for fn in self.functions:
            scopes: list[dict[str, Symbol]] = [{}]
            for param in fn["params"]:
                scopes[0][param["name"]] = Symbol(param["type"], False)
            body, returns = self.check_block(fn["body"], scopes, fn["return_type"], new_scope=False)
            if fn["return_type"] != "UNIT" and not returns:
                fail(f"function {fn['name']} may finish without returning {fn['return_type']}", fn)
            typed.append({"kind": "function", "name": fn["name"], "params": fn["params"],
                          "return_type": fn["return_type"], "body": body,
                          "line": fn["line"], "column": fn["column"]})
        return sorted(typed, key=lambda f: f["name"])

    def lookup(self, scopes: list[dict[str, Symbol]], name: str, loc: dict[str, Any]) -> Symbol:
        for scope in reversed(scopes):
            if name in scope:
                return scope[name]
        fail(f"name {name} is not declared", loc)

    def check_block(self, statements: list[dict[str, Any]], scopes: list[dict[str, Symbol]],
                    return_type: str, new_scope: bool) -> tuple[list[dict[str, Any]], bool]:
        if new_scope:
            scopes.append({})
        checked = []
        terminated = False
        try:
            for stmt in statements:
                if terminated:
                    fail("unreachable statement after a guaranteed RETURN", stmt)
                kind = stmt["kind"]
                out = dict(stmt)
                if kind == "binding":
                    if stmt["name"] in scopes[-1]:
                        fail(f"{stmt['name']} is already declared in this scope", stmt)
                    value = self.check_expr(stmt["value"], scopes)
                    declared = stmt["annotation"] or value["type"]
                    if value["type"] != declared:
                        fail(f"initializer has type {value['type']}, expected {declared}", stmt)
                    if declared == "UNIT":
                        fail("UNIT values cannot be stored in bindings", stmt)
                    scopes[-1][stmt["name"]] = Symbol(declared, stmt["mutable"])
                    out.update({"value": value, "type": declared})
                elif kind == "assignment":
                    symbol = self.lookup(scopes, stmt["name"], stmt)
                    if not symbol.mutable:
                        fail(f"cannot assign to immutable binding {stmt['name']}", stmt)
                    value = self.check_expr(stmt["value"], scopes)
                    if value["type"] != symbol.type_name:
                        fail(f"assignment has type {value['type']}, expected {symbol.type_name}", stmt)
                    out["value"] = value
                elif kind == "expression_statement":
                    expression = self.check_expr(stmt["expression"], scopes)
                    if expression["kind"] != "call":
                        fail("only a function call may be used as a statement", stmt)
                    out["expression"] = expression
                elif kind == "return":
                    if stmt["value"] is None:
                        if return_type != "UNIT":
                            fail(f"bare RETURN is only valid in a UNIT function, not {return_type}", stmt)
                        out["value"] = None
                    else:
                        value = self.check_expr(stmt["value"], scopes)
                        if value["type"] != return_type:
                            fail(f"RETURN has type {value['type']}, expected {return_type}", stmt)
                        out["value"] = value
                    terminated = True
                elif kind == "if":
                    condition = self.check_expr(stmt["condition"], scopes)
                    if condition["type"] != "BOOL":
                        fail(f"IF condition has type {condition['type']}, expected BOOL", stmt["condition"])
                    then_body, then_returns = self.check_block(stmt["then"], scopes, return_type, new_scope=True)
                    else_body = None
                    else_returns = False
                    if stmt["else"] is not None:
                        else_body, else_returns = self.check_block(stmt["else"], scopes, return_type, new_scope=True)
                    out.update({"condition": condition, "then": then_body, "else": else_body})
                    terminated = stmt["else"] is not None and then_returns and else_returns
                elif kind == "while":
                    condition = self.check_expr(stmt["condition"], scopes)
                    if condition["type"] != "BOOL":
                        fail(f"WHILE condition has type {condition['type']}, expected BOOL", stmt["condition"])
                    body, _ = self.check_block(stmt["body"], scopes, return_type, new_scope=True)
                    out.update({"condition": condition, "body": body})
                checked.append(out)
        finally:
            if new_scope:
                scopes.pop()
        return checked, terminated

    def check_expr(self, expr: dict[str, Any], scopes: list[dict[str, Symbol]]) -> dict[str, Any]:
        out = dict(expr)
        kind = expr["kind"]
        if kind == "integer":
            # Decimal strings preserve exact INT values in JSON consumers that
            # otherwise round large JSON numbers.
            out["value"] = str(int(expr["value"]))
            out["type"] = "INT"
        elif kind == "boolean":
            out["type"] = "BOOL"
        elif kind == "string":
            out["type"] = "STRING"
        elif kind == "list":
            values = [self.check_expr(value, scopes) for value in expr["values"]]
            if values and any(value["type"] != values[0]["type"] for value in values):
                fail("list values must all have the same type", expr)
            if not values:
                element_type = "INT"
            else:
                element_type = values[0]["type"]
            if element_type not in {"INT", "BOOL", "STRING"}:
                fail("list elements must be INT, BOOL, or STRING values", expr)
            out.update({"values": values, "type": f"LIST_{element_type}"})
        elif kind == "name":
            out["type"] = self.lookup(scopes, expr["name"], expr).type_name
        elif kind == "call":
            if expr["name"] in LIBRARY_BUILTINS:
                return self.check_library_call(expr, scopes)
            signature = self.signatures.get(expr["name"])
            if signature is None:
                fail(f"function {expr['name']} is not declared", expr)
            expected, result = signature
            args = [self.check_expr(arg, scopes) for arg in expr["args"]]
            if len(args) != len(expected):
                fail(f"{expr['name']} expects {len(expected)} arguments, received {len(args)}", expr)
            for index, (arg, expected_type) in enumerate(zip(args, expected), 1):
                if arg["type"] != expected_type:
                    fail(f"argument {index} to {expr['name']} has type {arg['type']}, expected {expected_type}", arg)
            out.update({"args": args, "type": result})
        elif kind == "unary":
            operand = self.check_expr(expr["operand"], scopes)
            required = "BOOL" if expr["op"] == "NOT" else "INT"
            if operand["type"] != required:
                fail(f"operator {expr['op']} requires {required}, received {operand['type']}", expr)
            out.update({"operand": operand, "type": required})
        elif kind == "binary":
            left = self.check_expr(expr["left"], scopes)
            right = self.check_expr(expr["right"], scopes)
            op = expr["op"]
            if op in {"+", "-", "*", "/", "%", "<", "<=", ">", ">="}:
                if left["type"] == "INT" and right["type"] == "INT":
                    result = "BOOL" if op in {"<", "<=", ">", ">="} else "INT"
                elif (left["type"] == "ARRAY" and right["type"] in {"ARRAY", "INT"}) or (right["type"] == "ARRAY" and left["type"] == "INT"):
                    result = "MASK" if op in {"<", "<=", ">", ">="} else "ARRAY"
                else:
                    fail(f"operator {op} does not accept {left['type']} and {right['type']}", expr)
            else:  # ==
                if left["type"] == "ARRAY" and right["type"] in {"ARRAY", "INT"} or right["type"] == "ARRAY" and left["type"] == "INT":
                    result = "MASK"
                elif left["type"] != right["type"]:
                    fail(f"equality operands must have the same type, received {left['type']} and {right['type']}", expr)
                else:
                    result = "BOOL"
            out.update({"left": left, "right": right, "type": result})
        return out

    def check_library_call(self, expr: dict[str, Any], scopes: list[dict[str, Symbol]]) -> dict[str, Any]:
        name = expr["name"]
        args = [self.check_expr(arg, scopes) for arg in expr["args"]]
        types = [arg["type"] for arg in args]
        signatures: dict[str, tuple[list[str], str]] = {
            "ARANGE": (["INT"], "ARRAY"), "ZEROS": (["INT"], "ARRAY"), "ONES": (["INT"], "ARRAY"),
            "SHAPE": (["ARRAY"], "LIST_INT"), "SUM": (["ARRAY"], "INT"), "MIN": (["ARRAY"], "INT"),
            "MAX": (["ARRAY"], "INT"), "CONCAT": (["ARRAY", "ARRAY"], "ARRAY"),
            "DOT": (["ARRAY", "ARRAY"], "INT"), "COLUMN": (["FRAME", "STRING"], "ARRAY"),
            "FILTER": (["FRAME", "MASK"], "FRAME"), "HEAD": (["FRAME", "INT"], "FRAME"),
            "NROWS": (["FRAME"], "INT"), "FILTER_GT": (["FRAME", "STRING", "INT"], "FRAME"),
            "FILTER_EQ": (["FRAME", "STRING", "INT"], "FRAME"),
            "SORT": (["FRAME", "STRING", "BOOL"], "FRAME"),
            "GROUP_SUM": (["FRAME", "STRING", "STRING"], "FRAME"),
            "JOIN": (["FRAME", "FRAME", "STRING"], "FRAME"),
        }
        if name == "ARRAY":
            if len(args) != 1 or types[0] != "LIST_INT":
                fail("ARRAY expects a list literal of INT values, such as ARRAY([1, 2, 3])", expr)
            result = "ARRAY"
        elif name == "ARANGE":
            if len(args) not in {1, 2, 3} or any(t != "INT" for t in types):
                fail("ARANGE expects one, two, or three INT arguments", expr)
            result = "ARRAY"
        elif name == "DATAFRAME":
            if len(args) < 2 or len(args) % 2:
                fail("DATAFRAME expects alternating STRING names and ARRAY columns", expr)
            for index in range(0, len(types), 2):
                if types[index] != "STRING" or types[index + 1] != "ARRAY":
                    fail("DATAFRAME expects alternating STRING names and ARRAY columns", args[index])
            result = "FRAME"
        elif name == "SELECT":
            if len(args) < 2 or types[0] != "FRAME" or any(t != "STRING" for t in types[1:]):
                fail("SELECT expects a FRAME followed by one or more STRING column names", expr)
            result = "FRAME"
        elif name == "ADD":
            if len(args) != 2 or not all(t in {"ARRAY", "INT"} for t in types) or ("ARRAY" not in types):
                fail("ADD expects two ARRAY values, or one ARRAY and one INT", expr)
            result = "ARRAY"
        elif name == "LENGTH":
            if len(args) != 1 or types[0] not in {"ARRAY", "FRAME"}:
                fail("LENGTH expects one ARRAY or FRAME", expr)
            result = "INT"
        else:
            expected, result = signatures[name]
            if len(args) != len(expected):
                fail(f"{name} expects {len(expected)} arguments, received {len(args)}", expr)
            for index, (actual, required) in enumerate(zip(types, expected), 1):
                if actual != required:
                    fail(f"argument {index} to {name} has type {actual}, expected {required}", args[index - 1])
        out = dict(expr)
        out.update({"args": args, "type": result})
        return out


class _ReturnSignal(Exception):
    def __init__(self, value: Any):
        self.value = value


class VM:
    def __init__(self, functions: list[dict[str, Any]], step_limit: int):
        self.functions = {fn["name"]: fn for fn in functions}
        self.step_limit = step_limit
        self.steps = 0

    def tick(self, node: dict[str, Any]) -> None:
        self.steps += 1
        if self.steps > self.step_limit:
            fail(f"execution step limit ({self.step_limit}) exceeded", node)

    def run(self, name: str, args: list[Any] | None = None) -> Any:
        args = args or []
        fn = self.functions.get(name)
        if fn is None:
            raise LangError(f"entry function {name} is not declared", 1, 1)
        if len(args) != len(fn["params"]):
            raise LangError(f"entry function {name} expects {len(fn['params'])} arguments; CLI supplies none", fn["line"], fn["column"])
        scope = {p["name"]: v for p, v in zip(fn["params"], args)}
        try:
            self.execute_block(fn["body"], [scope])
        except _ReturnSignal as result:
            return result.value
        return None

    def execute_block(self, statements: list[dict[str, Any]], scopes: list[dict[str, Any]], nested: bool = False) -> None:
        if nested:
            scopes.append({})
        try:
            for stmt in statements:
                self.tick(stmt)
                kind = stmt["kind"]
                if kind == "binding":
                    scopes[-1][stmt["name"]] = self.evaluate(stmt["value"], scopes)
                elif kind == "assignment":
                    for scope in reversed(scopes):
                        if stmt["name"] in scope:
                            scope[stmt["name"]] = self.evaluate(stmt["value"], scopes)
                            break
                elif kind == "expression_statement":
                    self.evaluate(stmt["expression"], scopes)
                elif kind == "return":
                    value = None if stmt["value"] is None else self.evaluate(stmt["value"], scopes)
                    raise _ReturnSignal(value)
                elif kind == "if":
                    branch = stmt["then"] if self.evaluate(stmt["condition"], scopes) else stmt["else"]
                    if branch is not None:
                        self.execute_block(branch, scopes, nested=True)
                elif kind == "while":
                    while self.evaluate(stmt["condition"], scopes):
                        self.tick(stmt)
                        self.execute_block(stmt["body"], scopes, nested=True)
        finally:
            if nested:
                scopes.pop()

    def evaluate(self, expr: dict[str, Any], scopes: list[dict[str, Any]]) -> Any:
        self.tick(expr)
        kind = expr["kind"]
        if kind in {"integer", "boolean"}:
            return int(expr["value"]) if kind == "integer" else expr["value"]
        if kind == "string":
            return expr["value"]
        if kind == "list":
            return [self.evaluate(value, scopes) for value in expr["values"]]
        if kind == "name":
            for scope in reversed(scopes):
                if expr["name"] in scope:
                    return scope[expr["name"]]
        if kind == "call":
            values = [self.evaluate(arg, scopes) for arg in expr["args"]]
            if expr["name"] in LIBRARY_BUILTINS:
                try:
                    result = call_builtin(expr["name"], values)
                except LibraryError as exc:
                    fail(str(exc), expr)
                if result is not NotImplemented:
                    return result
            return self.run(expr["name"], values)
        if kind == "unary":
            value = self.evaluate(expr["operand"], scopes)
            return not value if expr["op"] == "NOT" else -value
        if kind == "binary":
            left = self.evaluate(expr["left"], scopes)
            right = self.evaluate(expr["right"], scopes)
            op = expr["op"]
            if isinstance(left, NDArray) or isinstance(right, NDArray):
                left_values = left.values if isinstance(left, NDArray) else None
                right_values = right.values if isinstance(right, NDArray) else None
                if left_values is not None and right_values is not None and len(left_values) != len(right_values):
                    fail("array operands must have the same length", expr)
                length = len(left_values if left_values is not None else right_values)
                pairs = zip(left_values if left_values is not None else [left] * length,
                            right_values if right_values is not None else [right] * length)
                output = []
                for a, b in pairs:
                    if op == "+": output.append(a + b)
                    elif op == "-": output.append(a - b)
                    elif op == "*": output.append(a * b)
                    elif op in {"/", "%"}:
                        if b == 0:
                            fail("division by zero", expr)
                        quotient = abs(a) // abs(b)
                        if (a < 0) != (b < 0): quotient = -quotient
                        output.append(quotient if op == "/" else a - quotient * b)
                    elif op == "<": output.append(a < b)
                    elif op == "<=": output.append(a <= b)
                    elif op == ">": output.append(a > b)
                    elif op == ">=": output.append(a >= b)
                    elif op == "==": output.append(a == b)
                return NDArray(tuple(output))
            if op == "+": return left + right
            if op == "-": return left - right
            if op == "*": return left * right
            if op in {"/", "%"}:
                if right == 0:
                    fail("division by zero", expr)
                quotient = abs(left) // abs(right)
                if (left < 0) != (right < 0): quotient = -quotient
                return quotient if op == "/" else left - quotient * right
            if op == "==": return left == right
            if op == "<": return left < right
            if op == "<=": return left <= right
            if op == ">": return left > right
            if op == ">=": return left >= right
        fail("invalid expression in compiled program", expr)


def compile_source(source: str) -> list[dict[str, Any]]:
    parsed = Parser(lex(source)).program()
    return TypeChecker(parsed).check()


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(description="Compile the uppercase language to typed JSON IR.")
    cli.add_argument("source", type=Path, help="source file to compile")
    cli.add_argument("--run", action="store_true", help="execute the compiled program instead of printing IR")
    cli.add_argument("--entry", default="MAIN", help="entry function for --run (default: MAIN)")
    cli.add_argument("--steps", type=int, default=1_000_000, help="execution step limit for --run")
    args = cli.parse_args(argv)
    try:
        source = args.source.read_text(encoding="utf-8")
        ir = compile_source(source)
        if args.run:
            if args.steps <= 0:
                raise LangError("--steps must be a positive integer", 1, 1)
            result = VM(ir, args.steps).run(args.entry)
            if result is not None:
                result = encode_result(result)
                print(json.dumps({"result": result}, separators=(",", ":")))
        else:
            print(json.dumps({"language_ir": 1, "functions": ir}, ensure_ascii=False,
                             sort_keys=True, indent=2))
        return 0
    except OSError as exc:
        print(f"{args.source}: {exc}", file=sys.stderr)
        return 2
    except LangError as exc:
        print_diagnostic(args.source, source if "source" in locals() else None, exc)
        return 1


def encode_result(value: Any) -> Any:
    if isinstance(value, NDArray):
        return {"type": "ARRAY", "values": list(value.values)}
    if isinstance(value, DataFrame):
        return {"type": "FRAME", "columns": [
            {"name": name, "values": list(column.values)} for name, column in value.columns
        ], "rows": value.row_count}
    if isinstance(value, bool):
        return {"type": "BOOL", "value": value}
    if isinstance(value, int):
        return {"type": "INT", "value": str(value)}
    if isinstance(value, str):
        return {"type": "STRING", "value": value}
    return value


def print_diagnostic(path: Path, source: str | None, error: LangError) -> None:
    print(f"{path}, line {error.line}, column {error.column}:", file=sys.stderr)
    lines = source.splitlines() if source is not None else []
    if 1 <= error.line <= len(lines):
        line = lines[error.line - 1]
        print(f"  {line}", file=sys.stderr)
        print(f"  {' ' * max(0, error.column - 1)}^", file=sys.stderr)
    print(f"  Error: {error.message}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
