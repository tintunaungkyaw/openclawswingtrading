"""
Earnings Tracker
----------------
Fetches upcoming earnings previews and recent earnings results for a list of
tickers using yfinance. Returns structured dicts ready for Telegram formatting.

Data sources:
  yf.Ticker(t).calendar        — upcoming date + EPS/Revenue estimates
  yf.Ticker(t).earnings_history — DataFrame with actual vs estimate results
"""
from __future__ import annotations
from datetime import date, timedelta

import yfinance as yf
from loguru import logger


# ── Helpers ────────────────────────────────────────────────────────────────────

def _safe_float(v) -> float | None:
    """Convert a value to float, returning None for NaN/None/non-numeric."""
    if v is None:
        return None
    try:
        f = float(v)
        return None if f != f else f   # NaN check: NaN != NaN is True
    except (TypeError, ValueError):
        return None


def _parse_earnings_date(info) -> date | None:
    """Extract and normalise earnings date from yfinance calendar (dict or DataFrame).
    Mirrors the same logic used in earnings_filter.py."""
    earnings_date = None
    if isinstance(info, dict):
        earnings_date = info.get("Earnings Date")
        if isinstance(earnings_date, list) and earnings_date:
            earnings_date = earnings_date[0]
    elif hasattr(info, "loc"):
        if "Earnings Date" in info.index:
            val = info.loc["Earnings Date"]
            earnings_date = val.iloc[0] if hasattr(val, "iloc") else val

    if earnings_date is None:
        return None
    if hasattr(earnings_date, "date"):
        return earnings_date.date()
    if isinstance(earnings_date, date):
        return earnings_date
    return None


def _assess(surprise_pct: float) -> str:
    if surprise_pct > 2.0:
        return "BULLISH"
    if surprise_pct < -2.0:
        return "BEARISH"
    return "NEUTRAL"


# ── Public API ─────────────────────────────────────────────────────────────────

def get_upcoming_earnings(tickers: list[str], days_ahead: int = 3) -> list[dict]:
    """Return earnings due within the next days_ahead calendar days.

    Each dict: {ticker, earnings_date, eps_estimate, revenue_estimate}
    eps_estimate / revenue_estimate may be None if unavailable.
    Tickers with no yfinance data are silently skipped.
    """
    today = date.today()
    cutoff = today + timedelta(days=days_ahead)
    results = []

    for ticker in tickers:
        try:
            cal = yf.Ticker(ticker).calendar
            if cal is None or (hasattr(cal, "empty") and cal.empty):
                continue

            edate = _parse_earnings_date(cal)
            if edate is None:
                continue

            # Only include dates in [today, today + days_ahead]
            if not (today <= edate <= cutoff):
                continue

            eps_est = rev_est = None
            if isinstance(cal, dict):
                eps_est = _safe_float(cal.get("Earnings Average"))
                rev_est = _safe_float(cal.get("Revenue Average"))
            elif hasattr(cal, "loc"):
                if "Earnings Average" in cal.index:
                    v = cal.loc["Earnings Average"]
                    eps_est = _safe_float(v.iloc[0] if hasattr(v, "iloc") else v)
                if "Revenue Average" in cal.index:
                    v = cal.loc["Revenue Average"]
                    rev_est = _safe_float(v.iloc[0] if hasattr(v, "iloc") else v)

            results.append({
                "ticker": ticker,
                "earnings_date": edate,
                "eps_estimate": eps_est,
                "revenue_estimate": rev_est,
            })
            logger.debug(f"Upcoming earnings: {ticker} on {edate}")

        except Exception as e:
            logger.debug(f"Earnings preview fetch failed for {ticker}: {e}")

    return results


def get_recent_results(tickers: list[str], days_back: int = 2) -> list[dict]:
    """Return earnings results from the past days_back calendar days.

    Each dict: {ticker, earnings_date, eps_actual, eps_estimate, surprise_pct, assessment}
    Tickers with no yfinance data are silently skipped.
    Only the most recent result within the window is returned per ticker.
    """
    today = date.today()
    cutoff = today - timedelta(days=days_back)
    results = []

    for ticker in tickers:
        try:
            hist = yf.Ticker(ticker).earnings_history
            if hist is None or (hasattr(hist, "empty") and hist.empty):
                continue

            # earnings_history is a DataFrame indexed by date Timestamps
            for idx in hist.index:
                # Normalise index to date
                if hasattr(idx, "date"):
                    edate = idx.date()
                elif isinstance(idx, date):
                    edate = idx
                else:
                    continue

                if not (cutoff <= edate <= today):
                    continue

                row = hist.loc[idx]
                eps_actual   = _safe_float(row.get("Reported EPS"))
                eps_estimate = _safe_float(row.get("EPS Estimate"))
                surprise_pct = _safe_float(row.get("Surprise(%)"))

                # Fall back to manual calculation if Surprise(%) is absent
                if surprise_pct is None:
                    if eps_actual is not None and eps_estimate is not None and eps_estimate != 0:
                        surprise_pct = (eps_actual - eps_estimate) / abs(eps_estimate) * 100
                    else:
                        continue  # cannot assess

                results.append({
                    "ticker": ticker,
                    "earnings_date": edate,
                    "eps_actual": eps_actual,
                    "eps_estimate": eps_estimate,
                    "surprise_pct": surprise_pct,
                    "assessment": _assess(surprise_pct),
                })
                logger.debug(f"Recent earnings: {ticker} on {edate} — {_assess(surprise_pct)}")
                break  # take only the most recent result in the window

        except Exception as e:
            logger.debug(f"Earnings result fetch failed for {ticker}: {e}")

    return results
