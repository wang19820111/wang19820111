# RSI Mean-Reversion Trading Bot (Robinhood)

An automated trading system **you own and control**. The decision to execute a
trade is *your code and your configuration* — explicit, auditable rules — not a
model improvising in a chat. It watches a list of stocks, buys when they're
oversold (RSI), places a hard stop-loss on every entry, and exits when they
recover.

> ⚠️ **Real money.** When you turn off dry-run mode this places live trades from
> your Robinhood account. Markets are risky, this strategy can and will lose
> money, and there is no warranty. Start in paper mode, understand every rule,
> and only risk what you can afford to lose.

---

## How it works

Each cycle, for every symbol in your watchlist:

1. **Data** — fetch recent closing prices (via `yfinance`, free, no login).
2. **Signal** — compute RSI. `RSI < 30` (oversold) → **BUY**; `RSI > 55`
   (recovered) while holding → **SELL**.
3. **Risk** — size the position by your caps (% of equity, hard dollar ceiling,
   available cash, max open positions), compute a stop-loss price.
4. **Execute** — place a market buy, then a resting **stop-loss** order. Exits
   fire either from the RSI-recovery signal or the stop-loss, whichever hits first.
5. **Circuit breaker** — if the account draws down past your daily-loss cap, new
   buys are halted for the day.

Everything is driven by settings in `.env`, so you tune behaviour without
touching code.

## Safety model

- **`DRY_RUN=true` by default.** The bot computes and logs the exact orders it
  *would* place but sends nothing. Robinhood has no paper-trading sandbox, so a
  built-in **paper broker** simulates an account (using real prices) for
  realistic end-to-end testing.
- **No secrets in code.** Credentials load from `.env`, which is gitignored.
  This repo is public — never commit `.env`.
- **Hard caps everywhere** — per-position size, a stop-loss on every entry, a
  max number of open positions, and a daily-loss circuit breaker.

## Project layout

```
trading_bot/
├── run.py                # entry point + loop + market-hours gate
├── engine.py             # orchestrates: data → signal → risk → broker
├── config.py             # all settings, loaded from .env
├── data_feed.py          # historical prices (yfinance)
├── risk.py               # position sizing, stop-loss, guardrails (pure)
├── strategy/
│   ├── indicators.py     # RSI (Wilder's method, pure Python)
│   └── rsi_mean_reversion.py   # BUY/SELL/HOLD signal logic (pure)
├── brokers/
│   ├── base.py           # Broker interface
│   ├── paper.py          # simulated broker for testing
│   └── robinhood.py      # live Robinhood (robin_stocks)
└── tests/                # unit tests (no network, no broker)
```

## Setup

```bash
cd trading_bot
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env      # then edit .env
```

## Run it (paper mode — safe)

With `DRY_RUN=true` in `.env`:

```bash
python run.py
```

You'll see log lines like:

```
[DRY-RUN] WOULD BUY 10 AAPL @ ~100.00 then STOP-LOSS @ 95.00 — RSI 28.4 < entry 30 (oversold)
```

Set `RUN_ONCE=true` to run a single cycle and exit while you're experimenting.

## Going live (real money)

Only after you've watched it in paper mode and you trust the behaviour:

1. In `.env`, set your Robinhood details and `DRY_RUN=false`:
   ```
   DRY_RUN=false
   RH_USERNAME=you@example.com
   RH_PASSWORD=your-password
   RH_MFA_SECRET=your-totp-secret   # optional, for unattended MFA logins
   ```
2. `python run.py`

The bot logs in, and from then on `[LIVE]` lines mean real orders.

### About the Robinhood connection

Robinhood has no official public trading API. This uses
[`robin_stocks`](https://github.com/jmfernandes/robin_stocks), a community
library that talks to Robinhood's private endpoints. It works, but it can break
when Robinhood changes things, and aggressive automation may get an account
flagged. If you later want a broker built for automation, the engine's `Broker`
interface (`brokers/base.py`) is designed so you can drop in another
implementation (e.g. Alpaca) without changing anything else.

## Tune the strategy

All in `.env` — e.g. a more aggressive entry and tighter stop:

```
RSI_ENTRY=25
STOP_LOSS_PCT=0.03
MAX_POSITION_DOLLARS=500
WATCHLIST=AAPL,MSFT,NVDA,SPY,QQQ
```

## Tests

```bash
python -m pytest
```

Covers the RSI math (against Wilder's reference values), the signal logic, the
risk caps and circuit breaker, and the paper broker's fills, stops, and
persistence. None of them touch the network or a live account.

## Suggested next steps

- **Backtest** the RSI thresholds on historical data before trusting them live.
- **Move this to a private repo** if you'd rather not keep your strategy public
  (the code is broker-credential-free, but a private repo is tidier for trading).
- **Add a notifier** (email/Slack) on fills and stop-loss triggers.
