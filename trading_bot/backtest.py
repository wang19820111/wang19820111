"""Backtester: replay the RSI mean-reversion strategy over historical data.

The point of this file is to let you *validate your thresholds before trusting
them with real money*. It reuses the exact same ``strategy.evaluate`` and
``risk`` functions the live engine uses, so what you measure here is what the
bot would have done.

The core ``simulate`` function is pure (takes price data in, returns results
out), so it's unit-testable without any network. ``main`` is a thin CLI that
fetches real history and prints a report.

Modeling notes / honest caveats:
- Fills happen at the daily close (no intraday, no slippage, no commissions).
- Stop-losses trigger when a day's close is at/below the stop (we only have
  closes, not intraday lows), and fill at the stop price. Real fills can be
  worse on a gap down.
- This is a simplification. Treat results as directional, not gospel.
"""
from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from risk import RiskParams, shares_to_buy, stop_loss_price
from strategy import Signal, StrategyParams, evaluate

log = logging.getLogger(__name__)

PriceData = Dict[str, List[Tuple[str, float]]]  # symbol -> [(date_iso, close)]


@dataclass
class Trade:
    symbol: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    quantity: int
    pnl: float
    exit_reason: str  # "signal" | "stop" | "end-of-test"

    @property
    def won(self) -> bool:
        return self.pnl > 0


@dataclass
class BacktestResult:
    starting_cash: float
    ending_equity: float
    trades: List[Trade] = field(default_factory=list)
    max_drawdown_pct: float = 0.0

    @property
    def total_return_pct(self) -> float:
        if self.starting_cash <= 0:
            return 0.0
        return (self.ending_equity - self.starting_cash) / self.starting_cash * 100.0

    @property
    def num_trades(self) -> int:
        return len(self.trades)

    @property
    def wins(self) -> int:
        return sum(1 for t in self.trades if t.won)

    @property
    def losses(self) -> int:
        return sum(1 for t in self.trades if not t.won)

    @property
    def win_rate_pct(self) -> float:
        return (self.wins / self.num_trades * 100.0) if self.trades else 0.0


@dataclass
class _Pos:
    quantity: int
    entry_price: float
    entry_date: str
    stop: float


def simulate(
    price_data: PriceData,
    strategy: StrategyParams = StrategyParams(),
    risk: RiskParams = RiskParams(),
    starting_cash: float = 10000.0,
) -> BacktestResult:
    """Replay the strategy over aligned historical closes. Portfolio-level:
    shared cash and a shared ``max_open_positions`` cap, matching the live engine.
    """
    closes_by_symbol: Dict[str, Dict[str, float]] = {
        s: {d: c for d, c in series} for s, series in price_data.items()
    }
    all_dates = sorted({d for series in price_data.values() for d, _ in series})

    cash = starting_cash
    positions: Dict[str, _Pos] = {}
    running: Dict[str, List[float]] = {s: [] for s in price_data}
    last_close: Dict[str, float] = {}
    trades: List[Trade] = []
    peak = starting_cash
    max_dd = 0.0

    def equity_now() -> float:
        mv = sum(p.quantity * last_close.get(s, p.entry_price) for s, p in positions.items())
        return cash + mv

    for date in all_dates:
        for s in price_data:
            if date in closes_by_symbol[s]:
                price = closes_by_symbol[s][date]
                running[s].append(price)
                last_close[s] = price

        # 1) Stop-losses (checked against today's close).
        for s in list(positions.keys()):
            if date not in closes_by_symbol[s]:
                continue
            price = closes_by_symbol[s][date]
            pos = positions[s]
            if price <= pos.stop:
                cash += pos.stop * pos.quantity
                trades.append(Trade(
                    s, pos.entry_date, date, pos.entry_price, pos.stop,
                    pos.quantity, (pos.stop - pos.entry_price) * pos.quantity, "stop",
                ))
                del positions[s]

        # 2) Strategy signals.
        for s in price_data:
            if date not in closes_by_symbol[s]:
                continue
            price = closes_by_symbol[s][date]
            holding = s in positions
            ev = evaluate(s, running[s], holding, strategy)

            if ev.signal is Signal.SELL and holding:
                pos = positions[s]
                cash += price * pos.quantity
                trades.append(Trade(
                    s, pos.entry_date, date, pos.entry_price, price,
                    pos.quantity, (price - pos.entry_price) * pos.quantity, "signal",
                ))
                del positions[s]
            elif ev.signal is Signal.BUY and not holding:
                if len(positions) >= risk.max_open_positions:
                    continue
                qty = shares_to_buy(price, equity_now(), cash, risk)
                if qty <= 0:
                    continue
                cash -= price * qty
                positions[s] = _Pos(qty, price, date, stop_loss_price(price, risk))

        eq = equity_now()
        peak = max(peak, eq)
        if peak > 0:
            max_dd = max(max_dd, (peak - eq) / peak)

    # Close any still-open positions at the last known price (mark to market).
    last_date = all_dates[-1] if all_dates else ""
    for s, pos in list(positions.items()):
        price = last_close.get(s, pos.entry_price)
        cash += price * pos.quantity
        trades.append(Trade(
            s, pos.entry_date, last_date, pos.entry_price, price,
            pos.quantity, (price - pos.entry_price) * pos.quantity, "end-of-test",
        ))
    positions.clear()

    return BacktestResult(
        starting_cash=starting_cash,
        ending_equity=cash,
        trades=trades,
        max_drawdown_pct=max_dd * 100.0,
    )


def format_report(result: BacktestResult) -> str:
    lines = [
        "=" * 52,
        "BACKTEST RESULTS",
        "=" * 52,
        f"Starting cash:     ${result.starting_cash:,.2f}",
        f"Ending equity:     ${result.ending_equity:,.2f}",
        f"Total return:      {result.total_return_pct:+.2f}%",
        f"Max drawdown:      {result.max_drawdown_pct:.2f}%",
        f"Trades:            {result.num_trades}  "
        f"(W {result.wins} / L {result.losses}, win rate {result.win_rate_pct:.1f}%)",
        "-" * 52,
    ]
    for t in result.trades:
        lines.append(
            f"{t.symbol:<6} {t.entry_date[:10]} -> {t.exit_date[:10]}  "
            f"{t.quantity:>4} @ {t.entry_price:>8.2f} -> {t.exit_price:>8.2f}  "
            f"pnl {t.pnl:>+9.2f}  [{t.exit_reason}]"
        )
    lines.append("=" * 52)
    return "\n".join(lines)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    from config import Config
    from data_feed import get_closes_with_dates

    cfg = Config()
    # Use a longer window than the live loop so there's enough history to trade.
    period = "1y" if cfg.history_interval == "1d" else cfg.history_period
    log.info("Backtesting %s over %s (%s bars)...", cfg.watchlist, period, cfg.history_interval)

    price_data: PriceData = {}
    for symbol in cfg.watchlist:
        series = get_closes_with_dates(symbol, period, cfg.history_interval)
        if series:
            price_data[symbol] = series

    if not price_data:
        log.error("No price data fetched; cannot backtest.")
        return 1

    result = simulate(price_data, cfg.strategy, cfg.risk, cfg.paper_starting_cash)
    print(format_report(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
