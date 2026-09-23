import pytest

from races.templatetags.racing import hms, points, tcf


@pytest.mark.parametrize(
    "seconds, shown",
    [(None, ""), (0, "0:00:00"), (59.4, "0:00:59"), (59.6, "0:01:00"), (3737, "1:02:17"), (36000, "10:00:00")],
)
def test_hms(seconds, shown):
    assert hms(seconds) == shown


@pytest.mark.parametrize("value, shown", [(None, ""), (0.97404088, "0.974"), (0.9, "0.900")])
def test_tcf_rounds_for_display_only(value, shown):
    assert tcf(value) == shown


@pytest.mark.parametrize("value, shown", [(None, ""), (2.0, "2"), (2.5, "2.5")])
def test_points(value, shown):
    assert points(value) == shown
