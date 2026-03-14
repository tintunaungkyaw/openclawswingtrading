"""
Signal Performance Tracker
--------------------------
Records every signal sent, then evaluates outcomes weekly by checking
whether each signal's high/low since entry touched target or stop.

Weekly report is sent every Monday at 8:00 AM ET.
"""
from __future__ import annotations
import sqlite3
from datetime import datetime, timedelta, date

import yfinance as yf
from loguru import logger

from core.signal_model import TradingSignal


class PerformanceTracker:
    def __init__(self, db_path: str = "data/cache.db"):
        self.db_path = db_path
        self._init_table()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_table(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS signal_tracking (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker      TEXT NOT NULL,
                    signal_type TEXT NOT NULL,
                    entry       REAL NOT NULL,
                    stop        REAL NOT NULL,
                    target      REAL NOT NULL,
                    sent_at     TEXT NOT NULL,
                    outcome     TEXT DEFAULT 'open',
                    exit_price  REAL,
                    exit_date   TEXT
                )
            """)

    # ── recording ─────────────────────────────────────────────────────────────

    def record(self, signal: TradingSignal):
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO signal_tracking
                   (ticker, signal_type, entry, stop, target, sent_at)
                   VALUES (?,?,?,?,?,?)""",
                (
                    signal.ticker,
                    signal.signal_type.value,
                    signal.entry,
                    signal.stop,
                    signal.target,
                    datetime.utcnow().isoformat(),
                ),
            )
        logger.debug(f"Performance tracking: recorded {signal.ticker} {signal.signal_type.value}")

    # ── weekly report ─────────────────────────────────────────────────────────

    def generate_weekly_report(self) -> str:
        self._update_open_signals()

        cutoff = (datetime.utcnow() - timedelta(days=30)).isoformat()
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT ticker, signal_type, entry, stop, target,
                          sent_at, outcome, exit_price
                   FROM signal_tracking
                   WHERE sent_at >= ?
                   ORDER BY sent_at DESC""",
                (cutoff,),
            ).fetchall()

        if not rows:
            return (
                "📊 <b>Weekly Performance Report</b>\n\n"
                "No signals tracked in the last 30 days."
            )

        total = len(rows)
        won   = sum(1 for r in rows if r[6] == "target_hit")
        lost  = sum(1 for r in rows if r[6] == "stop_hit")
        open_ = sum(1 for r in rows if r[6] == "open")
        win_rate = won / (won + lost) * 100 if (won + lost) > 0 else 0

        lines = [
            "📊 <b>Weekly Performance Report</b>",
            f"<i>Past 30 days · {date.today().strftime('%B %d, %Y')}</i>\n",
            f"Total signals: <b>{total}</b>",
            f"  ✅ Target hit: {won}",
            f"  🛑 Stop hit:   {lost}",
            f"  ⏳ Still open: {open_}",
            f"  Win rate (closed): <b>{win_rate:.0f}%</b>\n",
            "<b>Recent signal outcomes:</b>",
        ]

        for r in rows[:12]:
            ticker, sig_type, entry, stop, target, sent_at, outcome, exit_price = r
            date_str = sent_at[:10]
            if outcome == "target_hit":
                pnl = (target - entry) / entry * 100
                status = f"✅ +{pnl:.1f}%"
            elif outcome == "stop_hit":
                pnl = (stop - entry) / entry * 100
                status = f"🛑 {pnl:.1f}%"
            else:
                cur_pnl = ((exit_price or entry) - entry) / entry * 100
                status = f"⏳ {cur_pnl:+.1f}% (open)"
            short_type = sig_type.split()[0]
            lines.append(f"  {date_str}  ${ticker:<6} {short_type:<10} {status}")

        return "\n".join(lines)

    # ── internal ──────────────────────────────────────────────────────────────

    def _update_open_signals(self):
        """Fetch recent OHLC and resolve outcomes for open signals."""
        cutoff = (datetime.utcnow() - timedelta(days=30)).isoformat()
        with self._conn() as conn:
            open_signals = conn.execute(
                """SELECT id, ticker, entry, stop, target FROM signal_tracking
                   WHERE outcome='open' AND sent_at >= ?""",
                (cutoff,),
            ).fetchall()

        for (id_, ticker, entry, stop, target) in open_signals:
            try:
                df = yf.download(
                    ticker, period="5d", interval="1d",
                    auto_adjust=True, progress=False, multi_level_index=False,
                )
                if df is None or df.empty:
                    continue

                highest = float(df["High"].max())
                lowest  = float(df["Low"].min())
                current = float(df["Close"].iloc[-1])

                if highest >= target:
                    outcome, exit_price = "target_hit", target
                elif lowest <= stop:
                    outcome, exit_price = "stop_hit", stop
                else:
                    outcome, exit_price = "open", current

                with self._conn() as conn:
                    conn.execute(
                        """UPDATE signal_tracking
                           SET outcome=?, exit_price=?, exit_date=?
                           WHERE id=?""",
                        (outcome, exit_price, date.today().isoformat(), id_),
                    )
            except Exception as e:
                logger.warning(f"Performance update failed for {ticker}: {e}")
