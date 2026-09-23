"""Smoke tests for the HTMX wiring in the races app.

Written against pytest-django's `client` fixture rather than
`django.test.TestCase`. The home page lists series, so it needs the database;
the ping view does not.
"""

import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_home_includes_htmx(client):
    response = client.get(reverse("races:home"))
    assert "js/htmx.min.js" in response.content.decode()


def test_ping_detects_htmx_request(client):
    url = reverse("races:ping")
    assert "pong (htmx)" in client.get(url, HTTP_HX_REQUEST="true").content.decode()
    assert client.get(url).content == b"pong"
