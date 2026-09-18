"""Market data feed.

Uses yfinance for historical closes (free, no auth) so signal generation is
decoupled from the broker. Prices for *execution* still come from the broker
itself (see Broker.get_price).
"""
from __future__ import annotations

import logging
from typing import List

log = logging.getLogger(__name__)


def get_closes(symbol: str, period: str = "3mo", interval: str = "1d") -> List[float]:
    """Return chronological closing prices for a symbol (oldest first).

    Returns an empty list if data can't be fetched, so the engine can skip the
    symbol rather than crash.
    """
    try:
        import yfinance as yf
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("yfinance is not installed. Run: pip install yfinance") from e

    try:
        df = yf.Ticker(symbol).history(period=period, interval=interval)
    except Exception as e:  # noqa: BLE001 - network/parse issues shouldn't kill the loop
        log.warning("Failed to fetch history for %s: %s", symbol, e)
        return []

    if df is None or df.empty or "Close" not in df:
        log.warning("No price data returned for %s", symbol)
        return []
    return [float(x) for x in df["Close"].dropna().tolist()]
