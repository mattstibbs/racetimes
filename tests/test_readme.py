"""Checks on the package README.

Slice 0's acceptance criteria include "public interface documented in the
package README". These tests make that checkable rather than a claim: the
documented example is executed and its output compared against what the README
says it prints, and every exported name has to appear somewhere in the text.

A README example that has quietly rotted is worse than no example, because a
reader will trust it.
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

import nhc

PROJECT_ROOT = Path(__file__).resolve().parent.parent
README = PROJECT_ROOT / "nhc" / "README.md"


def fenced_blocks(text):
    """(language, body) for every fenced code block, in order."""
    return [
        (match.group(1) or "", match.group(2))
        for match in re.finditer(r"```(\w*)\n(.*?)```", text, re.DOTALL)
    ]


@pytest.fixture(scope="module")
def readme():
    return README.read_text(encoding="utf-8")


def test_the_readme_exists_and_is_not_a_stub(readme):
    assert len(readme.splitlines()) > 50


def test_the_quick_start_example_runs_and_prints_what_the_readme_says(readme):
    blocks = fenced_blocks(readme)
    example = next(body for language, body in blocks if language == "python")
    index = next(i for i, (language, _) in enumerate(blocks) if language == "python")
    documented_output = blocks[index + 1][1]

    result = subprocess.run(
        [sys.executable, "-c", example],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(PROJECT_ROOT)},
    )
    assert result.returncode == 0, f"the README example failed:\n{result.stderr}"
    assert result.stdout == documented_output


@pytest.mark.parametrize("name", sorted(nhc.__all__))
def test_every_exported_name_is_documented(name, readme):
    assert name in readme, f"{name} is exported from nhc but not mentioned in the README"


def test_the_readme_does_not_document_names_that_no_longer_exist(readme):
    """The other direction: an entry left behind after a rename.

    Every backticked name the README writes as a call - `Boat(...)`,
    `score_series(...)` - has to be something the package actually exports.
    """
    documented = set(re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)\(", readme))
    assert documented, "no documented calls found; check the regex still matches"
    unknown = sorted(documented - set(nhc.__all__))
    assert not unknown, f"README documents names that nhc does not export: {unknown}"
