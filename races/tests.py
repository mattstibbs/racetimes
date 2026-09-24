"""Smoke tests for the HTMX wiring in the races app.

Written against pytest-django's `client` fixture rather than
`django.test.TestCase`. The ping view needs no database.
"""

from django.urls import reverse


def test_ping_detects_htmx_request(client):
    url = reverse("races:ping")
    assert "pong (htmx)" in client.get(url, HTTP_HX_REQUEST="true").content.decode()
    assert client.get(url).content == b"pong"
