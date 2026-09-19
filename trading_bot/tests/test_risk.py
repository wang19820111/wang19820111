"""Tests for the risk layer: sizing, stops, and guardrails."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from risk import (  # noqa: E402
    RiskParams,
    can_open_new_position,
    daily_loss_breached,
    shares_to_buy,
    stop_loss_price,
)


def test_position_capped_by_dollar_ceiling():
    p = RiskParams(max_position_pct=0.5, max_position_dollars=1000, stop_loss_pct=0.05)
    # 50% of 10k = 5000, but hard cap is 1000 -> 1000/100 = 10 shares.
    assert shares_to_buy(price=100, equity=10000, cash=10000, p=p) == 10


def test_position_capped_by_pct_of_equity():
    p = RiskParams(max_position_pct=0.10, max_position_dollars=100000)
    # 10% of 10k = 1000 -> 1000/50 = 20 shares.
    assert shares_to_buy(price=50, equity=10000, cash=10000, p=p) == 20


def test_position_capped_by_cash():
    p = RiskParams(max_position_pct=1.0, max_position_dollars=100000)
    assert shares_to_buy(price=100, equity=10000, cash=250, p=p) == 2


def test_zero_when_price_too_high():
    p = RiskParams(max_position_dollars=50)
    assert shares_to_buy(price=100, equity=10000, cash=10000, p=p) == 0


def test_zero_guards():
    p = RiskParams()
    assert shares_to_buy(price=0, equity=10000, cash=10000, p=p) == 0
    assert shares_to_buy(price=100, equity=0, cash=10000, p=p) == 0
    assert shares_to_buy(price=100, equity=10000, cash=0, p=p) == 0


def test_stop_loss_price():
    p = RiskParams(stop_loss_pct=0.05)
    assert stop_loss_price(100.0, p) == 95.0
    assert stop_loss_price(33.33, p) == 31.66  # rounded to the cent


def test_max_open_positions():
    p = RiskParams(max_open_positions=3)
    assert can_open_new_position(2, p) is True
    assert can_open_new_position(3, p) is False


def test_daily_loss_circuit_breaker():
    p = RiskParams(max_daily_loss_pct=0.03)
    assert daily_loss_breached(10000, 9800, p).breached is False   # 2% draw
    assert daily_loss_breached(10000, 9700, p).breached is True    # 3% draw
    assert daily_loss_breached(10000, 9500, p).breached is True    # 5% draw
    assert daily_loss_breached(0, 0, p).breached is False          # no anchor
