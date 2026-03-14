from __future__ import annotations
import time

import pandas as pd
import requests
import yfinance as yf
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Curated fallback: top 60 US tech stocks ordered by approximate market cap
FALLBACK_UNIVERSE: list[str] = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN",
    "TSLA", "AVGO", "ORCL", "ADBE", "CRM", "CSCO",
    "AMD", "INTC", "QCOM", "TXN", "IBM", "NOW",
    "SNOW", "PLTR", "CRWD", "PANW", "NET", "DDOG",
    "MDB", "ZS", "FTNT", "SMCI", "ARM", "AMAT",
    "LRCX", "KLAC", "MRVL", "MCHP", "ON", "CDNS",
    "SNPS", "MPWR", "TER", "HPE", "DELL", "STX",
    "JNPR", "ANSS", "PAYC", "WDAY", "VEEV", "TTD",
    "SHOP", "SQ", "COIN", "OKTA", "S", "GTLB",
    "KEYS", "EPAM", "SAMSF", "NTNX", "PATH", "DOCN",
]


class DataProvider:
    def __init__(self, universe_size: int = 50, request_delay: float = 0.5):
        self.universe_size = universe_size
        self.request_delay = request_delay

    def get_stock_universe(self) -> list[str]:
        """Return top tech tickers via Yahoo Finance screener (falls back to curated list)."""
        try:
            tickers = self._screener_fetch()
            if len(tickers) >= 20:
                logger.info(f"Screener returned {len(tickers)} tickers")
                return tickers[: self.universe_size]
        except Exception as e:
            logger.warning(f"Screener unavailable ({e}), using fallback list")
        return FALLBACK_UNIVERSE[: self.universe_size]

    def _screener_fetch(self) -> list[str]:
        url = "https://query2.finance.yahoo.com/v1/finance/screener/predefined/saved"
        params = {"count": self.universe_size, "scrIds": "ms_technology", "start": 0}
        headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        quotes = resp.json()["finance"]["result"][0]["quotes"]
        # Exclude ADRs / foreign listings (contain a dot)
        return [q["symbol"] for q in quotes if "." not in q["symbol"]]

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=3, max=30),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def fetch_ohlcv(self, ticker: str, period: str = "1y") -> pd.DataFrame | None:
        """Download daily OHLCV from yfinance with retry logic."""
        time.sleep(self.request_delay)   # gentle rate-limiting

        df = yf.download(
            ticker,
            period=period,
            interval="1d",
            auto_adjust=True,
            progress=False,
            multi_level_index=False,
        )

        if df is None or df.empty:
            logger.warning(f"No data for {ticker}")
            return None

        # Flatten MultiIndex if an older yfinance returns it
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.dropna(subset=["Close", "Volume"])

        if len(df) < 60:
            logger.warning(f"{ticker}: only {len(df)} rows — skipping")
            return None

        logger.debug(f"Fetched {len(df)} rows for {ticker}")
        return df
