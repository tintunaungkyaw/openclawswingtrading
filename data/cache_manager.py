from __future__ import annotations
import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from loguru import logger


class CacheManager:
    """SQLite-backed cache for OHLCV data and signal deduplication."""

    def __init__(self, db_path: str = "data/cache.db", expiry_hours: int = 23):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self.expiry = timedelta(hours=expiry_hours)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ohlcv_cache (
                    ticker   TEXT PRIMARY KEY,
                    cached_at TEXT NOT NULL,
                    data     TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS signal_history (
                    ticker      TEXT NOT NULL,
                    signal_type TEXT NOT NULL,
                    sent_at     TEXT NOT NULL,
                    PRIMARY KEY (ticker, signal_type)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS market_cap_cache (
                    ticker      TEXT PRIMARY KEY,
                    cached_at   TEXT NOT NULL,
                    market_cap  REAL NOT NULL
                )
            """)

    # ── OHLCV cache ──────────────────────────────────────────────────────────

    def get_ohlcv(self, ticker: str) -> pd.DataFrame | None:
        try:
            with self._conn() as conn:
                row = conn.execute(
                    "SELECT cached_at, data FROM ohlcv_cache WHERE ticker = ?", (ticker,)
                ).fetchone()
            if not row:
                return None
            if datetime.utcnow() - datetime.fromisoformat(row[0]) > self.expiry:
                logger.debug(f"Cache expired: {ticker}")
                return None
            # orient="index" stores {date: {col: val}}, so transpose on read
            df = pd.DataFrame(json.loads(row[1])).T
            df.index = pd.to_datetime(df.index, format="mixed")
            df.index.name = "Date"
            # Ensure numeric columns
            for col in ["Open", "High", "Low", "Close", "Volume"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            return df
        except Exception as e:
            logger.warning(f"Cache read error ({ticker}): {e}")
            return None

    def set_ohlcv(self, ticker: str, df: pd.DataFrame):
        try:
            serialisable = df.copy()
            serialisable.index = serialisable.index.astype(str)
            payload = serialisable.to_json(orient="index")
            with self._conn() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO ohlcv_cache (ticker, cached_at, data) VALUES (?,?,?)",
                    (ticker, datetime.utcnow().isoformat(), payload),
                )
        except Exception as e:
            logger.warning(f"Cache write error ({ticker}): {e}")

    # ── Signal deduplication ─────────────────────────────────────────────────

    def is_duplicate(self, ticker: str, signal_type: str, cooldown_hours: int) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT sent_at FROM signal_history WHERE ticker=? AND signal_type=?",
                (ticker, signal_type),
            ).fetchone()
        if not row:
            return False
        return datetime.utcnow() - datetime.fromisoformat(row[0]) < timedelta(hours=cooldown_hours)

    def record_signal(self, ticker: str, signal_type: str):
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO signal_history (ticker, signal_type, sent_at) VALUES (?,?,?)",
                (ticker, signal_type, datetime.utcnow().isoformat()),
            )

    # ── Market cap cache ─────────────────────────────────────────────────────

    def get_market_cap(self, ticker: str, expiry_days: int = 7) -> float | None:
        try:
            with self._conn() as conn:
                row = conn.execute(
                    "SELECT cached_at, market_cap FROM market_cap_cache WHERE ticker = ?",
                    (ticker,),
                ).fetchone()
            if not row:
                return None
            if datetime.utcnow() - datetime.fromisoformat(row[0]) > timedelta(days=expiry_days):
                logger.debug(f"Market cap cache expired: {ticker}")
                return None
            return float(row[1])
        except Exception as e:
            logger.warning(f"Market cap cache read error ({ticker}): {e}")
            return None

    def set_market_cap(self, ticker: str, market_cap: float):
        try:
            with self._conn() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO market_cap_cache (ticker, cached_at, market_cap) VALUES (?,?,?)",
                    (ticker, datetime.utcnow().isoformat(), market_cap),
                )
        except Exception as e:
            logger.warning(f"Market cap cache write error ({ticker}): {e}")
