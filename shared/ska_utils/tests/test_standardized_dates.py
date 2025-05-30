from freezegun import freeze_time

from ska_utils import StandardDates


@freeze_time("2025-05-15 18:33:50")
def test_get_date():
    expected_date = "2025-05-15T18:33:50+00:00Z"
    assert StandardDates.get_date() == expected_date


@freeze_time("2025-05-15 18:33:50")
def test_get_current_month_full_name():
    expected_month = "May"
    assert StandardDates.get_current_month_full_name() == expected_month


@freeze_time("2025-05-15 18:33:50")
def test_get_current_month_abv():
    expected_month_abv = "May"
    assert StandardDates.get_current_month_abv() == expected_month_abv


@freeze_time("2025-05-15 18:33:50")
def test_get_current_year():
    expected_year = 2025
    assert StandardDates.get_current_year() == expected_year
