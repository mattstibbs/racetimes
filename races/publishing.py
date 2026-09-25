"""Publishing a race's results, and sending them again after corrections.

Results are public as soon as they are saved; publishing marks them final and
emails them to the owners in the series. After that, any change that could
move the race's results marks it "amended since sent", and the committee
chooses when to send the updated results. The site never sends on its own.
"""

from django.db.models import Q
from django.utils import timezone

from . import notifications
from .models import Race, ScoringChange


def amended_since_sent(race):
    """Whether anything that could move this race's results changed since they were emailed.

    A change to this race, to any earlier race (whose handicaps this race sails
    on), or to the whole series (its settings, entries and boats' base numbers,
    recorded with no race) counts. Changes to later races cannot move this
    one's results, so they do not.
    """
    if race.results_sent_at is None:
        return False
    return (
        ScoringChange.objects.filter(series=race.series, timestamp__gt=race.results_sent_at)
        .exclude(kind=ScoringChange.Kind.FINAL)
        .filter(Q(race__isnull=True) | Q(race__number__lte=race.number))
        .exists()
    )


def publish(race, request):
    """Mark the race published and email its results. Returns how many owners."""
    now = timezone.now()
    Race.objects.filter(pk=race.pk, published_at__isnull=True).update(published_at=now)
    race.refresh_from_db()
    return _send(race, request, updated=False)


def send_updated(race, request):
    """Email the race's results again, as they now stand. Returns how many owners."""
    return _send(race, request, updated=True)


def _send(race, request, *, updated):
    sent_at = timezone.now()

    def mark_sent():
        # Only once every email has gone: a failure leaves the race unsent, so
        # the committee is offered the button again.
        Race.objects.filter(pk=race.pk).update(results_sent_at=sent_at)

    return notifications.race_results(race, request, updated=updated, on_sent=mark_sent)
