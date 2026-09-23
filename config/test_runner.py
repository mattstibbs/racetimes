"""Stops `manage.py test` from reporting a false green.

The test suite is pytest, and pytest-style tests are plain functions rather
than `unittest.TestCase` subclasses. Django's own runner therefore collects
nothing from them and exits 0 with "Ran 0 tests ... OK" - which looks like a
pass and would be one in CI. Failing loudly with a pointer is safer than
leaving that trap in place for whoever types the old command out of habit.
"""


class PytestRedirectRunner:
    """A Django TEST_RUNNER that refuses to run and says what to use instead."""

    def __init__(self, *args, **kwargs):
        pass

    def run_tests(self, test_labels=None, **kwargs):
        raise SystemExit(
            "\nThis project's tests run under pytest, not the Django test runner.\n"
            "`manage.py test` would collect 0 tests and report success.\n\n"
            "Use instead:\n"
            "    .venv/bin/python -m pytest              # everything\n"
            "    .venv/bin/python -m pytest tests        # scoring engine only\n"
            "    .venv/bin/python -m pytest races        # Django app only\n"
        )
