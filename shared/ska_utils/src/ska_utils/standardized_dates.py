from datetime import UTC, datetime


class StandardDates:
    @staticmethod
    def get_date():
        """
        Returns the current date and time in UTC as a
        string in ISO format with the 'Z' suffix.
        Returns:
            str: The current date and time in UTC in the
            format 'YYYY-MM-DDTHH:MM:SS.ffffZ'
        """
        now_utc = datetime.now(UTC)
        utc_string = now_utc.isoformat() + "Z"
        return utc_string

    @staticmethod
    def get_current_month_full_name():
        current_month = datetime.now()
        return current_month.strftime("%B")

    @staticmethod
    def get_current_month_abv():
        current_month = datetime.now()
        return current_month.strftime("%b")

    @staticmethod
    def get_current_year():
        current_year = datetime.now()
        return current_year.year
