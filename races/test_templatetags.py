import pytest

from races.templatetags.racing import hms, ordinal, points, tcf


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


@pytest.mark.parametrize(
    "number, shown",
    [(None, ""), (1, "1st"), (2, "2nd"), (3, "3rd"), (4, "4th"), (11, "11th"), (12, "12th"),
     (13, "13th"), (21, "21st"), (22, "22nd"), (101, "101st"), (111, "111th")],
)
def test_ordinal(number, shown):
    assert ordinal(number) == shown
