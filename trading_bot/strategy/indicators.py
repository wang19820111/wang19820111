"""Technical indicators, implemented in pure Python.

Kept dependency-free (no pandas/numpy) so the math is transparent, deterministic,
and trivially unit-testable. The data feed converts market data into a plain list
of closing prices before calling into here.
"""
from __future__ import annotations

from typing import List


def rsi_series(closes: List[float], period: int = 14) -> List[float]:
    """Relative Strength Index using Wilder's smoothing method.

    Args:
        closes: Chronological list of closing prices (oldest first).
        period: Lookback window (Wilder's default is 14).

    Returns:
        A list of RSI values. The first value corresponds to ``closes[period]``,
        so the returned list has ``len(closes) - period`` entries. Returns an
        empty list when there is not enough data.
    """
    if period < 1:
        raise ValueError("period must be >= 1")
    if len(closes) < period + 1:
        return []

    gains: List[float] = []
    losses: List[float] = []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    # Seed with a simple average of the first `period` changes.
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    def _rsi(ag: float, al: float) -> float:
        if al == 0:
            return 100.0
        rs = ag / al
        return 100.0 - (100.0 / (1.0 + rs))

    out: List[float] = [_rsi(avg_gain, avg_loss)]
    # Apply Wilder smoothing across the remaining changes.
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        out.append(_rsi(avg_gain, avg_loss))
    return out


def latest_rsi(closes: List[float], period: int = 14) -> float | None:
    """Return the most recent RSI value, or ``None`` if there isn't enough data."""
    series = rsi_series(closes, period)
    return series[-1] if series else None
