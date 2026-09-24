"""Slice 7: the site's look stays readable, and loads nothing from elsewhere.

static/css/site.css keeps every colour as a token in :root. These tests read
the tokens and check each text colour against the backgrounds it is used on,
so changing a token (to a club's own colours, say) cannot quietly make text
unreadable. The pairs below are the ones the stylesheet actually uses.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.messages import constants
from django.template.loader import render_to_string
from django.urls import reverse

CSS = (Path(settings.BASE_DIR) / "static" / "css" / "site.css").read_text()
ROOT = re.search(r":root\s*\{(.*?)\}", CSS, re.S).group(1)
TOKENS = dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})\b", ROOT))

# WCAG 2.1 AA: 4.5:1 for text, 3:1 for large headings and for the edges of
# controls (buttons, inputs) that people need to find.
TEXT, LARGE_OR_EDGE = 4.5, 3.0
PAIRS = [
    # Text on the page and on cards, tables and rows.
    ("text", "page", TEXT), ("text", "surface", TEXT), ("text", "th-bg", TEXT),
    ("muted", "page", TEXT), ("muted", "surface", TEXT), ("muted", "th-bg", TEXT),
    ("accent", "page", TEXT), ("accent", "surface", TEXT),
    ("navy", "page", LARGE_OR_EDGE), ("navy", "surface", LARGE_OR_EDGE),
    # Buttons, the chosen race, and the header band.
    ("surface", "accent", TEXT), ("surface", "accent-strong", TEXT),
    ("accent-strong", "accent-soft", TEXT),
    ("surface", "navy", TEXT), ("header-link", "navy", TEXT),
    # The followed boat and the next handicap, including its discarded scores.
    ("text", "accent-soft", TEXT), ("accent", "accent-soft", TEXT), ("muted", "accent-soft", TEXT),
    # States: saved, error, provisional or amended - and ordinary text on them.
    ("ok", "ok-bg", TEXT), ("err", "err-bg", TEXT), ("warn", "warn-bg", TEXT),
    ("text", "ok-bg", TEXT), ("text", "err-bg", TEXT), ("text", "warn-bg", TEXT),
    ("muted", "ok-bg", TEXT), ("muted", "err-bg", TEXT), ("muted", "warn-bg", TEXT),
    ("accent", "ok-bg", TEXT), ("accent", "err-bg", TEXT), ("accent", "warn-bg", TEXT),
    ("err", "surface", TEXT), ("ok", "surface", TEXT), ("warn", "surface", TEXT),
    ("warn", "page", TEXT), ("ok", "page", TEXT),
    # Edges people need to see: inputs, and the focus outline.
    ("field-border", "surface", LARGE_OR_EDGE), ("accent", "page", LARGE_OR_EDGE),
]


def luminance(colour):
    channels = [int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(one, two):
    lighter, darker = sorted([luminance(one), luminance(two)], reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


@pytest.mark.parametrize("fg, bg, minimum", PAIRS, ids=[f"{fg} on {bg}" for fg, bg, _ in PAIRS])
def test_colours_meet_wcag_aa(fg, bg, minimum):
    ratio = contrast(TOKENS[fg], TOKENS[bg])
    assert ratio >= minimum, f"--{fg} on --{bg} is {ratio:.2f}:1, needs {minimum}:1"


def test_every_colour_is_a_token():
    """Outside :root, colours are only ever var(--...), so the tokens are the whole palette."""
    rest = CSS.replace(ROOT, "")
    rest = re.sub(r"/\*.*?\*/", "", rest, flags=re.S)  # comments may name colours
    literals = re.findall(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(", rest)
    assert literals == []


def test_every_token_used_is_defined():
    defined = set(re.findall(r"--([\w-]+):", ROOT))
    used = set(re.findall(r"var\(--([\w-]+)\)", CSS))
    assert used <= defined, f"undefined: {sorted(used - defined)}"


# --- Nothing is loaded from another site -------------------------------------------


def assets(html):
    """Every file the page asks the browser to load: stylesheets, icons, scripts, images."""
    return re.findall(r'<(?:link|script|img)\b[^>]*?\b(?:href|src)="([^"]+)"', html)


@pytest.mark.django_db
def test_pages_load_only_the_sites_own_files(client):
    html = client.get(reverse("results:home")).content.decode()
    found = assets(html)
    assert {"/static/css/site.css", "/static/js/htmx.min.js", "/static/img/sail.svg"} <= set(found)
    assert all(url.startswith(settings.STATIC_URL) for url in found), found


def test_the_error_page_loads_nothing_at_all():
    html = render_to_string("500.html")
    assert assets(html) == []
    assert "<style>" in html  # its look is copied in instead


# --- Messages carry their level, so an error shows in red --------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("level, css_class", [(constants.ERROR, "error"), (constants.SUCCESS, "success"),
                                              (constants.WARNING, "warning")])
def test_a_message_is_styled_by_its_level(rf, level, css_class):
    from django.contrib.auth.models import AnonymousUser
    from django.contrib.messages.storage.fallback import FallbackStorage

    request = rf.get("/")
    request.user = AnonymousUser()
    request.session = {}
    request._messages = FallbackStorage(request)
    request._messages.add(level, "Something happened")
    html = render_to_string("races/my_boats.html", {"boats": []}, request=request)
    assert f'<li class="{css_class}">Something happened</li>' in html
