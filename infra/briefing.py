"""
Pre-Market Morning Briefing
---------------------------
Sent every trading day at 9:00 AM ET.

Contents:
  1. Market regime (SPY / QQQ / XLK status)
  2. Top 3 stocks from the universe that are closest to triggering a signal
     (uses yesterday's cached OHLCV — no new API calls at open)
"""
from __future__ import annotations
from datetime import date

import pandas as pd
from loguru import logger

from core.market_regime import detect_regime, MarketRegime
from core.indicators import calculate_indicators


def send_morning_briefing(notifier, data_provider, cache_manager, config: dict):
    """Generate and send the pre-market briefing."""
    logger.info("Generating morning briefing…")

    regime, regime_desc = detect_regime(data_provider, cache_manager)

    watchlist = _build_watchlist(data_provider, cache_manager, config)

    if watchlist:
        watch_lines = "\n".join(
            f"  • ${t}  ${p:.2f}  — {', '.join(notes)}"
            for t, p, notes in watchlist[:3]
        )
    else:
        watch_lines = "  No setups near trigger today"

    regime_note = ""
    if regime == MarketRegime.BEAR:
        regime_note = "\n⚠️ <b>Bear market detected — signals are suppressed today.</b>\n"
    elif regime == MarketRegime.CAUTION:
        regime_note = "\n⚠️ <b>Caution mode — only highest-confidence signals will be sent.</b>\n"

    today_str = date.today().strftime("%A, %B %d, %Y")

    msg = (
        f"🌅 <b>OpenClaw Morning Briefing</b>\n"
        f"<i>{today_str}</i>\n"
        f"{'─' * 32}\n"
        f"<b>Market Regime: {regime.value}</b>{regime_note}\n"
        f"<b>Benchmarks (vs 50-day SMA):</b>\n{regime_desc}\n\n"
        f"<b>Watchlist — Near Signal:</b>\n{watch_lines}\n"
        f"{'─' * 32}\n"
        f"<i>Signal scan runs at 4:30 PM ET after market close.</i>"
    )

    notifier.send_text(msg)
    logger.info("Morning briefing sent.")


# ── internal ──────────────────────────────────────────────────────────────────

def _build_watchlist(data_provider, cache_manager, config: dict) -> list[tuple]:
    """Score cached stocks by proximity to signal conditions. Returns sorted list."""
    universe = data_provider.get_stock_universe()
    candidates: list[tuple] = []

    for ticker in universe:
        try:
            df = cache_manager.get_ohlcv(ticker)
            if df is None or len(df) < 60:
                continue   # briefing only uses cached data — no fresh yfinance calls

            df = calculate_indicators(df)
            row = df.iloc[-1]
            close = row.get("Close", 0)
            rsi = row.get("rsi", float("nan"))
            sma_20 = row.get("sma_20", float("nan"))
            sma_50 = row.get("sma_50", float("nan"))
            vol_ratio = row.get("vol_ratio", float("nan"))
            high_20 = row.get("high_20", float("nan"))

            if any(pd.isna(v) for v in [close, rsi, sma_50]):
                continue

            score = 0
            notes: list[str] = []

            # Near 20-day SMA (pullback setup building)
            if not pd.isna(sma_20) and abs(close - sma_20) / sma_20 < 0.04:
                score += 1
                notes.append(f"near 20d SMA ${sma_20:.2f}")

            # RSI in actionable range
            if 40 <= rsi <= 65:
                score += 1
                notes.append(f"RSI {rsi:.0f}")

            # Volume picking up
            if not pd.isna(vol_ratio) and vol_ratio >= 1.2:
                score += 1
                notes.append(f"vol {vol_ratio:.1f}x")

            # Near 20-day high (breakout setup building)
            if not pd.isna(high_20) and close >= high_20 * 0.97:
                score += 1
                notes.append("near 20d high")

            # Above 50-day SMA (uptrend intact)
            if close > sma_50:
                score += 1

            if score >= 3:
                candidates.append((ticker, close, notes))

        except Exception as e:
            logger.debug(f"Briefing watchlist error ({ticker}): {e}")

    # Sort by number of positive notes
    candidates.sort(key=lambda x: -len(x[2]))
    return candidates
