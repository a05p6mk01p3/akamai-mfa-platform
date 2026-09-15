from __future__ import annotations

import ast
from pathlib import Path


path = Path(__file__).parents[1] / "app" / "server.py"
tree = ast.parse(path.read_text(encoding="utf-8"))
for node in tree.body:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        continue
    if any(
        isinstance(dec, ast.Call)
        and isinstance(dec.func, ast.Attribute)
        and dec.func.attr == "tool"
        for dec in node.decorator_list
    ):
        args = [
            arg.arg
            for arg in node.args.args
            if arg.arg != "ctx"
        ]
        print(f"{node.name}: {', '.join(args) if args else '(no args)'}")
