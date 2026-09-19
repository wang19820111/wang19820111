"""Tests for the paper broker: fills, stops, and persistence."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brokers.paper import PaperBroker  # noqa: E402


class FakePrices:
    def __init__(self, price):
        self.price = price

    def __call__(self, symbol):
        return self.price


def _broker(price=100.0, cash=10000.0):
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    tmp.close()
    os.unlink(tmp.name)  # start with no state file
    return PaperBroker(FakePrices(price), starting_cash=cash, state_file=tmp.name), tmp.name


def test_buy_reduces_cash_and_opens_position():
    b, path = _broker(price=100, cash=10000)
    try:
        res = b.buy_market("AAPL", 10)
        assert res.ok
        assert b.get_cash() == 9000
        assert b.get_positions()["AAPL"].quantity == 10
    finally:
        os.path.exists(path) and os.unlink(path)


def test_buy_rejected_when_insufficient_cash():
    b, path = _broker(price=100, cash=50)
    try:
        res = b.buy_market("AAPL", 10)
        assert not res.ok
        assert b.get_positions() == {}
    finally:
        os.path.exists(path) and os.unlink(path)


def test_stop_loss_triggers_when_price_drops():
    prices = FakePrices(100.0)
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    tmp.close()
    os.unlink(tmp.name)
    b = PaperBroker(prices, starting_cash=10000, state_file=tmp.name)
    try:
        b.buy_market("AAPL", 10)
        b.place_stop_loss("AAPL", 10, stop_price=95.0)
        # Not breached yet.
        assert b.check_stops() == [] or all(r.ok for r in b.check_stops())
        assert "AAPL" in b.get_positions()
        # Drop below the stop.
        prices.price = 94.0
        triggered = b.check_stops()
        assert any(r.ok for r in triggered)
        assert "AAPL" not in b.get_positions()
    finally:
        os.path.exists(tmp.name) and os.unlink(tmp.name)


def test_state_persists_across_instances():
    prices = FakePrices(100.0)
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    tmp.close()
    os.unlink(tmp.name)
    try:
        b1 = PaperBroker(prices, starting_cash=10000, state_file=tmp.name)
        b1.buy_market("MSFT", 5)
        b2 = PaperBroker(prices, starting_cash=10000, state_file=tmp.name)
        assert b2.get_positions()["MSFT"].quantity == 5
        assert b2.get_cash() == 9500
    finally:
        os.path.exists(tmp.name) and os.unlink(tmp.name)
