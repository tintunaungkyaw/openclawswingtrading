"""
Weekly Market Summary
---------------------
Sent every Sunday at 18:00 ET.

Sections:
  1. Market performance (SPY / QQQ / XLK weekly return)
  2. Market regime
  3. Top 5 gainers & Top 5 losers from the scanned universe
  4. Signals sent this week
  5. Earnings watch — companies in universe reporting next week
  6. Key levels to watch (50-day SMA support for SPY / QQQ)
"""
from __future__ import annotations

from datetime import date, timedelta, datetime
from loguru import logger

import pandas as pd
import yfinance as yf

from core.market_regime import detect_regime

_DIV = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"


def send_weekly_summary(notifier, data_provider, cache_manager, config: dict):
    logger.info("Generating weekly market summary…")
    try:
        msg = _build_summary(data_provider, cache_manager)
        notifier.send_text(msg)
        logger.info("Weekly summary sent.")
    except Exception as e:
        logger.error(f"Weekly summary failed: {e}")
        notifier.send_text("⚠️ Weekly summary could not be generated. Check logs.")


# ── builder ───────────────────────────────────────────────────────────────────

def _build_summary(data_provider, cache_manager) -> str:
    today = date.today()                       # Sunday
    week_fri = today - timedelta(days=1)       # Friday (last trading day)
    week_mon = today - timedelta(days=6)       # Monday
    week_label = f"{week_mon.strftime('%b %d')} – {week_fri.strftime('%b %d, %Y')}"

    # ── 1. Benchmark weekly returns ───────────────────────────────────────
    bench_tickers = ["SPY", "QQQ", "XLK"]
    bench_returns = _fetch_weekly_returns(bench_tickers)

    # ── 2. Market regime ─────────────────────────────────────────────────
    regime, _ = detect_regime(data_provider, cache_manager)

    # ── 3. Universe performance ───────────────────────────────────────────
    universe = data_provider.get_stock_universe()
    universe_returns = _fetch_weekly_returns(universe)

    sorted_returns = sorted(
        [(t, r) for t, r in universe_returns.items() if r is not None],
        key=lambda x: x[1],
    )
    top_gainers = list(reversed(sorted_returns[-5:]))   # best 5
    top_losers  = sorted_returns[:5]                    # worst 5

    # ── 4. Signals this week ──────────────────────────────────────────────
    weekly_signals = _get_weekly_signals(cache_manager)

    # ── 5. Earnings next week ─────────────────────────────────────────────
    earnings = _get_earnings_next_week(universe[:35])

    # ── 6. Key levels ─────────────────────────────────────────────────────
    spy_lvl = _key_level("SPY")
    qqq_lvl = _key_level("QQQ")

    # ── Assemble message ──────────────────────────────────────────────────
    return _format(
        week_label, bench_returns, regime,
        top_gainers, top_losers,
        weekly_signals, earnings,
        spy_lvl, qqq_lvl,
    )


def _format(
    week_label, bench_returns, regime,
    top_gainers, top_losers,
    weekly_signals, earnings,
    spy_lvl, qqq_lvl,
) -> str:

    lines = [
        _DIV,
        "📅  WEEKLY MARKET SUMMARY",
        _DIV,
        f"\nWeek of {week_label}\n",
    ]

    # ── Market performance ────────────────────────────────────────────────
    lines += [_DIV, "📊  MARKET PERFORMANCE", _DIV, ""]
    for ticker in ["SPY", "QQQ", "XLK"]:
        ret = bench_returns.get(ticker)
        price = bench_returns.get(f"{ticker}_price")
        if ret is not None and price is not None:
            arrow = "▲" if ret >= 0 else "▼"
            lines.append(f"{ticker:<4}  ${price:.2f}  {arrow} {ret:+.2f}%")
        else:
            lines.append(f"{ticker:<4}  n/a")
    lines.append(f"\nRegime:  {regime.value}\n")

    # ── Top gainers ───────────────────────────────────────────────────────
    lines += [_DIV, "🏆  WEEK'S TOP PERFORMERS", _DIV, ""]
    if top_gainers:
        for i, (t, r) in enumerate(top_gainers, 1):
            lines.append(f"{i}. ${t:<6}  +{r:.2f}%")
    else:
        lines.append("  No data available")
    lines.append("")

    # ── Top losers ────────────────────────────────────────────────────────
    lines += [_DIV, "🔻  WEEK'S LAGGARDS", _DIV, ""]
    if top_losers:
        for i, (t, r) in enumerate(top_losers, 1):
            lines.append(f"{i}. ${t:<6}  {r:.2f}%")
    else:
        lines.append("  No data available")
    lines.append("")

    # ── Signals this week ─────────────────────────────────────────────────
    lines += [_DIV, "📡  SIGNALS THIS WEEK", _DIV, ""]
    if weekly_signals:
        lines.append(f"{len(weekly_signals)} signal(s) sent:\n")
        for ticker, sig_type, sent_at in weekly_signals[:8]:
            day = datetime.fromisoformat(sent_at).strftime("%a %b %d")
            lines.append(f"  • ${ticker:<6}  {sig_type}  ({day})")
    else:
        lines.append("  No signals sent this week")
    lines.append("")

    # ── Earnings next week ────────────────────────────────────────────────
    lines += [_DIV, "📆  EARNINGS WATCH — NEXT WEEK", _DIV, ""]
    if earnings:
        for ticker, earn_date in earnings[:6]:
            lines.append(f"  • ${ticker:<6}  {earn_date.strftime('%a %b %d')}")
    else:
        lines.append("  No earnings found in scanned universe")
    lines.append("")

    # ── Key levels ────────────────────────────────────────────────────────
    lines += [_DIV, "🔭  KEY LEVELS TO WATCH", _DIV, ""]
    if spy_lvl:
        price, sma50, sma200 = spy_lvl
        above50 = "above" if price > sma50 else "BELOW"
        lines.append(f"SPY   ${price:.2f}  |  50d SMA ${sma50:.2f} ({above50})")
        lines.append(f"       200d SMA ${sma200:.2f}")
    if qqq_lvl:
        price, sma50, sma200 = qqq_lvl
        above50 = "above" if price > sma50 else "BELOW"
        lines.append(f"QQQ   ${price:.2f}  |  50d SMA ${sma50:.2f} ({above50})")
        lines.append(f"       200d SMA ${sma200:.2f}")
    lines.append("")

    lines += [_DIV, "<i>For informational purposes only. Not financial advice.</i>"]
    return "\n".join(lines)


# ── data helpers ──────────────────────────────────────────────────────────────

def _fetch_weekly_returns(tickers: list[str]) -> dict:
    """Return dict of ticker → weekly_return_pct (and ticker_price → close)."""
    result: dict = {}
    if not tickers:
        return result

    try:
        raw = yf.download(
            tickers,
            period="5d",
            interval="1d",
            auto_adjust=True,
            progress=False,
            multi_level_index=True,
        )
        if raw.empty:
            return result

        close = raw["Close"] if "Close" in raw.columns else raw.xs("Close", axis=1, level=0)

        # Single ticker → Series; multiple → DataFrame
        if isinstance(close, pd.Series):
            close = close.to_frame(name=tickers[0])

        for ticker in tickers:
            if ticker not in close.columns:
                continue
            col = close[ticker].dropna()
            if len(col) < 2:
                continue
            pct = (col.iloc[-1] - col.iloc[0]) / col.iloc[0] * 100
            result[ticker] = round(float(pct), 2)
            result[f"{ticker}_price"] = round(float(col.iloc[-1]), 2)

    except Exception as e:
        logger.warning(f"Weekly return fetch failed: {e}")

    return result


def _get_weekly_signals(cache_manager) -> list[tuple]:
    """Return signals sent in the last 7 days from the signal_history table."""
    try:
        cutoff = (datetime.utcnow() - timedelta(days=7)).isoformat()
        with cache_manager._conn() as conn:
            rows = conn.execute(
                """SELECT ticker, signal_type, sent_at
                   FROM signal_history
                   WHERE sent_at >= ?
                   ORDER BY sent_at DESC""",
                (cutoff,),
            ).fetchall()
        return rows
    except Exception as e:
        logger.warning(f"Weekly signal fetch failed: {e}")
        return []


def _get_earnings_next_week(tickers: list[str]) -> list[tuple[str, date]]:
    """Return list of (ticker, earnings_date) for companies reporting next week."""
    today = date.today()
    next_mon = today + timedelta(days=1)         # Monday
    next_fri = today + timedelta(days=5)         # Friday

    results: list[tuple[str, date]] = []

    for ticker in tickers:
        try:
            cal = yf.Ticker(ticker).calendar
            if cal is None or (hasattr(cal, "empty") and cal.empty):
                continue

            earn_date = None
            if isinstance(cal, dict):
                val = cal.get("Earnings Date")
                if isinstance(val, list) and val:
                    earn_date = val[0]
                elif val:
                    earn_date = val
            elif hasattr(cal, "loc") and "Earnings Date" in cal.index:
                val = cal.loc["Earnings Date"]
                earn_date = val.iloc[0] if hasattr(val, "iloc") else val

            if earn_date is None:
                continue
            if hasattr(earn_date, "date"):
                earn_date = earn_date.date()
            if not isinstance(earn_date, date):
                continue

            if next_mon <= earn_date <= next_fri:
                results.append((ticker, earn_date))

        except Exception:
            continue

    results.sort(key=lambda x: x[1])
    return results


def _key_level(ticker: str) -> tuple[float, float, float] | None:
    """Return (latest_close, sma_50, sma_200) for SPY or QQQ."""
    try:
        df = yf.download(
            ticker, period="1y", interval="1d",
            auto_adjust=True, progress=False, multi_level_index=False,
        )
        if df is None or len(df) < 50:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        close = df["Close"].dropna()
        return (
            round(float(close.iloc[-1]), 2),
            round(float(close.rolling(50).mean().iloc[-1]), 2),
            round(float(close.rolling(200).mean().iloc[-1]), 2),
        )
    except Exception as e:
        logger.warning(f"Key level fetch failed ({ticker}): {e}")
        return None
