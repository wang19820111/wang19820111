"""Configuration, loaded entirely from environment variables.

No secret ever lives in code. Copy ``.env.example`` to ``.env`` (which is
gitignored), fill it in, and it gets loaded automatically.

DRY_RUN defaults to True: the system will compute and log every decision but
place no real orders until you explicitly set DRY_RUN=false.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # dotenv is optional; env vars still work without it.
    pass

from risk import RiskParams
from strategy import StrategyParams


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw not in (None, "") else default


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw not in (None, "") else default


def _get_list(name: str, default: List[str]) -> List[str]:
    raw = os.getenv(name)
    if not raw:
        return default
    return [s.strip().upper() for s in raw.split(",") if s.strip()]


@dataclass
class Config:
    # --- Safety ---
    dry_run: bool = field(default_factory=lambda: _get_bool("DRY_RUN", True))

    # --- What to trade ---
    watchlist: List[str] = field(
        default_factory=lambda: _get_list("WATCHLIST", ["AAPL", "MSFT", "SPY"])
    )
    # yfinance history window + bar size used to compute RSI.
    history_period: str = field(default_factory=lambda: os.getenv("HISTORY_PERIOD", "3mo"))
    history_interval: str = field(default_factory=lambda: os.getenv("HISTORY_INTERVAL", "1d"))

    # --- Loop ---
    poll_seconds: int = field(default_factory=lambda: _get_int("POLL_SECONDS", 900))
    run_once: bool = field(default_factory=lambda: _get_bool("RUN_ONCE", False))
    respect_market_hours: bool = field(
        default_factory=lambda: _get_bool("RESPECT_MARKET_HOURS", True)
    )

    # --- Robinhood credentials (only read when dry_run is False) ---
    rh_username: str = field(default_factory=lambda: os.getenv("RH_USERNAME", ""))
    rh_password: str = field(default_factory=lambda: os.getenv("RH_PASSWORD", ""))
    rh_mfa_secret: str = field(default_factory=lambda: os.getenv("RH_MFA_SECRET", ""))

    # --- Paper broker starting cash (dry-run only) ---
    paper_starting_cash: float = field(
        default_factory=lambda: _get_float("PAPER_STARTING_CASH", 10000.0)
    )

    # --- Persistence ---
    state_file: str = field(default_factory=lambda: os.getenv("STATE_FILE", "state.json"))

    # --- Notifications (optional Slack/Discord-style webhook) ---
    notify_webhook_url: str = field(default_factory=lambda: os.getenv("NOTIFY_WEBHOOK_URL", ""))

    strategy: StrategyParams = field(
        default_factory=lambda: StrategyParams(
            rsi_period=_get_int("RSI_PERIOD", 14),
            entry_threshold=_get_float("RSI_ENTRY", 30.0),
            exit_threshold=_get_float("RSI_EXIT", 55.0),
        )
    )
    risk: RiskParams = field(
        default_factory=lambda: RiskParams(
            max_position_pct=_get_float("MAX_POSITION_PCT", 0.10),
            max_position_dollars=_get_float("MAX_POSITION_DOLLARS", 1000.0),
            stop_loss_pct=_get_float("STOP_LOSS_PCT", 0.05),
            max_open_positions=_get_int("MAX_OPEN_POSITIONS", 5),
            max_daily_loss_pct=_get_float("MAX_DAILY_LOSS_PCT", 0.03),
        )
    )

    def validate_for_live(self) -> None:
        """Raise if we're about to trade live without credentials."""
        if self.dry_run:
            return
        missing = [
            n for n, v in (
                ("RH_USERNAME", self.rh_username),
                ("RH_PASSWORD", self.rh_password),
            ) if not v
        ]
        if missing:
            raise RuntimeError(
                "DRY_RUN is false but these are not set: " + ", ".join(missing)
            )
