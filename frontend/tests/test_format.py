"""Tests for display formatting helpers (ui.format)."""

from ui.format import fmt_date, fmt_datetime, fmt_money, fmt_percent


class TestFmtMoney:
    def test_integer(self):
        assert fmt_money(1000) == "1\xa0000,00 DA"

    def test_decimal_string(self):
        assert fmt_money("1234567.50") == "1\xa0234\xa0567,50 DA"

    def test_none(self):
        assert fmt_money(None) == "0,00 DA"

    def test_zero(self):
        assert fmt_money(0) == "0,00 DA"

    def test_custom_symbol(self):
        assert fmt_money(100, symbol="EUR") == "100,00 EUR"

    def test_no_symbol(self):
        assert fmt_money(100, symbol="") == "100,00"

    def test_negative(self):
        result = fmt_money(-500)
        assert "500,00" in result


class TestFmtPercent:
    def test_whole(self):
        assert fmt_percent(0.5) == "50 %"

    def test_with_decimals(self):
        assert fmt_percent(0.724, decimals=1) == "72,4 %"

    def test_zero(self):
        assert fmt_percent(0.0) == "0 %"


class TestFmtDate:
    def test_iso_date(self):
        assert fmt_date("2026-01-15T10:30:00") == "15/01/2026"

    def test_none(self):
        assert fmt_date(None) == "—"

    def test_empty(self):
        assert fmt_date("") == "—"

    def test_invalid(self):
        assert fmt_date("not-a-date") == "not-a-date"


class TestFmtDatetime:
    def test_iso_datetime(self):
        assert fmt_datetime("2026-07-12T14:05:00") == "12/07/2026 14:05"

    def test_none(self):
        assert fmt_datetime(None) == "—"
