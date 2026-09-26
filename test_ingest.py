"""
Unit tests for autopsy/ingest.py.

Tests are split into three groups:
  - TestParseFile  – parse_file() against individual synthetic snippets
  - TestParseFileSampleRepo – parse_file() against the real sample_repo files
  - TestWalkRepo   – walk_repo() against the real sample_repo directory tree
"""

from __future__ import annotations

import os
import textwrap

import pytest

from autopsy.ingest import (
    ClassInfo,
    FunctionInfo,
    ModuleInfo,
    parse_file,
    walk_repo,
    DEFAULT_IGNORE_DIRS,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

SAMPLE_REPO = os.path.join(os.path.dirname(__file__), "..", "sample_repo")
SAMPLE_REPO = os.path.normpath(SAMPLE_REPO)


@pytest.fixture()
def sample_repo() -> str:
    """Return the absolute path to the sample_repo directory."""
    assert os.path.isdir(SAMPLE_REPO), f"sample_repo not found at {SAMPLE_REPO}"
    return SAMPLE_REPO


@pytest.fixture()
def tmp_py_file(tmp_path):
    """Factory fixture: write a .py snippet to a temp file and return (path, repo_root)."""
    def _make(source: str, filename: str = "module.py") -> tuple[str, str]:
        p = tmp_path / filename
        p.write_text(textwrap.dedent(source), encoding="utf-8")
        return str(p), str(tmp_path)
    return _make


# ---------------------------------------------------------------------------
# parse_file — synthetic snippets
# ---------------------------------------------------------------------------

class TestParseFile:
    # --- return type -------------------------------------------------------

    def test_returns_module_info(self, tmp_py_file):
        path, root = tmp_py_file("x = 1\n")
        result = parse_file(path, root)
        assert isinstance(result, ModuleInfo)

    def test_returns_none_for_syntax_error(self, tmp_py_file):
        path, root = tmp_py_file("def (\n")
        assert parse_file(path, root) is None

    def test_returns_none_for_missing_file(self, tmp_path):
        missing = str(tmp_path / "no_such_file.py")
        assert parse_file(missing, str(tmp_path)) is None

    # --- path --------------------------------------------------------------

    def test_path_is_relative_to_repo_root(self, tmp_py_file):
        path, root = tmp_py_file("x = 1\n", filename="mymod.py")
        info = parse_file(path, root)
        assert info.path == "mymod.py"

    # --- loc ---------------------------------------------------------------

    def test_loc_matches_line_count(self, tmp_py_file):
        source = "a = 1\nb = 2\nc = 3\n"
        path, root = tmp_py_file(source)
        info = parse_file(path, root)
        assert info.loc == 3

    def test_loc_single_line(self, tmp_py_file):
        path, root = tmp_py_file("x = 42\n")
        info = parse_file(path, root)
        assert info.loc == 1

    # --- raw_source --------------------------------------------------------

    def test_raw_source_preserved(self, tmp_py_file):
        source = "# hello\nx = 1\n"
        path, root = tmp_py_file(source)
        info = parse_file(path, root)
        assert info.raw_source == source

    # --- docstring ---------------------------------------------------------

    def test_module_docstring_extracted(self, tmp_py_file):
        path, root = tmp_py_file('"""Top-level docstring."""\nx = 1\n')
        info = parse_file(path, root)
        assert info.docstring == "Top-level docstring."

    def test_no_docstring_is_none(self, tmp_py_file):
        path, root = tmp_py_file("x = 1\n")
        info = parse_file(path, root)
        assert info.docstring is None

    # --- imports -----------------------------------------------------------

    def test_plain_import(self, tmp_py_file):
        path, root = tmp_py_file("import os\nimport sys\n")
        info = parse_file(path, root)
        assert "os" in info.imports
        assert "sys" in info.imports

    def test_from_import_absolute(self, tmp_py_file):
        path, root = tmp_py_file("from os.path import join\n")
        info = parse_file(path, root)
        assert "os.path" in info.imports

    def test_from_import_relative_single_dot(self, tmp_py_file):
        path, root = tmp_py_file("from . import utils\n")
        info = parse_file(path, root)
        assert "." in info.imports

    def test_from_import_relative_package(self, tmp_py_file):
        path, root = tmp_py_file("from .helpers import do_thing\n")
        info = parse_file(path, root)
        assert ".helpers" in info.imports

    def test_from_import_relative_double_dot(self, tmp_py_file):
        path, root = tmp_py_file("from ..pkg import something\n")
        info = parse_file(path, root)
        assert "..pkg" in info.imports

    def test_no_imports(self, tmp_py_file):
        path, root = tmp_py_file("x = 1\n")
        info = parse_file(path, root)
        assert info.imports == []

    # --- functions ---------------------------------------------------------

    def test_function_detected(self, tmp_py_file):
        path, root = tmp_py_file("def greet(): pass\n")
        info = parse_file(path, root)
        names = [f.name for f in info.functions]
        assert "greet" in names

    def test_function_info_type(self, tmp_py_file):
        path, root = tmp_py_file("def greet(): pass\n")
        info = parse_file(path, root)
        assert all(isinstance(f, FunctionInfo) for f in info.functions)

    def test_function_docstring(self, tmp_py_file):
        src = '''\
            def greet():
                """Say hello."""
                pass
        '''
        path, root = tmp_py_file(src)
        info = parse_file(path, root)
        func = next(f for f in info.functions if f.name == "greet")
        assert func.docstring == "Say hello."

    def test_function_no_docstring(self, tmp_py_file):
        path, root = tmp_py_file("def greet(): pass\n")
        info = parse_file(path, root)
        func = next(f for f in info.functions if f.name == "greet")
        assert func.docstring is None

    def test_function_lineno(self, tmp_py_file):
        src = "x = 1\ndef greet(): pass\n"
        path, root = tmp_py_file(src)
        info = parse_file(path, root)
        func = next(f for f in info.functions if f.name == "greet")
        assert func.lineno == 2

    def test_async_function_detected(self, tmp_py_file):
        path, root = tmp_py_file("async def fetch(): pass\n")
        info = parse_file(path, root)
        names = [f.name for f in info.functions]
        assert "fetch" in names

    def test_multiple_functions(self, tmp_py_file):
        src = "def foo(): pass\ndef bar(): pass\ndef baz(): pass\n"
        path, root = tmp_py_file(src)
        info = parse_file(path, root)
        names = [f.name for f in info.functions]
        assert set(names) >= {"foo", "bar", "baz"}

    def test_function_calls_recorded(self, tmp_py_file):
        src = '''\
            def my_func():
                print("hello")
                len([1, 2])
        '''
        path, root = tmp_py_file(src)
        info = parse_file(path, root)
        func = next(f for f in info.functions if f.name == "my_func")
        assert "print" in func.calls
        assert "len" in func.calls

    def test_method_call_records_attribute_name(self, tmp_py_file):
        src = '''\
            def my_func():
                obj.do_something()
        '''
        path, root = tmp_py_file(src)
        info = parse_file(path, root)
        func = next(f for f in info.functions if f.name == "my_func")
        assert "do_something" in func.calls

    def test_no_functions(self, tmp_py_file):
        path, root = tmp_py_file("x = 1\n")
        info = parse_file(path, root)
        assert info.functions == []

    # --- classes -----------------------------------------------------------

    def test_class_detected(self, tmp_py_file):
        path, root = tmp_py_file("class Foo: pass\n")
        info = parse_file(path, root)
        names = [c.name for c in info.classes]
        assert "Foo" in names

    def test_class_info_type(self, tmp_py_file):
        path, root = tmp_py_file("class Foo: pass\n")
        info = parse_file(path, root)
        assert all(isinstance(c, ClassInfo) for c in info.classes)

    def test_class_docstring(self, tmp_py_file):
        src = '''\
            class Foo:
                """A foo class."""
                pass
        '''
        path, root = tmp_py_file(src)
        info = parse_file(path, root)
        cls = next(c for c in info.classes if c.name == "Foo")
        assert cls.docstring == "A foo class."

    def test_class_no_docstring(self, tmp_py_file):
        path, root = tmp_py_file("class Foo: pass\n")
        info = parse_file(path, root)
        cls = next(c for c in info.classes if c.name == "Foo")
        assert cls.docstring is None

    def test_class_lineno(self, tmp_py_file):
        src = "x = 1\nclass Foo: pass\n"
        path, root = tmp_py_file(src)
        info = parse_file(path, root)
        cls = next(c for c in info.classes if c.name == "Foo")
        assert cls.lineno == 2

    def test_class_methods_listed(self, tmp_py_file):
        src = '''\
            class Foo:
                def method_a(self): pass
                def method_b(self): pass
        '''
        path, root = tmp_py_file(src)
        info = parse_file(path, root)
        cls = next(c for c in info.classes if c.name == "Foo")
        assert set(cls.methods) >= {"method_a", "method_b"}

    def test_class_no_methods(self, tmp_py_file):
        src = '''\
            class Empty:
                pass
        '''
        path, root = tmp_py_file(src)
        info = parse_file(path, root)
        cls = next(c for c in info.classes if c.name == "Empty")
        assert cls.methods == []

    def test_no_classes(self, tmp_py_file):
        path, root = tmp_py_file("x = 1\n")
        info = parse_file(path, root)
        assert info.classes == []

    # --- module_calls ------------------------------------------------------

    def test_module_scope_calls_recorded(self, tmp_py_file):
        src = "print('hi')\nlen([1, 2, 3])\n"
        path, root = tmp_py_file(src)
        info = parse_file(path, root)
        assert "print" in info.module_calls
        assert "len" in info.module_calls

    def test_function_body_calls_not_in_module_calls(self, tmp_py_file):
        src = '''\
            def foo():
                helper()
        '''
        path, root = tmp_py_file(src)
        info = parse_file(path, root)
        assert "helper" not in info.module_calls

    def test_no_module_scope_calls(self, tmp_py_file):
        src = "x = 1 + 2\n"
        path, root = tmp_py_file(src)
        info = parse_file(path, root)
        assert info.module_calls == []


# ---------------------------------------------------------------------------
# parse_file — sample_repo files
# ---------------------------------------------------------------------------

class TestParseFileSampleRepo:
    def _parse(self, relative: str) -> ModuleInfo:
        full = os.path.join(SAMPLE_REPO, relative)
        info = parse_file(full, SAMPLE_REPO)
        assert info is not None, f"parse_file returned None for {relative}"
        return info

    def test_math_utils_path(self):
        info = self._parse(os.path.join("app", "math_utils.py"))
        # path is always relative to repo_root, uses os.sep
        assert info.path == os.path.join("app", "math_utils.py")

    def test_math_utils_docstring(self):
        info = self._parse(os.path.join("app", "math_utils.py"))
        assert info.docstring is not None
        assert "math" in info.docstring.lower()

    def test_math_utils_imports_json(self):
        info = self._parse(os.path.join("app", "math_utils.py"))
        assert "json" in info.imports

    def test_math_utils_imports_logger(self):
        info = self._parse(os.path.join("app", "math_utils.py"))
        # "from app.logger import log_event"
        assert "app.logger" in info.imports

    def test_math_utils_functions(self):
        info = self._parse(os.path.join("app", "math_utils.py"))
        names = [f.name for f in info.functions]
        assert "add" in names
        assert "compute_and_save_report" in names

    def test_math_utils_add_docstring(self):
        info = self._parse(os.path.join("app", "math_utils.py"))
        add_fn = next(f for f in info.functions if f.name == "add")
        assert add_fn.docstring is not None

    def test_math_utils_compute_calls_log_event(self):
        info = self._parse(os.path.join("app", "math_utils.py"))
        fn = next(f for f in info.functions if f.name == "compute_and_save_report")
        assert "log_event" in fn.calls

    def test_logger_imports_math_utils(self):
        info = self._parse(os.path.join("app", "logger.py"))
        assert "app.math_utils" in info.imports

    def test_logger_functions(self):
        info = self._parse(os.path.join("app", "logger.py"))
        names = [f.name for f in info.functions]
        assert "log_event" in names
        assert "log_count" in names

    def test_logger_log_count_calls_add(self):
        info = self._parse(os.path.join("app", "logger.py"))
        fn = next(f for f in info.functions if f.name == "log_count")
        assert "add" in fn.calls

    def test_main_imports_compute_and_save_report(self):
        info = self._parse(os.path.join("app", "main.py"))
        assert "app.math_utils" in info.imports

    def test_main_functions(self):
        info = self._parse(os.path.join("app", "main.py"))
        names = [f.name for f in info.functions]
        assert "run" in names

    def test_main_run_calls_compute_and_save_report(self):
        info = self._parse(os.path.join("app", "main.py"))
        fn = next(f for f in info.functions if f.name == "run")
        assert "compute_and_save_report" in fn.calls


# ---------------------------------------------------------------------------
# walk_repo — sample_repo
# ---------------------------------------------------------------------------

class TestWalkRepo:
    def test_returns_list(self, sample_repo):
        modules = walk_repo(sample_repo)
        assert isinstance(modules, list)

    def test_all_items_are_module_info(self, sample_repo):
        modules = walk_repo(sample_repo)
        assert all(isinstance(m, ModuleInfo) for m in modules)

    def test_discovers_all_py_files(self, sample_repo):
        modules = walk_repo(sample_repo)
        relative_paths = {m.path for m in modules}
        expected = {
            os.path.join("app", "main.py"),
            os.path.join("app", "math_utils.py"),
            os.path.join("app", "logger.py"),
            os.path.join("app", "__init__.py"),
            "__init__.py",
        }
        assert expected.issubset(relative_paths)

    def test_skips_pycache_by_default(self, sample_repo):
        modules = walk_repo(sample_repo)
        for m in modules:
            assert "__pycache__" not in m.path

    def test_custom_ignore_dirs_respected(self, sample_repo):
        """Passing a custom ignore set that includes 'app' skips all app/*.py files."""
        modules = walk_repo(sample_repo, ignore_dirs={"app", "__pycache__"})
        for m in modules:
            assert not m.path.startswith("app")

    def test_empty_dir_returns_empty_list(self, tmp_path):
        modules = walk_repo(str(tmp_path))
        assert modules == []

    def test_only_py_files_collected(self, tmp_path):
        (tmp_path / "readme.txt").write_text("hello")
        (tmp_path / "script.py").write_text("x = 1\n")
        modules = walk_repo(str(tmp_path))
        assert len(modules) == 1
        assert modules[0].path == "script.py"

    def test_syntax_error_file_skipped(self, tmp_path):
        (tmp_path / "good.py").write_text("x = 1\n")
        (tmp_path / "bad.py").write_text("def (\n")
        modules = walk_repo(str(tmp_path))
        paths = [m.path for m in modules]
        assert "good.py" in paths
        assert "bad.py" not in paths

    def test_default_ignore_dirs_constant(self):
        """Ensure DEFAULT_IGNORE_DIRS contains the expected sentinel directories."""
        for d in (".git", "__pycache__", ".venv", "venv"):
            assert d in DEFAULT_IGNORE_DIRS
