"""Guards the one structural promise the nhc package makes.

Slice 0 requires the scoring engine to be "a pure Python package ... No Django,
no database, no I/O" that drops into any Python project. That is easy to state
and easy to erode: one convenience import of ``django.utils`` and the package
quietly stops being portable. These tests fail the moment that happens.
"""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parent.parent / "nhc"

SOURCE_FILES = sorted(PACKAGE_ROOT.rglob("*.py"))


def _imported_roots(path):
    """Top-level module names imported by `path`, ignoring relative imports."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            # level > 0 is a relative import, i.e. within nhc itself.
            if node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
    return roots


def test_package_has_source_files():
    # Guards against every parametrised test below passing vacuously if the
    # package is moved or renamed.
    assert SOURCE_FILES, f"no Python sources found under {PACKAGE_ROOT}"


@pytest.mark.parametrize("source", SOURCE_FILES, ids=lambda p: p.name)
def test_imports_only_the_standard_library(source):
    allowed = sys.stdlib_module_names | {"nhc"}
    extras = sorted(_imported_roots(source) - allowed)
    assert not extras, (
        f"{source.name} imports {extras}; nhc must depend on the standard "
        f"library alone so it can be vendored into any project"
    )


@pytest.mark.parametrize("source", SOURCE_FILES, ids=lambda p: p.name)
def test_does_not_import_django(source):
    roots = {root.lower() for root in _imported_roots(source)}
    assert "django" not in roots, f"{source.name} imports django"


def test_imports_cleanly_without_django_configured():
    """Importing nhc must not need Django settings, or any Django at all.

    Run in a subprocess: this suite runs with DJANGO_SETTINGS_MODULE set and
    django already imported, so an in-process check would prove nothing.
    """
    result = subprocess.run(
        [sys.executable, "-c", "import sys; import nhc; print('django' in sys.modules)"],
        cwd=PACKAGE_ROOT.parent,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 0, f"importing nhc failed:\n{result.stderr}"
    assert result.stdout.strip() == "False", "importing nhc pulled django into sys.modules"
