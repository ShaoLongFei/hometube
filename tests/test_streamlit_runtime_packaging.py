from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_background_jobs_fragment_uses_numeric_rerun_interval() -> None:
    """Numeric intervals avoid Streamlit's pandas-backed string parser at startup."""
    tree = ast.parse((PROJECT_ROOT / "app" / "main.py").read_text())

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.name != "render_background_jobs_panel":
            continue

        fragment_decorators = [
            decorator
            for decorator in node.decorator_list
            if isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr == "fragment"
        ]
        assert len(fragment_decorators) == 1

        run_every_keywords = [
            keyword
            for keyword in fragment_decorators[0].keywords
            if keyword.arg == "run_every"
        ]
        assert len(run_every_keywords) == 1
        assert isinstance(run_every_keywords[0].value, ast.Constant)
        assert isinstance(run_every_keywords[0].value.value, int | float)
        assert run_every_keywords[0].value.value == 2.0
        return

    raise AssertionError("render_background_jobs_panel was not found")


def test_background_jobs_panel_uses_active_progress_translation() -> None:
    """The panel should label in-flight work, not only completed item counts."""
    source = (PROJECT_ROOT / "app" / "main.py").read_text()

    assert "background_jobs_progress_active" in source


def test_main_no_longer_contains_unreachable_foreground_download_fallback() -> None:
    """Submitted downloads should go through the persistent background queue only."""
    source = (PROJECT_ROOT / "app" / "main.py").read_text()

    assert "=== PLAYLIST DOWNLOAD MODE ===" not in source
    assert "=== SINGLE VIDEO DOWNLOAD MODE (existing logic continues below) ===" not in source


def test_dockerfile_pruning_preserves_pandas_runtime_testing_package() -> None:
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text()

    assert "pandas/_testing" in dockerfile
    assert "-path '*/pandas/_testing' -prune" in dockerfile
