from datetime import date

from data.fetchers.nse_symbols import get_lot_size


class TestGetLotSize:
    def test_nifty_pre_july_2021(self):
        assert get_lot_size("NIFTY", date(2021, 3, 1)) == 75

    def test_nifty_post_july_2021(self):
        assert get_lot_size("NIFTY", date(2022, 6, 1)) == 50

    def test_nifty_post_april_2024(self):
        assert get_lot_size("NIFTY", date(2024, 8, 1)) == 25

    def test_nifty_post_november_2024(self):
        assert get_lot_size("NIFTY", date(2025, 3, 1)) == 75

    def test_nifty_post_january_2026(self):
        assert get_lot_size("NIFTY", date(2026, 6, 1)) == 65

    def test_banknifty_pre_june_2023(self):
        assert get_lot_size("BANKNIFTY", date(2023, 3, 1)) == 25

    def test_banknifty_15_lot_period(self):
        assert get_lot_size("BANKNIFTY", date(2024, 3, 1)) == 15

    def test_banknifty_post_november_2024(self):
        assert get_lot_size("BANKNIFTY", date(2025, 6, 1)) == 30

    def test_stock_from_fo_list(self):
        assert get_lot_size("RELIANCE", date(2025, 1, 1)) == 500

    def test_unknown_symbol_returns_1(self):
        assert get_lot_size("UNKNOWNSYMBOL", date(2025, 1, 1)) == 1

    def test_live_data_override(self):
        live = {"RELIANCE": 600}
        assert get_lot_size("RELIANCE", date(2025, 1, 1), live_data=live) == 600
