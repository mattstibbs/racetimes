"""Exceptions raised by the scoring engine."""


class InvalidInput(ValueError):
    """Input cannot be scored, and scoring it anyway would produce nonsense.

    Raised for the rejection cases in section 7 of the RYA spec: a non-positive
    or non-finite handicap (every formula divides or multiplies by it), a boat
    recorded as FINISHED with no usable elapsed time, and so on.

    Subclasses ValueError so callers that already handle bad input generically -
    a Django form, say - catch it without importing anything from nhc.
    """
