#!/usr/bin/env python3
"""
py-organizer: reorganizes a Python file on save.

Rules:
  Imports order:
    1. stdlib  (import x)
    2. stdlib  (from x import y)
    3. third-party (import x)
    4. third-party (from x import y)
    5. local/custom (import x)
    6. local/custom (from x import y)

  Class methods order:
    1. __init__ always first
    2. Private methods (_ prefix) A-Z
    3. Public methods A-Z

Usage:
    python organize.py <filepath>
    Prints reorganized content to stdout.
"""

import ast
import sys
import sys as _sys
import sysconfig as _sysconfig
import textwrap

from pathlib import Path

_STDLIB_NAMES: set[str] = set()


def _build_stdlib_set() -> set[str]:
    """Return the set of top-level stdlib module names."""
    # Python 3.10+
    if hasattr(_sys, "stdlib_module_names"):
        return set(_sys.stdlib_module_names)
    # Fallback: use sysconfig paths
    import pkgutil, importlib.util

    stdlib_path = _sysconfig.get_paths()["stdlib"]
    names = {m.name for m in pkgutil.iter_modules([stdlib_path])}
    names.update({"builtins", "sys", "os", "io", "abc", "re"})
    return names


_STDLIB_NAMES = _build_stdlib_set()


def _top_level(module: str) -> str:
    return module.split(".")[0] if module else ""


def _is_stdlib(module: str) -> bool:
    return _top_level(module) in _STDLIB_NAMES


def _is_local(module: str) -> bool:
    """Heuristic: relative imports only. Everything else is third-party."""
    return module.startswith(".")


# ---------------------------------------------------------------------------
# Import classification
# ---------------------------------------------------------------------------

# Priority buckets (lower = earlier)
STDLIB_PLAIN = 0  # import os
STDLIB_FROM = 1  # from os import path
THIRD_PARTY_PLAIN = 2  # import requests
THIRD_PARTY_FROM = 3  # from requests import Session
LOCAL_PLAIN = 4  # import mymodule  /  from . import x
LOCAL_FROM = 5  # from mymodule import thing


def _classify_import(node: ast.stmt) -> int:
    if isinstance(node, ast.Import):
        mod = node.names[0].name
        if _is_stdlib(mod):
            return STDLIB_PLAIN
        # relative check not applicable for plain import
        return THIRD_PARTY_PLAIN

    if isinstance(node, ast.ImportFrom):
        mod = node.module or ""
        level = node.level or 0  # level > 0 means relative
        if level > 0 or _is_local(mod):
            return LOCAL_FROM
        if _is_stdlib(mod):
            return STDLIB_FROM
        return THIRD_PARTY_FROM

    return 99


def _import_sort_key(node: ast.stmt) -> tuple:
    bucket = _classify_import(node)
    # secondary: alphabetical on the raw module name
    if isinstance(node, ast.Import):
        name = node.names[0].name
    else:
        name = ("." * (node.level or 0)) + (node.module or "")
    return (bucket, name.lower())


# ---------------------------------------------------------------------------
# Source reconstruction helpers
# ---------------------------------------------------------------------------


def _node_source(source_lines: list[str], node: ast.stmt) -> str:
    """Extract the exact source lines for an AST node (handles multi-line)."""
    start = node.lineno - 1
    end = node.end_lineno
    return "".join(source_lines[start:end])


# ---------------------------------------------------------------------------
# Import block reorganization
# ---------------------------------------------------------------------------


def _reorganize_imports(source: str) -> str:
    """
    Collect all top-level import statements, sort them by PEP-8 bucket,
    replace the original block with the sorted version.
    Returns the new source string.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # Don't touch files with syntax errors
        return source

    lines = source.splitlines(keepends=True)
    import_nodes: list[ast.stmt] = []
    first_import_line = None
    last_import_line = None

    for node in ast.walk(tree):
        if not isinstance(node, ast.Module):
            continue
        for child in node.body:
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                import_nodes.append(child)
                if first_import_line is None:
                    first_import_line = child.lineno - 1
                last_import_line = child.end_lineno
        break  # only top-level module body

    if not import_nodes:
        return source

    # Sort
    import_nodes.sort(key=_import_sort_key)

    # Rebuild import block with blank lines between buckets
    new_import_lines: list[str] = []
    prev_bucket = None

    for node in import_nodes:
        bucket = _classify_import(node)
        if prev_bucket is not None and bucket != prev_bucket:
            new_import_lines.append("\n")
        new_import_lines.append(_node_source(lines, node))
        prev_bucket = bucket

    # Replace original import region in source
    before = lines[:first_import_line]
    after = lines[last_import_line:]

    return "".join(before + new_import_lines + after)


# ---------------------------------------------------------------------------
# Method sorting inside classes
# ---------------------------------------------------------------------------


def _method_sort_key(node: ast.stmt) -> tuple:
    """
    Sort order for class methods:
      0 � __init__
      1 � other dunder methods (__x__)
      2 � private methods (_x, not dunder)
      3 � public methods
    Within each group: alphabetical.
    """
    if not isinstance(node, ast.FunctionDef):
        return (99, "")

    name = node.name
    if name == "__init__":
        return (0, "")
    if name.startswith("__") and name.endswith("__"):
        return (1, name.lower())
    if name.startswith("_"):
        return (2, name.lower())
    return (3, name.lower())


def _reorganize_class_methods(source: str) -> str:
    """
    For each class in the module, sort its methods.
    Decorators and docstrings are preserved.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source

    lines = source.splitlines(keepends=True)
    replacements: list[tuple[int, int, str]] = []  # (start_line, end_line, new_src)

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue

        # Separate class-level non-method nodes from methods
        methods = [n for n in node.body if isinstance(n, ast.FunctionDef)]
        non_methods = [n for n in node.body if not isinstance(n, ast.FunctionDef)]

        if len(methods) <= 1:
            continue  # nothing to sort

        sorted_methods = sorted(methods, key=_method_sort_key)
        if [m.name for m in methods] == [m.name for m in sorted_methods]:
            continue  # already in order

        # Collect source for each method (including decorators)
        def method_source(m: ast.FunctionDef) -> str:
            # Walk back to include decorators
            deco_start = (
                m.decorator_list[0].lineno - 1 if m.decorator_list else m.lineno - 1
            )
            end = m.end_lineno
            raw = "".join(lines[deco_start:end])
            return raw

        sorted_sources = [method_source(m) for m in sorted_methods]

        # Determine the region to replace: from first method to last method
        first_method = methods[0]
        last_method = methods[-1]

        deco_start = (
            first_method.decorator_list[0].lineno - 1
            if first_method.decorator_list
            else first_method.lineno - 1
        )
        region_start = deco_start
        region_end = last_method.end_lineno

        # Detect indentation from the first method line
        indent = ""
        first_line = lines[first_method.lineno - 1]
        for ch in first_line:
            if ch in (" ", "\t"):
                indent += ch
            else:
                break

        # Join sorted methods with a blank line between each
        new_block = "\n\n".join(s.rstrip("\n") for s in sorted_sources) + "\n"

        replacements.append((region_start, region_end, new_block))

    if not replacements:
        return source

    # Apply replacements in reverse order (bottom-up) to preserve line numbers
    replacements.sort(key=lambda r: r[0], reverse=True)
    for start, end, new_block in replacements:
        lines[start:end] = [new_block]

    return "".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def organize(filepath: str) -> str:
    source = Path(filepath).read_text(encoding="utf-8")
    source = _reorganize_imports(source)
    source = _reorganize_class_methods(source)
    return source


if __name__ == "__main__":
    # Force UTF-8 for stdout/stderr to avoid charmap errors on Windows
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2:
        print("Usage: organize.py <filepath>", file=sys.stderr)
        sys.exit(1)

    filepath = sys.argv[1]
    try:
        result = organize(filepath)
        sys.stdout.write(result)
    except Exception as e:
        print(f"[py-organizer] Fatal error: {e}", file=sys.stderr)
        sys.exit(1)
