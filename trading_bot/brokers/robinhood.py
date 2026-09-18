"""Robinhood broker, backed by the ``robin_stocks`` library.

Heads-up: Robinhood does not publish an official trading API. ``robin_stocks``
is a community library that talks to Robinhood's private endpoints. It works, but
it can break when Robinhood changes things, and heavy automated use may get an
account flagged. Treat live trading here as genuinely at-your-own-risk, and lean
on the paper broker + DRY_RUN for everything you can.

Credentials come only from the environment (see config.py / .env). MFA is
supported via a TOTP secret so logins can run unattended.
"""
from __future__ import annotations

import logging
from typing import Dict

from .base import Broker, OrderResult, Position

log = logging.getLogger(__name__)


class RobinhoodBroker(Broker):
    def __init__(self, username: str, password: str, mfa_secret: str = "") -> None:
        try:
            import robin_stocks.robinhood as rh
        except ImportError as e:  # pragma: no cover - only hit without the extra
            raise RuntimeError(
                "robin_stocks is not installed. Run: pip install robin_stocks pyotp"
            ) from e
        self._rh = rh
        self._login(username, password, mfa_secret)

    def _login(self, username: str, password: str, mfa_secret: str) -> None:
        mfa_code = None
        if mfa_secret:
            try:
                import pyotp

                mfa_code = pyotp.TOTP(mfa_secret).now()
            except ImportError as e:  # pragma: no cover
                raise RuntimeError("pyotp is required for MFA. pip install pyotp") from e
        self._rh.login(username=username, password=password, mfa_code=mfa_code)
        log.info("Logged in to Robinhood as %s", username)

    def get_equity(self) -> float:
        profile = self._rh.profiles.load_portfolio_profile()
        val = profile.get("equity") or profile.get("extended_hours_equity")
        return float(val) if val else 0.0

    def get_cash(self) -> float:
        me = self._rh.profiles.load_account_profile()
        return float(me.get("buying_power", 0.0))

    def get_positions(self) -> Dict[str, Position]:
        out: Dict[str, Position] = {}
        for p in self._rh.account.get_open_stock_positions():
            qty = float(p.get("quantity", 0))
            if qty <= 0:
                continue
            symbol = self._rh.stocks.get_symbol_by_url(p["instrument"])
            out[symbol] = Position(
                symbol=symbol,
                quantity=qty,
                avg_price=float(p.get("average_buy_price", 0.0)),
            )
        return out

    def get_price(self, symbol: str) -> float:
        price = self._rh.stocks.get_latest_price(symbol, includeExtendedHours=False)
        return float(price[0])

    def buy_market(self, symbol: str, quantity: float) -> OrderResult:
        try:
            res = self._rh.orders.order_buy_market(symbol, int(quantity))
        except Exception as e:  # noqa: BLE001 - surface any broker error as a result
            return OrderResult(False, symbol, "buy", quantity, f"error: {e}")
        return self._wrap(res, symbol, "buy", quantity)

    def sell_market(self, symbol: str, quantity: float) -> OrderResult:
        try:
            res = self._rh.orders.order_sell_market(symbol, int(quantity))
        except Exception as e:  # noqa: BLE001
            return OrderResult(False, symbol, "sell", quantity, f"error: {e}")
        return self._wrap(res, symbol, "sell", quantity)

    def place_stop_loss(self, symbol: str, quantity: float, stop_price: float) -> OrderResult:
        try:
            res = self._rh.orders.order_sell_stop_loss(symbol, int(quantity), stop_price)
        except Exception as e:  # noqa: BLE001
            return OrderResult(False, symbol, "stop_loss", quantity, f"error: {e}")
        return self._wrap(res, symbol, "stop_loss", quantity)

    @staticmethod
    def _wrap(res: dict, symbol: str, side: str, qty: float) -> OrderResult:
        if isinstance(res, dict) and res.get("id"):
            return OrderResult(True, symbol, side, qty, f"order id {res['id']}")
        detail = res.get("detail") if isinstance(res, dict) else str(res)
        return OrderResult(False, symbol, side, qty, f"rejected: {detail}")
