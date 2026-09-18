"""Trading engine: orchestrates one full evaluation cycle.

Flow per cycle:
  1. Circuit breaker: if the daily-loss cap is breached, block new buys.
  2. For each symbol: fetch closes -> RSI signal.
  3. BUY  -> size via risk rules -> place market buy -> place resting stop-loss.
     SELL -> exit the position (RSI recovery).
     HOLD -> do nothing.

In DRY_RUN mode the engine logs the exact order it *would* place and calls
nothing on the broker.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, List

from brokers.base import Broker
from risk import (
    RiskParams,
    can_open_new_position,
    daily_loss_breached,
    shares_to_buy,
    stop_loss_price,
)
from strategy import Signal, StrategyParams, evaluate

log = logging.getLogger(__name__)


@dataclass
class EngineDeps:
    broker: Broker
    closes_fn: Callable[[str], List[float]]
    watchlist: List[str]
    strategy: StrategyParams
    risk: RiskParams
    dry_run: bool


class Engine:
    def __init__(self, deps: EngineDeps) -> None:
        self.d = deps
        # Anchor for the daily-loss circuit breaker; set on first run of the day.
        self._starting_equity: float | None = None

    def _tag(self) -> str:
        return "[DRY-RUN]" if self.d.dry_run else "[LIVE]"

    def run_cycle(self) -> None:
        broker = self.d.broker
        equity = broker.get_equity()
        if self._starting_equity is None:
            self._starting_equity = equity
            log.info("Anchored starting equity at %.2f", equity)

        breaker = daily_loss_breached(self._starting_equity, equity, self.d.risk)
        buys_allowed = not breaker.breached
        if breaker.breached:
            log.warning("%s CIRCUIT BREAKER: %s", self._tag(), breaker.reason)

        positions = broker.get_positions()
        log.info(
            "%s equity=%.2f cash=%.2f open_positions=%d",
            self._tag(), equity, broker.get_cash(), len(positions),
        )

        for symbol in self.d.watchlist:
            closes = self.d.closes_fn(symbol)
            if not closes:
                continue
            holding = symbol in positions
            ev = evaluate(symbol, closes, holding, self.d.strategy)

            if ev.signal is Signal.HOLD:
                log.info("%s %s HOLD — %s", self._tag(), symbol, ev.reason)
                continue

            if ev.signal is Signal.BUY:
                self._handle_buy(symbol, ev.reason, equity, buys_allowed, len(positions))
            elif ev.signal is Signal.SELL:
                self._handle_sell(symbol, ev.reason, positions[symbol].quantity)

    def _handle_buy(
        self, symbol: str, reason: str, equity: float, buys_allowed: bool, open_count: int
    ) -> None:
        if not buys_allowed:
            log.info("%s %s BUY suppressed (circuit breaker) — %s", self._tag(), symbol, reason)
            return
        if not can_open_new_position(open_count, self.d.risk):
            log.info("%s %s BUY skipped: max open positions reached", self._tag(), symbol)
            return

        broker = self.d.broker
        price = broker.get_price(symbol)
        qty = shares_to_buy(price, equity, broker.get_cash(), self.d.risk)
        if qty <= 0:
            log.info("%s %s BUY skipped: size rounds to 0 shares @ %.2f", self._tag(), symbol, price)
            return
        stop = stop_loss_price(price, self.d.risk)

        if self.d.dry_run:
            log.info(
                "%s WOULD BUY %d %s @ ~%.2f then STOP-LOSS @ %.2f — %s",
                self._tag(), qty, symbol, price, stop, reason,
            )
            return

        res = broker.buy_market(symbol, qty)
        log.info("%s BUY %d %s -> %s", self._tag(), qty, symbol, res.detail)
        if res.ok:
            stop_res = broker.place_stop_loss(symbol, qty, stop)
            log.info("%s STOP-LOSS %s @ %.2f -> %s", self._tag(), symbol, stop, stop_res.detail)

    def _handle_sell(self, symbol: str, reason: str, quantity: float) -> None:
        if self.d.dry_run:
            log.info("%s WOULD SELL %s %s — %s", self._tag(), quantity, symbol, reason)
            return
        res = self.d.broker.sell_market(symbol, quantity)
        log.info("%s SELL %s %s -> %s — %s", self._tag(), quantity, symbol, res.detail, reason)
