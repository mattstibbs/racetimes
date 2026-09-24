"""The user manual (manual/, built by MkDocs from mkdocs.yml) stays whole.

Runs with the rest of the suite and needs only PyYAML, so a broken link or a
forgotten page fails here without MkDocs installed. CI also builds the manual
itself with `mkdocs build --strict`.
"""

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
MANUAL = ROOT / "manual"
PAGES = sorted(MANUAL.rglob("*.md"))

# [text](target) and ![alt](target); the target stops at whitespace or ")".
LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)\)")


def nav_pages(entries):
    for entry in entries:
        for value in entry.values() if isinstance(entry, dict) else [entry]:
            if isinstance(value, list):
                yield from nav_pages(value)
            else:
                yield value


def local_links(page):
    for target in LINK.findall(page.read_text(encoding="utf-8")):
        if not re.match(r"[a-z]+:", target) and not target.startswith("#"):
            yield target.split("#")[0]


def test_the_manual_has_pages():
    assert MANUAL / "index.md" in PAGES


@pytest.mark.parametrize("page", PAGES, ids=lambda p: str(p.relative_to(MANUAL)))
def test_every_link_and_image_exists(page):
    missing = [t for t in local_links(page) if not (page.parent / t).resolve().exists()]
    assert not missing, f"{page.relative_to(ROOT)} links to missing files: {missing}"


def test_every_page_is_in_the_contents_and_every_entry_exists():
    config = yaml.safe_load((ROOT / "mkdocs.yml").read_text(encoding="utf-8"))
    listed = set(nav_pages(config["nav"]))
    written = {str(p.relative_to(MANUAL)) for p in PAGES}
    assert listed == written


def test_every_screenshot_is_used():
    used = {
        (page.parent / target).resolve()
        for page in PAGES
        for target in local_links(page)
    }
    unused = [p.name for p in (MANUAL / "images").glob("*.png") if p.resolve() not in used]
    assert not unused, f"Screenshots no page uses: {unused}"
