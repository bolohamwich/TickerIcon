from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

import yfinance as yf

# Maps Yahoo Finance exchange codes to human-friendly names for the tooltip.
# Falls back to the metadata's own "fullExchangeName" when a code is unknown.
_EXCHANGE_NAMES = {
    'NMS': 'Nasdaq',
    'NYQ': 'NYSE',
    'ASE': 'NYSE American',
    'PCX': 'NYSE Arca',
    'LSE': 'London',
    'TOR': 'Toronto',
    'GER': 'Frankfurt',
    'PAR': 'Paris',
    'AMS': 'Amsterdam',
    'HKG': 'Hong Kong',
    'TYO': 'Tokyo',
    'SHH': 'Shanghai',
    'SHZ': 'Shenzhen',
    'NSI': 'NSE India',
    'BSE': 'BSE India',
    'ASX': 'Sydney',
}


@dataclass
class StockData:
    """Latest known snapshot of a single tracked ticker."""

    symbol: str
    price: float = 0.0
    change_pct: float = 0.0
    day_high: float = 0.0
    day_low: float = 0.0
    state: str = 'closed'
    exchange: str = ''
    next_open: Optional[datetime] = None
    has_error: bool = False


class MarketAPI:
    """
    Fetches quote data for one or more tickers from Yahoo Finance and
    resolves each ticker's own market session state from its exchange's
    trading hours, so symbols from different markets/timezones are all
    handled correctly.
    """

    def __init__(self, ticker_symbols: List[str]):
        """
        Args:
            ticker_symbols (List[str]): The ticker symbols to track.
        """
        self.ticker_symbols = ticker_symbols

    def fetch_all(self, previous: Optional[Dict[str, StockData]] = None) -> Dict[str, StockData]:
        """
        Fetches the latest snapshot for every tracked ticker.

        Note: yfinance has no batch quote endpoint, so this issues one
        request per ticker (sequentially, to avoid hammering Yahoo Finance).

        Args:
            previous (Optional[Dict[str, StockData]]): The last known snapshot;
                a ticker whose fetch fails keeps its previous values (flagged
                with has_error) instead of resetting to zeros.

        Returns:
            Dict[str, StockData]: Latest data keyed by ticker symbol.
        """
        previous = previous or {}
        return {symbol: self._fetch_one(symbol, previous.get(symbol)) for symbol in self.ticker_symbols}

    def _fetch_one(self, symbol: str, previous: Optional[StockData] = None) -> StockData:
        """
        Fetches and parses quote and session data for a single ticker.

        Args:
            symbol (str): The ticker symbol to fetch, e.g. 'AMD'.
            previous (Optional[StockData]): The last known snapshot for this
                symbol, returned (with has_error set) if the fetch fails.

        Returns:
            StockData: The parsed snapshot, or the last known values with
                has_error set if the fetch failed or returned no data.
        """
        data = StockData(symbol=symbol)
        try:
            ticker = yf.Ticker(symbol)
            # 1m bars: daily bars ignore prepost, hiding extended-hours moves
            todays_data = ticker.history(period='1d', interval='1m', prepost=True)

            if todays_data.empty:
                return self._error_result(symbol, previous)

            data.price = todays_data['Close'].iloc[-1]

            metadata = ticker.history_metadata
            data.exchange = _EXCHANGE_NAMES.get(
                metadata.get('exchangeName', ''),
                metadata.get('fullExchangeName', symbol),
            )
            data.state = self._resolve_state(metadata)
            data.next_open = self._resolve_next_open(metadata)

            prev_close = self._resolve_previous_close(ticker, metadata, data.state)
            data.change_pct = ((data.price - prev_close) / prev_close) * 100

            # Attempt to fetch high/low via fast_info, fallback to history dataframe
            try:
                data.day_high = ticker.fast_info['day_high']
                data.day_low = ticker.fast_info['day_low']
            except Exception:
                data.day_high = todays_data['High'].max()
                data.day_low = todays_data['Low'].min()

        except Exception:
            return self._error_result(symbol, previous)

        return data

    @staticmethod
    def _error_result(symbol: str, previous: Optional[StockData]) -> StockData:
        """
        Builds the snapshot returned for a failed fetch: the last known
        values flagged with has_error, or a zeroed placeholder if the
        symbol has never been fetched successfully.

        Args:
            symbol (str): The ticker symbol whose fetch failed.
            previous (Optional[StockData]): The last known snapshot, if any.

        Returns:
            StockData: The snapshot to display for the failed fetch.
        """
        if previous is not None:
            return replace(previous, has_error=True)
        return StockData(symbol=symbol, has_error=True)

    @staticmethod
    def _resolve_previous_close(ticker, metadata: dict, state: str) -> float:
        """
        Resolves the baseline close for the change percentage.

        During premarket, Yahoo's "regular market" fields still describe the
        previous day's session, so regular_market_previous_close is the close
        from two sessions back. The metadata's regularMarketPrice is the last
        regular close then (the session hasn't traded yet) - the baseline that
        matches the premarket change Yahoo itself displays.

        Args:
            ticker (yf.Ticker): The ticker being fetched.
            metadata (dict): Ticker.history_metadata for the symbol.
            state (str): The already-resolved market state for the symbol.

        Returns:
            float: The previous close to compute the change percentage against.
        """
        if state == 'premarket':
            last_close = metadata.get('regularMarketPrice')
            if last_close:
                return last_close

        # Prefer Yahoo's quoted previous close; fast_info['previous_close'] is
        # derived from daily bars and drifts around session boundaries/weekends.
        try:
            prev_close = ticker.fast_info['regular_market_previous_close']
        except (KeyError, TypeError):
            prev_close = None
        if not prev_close:
            prev_close = ticker.fast_info['previous_close']
        return prev_close

    @staticmethod
    def _resolve_state(metadata: dict) -> str:
        """
        Determines market state from the exchange's own current trading
        period (pre/regular/post), so it works regardless of which
        timezone or exchange the ticker trades on.

        Args:
            metadata (dict): Ticker.history_metadata for the symbol.

        Returns:
            str: One of 'premarket', 'open', 'after_hours', or 'closed'.
        """
        trading_period = metadata.get('currentTradingPeriod')
        if not trading_period:
            return 'closed'

        now = datetime.now(ZoneInfo("UTC"))
        pre, regular, post = trading_period['pre'], trading_period['regular'], trading_period['post']

        if pre['start'] <= now < pre['end']:
            return 'premarket'
        elif regular['start'] <= now < regular['end']:
            return 'open'
        elif post['start'] <= now < post['end']:
            return 'after_hours'
        return 'closed'

    @staticmethod
    def _resolve_next_open(metadata: dict) -> Optional[datetime]:
        """
        Projects the next weekday pre-market open for this exchange, using
        its own local trading hours.

        Args:
            metadata (dict): Ticker.history_metadata for the symbol.

        Returns:
            Optional[datetime]: The next pre-market open time in UTC, or
                None if the metadata doesn't include a trading period.
        """
        trading_period = metadata.get('currentTradingPeriod')
        if not trading_period:
            return None

        candidate = trading_period['pre']['start'].to_pydatetime()
        now = datetime.now(candidate.tzinfo)

        if candidate <= now:
            candidate += timedelta(days=1)

        # Skip Saturday/Sunday; exchange-specific holidays aren't tracked
        while candidate.weekday() >= 5:
            candidate += timedelta(days=1)

        return candidate.astimezone(ZoneInfo("UTC"))

    @staticmethod
    def get_next_open_time(snapshot: Dict[str, StockData]) -> Optional[datetime]:
        """
        Finds the soonest upcoming market open across a snapshot of tickers,
        used to let the update loop sleep longer when every market is closed.

        Args:
            snapshot (Dict[str, StockData]): Latest fetched data per ticker.

        Returns:
            Optional[datetime]: The earliest next open time, or None if no
                ticker in the snapshot has a known next open time.
        """
        next_opens = [d.next_open for d in snapshot.values() if d.next_open is not None]
        return min(next_opens) if next_opens else None