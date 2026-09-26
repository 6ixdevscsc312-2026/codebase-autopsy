"""
ingest.py
Walks a repository, parses each Python file with `ast`, and extracts a
structural summary: imports, defined functions/classes, docstrings, and
calls made. This becomes the raw material for the dependency graph and
for the "declared vs observed" reasoning step.
"""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass, field


@dataclass
class FunctionInfo:
    name: str
    docstring: str | None
    calls: list[str] = field(default_factory=list)
    lineno: int = 0


@dataclass
class ClassInfo:
    name: str
    docstring: str | None
    methods: list[str] = field(default_factory=list)
    lineno: int = 0


@dataclass
class ModuleInfo:
    path: str  # path relative to repo root
    docstring: str | None
    imports: list[str] = field(default_factory=list)
    functions: list[FunctionInfo] = field(default_factory=list)
    classes: list[ClassInfo] = field(default_factory=list)
    module_calls: list[str] = field(default_factory=list)  # calls made at module scope
    loc: int = 0
    raw_source: str = ""


class _CallCollector(ast.NodeVisitor):
    """Collects the names of everything a function body calls.

    Handles:
    - Regular calls: foo(), obj.method()
    - Awaited calls: await foo(), await obj.method()
    - match/case MatchClass patterns: case Point(x=0) — cls name treated as a call
      (both ast.Name and ast.Attribute forms, e.g. pkg.Point)
    """

    def __init__(self) -> None:
        self.calls: list[str] = []

    def _record_func(self, func_node: ast.expr) -> None:
        """Extract a call name from an ast.Name or ast.Attribute node."""
        if isinstance(func_node, ast.Name):
            self.calls.append(func_node.id)
        elif isinstance(func_node, ast.Attribute):
            self.calls.append(func_node.attr)

    def visit_Call(self, node: ast.Call) -> None:
        self._record_func(node.func)
        self.generic_visit(node)

    def visit_MatchClass(self, node: ast.MatchClass) -> None:
        self._record_func(node.cls)
        self.generic_visit(node)


def _get_docstring(node) -> str | None:
    try:
        return ast.get_docstring(node)
    except TypeError:
        return None


def parse_file(filepath: str, repo_root: str) -> ModuleInfo | None:
    """Parse a single .py file into a ModuleInfo. Returns None on syntax errors
    (we don't want one broken file to kill the whole scan)."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            source = f.read()
        tree = ast.parse(source, filename=filepath)
    except (SyntaxError, UnicodeDecodeError, OSError):
        return None

    rel_path = os.path.relpath(filepath, repo_root)
    module = ModuleInfo(
        path=rel_path,
        docstring=_get_docstring(tree),
        loc=len(source.splitlines()),
        raw_source=source,
    )

    # Collect calls made at module scope (outside any function or class).
    # Walk only the direct statement children of the module body; stop descent
    # into FunctionDef/AsyncFunctionDef/ClassDef so we don't double-count calls
    # that belong to a function's own FunctionInfo.
    for stmt in tree.body:
        if not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            collector = _CallCollector()
            collector.visit(stmt)
            module.module_calls.extend(collector.calls)

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.Import):
                module.imports.extend(alias.name for alias in node.names)
            else:
                # Preserve relative-import level as leading dots so that
                # graph.py can resolve "from . import x" and "from ..y import z"
                # against the importing file's location.
                # level=0 → absolute, level=1 → ".", level=2 → "..", etc.
                prefix = "." * node.level
                mod = node.module or ""
                module.imports.append(prefix + mod)

        elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            collector = _CallCollector()
            collector.visit(node)
            module.functions.append(
                FunctionInfo(
                    name=node.name,
                    docstring=_get_docstring(node),
                    calls=collector.calls,
                    lineno=node.lineno,
                )
            )

        elif isinstance(node, ast.ClassDef):
            methods = [
                n.name for n in node.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            module.classes.append(
                ClassInfo(
                    name=node.name,
                    docstring=_get_docstring(node),
                    methods=methods,
                    lineno=node.lineno,
                )
            )

    return module


DEFAULT_IGNORE_DIRS = {
    ".git", "__pycache__", ".venv", "venv", "node_modules",
    "build", "dist", ".mypy_cache", ".pytest_cache", "egg-info",
}


def walk_repo(repo_root: str, ignore_dirs: set[str] | None = None) -> list[ModuleInfo]:
    """Walk repo_root, parse every .py file, return list of ModuleInfo."""
    ignore = ignore_dirs or DEFAULT_IGNORE_DIRS
    modules: list[ModuleInfo] = []

    for dirpath, dirnames, filenames in os.walk(repo_root):
        dirnames[:] = [d for d in dirnames if d not in ignore and not d.startswith(".")]
        for fname in filenames:
            if fname.endswith(".py"):
                full_path = os.path.join(dirpath, fname)
                info = parse_file(full_path, repo_root)
                if info is not None:
                    modules.append(info)

    return modules


if __name__ == "__main__":
    import sys
    import json

    target = sys.argv[1] if len(sys.argv) > 1 else "."
    mods = walk_repo(target)
    print(f"Parsed {len(mods)} modules from {target}")
    for m in mods[:5]:
        print(f"  {m.path}: {len(m.functions)} funcs, {len(m.classes)} classes, {m.loc} LOC")
