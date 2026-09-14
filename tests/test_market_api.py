from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from src.market_api import MarketAPI, StockData


def _trading_period(now, pre_offset, regular_offset, post_offset):
    """Builds a currentTradingPeriod dict with pre/regular/post windows relative to `now`."""
    def window(start_min, end_min):
        return {
            "start": pd.Timestamp(now + timedelta(minutes=start_min)),
            "end": pd.Timestamp(now + timedelta(minutes=end_min)),
        }

    return {
        "pre": window(*pre_offset),
        "regular": window(*regular_offset),
        "post": window(*post_offset),
    }


class TestResolveState:
    def test_returns_closed_when_no_trading_period(self):
        assert MarketAPI._resolve_state({}) == "closed"

    def test_returns_premarket_when_now_within_pre_window(self):
        now = datetime.now(ZoneInfo("UTC"))
        metadata = {"currentTradingPeriod": _trading_period(now, (-30, 30), (60, 120), (150, 180))}
        assert MarketAPI._resolve_state(metadata) == "premarket"

    def test_returns_open_when_now_within_regular_window(self):
        now = datetime.now(ZoneInfo("UTC"))
        metadata = {"currentTradingPeriod": _trading_period(now, (-90, -30), (-15, 15), (30, 60))}
        assert MarketAPI._resolve_state(metadata) == "open"

    def test_returns_after_hours_when_now_within_post_window(self):
        now = datetime.now(ZoneInfo("UTC"))
        metadata = {"currentTradingPeriod": _trading_period(now, (-120, -90), (-60, -30), (-15, 15))}
        assert MarketAPI._resolve_state(metadata) == "after_hours"

    def test_returns_closed_when_outside_all_windows(self):
        now = datetime.now(ZoneInfo("UTC"))
        metadata = {"currentTradingPeriod": _trading_period(now, (-300, -240), (-230, -170), (-160, -100))}
        assert MarketAPI._resolve_state(metadata) == "closed"


class TestResolveNextOpen:
    def test_returns_none_when_no_trading_period(self):
        assert MarketAPI._resolve_next_open({}) is None

    def test_projects_next_open_in_the_future_on_a_weekday(self):
        now = datetime.now(ZoneInfo("UTC"))
        metadata = {"currentTradingPeriod": _trading_period(now, (-120, -60), (-30, 30), (60, 90))}

        next_open = MarketAPI._resolve_next_open(metadata)

        assert next_open is not None
        assert next_open > now
        assert next_open.weekday() < 5

    def test_skips_weekend_when_pre_market_already_elapsed_on_friday(self):
        friday = datetime(2026, 9, 11, 18, 0, tzinfo=ZoneInfo("UTC"))
        metadata = {"currentTradingPeriod": _trading_period(friday, (-120, -60), (-30, 30), (60, 90))}

        with patch("src.market_api.datetime") as mock_datetime:
            mock_datetime.now.return_value = friday
            next_open = MarketAPI._resolve_next_open(metadata)

        assert next_open.weekday() == 0  # Monday


class TestGetNextOpenTime:
    def test_returns_none_for_empty_snapshot(self):
        assert MarketAPI.get_next_open_time({}) is None

    def test_returns_none_when_no_ticker_has_a_next_open(self):
        snapshot = {"AMD": StockData(symbol="AMD", next_open=None)}
        assert MarketAPI.get_next_open_time(snapshot) is None

    def test_returns_earliest_next_open_across_tickers(self):
        now = datetime.now(ZoneInfo("UTC"))
        earlier = now + timedelta(hours=1)
        later = now + timedelta(hours=5)
        snapshot = {
            "AMD": StockData(symbol="AMD", next_open=later),
            "AAPL": StockData(symbol="AAPL", next_open=earlier),
            "MSFT": StockData(symbol="MSFT", next_open=None),
        }

        assert MarketAPI.get_next_open_time(snapshot) == earlier


class TestFetchAll:
    def test_fetch_all_builds_snapshot_keyed_by_symbol(self):
        api = MarketAPI(["AMD", "AAPL"])
        placeholder = StockData(symbol="PLACEHOLDER")

        with patch.object(MarketAPI, "_fetch_one", return_value=placeholder) as mock_fetch_one:
            snapshot = api.fetch_all()

        assert set(snapshot.keys()) == {"AMD", "AAPL"}
        assert mock_fetch_one.call_count == 2


class TestFetchOne:
    def test_marks_error_when_history_is_empty(self):
        api = MarketAPI(["AMD"])
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()

        with patch("src.market_api.yf.Ticker", return_value=mock_ticker):
            data = api._fetch_one("AMD")

        assert data.has_error is True
        assert data.symbol == "AMD"

    def test_marks_error_on_unexpected_exception(self):
        api = MarketAPI(["AMD"])

        with patch("src.market_api.yf.Ticker", side_effect=RuntimeError("boom")):
            data = api._fetch_one("AMD")

        assert data.has_error is True

    def test_parses_successful_response(self):
        api = MarketAPI(["AMD"])
        now = datetime.now(ZoneInfo("UTC"))

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame({"Close": [123.45], "High": [125.0], "Low": [120.0]})
        mock_ticker.fast_info = {"previous_close": 100.0, "day_high": 130.0, "day_low": 95.0}
        mock_ticker.history_metadata = {
            "exchangeName": "NMS",
            "fullExchangeName": "NasdaqGS",
            "currentTradingPeriod": _trading_period(now, (-90, -30), (-15, 15), (30, 60)),
        }

        with patch("src.market_api.yf.Ticker", return_value=mock_ticker):
            data = api._fetch_one("AMD")

        assert data.has_error is False
        assert data.price == 123.45
        assert data.change_pct == pytest.approx(23.45)
        assert data.day_high == 130.0
        assert data.day_low == 95.0
        assert data.exchange == "Nasdaq"
        assert data.state == "open"
        assert data.next_open is not None

    def test_requests_intraday_bars_with_extended_hours(self):
        api = MarketAPI(["AMD"])

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame({"Close": [10.0], "High": [11.0], "Low": [9.0]})
        mock_ticker.fast_info = {"previous_close": 10.0, "day_high": 11.0, "day_low": 9.0}
        mock_ticker.history_metadata = {}

        with patch("src.market_api.yf.Ticker", return_value=mock_ticker):
            api._fetch_one("AMD")

        mock_ticker.history.assert_called_once_with(period='1d', interval='1m', prepost=True)

    def test_prefers_regular_market_previous_close_when_available(self):
        api = MarketAPI(["AMD"])

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame({"Close": [102.0], "High": [103.0], "Low": [99.0]})
        mock_ticker.fast_info = {
            # Stale daily-bar derived value that must be ignored
            "previous_close": 90.0,
            "regular_market_previous_close": 100.0,
            "day_high": 103.0,
            "day_low": 99.0,
        }
        mock_ticker.history_metadata = {}

        with patch("src.market_api.yf.Ticker", return_value=mock_ticker):
            data = api._fetch_one("AMD")

        assert data.change_pct == pytest.approx(2.0)

    def test_falls_back_to_previous_close_when_regular_market_value_missing(self):
        api = MarketAPI(["AMD"])

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame({"Close": [102.0], "High": [103.0], "Low": [99.0]})
        mock_ticker.fast_info = {"previous_close": 100.0, "day_high": 103.0, "day_low": 99.0}
        mock_ticker.history_metadata = {}

        with patch("src.market_api.yf.Ticker", return_value=mock_ticker):
            data = api._fetch_one("AMD")

        assert data.change_pct == pytest.approx(2.0)

    def test_premarket_change_is_measured_against_last_regular_close(self):
        api = MarketAPI(["AMD"])
        now = datetime.now(ZoneInfo("UTC"))

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame({"Close": [94.0], "High": [95.0], "Low": [93.0]})
        mock_ticker.fast_info = {
            # In premarket this is the close from two sessions back; must be ignored
            "regular_market_previous_close": 90.0,
            "previous_close": 90.0,
            "day_high": 95.0,
            "day_low": 93.0,
        }
        mock_ticker.history_metadata = {
            "regularMarketPrice": 100.0,
            "currentTradingPeriod": _trading_period(now, (-30, 30), (60, 120), (150, 180)),
        }

        with patch("src.market_api.yf.Ticker", return_value=mock_ticker):
            data = api._fetch_one("AMD")

        assert data.state == "premarket"
        assert data.change_pct == pytest.approx(-6.0)

    def test_premarket_falls_back_to_fast_info_when_metadata_price_missing(self):
        api = MarketAPI(["AMD"])
        now = datetime.now(ZoneInfo("UTC"))

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame({"Close": [102.0], "High": [103.0], "Low": [99.0]})
        mock_ticker.fast_info = {"regular_market_previous_close": 100.0, "day_high": 103.0, "day_low": 99.0}
        mock_ticker.history_metadata = {
            "currentTradingPeriod": _trading_period(now, (-30, 30), (60, 120), (150, 180)),
        }

        with patch("src.market_api.yf.Ticker", return_value=mock_ticker):
            data = api._fetch_one("AMD")

        assert data.state == "premarket"
        assert data.change_pct == pytest.approx(2.0)

    def test_falls_back_to_history_high_low_when_fast_info_missing_them(self):
        api = MarketAPI(["AMD"])

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame({"Close": [10.0], "High": [12.0], "Low": [8.0]})
        mock_ticker.fast_info = {"previous_close": 10.0}
        mock_ticker.history_metadata = {}

        with patch("src.market_api.yf.Ticker", return_value=mock_ticker):
            data = api._fetch_one("AMD")

        assert data.day_high == 12.0
        assert data.day_low == 8.0

    def test_falls_back_to_full_exchange_name_for_unknown_exchange_code(self):
        api = MarketAPI(["FOO"])
        now = datetime.now(ZoneInfo("UTC"))

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame({"Close": [1.0], "High": [1.0], "Low": [1.0]})
        mock_ticker.fast_info = {"previous_close": 1.0, "day_high": 1.0, "day_low": 1.0}
        mock_ticker.history_metadata = {
            "exchangeName": "XYZ",
            "fullExchangeName": "Some Exchange",
            "currentTradingPeriod": _trading_period(now, (-300, -240), (-230, -170), (-160, -100)),
        }

        with patch("src.market_api.yf.Ticker", return_value=mock_ticker):
            data = api._fetch_one("FOO")

        assert data.exchange == "Some Exchange"
        assert data.state == "closed"
