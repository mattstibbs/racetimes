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


@register.filter
def ordinal(number):
    """1st, 2nd, 3rd, 4th ... 11th, 12th, 13th ... 21st, 22nd."""
    if number is None:
        return ""
    if 10 <= number % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return f"{number}{suffix}"
