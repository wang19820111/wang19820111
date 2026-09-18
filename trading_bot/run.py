"""Entry point: wire everything together and run the loop.

    python run.py

Defaults to DRY_RUN (no real orders). Set DRY_RUN=false in .env to go live.
"""
from __future__ import annotations

import logging
import sys
import time
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

from brokers.paper import PaperBroker
from config import Config
from data_feed import get_closes
from engine import Engine, EngineDeps

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("run")

_ET = ZoneInfo("America/New_York")
_MARKET_OPEN = dtime(9, 30)
_MARKET_CLOSE = dtime(16, 0)


def market_is_open(now_et: datetime | None = None) -> bool:
    now = now_et or datetime.now(_ET)
    if now.weekday() >= 5:  # Sat/Sun
        return False
    return _MARKET_OPEN <= now.time() <= _MARKET_CLOSE


def build_engine(cfg: Config) -> Engine:
    cfg.validate_for_live()

    if cfg.dry_run:
        log.info("DRY_RUN is ON — using paper broker, no real orders will be placed.")
        # Paper broker prices come from the live data feed (last close).
        def paper_price(symbol: str) -> float:
            closes = get_closes(symbol, cfg.history_period, cfg.history_interval)
            if not closes:
                raise RuntimeError(f"no price for {symbol}")
            return closes[-1]

        broker = PaperBroker(paper_price, cfg.paper_starting_cash, cfg.state_file)
    else:
        log.warning("DRY_RUN is OFF — LIVE trading against Robinhood with real money.")
        from brokers.robinhood import RobinhoodBroker

        broker = RobinhoodBroker(cfg.rh_username, cfg.rh_password, cfg.rh_mfa_secret)

    deps = EngineDeps(
        broker=broker,
        closes_fn=lambda s: get_closes(s, cfg.history_period, cfg.history_interval),
        watchlist=cfg.watchlist,
        strategy=cfg.strategy,
        risk=cfg.risk,
        dry_run=cfg.dry_run,
    )
    return Engine(deps)


def main() -> int:
    cfg = Config()
    log.info(
        "Config: dry_run=%s watchlist=%s poll=%ss run_once=%s",
        cfg.dry_run, cfg.watchlist, cfg.poll_seconds, cfg.run_once,
    )
    engine = build_engine(cfg)
    broker = engine.d.broker

    while True:
        try:
            if cfg.respect_market_hours and not market_is_open():
                log.info("Market closed — skipping cycle.")
            else:
                engine.run_cycle()
                # Paper broker evaluates its own resting stops each cycle.
                if isinstance(broker, PaperBroker):
                    broker.check_stops()
        except KeyboardInterrupt:
            log.info("Interrupted — shutting down.")
            return 0
        except Exception as e:  # noqa: BLE001 - keep the loop alive across transient errors
            log.exception("Cycle error: %s", e)

        if cfg.run_once:
            return 0
        time.sleep(cfg.poll_seconds)


if __name__ == "__main__":
    sys.exit(main())
