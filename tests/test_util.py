import pytest

from datadiff.util import parse_duration


def test_parse_duration_units():
    assert parse_duration("10s") == 10
    assert parse_duration("2m") == 120
    assert parse_duration("1.5h") == 5400


def test_parse_duration_rejects_bad_input():
    with pytest.raises(ValueError):
        parse_duration("abc")
