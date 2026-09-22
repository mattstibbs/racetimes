"""Guards the one structural promise the nhc package makes.

Slice 0 requires the scoring engine to be "a pure Python package ... No Django,
no database, no I/O" that drops into any Python project. That is easy to state
and easy to erode: one convenience import of ``django.utils`` and the package
quietly stops being portable. These tests fail the moment that happens.

Written against stdlib unittest rather than a test framework's own API, so the
suite runs unchanged under ``manage.py test``, ``python -m unittest`` and
``pytest``. That keeps the engine's tests runnable by anyone who vendors the
package, without imposing a test dependency on them.
"""

import ast
import subprocess
import sys
import unittest
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent / "nhc"


def _source_files():
    return sorted(PACKAGE_ROOT.rglob("*.py"))


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


class PackagePurityTests(unittest.TestCase):
    def test_package_has_source_files(self):
        # Guards against the rest of this module passing vacuously if the
        # package is moved or renamed.
        self.assertTrue(_source_files(), f"no Python sources found under {PACKAGE_ROOT}")

    def test_imports_only_the_standard_library(self):
        allowed = sys.stdlib_module_names | {"nhc"}
        offenders = {}
        for path in _source_files():
            extras = _imported_roots(path) - allowed
            if extras:
                offenders[path.name] = sorted(extras)
        self.assertEqual(
            offenders,
            {},
            "nhc must depend on the standard library alone; found third-party imports",
        )

    def test_does_not_import_django(self):
        for path in _source_files():
            self.assertNotIn(
                "django",
                {root.lower() for root in _imported_roots(path)},
                f"{path.name} imports django",
            )

    def test_imports_cleanly_without_django_configured(self):
        """Importing nhc must not need Django settings, or any Django at all.

        Run in a subprocess: this test suite itself may be running under the
        Django test runner, where django is already imported and configured, so
        an in-process check would prove nothing.
        """
        project_root = PACKAGE_ROOT.parent
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; import nhc; "
                "print('django' in sys.modules)",
            ],
            cwd=project_root,
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin"},
        )
        self.assertEqual(
            result.returncode, 0, f"importing nhc failed:\n{result.stderr}"
        )
        self.assertEqual(
            result.stdout.strip(),
            "False",
            "importing nhc pulled django into sys.modules",
        )


if __name__ == "__main__":
    unittest.main()
