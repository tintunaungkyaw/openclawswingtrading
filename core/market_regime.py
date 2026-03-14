"""
Market Regime Detection
-----------------------
Evaluates SPY, QQQ, and XLK against their 50-day and 200-day SMAs to
classify the current market environment.

Regimes:
  BULL    — SPY and QQQ both above 50-day SMA → send all signals
  CAUTION — One index below 50-day SMA       → only highest-confidence signals (5 reasons)
  BEAR    — SPY below 200-day SMA             → suppress all signals
"""
from __future__ import annotations
from enum import Enum

import pandas as pd
from loguru import logger


class MarketRegime(str, Enum):
    BULL = "Risk On 🟢"
    CAUTION = "Caution 🟡"
    BEAR = "Risk Off 🔴"


def detect_regime(data_provider, cache_manager) -> tuple[MarketRegime, str]:
    """Return (regime, formatted_benchmark_status_text)."""
    tickers = ["SPY", "QQQ", "XLK"]
    stats: dict[str, dict] = {}

    for t in tickers:
        df = cache_manager.get_ohlcv(t)
        if df is None:
            df = data_provider.fetch_ohlcv(t)
            if df is not None:
                cache_manager.set_ohlcv(t, df)
        if df is None or len(df) < 50:
            logger.warning(f"Market regime: no data for {t}")
            continue

        close = df["Close"].iloc[-1]
        sma_50 = df["Close"].rolling(50).mean().iloc[-1]
        sma_200 = df["Close"].rolling(200).mean().iloc[-1]
        ret_5d = (close - df["Close"].iloc[-6]) / df["Close"].iloc[-6] * 100 if len(df) >= 6 else 0

        stats[t] = {
            "close": close,
            "sma_50": sma_50,
            "sma_200": sma_200,
            "above_50": close > sma_50,
            "above_200": close > sma_200,
            "ret_5d": ret_5d,
        }

    # Regime logic
    spy = stats.get("SPY")
    qqq = stats.get("QQQ")

    if spy and not spy["above_200"]:
        regime = MarketRegime.BEAR
    elif spy and qqq and spy["above_50"] and qqq["above_50"]:
        regime = MarketRegime.BULL
    else:
        regime = MarketRegime.CAUTION

    # Format status lines
    lines = []
    for t, s in stats.items():
        arrow = "▲" if s["above_50"] else "▼"
        flag = " ⚠️" if not s["above_50"] else ""
        lines.append(
            f"  {t}: ${s['close']:.2f} {arrow} 50d SMA (${s['sma_50']:.2f})"
            f"  {s['ret_5d']:+.1f}% 5d{flag}"
        )

    return regime, "\n".join(lines)
