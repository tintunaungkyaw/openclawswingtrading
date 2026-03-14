from __future__ import annotations
import pandas as pd
import numpy as np
from loguru import logger


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate all technical indicators needed for signal generation.

    Requires at least 60 rows; 200 rows recommended for full indicator coverage.
    """
    if len(df) < 60:
        logger.warning(f"Insufficient data: {len(df)} rows")
        return df

    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    # Moving averages
    df["sma_20"] = close.rolling(20).mean()
    df["sma_50"] = close.rolling(50).mean()
    df["sma_200"] = close.rolling(200).mean()

    # RSI (14-period, Wilder smoothing)
    df["rsi"] = _rsi(close, 14)

    # MACD (12, 26, 9)
    ema_12 = close.ewm(span=12, adjust=False).mean()
    ema_26 = close.ewm(span=26, adjust=False).mean()
    df["macd"] = ema_12 - ema_26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    # ATR (14-period)
    df["atr"] = _atr(high, low, close, 14)

    # Volume metrics
    df["vol_avg_20"] = volume.rolling(20).mean()
    df["vol_ratio"] = volume / df["vol_avg_20"]

    # Rolling highs and lows
    df["high_20"] = high.rolling(20).max()
    df["low_20"] = low.rolling(20).min()
    df["high_5"] = high.rolling(5).max()
    df["low_5"] = low.rolling(5).min()

    # Short-term performance
    df["ret_5d"] = close.pct_change(5)
    df["ret_20d"] = close.pct_change(20)

    # 50-day SMA slope (positive = rising)
    df["sma_50_slope"] = df["sma_50"].diff(5) / df["sma_50"].shift(5)

    return df


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(com=period - 1, min_periods=period).mean()
