"""Run this file to see the core language and dataframe example in action."""

import json
from pathlib import Path

from langc import VM, compile_source, encode_result


SOURCE = """\
FN COUNT_TO(LIMIT: INT) -> INT:
    VAR COUNT: INT = 0
    WHILE COUNT < LIMIT:
        COUNT = COUNT + 1
    RETURN COUNT

FN MAIN() -> INT:
    RETURN COUNT_TO(10)
"""


def main() -> None:
    print("Core language example:")
    print(SOURCE)
    core_ir = compile_source(SOURCE)
    core_result = VM(core_ir, step_limit=1_000).run("MAIN")
    print(f"Core result: {encode_result(core_result)}")

    data_source = Path(__file__).with_name("examples_data.lang").read_text(encoding="utf-8")
    print("\nArray and dataframe example:")
    print(data_source)
    data_ir = compile_source(data_source)
    data_result = VM(data_ir, step_limit=1_000).run("MAIN")
    print(f"Data result: {encode_result(data_result)}")

    print("\nCore typed JSON IR:")
    print(json.dumps({"language_ir": 1, "functions": core_ir}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
