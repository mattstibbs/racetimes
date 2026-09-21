from django.test import TestCase
from django.urls import reverse


class HtmxSmokeTests(TestCase):
    def test_home_includes_htmx(self):
        response = self.client.get(reverse('races:home'))
        self.assertContains(response, 'js/htmx.min.js')

    def test_ping_detects_htmx_request(self):
        url = reverse('races:ping')
        self.assertContains(self.client.get(url, HTTP_HX_REQUEST='true'), 'pong (htmx)')
        self.assertEqual(self.client.get(url).content, b'pong')
