"""Smoke tests for the HTMX wiring in the races app.

Written against pytest-django's `client` fixture rather than
`django.test.TestCase`. The ping view itself needs no database, but since
slice 11 every request looks up its club first.
"""

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_ping_detects_htmx_request(client):
    url = reverse("races:ping")
    assert "pong (htmx)" in client.get(url, HTTP_HX_REQUEST="true").content.decode()
    assert client.get(url).content == b"pong"
