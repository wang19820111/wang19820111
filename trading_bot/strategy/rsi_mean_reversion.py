"""RSI mean-reversion strategy.

Idea: markets that fall hard short-term tend to bounce. We BUY when RSI is
oversold (below ``entry_threshold``) and EXIT when it recovers past
``exit_threshold``. Downside is capped separately by a hard stop-loss placed at
order time (see ``risk.py``) — the RSI exit is the "take profit / thesis is done"
signal, the stop-loss is the "I was wrong" signal.

This module only produces *signals*. It never talks to a broker and never sizes
a position — that separation keeps the decision logic pure and testable.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List

from .indicators import latest_rsi


class Signal(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass(frozen=True)
class StrategyParams:
    rsi_period: int = 14
    entry_threshold: float = 30.0   # buy when RSI < this (oversold)
    exit_threshold: float = 55.0    # exit when RSI > this (recovered)


@dataclass(frozen=True)
class Evaluation:
    symbol: str
    signal: Signal
    rsi: float | None
    reason: str


def evaluate(
    symbol: str,
    closes: List[float],
    holding: bool,
    params: StrategyParams = StrategyParams(),
) -> Evaluation:
    """Decide BUY / SELL / HOLD for a single symbol.

    Args:
        symbol: Ticker being evaluated (for logging/traceability).
        closes: Chronological closing prices (oldest first).
        holding: Whether we currently hold a position in this symbol.
        params: Strategy thresholds.
    """
    rsi = latest_rsi(closes, params.rsi_period)
    if rsi is None:
        return Evaluation(symbol, Signal.HOLD, None, "insufficient price history")

    if not holding:
        if rsi < params.entry_threshold:
            return Evaluation(
                symbol, Signal.BUY, rsi,
                f"RSI {rsi:.1f} < entry {params.entry_threshold:.0f} (oversold)",
            )
        return Evaluation(symbol, Signal.HOLD, rsi, f"RSI {rsi:.1f}, no entry")

    # Currently holding -> look for the recovery exit. (Stop-loss is handled by a
    # resting stop order at the broker, independent of this loop.)
    if rsi > params.exit_threshold:
        return Evaluation(
            symbol, Signal.SELL, rsi,
            f"RSI {rsi:.1f} > exit {params.exit_threshold:.0f} (recovered)",
        )
    return Evaluation(symbol, Signal.HOLD, rsi, f"RSI {rsi:.1f}, holding")
