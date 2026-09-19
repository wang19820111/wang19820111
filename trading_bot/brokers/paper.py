"""Paper (simulated) broker.

Robinhood has no paper-trading sandbox, so this fills the gap: it mimics a
brokerage account in a local JSON file, using real market prices from the data
feed. Use it to validate the whole pipeline end-to-end before ever going live.

It is intentionally simple — market orders fill immediately at the current price
and stop-loss orders are tracked and triggered on each poll.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Callable, Dict, List

from .base import Broker, OrderResult, Position

log = logging.getLogger(__name__)


class PaperBroker(Broker):
    def __init__(
        self,
        price_fn: Callable[[str], float],
        starting_cash: float,
        state_file: str,
    ) -> None:
        self._price_fn = price_fn
        self._state_file = state_file
        self._cash: float = starting_cash
        self._positions: Dict[str, Position] = {}
        # Resting stops: symbol -> {"quantity", "stop_price"}
        self._stops: Dict[str, dict] = {}
        self._load(starting_cash)

    # --- persistence ---
    def _load(self, starting_cash: float) -> None:
        if not os.path.exists(self._state_file):
            return
        try:
            with open(self._state_file) as f:
                data = json.load(f)
            self._cash = data.get("cash", starting_cash)
            self._positions = {
                s: Position(**p) for s, p in data.get("positions", {}).items()
            }
            self._stops = data.get("stops", {})
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            log.warning("Could not load paper state (%s); starting fresh.", e)

    def _save(self) -> None:
        data = {
            "cash": self._cash,
            "positions": {s: vars(p) for s, p in self._positions.items()},
            "stops": self._stops,
        }
        tmp = self._state_file + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, self._state_file)

    # --- Broker interface ---
    def get_price(self, symbol: str) -> float:
        return self._price_fn(symbol)

    def get_cash(self) -> float:
        return self._cash

    def get_positions(self) -> Dict[str, Position]:
        return dict(self._positions)

    def get_equity(self) -> float:
        market_value = 0.0
        for sym, pos in self._positions.items():
            try:
                market_value += pos.quantity * self._price_fn(sym)
            except Exception:  # noqa: BLE001 - price lookup best-effort for equity
                market_value += pos.quantity * pos.avg_price
        return self._cash + market_value

    def buy_market(self, symbol: str, quantity: float) -> OrderResult:
        price = self._price_fn(symbol)
        cost = price * quantity
        if cost > self._cash:
            return OrderResult(False, symbol, "buy", quantity, "insufficient paper cash")
        existing = self._positions.get(symbol)
        if existing:
            total_qty = existing.quantity + quantity
            avg = (existing.avg_price * existing.quantity + price * quantity) / total_qty
            self._positions[symbol] = Position(symbol, total_qty, round(avg, 4))
        else:
            self._positions[symbol] = Position(symbol, quantity, round(price, 4))
        self._cash -= cost
        self._save()
        return OrderResult(True, symbol, "buy", quantity, f"filled @ {price:.2f} (paper)")

    def sell_market(self, symbol: str, quantity: float) -> OrderResult:
        pos = self._positions.get(symbol)
        if not pos or pos.quantity < quantity:
            return OrderResult(False, symbol, "sell", quantity, "no/insufficient position")
        price = self._price_fn(symbol)
        self._cash += price * quantity
        remaining = pos.quantity - quantity
        if remaining <= 0:
            self._positions.pop(symbol, None)
            self._stops.pop(symbol, None)
        else:
            self._positions[symbol] = Position(symbol, remaining, pos.avg_price)
        self._save()
        return OrderResult(True, symbol, "sell", quantity, f"filled @ {price:.2f} (paper)")

    def place_stop_loss(self, symbol: str, quantity: float, stop_price: float) -> OrderResult:
        self._stops[symbol] = {"quantity": quantity, "stop_price": stop_price}
        self._save()
        return OrderResult(True, symbol, "stop_loss", quantity, f"stop @ {stop_price:.2f} (paper)")

    # --- paper-only: evaluate resting stops against live prices ---
    def check_stops(self) -> List[OrderResult]:
        """Trigger any stop whose price has been breached. Call once per poll."""
        triggered: List[OrderResult] = []
        for symbol, stop in list(self._stops.items()):
            try:
                price = self._price_fn(symbol)
            except Exception:  # noqa: BLE001
                continue
            if price <= stop["stop_price"]:
                res = self.sell_market(symbol, stop["quantity"])
                if res.ok:
                    log.info("STOP-LOSS hit for %s at ~%.2f (paper)", symbol, price)
                triggered.append(res)
        return triggered
