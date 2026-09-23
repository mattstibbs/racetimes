"""Display formatting for results. Rounding happens here and nowhere earlier.

The engine carries full precision throughout (spec section 7); these filters
round only what a person reads.
"""

from django import template

register = template.Library()


@register.filter
def hms(seconds):
    """Seconds as h:mm:ss, rounded to the whole second. Blank for None."""
    if seconds is None:
        return ""
    total = round(seconds)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}"


@register.filter
def tcf(value):
    """A handicap to 3 decimal places, as the RYA publishes them."""
    if value is None:
        return ""
    return f"{float(value):.3f}"


@register.filter
def points(value):
    """Race points: whole, or halves after a tie. 2.0 shows as 2."""
    if value is None:
        return ""
    return f"{value:g}"
