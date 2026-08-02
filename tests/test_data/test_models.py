from datetime import date

from data.models import FuturesData, OHLCVBar, OISnapshot, OptionChainRow


class TestOHLCVBar:
    def test_create(self):
        bar = OHLCVBar(
            symbol="NIFTY", date=date(2024, 6, 1),
            open=22000, high=22100, low=21900, close=22050, volume=1_000_000,
        )
        assert bar.symbol == "NIFTY"
        assert bar.close == 22050


class TestFuturesData:
    def test_extends_ohlcv(self):
        fut = FuturesData(
            symbol="NIFTY", date=date(2024, 6, 1),
            open=22000, high=22100, low=21900, close=22050,
            volume=500_000, expiry=date(2024, 6, 27), oi=150_000,
        )
        assert fut.oi == 150_000
        assert fut.expiry == date(2024, 6, 27)


class TestOptionChainRow:
    def test_create(self):
        opt = OptionChainRow(
            symbol="NIFTY", date=date(2024, 6, 1), expiry=date(2024, 6, 27),
            strike=22500, option_type="CE",
            open=150, high=180, low=140, close=160, volume=50_000, oi=200_000,
        )
        assert opt.option_type == "CE"
        assert opt.strike == 22500


class TestOISnapshot:
    def test_pcr(self):
        snap = OISnapshot(
            symbol="NIFTY", date=date(2024, 6, 1), expiry=date(2024, 6, 27),
            total_ce_oi=100_000, total_pe_oi=120_000, pcr=1.2,
        )
        assert snap.pcr == 1.2
