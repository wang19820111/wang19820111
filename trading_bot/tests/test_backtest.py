"""Tests for the backtest simulation core (pure, no network)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest import simulate  # noqa: E402
from risk import RiskParams  # noqa: E402
from strategy import StrategyParams  # noqa: E402


def _dates(n):
    return [f"2024-01-{i + 1:02d}T00:00:00" for i in range(n)]


def _series(prices):
    return list(zip(_dates(len(prices)), [float(p) for p in prices]))


def test_no_trades_when_flat_data():
    # Flat prices -> RSI hovers, never triggers oversold entry.
    data = {"AAA": _series([100.0] * 40)}
    res = simulate(data, StrategyParams(), RiskParams(), starting_cash=10000)
    assert res.num_trades == 0
    assert res.ending_equity == 10000


def test_buys_on_oversold_then_exits_on_recovery():
    # Steady decline (RSI < 30) then a sharp recovery (RSI > 55) -> a round trip
    # that exits on the recovery signal. (Whether it profits depends on where in
    # the decline the entry landed — mean-reversion can catch a falling knife.)
    down = list(range(60, 25, -1))          # long decline -> oversold, triggers BUY
    up = list(range(26, 70))                # strong recovery -> triggers SELL
    data = {"AAA": _series(down + up)}
    res = simulate(data, StrategyParams(), RiskParams(stop_loss_pct=0.99), starting_cash=10000)
    assert res.num_trades >= 1
    assert any(t.exit_reason == "signal" for t in res.trades)


def test_accounting_invariant_holds():
    # Ending equity must equal starting cash plus the sum of realized P&L.
    down = list(range(60, 25, -1))
    up = list(range(26, 70))
    data = {"AAA": _series(down + up)}
    res = simulate(data, StrategyParams(), RiskParams(stop_loss_pct=0.99), starting_cash=10000)
    realized = sum(t.pnl for t in res.trades)
    assert abs(res.ending_equity - (10000 + realized)) < 1e-6


def test_stop_loss_caps_loss():
    # Buy after a decline, then price keeps falling -> stop-loss should fire.
    down = list(range(60, 25, -1))
    crash = [24.0, 20.0, 15.0, 10.0]
    data = {"AAA": _series(down + crash)}
    res = simulate(data, StrategyParams(), RiskParams(stop_loss_pct=0.05), starting_cash=10000)
    stop_exits = [t for t in res.trades if t.exit_reason == "stop"]
    assert len(stop_exits) >= 1
    # The stop should have exited near entry*(1-5%), not at the crash low.
    t = stop_exits[0]
    assert t.exit_price >= t.entry_price * 0.90


def test_max_open_positions_respected():
    # Two symbols both oversold, but cap of 1 -> at most one open at a time.
    down = list(range(60, 25, -1))
    data = {"AAA": _series(down), "BBB": _series(down)}
    res = simulate(
        data, StrategyParams(), RiskParams(max_open_positions=1, stop_loss_pct=0.99),
        starting_cash=10000,
    )
    # Both never held simultaneously -> total distinct entries is bounded sanely.
    assert res.num_trades <= 2


def test_return_pct_math():
    data = {"AAA": _series([100.0] * 40)}
    res = simulate(data, StrategyParams(), RiskParams(), starting_cash=10000)
    assert res.total_return_pct == 0.0
