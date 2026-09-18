"""Tests for the RSI indicator, checked against known reference behaviour."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategy.indicators import latest_rsi, rsi_series  # noqa: E402


def test_not_enough_data_returns_empty():
    assert rsi_series([1, 2, 3], period=14) == []
    assert latest_rsi([1, 2, 3], period=14) is None


def test_straight_up_is_100():
    closes = [float(i) for i in range(1, 30)]  # monotonically increasing
    assert latest_rsi(closes, period=14) == 100.0


def test_straight_down_is_0():
    closes = [float(i) for i in range(30, 1, -1)]  # monotonically decreasing
    assert latest_rsi(closes, period=14) == 0.0


def test_classic_wilder_reference_value():
    # Wilder's canonical worked example (from "New Concepts in Technical Trading
    # Systems"); first RSI value should be ~70.53.
    closes = [
        44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42,
        45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28,
    ]
    series = rsi_series(closes, period=14)
    assert len(series) == 1
    assert abs(series[0] - 70.53) < 0.1


def test_length_of_series():
    closes = [float(i % 7) + 1 for i in range(50)]
    assert len(rsi_series(closes, period=14)) == len(closes) - 14
