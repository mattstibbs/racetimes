"""Sharing published results to WhatsApp (slice 21).

The committee's pages offer a WhatsApp "click to chat" link with a message
already written: ``https://wa.me/?text=<message>``. With no phone number in
it, WhatsApp asks which chat to send it to. It's an ordinary link, so Race
Times sends nothing itself: the message goes nowhere unless the person
presses send in WhatsApp.

A message holds only what the public results page shows (boats by name and
sail number, never owners), and links to the club's own address.
"""

from urllib.parse import quote

from django.template.loader import render_to_string
from django.urls import reverse

WHATSAPP = "https://wa.me/?text="


def race_message(race, results, request, *, updated=False):
    """A race's results: every place, and a link to the race on the series page."""
    link = request.build_absolute_uri(reverse("results:series", args=[race.series_id]))
    return _render(
        "races/share/race.txt",
        {
            "race": race,
            "race_results": results.for_race(race),
            "updated": updated,
            "results_url": f"{link}?race={race.number}",
        },
    )


def final_message(series, results, request):
    """A final series' standings: every place with its points, and a link."""
    return _render(
        "races/share/final.txt",
        {
            "series": series,
            "standings": results.standings,
            "results_url": request.build_absolute_uri(
                reverse("results:series", args=[series.pk])
            ),
        },
    )


def whatsapp_url(message):
    """The click-to-chat link for a message. Everything is encoded, so line
    breaks, ``&``, ``#`` and ``*`` reach WhatsApp as they are."""
    return WHATSAPP + quote(message, safe="")


def _render(template, context):
    # The templates control their own line breaks; this only trims the ends.
    return render_to_string(template, context).strip()
