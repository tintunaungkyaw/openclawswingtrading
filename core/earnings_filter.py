"""
Earnings Calendar Filter
------------------------
Blocks signals within WINDOW trading days before or after a company's
earnings announcement. Earnings are the #1 risk for swing trades.

Uses yfinance Ticker.calendar for earnings dates.
Gracefully passes (does not block) if the data is unavailable.
"""
from __future__ import annotations
from datetime import date, timedelta

import yfinance as yf
from loguru import logger

WINDOW_DAYS = 3   # block signals within ±3 calendar days of earnings


def is_near_earnings(ticker: str) -> tuple[bool, str]:
    """Return (blocked, reason). If blocked=True the signal should be suppressed."""
    try:
        info = yf.Ticker(ticker).calendar

        if info is None or (hasattr(info, "empty") and info.empty):
            return False, ""

        # yfinance returns a dict or DataFrame depending on version
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
            return False, ""

        # Normalise to date
        if hasattr(earnings_date, "date"):
            earnings_date = earnings_date.date()
        elif not isinstance(earnings_date, date):
            return False, ""

        today = date.today()
        delta = (earnings_date - today).days   # negative = earnings already passed

        if abs(delta) <= WINDOW_DAYS:
            direction = "in" if delta >= 0 else "was"
            days_str = f"{abs(delta)} day(s)"
            return True, (
                f"Earnings {direction} {days_str} "
                f"({earnings_date}) — signal blocked to avoid earnings risk"
            )

    except Exception as e:
        logger.debug(f"Earnings check failed for {ticker}: {e}")

    return False, ""
