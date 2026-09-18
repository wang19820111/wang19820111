"""Broker interface.

The engine only ever talks to this abstract interface, so swapping Robinhood for
another broker (or the paper simulator) touches nothing else.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict


@dataclass
class Position:
    symbol: str
    quantity: float
    avg_price: float


@dataclass
class OrderResult:
    ok: bool
    symbol: str
    side: str          # "buy" | "sell" | "stop_loss"
    quantity: float
    detail: str        # broker order id, or an explanation on failure


class Broker(ABC):
    @abstractmethod
    def get_equity(self) -> float:
        """Total account value (cash + market value of positions)."""

    @abstractmethod
    def get_cash(self) -> float:
        """Buying power available for new positions."""

    @abstractmethod
    def get_positions(self) -> Dict[str, Position]:
        """Open positions keyed by symbol."""

    @abstractmethod
    def get_price(self, symbol: str) -> float:
        """Latest trade price for a symbol."""

    @abstractmethod
    def buy_market(self, symbol: str, quantity: float) -> OrderResult:
        """Submit a market BUY."""

    @abstractmethod
    def sell_market(self, symbol: str, quantity: float) -> OrderResult:
        """Submit a market SELL (used for the RSI-recovery exit)."""

    @abstractmethod
    def place_stop_loss(self, symbol: str, quantity: float, stop_price: float) -> OrderResult:
        """Submit a resting stop (sell-stop) order to cap downside."""
