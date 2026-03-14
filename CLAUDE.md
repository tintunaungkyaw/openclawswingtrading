# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OpenClaw Swing Trading is a **swing trading signal bot** that scans US technology stocks and sends alerts to a Telegram group during US market hours. It runs on a remote Linux server (Singapore timezone, but tracks US market sessions). It does **NOT** execute trades — signals only.

The full specification is in `prompt.txt`. The project is in the implementation phase; no source code exists yet.

## Technology Stack

- **Python 3.11+**
- **Data:** `yfinance`, `yfscreen`, `pandas`, `numpy`, `pandas-ta` or `TA-Lib`
- **Telegram:** `python-telegram-bot`
- **Scheduling:** `APScheduler` or cron
- **Caching:** SQLite, Redis, or local parquet files
- **Config validation:** `pydantic`
- **Logging:** `loguru`
- **Retries/resilience:** `tenacity`
- **Async (optional):** `aiohttp`

## Planned Project Structure

```
trading-signal-bot/
├── config/
│   └── config.yaml           # All runtime config (no secrets)
├── core/
│   ├── scanner.py            # Orchestrates stock scanning loop
│   ├── strategy_engine.py    # Evaluates signals per ticker
│   ├── indicators.py         # Technical indicator calculations
│   └── signal_model.py       # Pydantic signal data model
├── data/
│   ├── data_provider.py      # yfinance data fetching
│   └── cache_manager.py      # Caching layer (SQLite/parquet)
├── integration/
│   └── telegram_notifier.py  # Telegram alert sending
├── infra/
│   ├── scheduler.py          # APScheduler task scheduling
│   ├── rate_limiter.py       # Throttling + exponential backoff
│   └── logging.py            # Loguru structured logging setup
├── main.py                   # Entry point
└── tests/                    # Unit tests
```

## Architecture Principles

- **Separation of concerns:** Data fetching, signal logic, and notifications are isolated modules. No module should cross these boundaries.
- **Signal clarity:** Every alert must include WHY it triggered (reason bullets, entry/stop/target levels).
- **No duplicate alerts:** Track sent signals to prevent re-alerting on the same setup.
- **Fault tolerance:** All external calls (yfinance, Telegram API) must use `tenacity` retry with exponential backoff. The main loop must never crash due to transient failures.
- **Market hours gate:** Only scan during US market hours. Must handle DST automatically (use `exchange_calendars` or `pandas_market_calendars`, not hardcoded times).
- **Caching:** Cache market data locally to avoid excessive yfinance calls. Cache expiry is configurable in `config.yaml`.

## Configuration

All settings live in `config/config.yaml`. **Secrets (Telegram token, chat ID) must come from environment variables, never from the config file or code.**

Key config fields:
- `scan_interval_minutes` (default: 15)
- `stock_universe` (list of tickers, e.g. AAPL, MSFT, NVDA, ...)
- `cache_expiry_seconds`
- `log_level`
- `telegram.chat_id` (non-secret; token via env var `TELEGRAM_BOT_TOKEN`)

## Signal Types

Implement these signal categories (add more if useful, avoid noisy ones):
1. **Trend Pullback** — price retreats to support within uptrend
2. **Breakout from Consolidation** — price breaks above resistance with volume
3. **Momentum Continuation** — RSI/momentum strengthening
4. **Volume Expansion** — volume spike above average
5. **Relative Strength** — outperformance vs sector/market

## Alert Message Format

```
🚨 Swing Trading Signal

Ticker: NVDA
Price: 875.20

Signal: Breakout

Reason Summary:
• Price broke above 20-day resistance
• Volume 135% above average
• RSI momentum strengthening
• Trend above 50-day moving average

Suggested Levels:
Entry: 876
Stop: 845
Target: 940
```

## Common Commands (once implemented)

```bash
# Install dependencies
pip install -r requirements.txt

# Set required environment variable
export TELEGRAM_BOT_TOKEN="your_token_here"

# Run the bot
python main.py

# Run tests
pytest tests/

# Run a single test file
pytest tests/test_indicators.py -v
```

## Deployment (Linux server)

- Run as a `systemd` service or with `nohup`/`screen` for persistent background execution
- Logs should be written to a file via loguru rotation (e.g. `logs/bot.log`)
- Use a `.env` file (not committed) and load with `python-dotenv`, or set env vars in the systemd unit file

## Extensibility Notes

Architecture should accommodate future additions without major refactoring:
- Options signals
- Earnings filters
- AI-based signal ranking
- Portfolio tracking
- Backtesting engine
