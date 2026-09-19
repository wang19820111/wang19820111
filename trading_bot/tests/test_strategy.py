"""Tests for the RSI mean-reversion signal logic."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategy.rsi_mean_reversion import Signal, StrategyParams, evaluate  # noqa: E402

PARAMS = StrategyParams(rsi_period=14, entry_threshold=30.0, exit_threshold=55.0)


def _oversold_closes():
    # Long decline drives RSI well below 30.
    return [float(i) for i in range(60, 20, -1)]


def _overbought_closes():
    return [float(i) for i in range(20, 60)]


def test_buy_when_oversold_and_flat():
    ev = evaluate("AAPL", _oversold_closes(), holding=False, params=PARAMS)
    assert ev.signal is Signal.BUY
    assert ev.rsi is not None and ev.rsi < 30


def test_no_buy_when_already_holding():
    ev = evaluate("AAPL", _oversold_closes(), holding=True, params=PARAMS)
    # Oversold while holding -> not an exit, so HOLD.
    assert ev.signal is Signal.HOLD


def test_sell_when_recovered_and_holding():
    ev = evaluate("AAPL", _overbought_closes(), holding=True, params=PARAMS)
    assert ev.signal is Signal.SELL
    assert ev.rsi is not None and ev.rsi > 55


def test_hold_when_recovered_but_flat():
    ev = evaluate("AAPL", _overbought_closes(), holding=False, params=PARAMS)
    assert ev.signal is Signal.HOLD


def test_hold_on_insufficient_data():
    ev = evaluate("AAPL", [1.0, 2.0, 3.0], holding=False, params=PARAMS)
    assert ev.signal is Signal.HOLD
    assert ev.rsi is None
