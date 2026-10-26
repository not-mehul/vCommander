import pytest

from utils.validation import format_serial, is_valid_serial


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("a1a1b2b2c3c3", "A1A1-B2B2-C3C3"),
        ("a1a1b", "A1A1-B"),
        ("A1A1-B2B2-C3C3", "A1A1-B2B2-C3C3"),
        (" a1 a1/b2b2.c3c3 extra", "A1A1-B2B2-C3C3"),
        ("", ""),
        (None, ""),
    ],
)
def test_format_serial(raw, expected):
    assert format_serial(raw) == expected


@pytest.mark.parametrize(
    ("value", "ok"),
    [
        ("A1A1-B2B2-C3C3", True),
        (" A1A1-B2B2-C3C3 ", True),
        ("A1A1-B2B2", False),
        ("a1a1-b2b2-c3c3", False),
        ("A1A1B2B2C3C3", False),
        (None, False),
    ],
)
def test_is_valid_serial(value, ok):
    assert is_valid_serial(value) is ok
