"""Risk management: position sizing, stop-loss levels, and trading guardrails.

Every rule here is deliberately explicit and boring. This is the layer that
protects your account, so it favours hard caps over cleverness. All functions
are pure (no I/O), so they can be unit-tested without a broker or network.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import floor


@dataclass(frozen=True)
class RiskParams:
    # Fraction of *total account equity* to deploy into a single position.
    max_position_pct: float = 0.10
    # Absolute ceiling on any one position, in dollars (hard cap).
    max_position_dollars: float = 1000.0
    # Stop-loss distance below entry, as a fraction (0.05 = 5% stop).
    stop_loss_pct: float = 0.05
    # Never hold more than this many concurrent positions.
    max_open_positions: int = 5
    # Halt all new BUYs for the day once realized+unrealized loss hits this
    # fraction of starting equity (0.03 = 3% daily drawdown circuit breaker).
    max_daily_loss_pct: float = 0.03


def shares_to_buy(price: float, equity: float, cash: float, p: RiskParams) -> int:
    """Whole shares to buy for a new position, respecting every cap.

    Bounded by: the per-position % of equity, the absolute dollar ceiling, and
    the cash actually available. Returns 0 if a sensible position can't be formed.
    """
    if price <= 0 or equity <= 0 or cash <= 0:
        return 0
    budget = min(equity * p.max_position_pct, p.max_position_dollars, cash)
    qty = floor(budget / price)
    return max(qty, 0)


def stop_loss_price(entry_price: float, p: RiskParams) -> float:
    """Stop-loss trigger price for a long position, rounded to the cent."""
    return round(entry_price * (1.0 - p.stop_loss_pct), 2)


def can_open_new_position(open_positions: int, p: RiskParams) -> bool:
    return open_positions < p.max_open_positions


@dataclass(frozen=True)
class DailyLossCheck:
    breached: bool
    drawdown_pct: float
    reason: str


def daily_loss_breached(
    starting_equity: float, current_equity: float, p: RiskParams
) -> DailyLossCheck:
    """Circuit breaker: True once the day's drawdown exceeds the configured cap."""
    if starting_equity <= 0:
        return DailyLossCheck(False, 0.0, "no starting equity recorded")
    drawdown = (starting_equity - current_equity) / starting_equity
    if drawdown >= p.max_daily_loss_pct:
        return DailyLossCheck(
            True, drawdown,
            f"daily drawdown {drawdown:.1%} >= cap {p.max_daily_loss_pct:.1%} — "
            f"halting new buys",
        )
    return DailyLossCheck(False, drawdown, f"daily drawdown {drawdown:.1%}, ok")
