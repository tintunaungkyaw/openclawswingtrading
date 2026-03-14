from __future__ import annotations
import pandas as pd
from loguru import logger
from core.signal_model import TradingSignal, SignalType


def evaluate_signals(
    ticker: str,
    df: pd.DataFrame,
    df_benchmark: pd.DataFrame | None,
    config: dict,
) -> list[TradingSignal]:
    """Evaluate all enabled signal types for a ticker. Returns confirmed signals only."""
    if len(df) < 60:
        return []

    signals: list[TradingSignal] = []
    row = df.iloc[-1]
    sig_cfg = config.get("signals", {})
    risk_cfg = config.get("risk", {})

    checks = [
        ("breakout", _check_breakout),
        ("trend_pullback", _check_trend_pullback),
        ("momentum_continuation", _check_momentum_continuation),
        ("volume_expansion", _check_volume_expansion),
    ]
    for key, fn in checks:
        if sig_cfg.get(key, {}).get("enabled", True):
            s = fn(ticker, df, row, sig_cfg.get(key, {}), risk_cfg)
            if s:
                signals.append(s)

    if df_benchmark is not None and sig_cfg.get("relative_strength", {}).get("enabled", True):
        s = _check_relative_strength(
            ticker, df, df_benchmark, row, sig_cfg.get("relative_strength", {}), risk_cfg
        )
        if s:
            signals.append(s)

    return signals


# ── helpers ──────────────────────────────────────────────────────────────────

def _has_nan(*values) -> bool:
    return any(pd.isna(v) for v in values)


def _rr_levels(entry: float, stop: float, rr: float) -> tuple[float, float]:
    """Return (stop, target) after clamping and applying risk/reward."""
    risk = entry - stop
    if risk <= 0 or risk > entry * 0.12:   # stop too tight or too wide (>12%)
        return 0.0, 0.0
    target = round(entry + risk * rr, 2)
    return round(stop, 2), target


# ── signal checks ─────────────────────────────────────────────────────────────

def _check_breakout(
    ticker: str, df: pd.DataFrame, row: pd.Series, cfg: dict, risk_cfg: dict
) -> TradingSignal | None:
    """Breakout from consolidation: price closes above 20-day high on volume."""
    try:
        vol_min = cfg.get("volume_ratio_min", 1.5)
        rsi_lo = cfg.get("rsi_min", 55)
        rsi_hi = cfg.get("rsi_max", 75)
        lookback = cfg.get("lookback_days", 20)
        cons_pct = cfg.get("consolidation_range_pct", 8.0)

        close = row["Close"]
        rsi = row["rsi"]
        vol_ratio = row["vol_ratio"]
        atr = row["atr"]
        sma_50 = row["sma_50"]

        if _has_nan(rsi, vol_ratio, atr, sma_50):
            return None

        # Mandatory: close breaks above yesterday's 20-day high
        prior_high_20 = df["high_20"].iloc[-2]
        if pd.isna(prior_high_20) or close <= prior_high_20:
            return None

        reasons: list[str] = []
        score = 0

        reasons.append(f"Price closed above {lookback}-day high (${prior_high_20:.2f})")
        score += 1  # mandatory

        if vol_ratio >= vol_min:
            reasons.append(f"Volume {vol_ratio:.1f}x the 20-day average")
            score += 1
        else:
            return None  # volume confirmation required

        if rsi_lo <= rsi <= rsi_hi:
            reasons.append(f"RSI at {rsi:.0f} — momentum without being overbought")
            score += 1

        if close > sma_50:
            reasons.append(f"Trend above 50-day SMA (${sma_50:.2f})")
            score += 1

        prior_10 = df.iloc[-12:-2]
        if len(prior_10) >= 5:
            hi = prior_10["High"].max()
            lo = prior_10["Low"].min()
            if lo > 0:
                cons_range = (hi - lo) / lo * 100
                if cons_range <= cons_pct:
                    reasons.append(f"Breaks out of {cons_range:.1f}% consolidation range")
                    score += 1

        if score < 4:
            return None

        rr = risk_cfg.get("risk_reward_ratio", 2.0)
        atr_mult = risk_cfg.get("atr_stop_multiplier", 1.5)
        entry = round(close, 2)
        raw_stop = entry - atr * atr_mult
        stop, target = _rr_levels(entry, raw_stop, rr)
        if stop == 0.0:
            return None

        return TradingSignal(
            ticker=ticker, signal_type=SignalType.BREAKOUT,
            price=close, reasons=reasons, entry=entry, stop=stop, target=target,
            rsi=round(rsi, 1), volume_ratio=round(vol_ratio, 2),
        )
    except Exception as e:
        logger.warning(f"{ticker} breakout check error: {e}")
        return None


def _check_trend_pullback(
    ticker: str, df: pd.DataFrame, row: pd.Series, cfg: dict, risk_cfg: dict
) -> TradingSignal | None:
    """Trend pullback: price pulls back to 20-day SMA support within an uptrend."""
    try:
        rsi_lo = cfg.get("rsi_min", 35)
        rsi_hi = cfg.get("rsi_max", 55)
        pull_pct = cfg.get("pullback_to_sma_pct", 3.0)

        close = row["Close"]
        open_ = row["Open"]
        rsi = row["rsi"]
        sma_20 = row["sma_20"]
        sma_50 = row["sma_50"]
        sma_50_slope = row["sma_50_slope"]
        low_5 = row["low_5"]

        if _has_nan(rsi, sma_20, sma_50, sma_50_slope, low_5):
            return None

        # Mandatory: price in uptrend (above 50-day SMA)
        if close < sma_50:
            return None

        # Mandatory: pulled back to near 20-day SMA
        dist_pct = abs(close - sma_20) / sma_20 * 100
        if dist_pct > pull_pct:
            return None

        # Mandatory: RSI reset
        if not (rsi_lo <= rsi <= rsi_hi):
            return None

        reasons: list[str] = []
        score = 0

        reasons.append(f"Pulled back to 20-day SMA support (${sma_20:.2f})")
        score += 1

        if sma_50_slope > 0:
            reasons.append(f"Uptrend intact — 50-day SMA is rising")
            score += 1

        reasons.append(f"RSI reset to {rsi:.0f} — healthy pullback zone")
        score += 1

        reasons.append(f"Price above 50-day SMA (${sma_50:.2f})")
        score += 1

        if not pd.isna(open_) and close > open_:
            reasons.append("Positive candle — potential reversal at support")
            score += 1

        if score < 4:
            return None

        rr = risk_cfg.get("risk_reward_ratio", 2.0)
        entry = round(close, 2)
        raw_stop = low_5 * 0.99
        stop, target = _rr_levels(entry, raw_stop, rr)
        if stop == 0.0:
            return None

        return TradingSignal(
            ticker=ticker, signal_type=SignalType.TREND_PULLBACK,
            price=close, reasons=reasons, entry=entry, stop=stop, target=target,
            rsi=round(rsi, 1),
        )
    except Exception as e:
        logger.warning(f"{ticker} trend pullback check error: {e}")
        return None


def _check_momentum_continuation(
    ticker: str, df: pd.DataFrame, row: pd.Series, cfg: dict, risk_cfg: dict
) -> TradingSignal | None:
    """Momentum continuation: strong RSI + accelerating MACD above both SMAs."""
    try:
        rsi_lo = cfg.get("rsi_min", 60)
        rsi_hi = cfg.get("rsi_max", 80)

        close = row["Close"]
        rsi = row["rsi"]
        sma_20 = row["sma_20"]
        sma_50 = row["sma_50"]
        macd_hist = row["macd_hist"]
        vol_ratio = row["vol_ratio"]
        ret_5d = row["ret_5d"]

        if _has_nan(rsi, sma_20, sma_50, macd_hist, vol_ratio):
            return None

        # All of these are mandatory for momentum continuation
        if close <= sma_20 or close <= sma_50:
            return None
        if not (rsi_lo <= rsi <= rsi_hi):
            return None

        prev_hist = df["macd_hist"].iloc[-2]
        if macd_hist <= 0 or (not pd.isna(prev_hist) and macd_hist <= prev_hist):
            return None

        reasons: list[str] = []
        score = 0

        reasons.append(f"Price above 20-day (${sma_20:.2f}) and 50-day SMA (${sma_50:.2f})")
        score += 1
        reasons.append(f"RSI at {rsi:.0f} — strong momentum zone")
        score += 1
        reasons.append("MACD histogram positive and accelerating")
        score += 1

        if vol_ratio >= 1.0:
            reasons.append(f"Volume {vol_ratio:.1f}x the 20-day average")
            score += 1

        if not pd.isna(ret_5d) and ret_5d > 0.02:
            reasons.append(f"Up {ret_5d:.1%} in the last 5 days")
            score += 1

        if score < 4:
            return None

        rr = risk_cfg.get("risk_reward_ratio", 2.0)
        entry = round(close, 2)
        raw_stop = sma_20 * 0.99
        stop, target = _rr_levels(entry, raw_stop, rr)
        if stop == 0.0:
            return None

        return TradingSignal(
            ticker=ticker, signal_type=SignalType.MOMENTUM_CONTINUATION,
            price=close, reasons=reasons, entry=entry, stop=stop, target=target,
            rsi=round(rsi, 1), volume_ratio=round(vol_ratio, 2),
        )
    except Exception as e:
        logger.warning(f"{ticker} momentum check error: {e}")
        return None


def _check_volume_expansion(
    ticker: str, df: pd.DataFrame, row: pd.Series, cfg: dict, risk_cfg: dict
) -> TradingSignal | None:
    """Volume expansion: massive volume surge on a strong positive candle."""
    try:
        vol_min = cfg.get("volume_ratio_min", 2.0)

        close = row["Close"]
        open_ = row["Open"]
        high = row["High"]
        low = row["Low"]
        rsi = row["rsi"]
        vol_ratio = row["vol_ratio"]

        if _has_nan(open_, rsi, vol_ratio):
            return None

        # Mandatory conditions
        if vol_ratio < vol_min:
            return None
        if close <= open_:
            return None

        day_range = high - low
        if day_range <= 0:
            return None
        close_position = (close - low) / day_range
        if close_position < 0.75:   # Must close in top 25% of range
            return None

        prior_high_5 = df["high_5"].iloc[-2]
        breaks_5d_high = not pd.isna(prior_high_5) and close > prior_high_5

        reasons: list[str] = []
        score = 0

        reasons.append(f"Volume surge {vol_ratio:.1f}x the 20-day average")
        score += 1
        reasons.append("Strong positive candle (close > open)")
        score += 1
        reasons.append(f"Closed in top {(1 - close_position):.0%} of day's range")
        score += 1

        if breaks_5d_high:
            reasons.append(f"Closed above 5-day high (${prior_high_5:.2f})")
            score += 1

        if not pd.isna(rsi) and rsi < 75:
            reasons.append(f"RSI at {rsi:.0f} — not yet overbought")
            score += 1

        if score < 4:
            return None

        rr = risk_cfg.get("risk_reward_ratio", 2.0)
        entry = round(close, 2)
        raw_stop = low   # Stop at candle low
        stop, target = _rr_levels(entry, raw_stop, rr)
        if stop == 0.0:
            return None

        return TradingSignal(
            ticker=ticker, signal_type=SignalType.VOLUME_EXPANSION,
            price=close, reasons=reasons, entry=entry, stop=stop, target=target,
            rsi=round(rsi, 1) if not pd.isna(rsi) else None,
            volume_ratio=round(vol_ratio, 2),
        )
    except Exception as e:
        logger.warning(f"{ticker} volume expansion check error: {e}")
        return None


def _check_relative_strength(
    ticker: str,
    df: pd.DataFrame,
    df_benchmark: pd.DataFrame,
    row: pd.Series,
    cfg: dict,
    risk_cfg: dict,
) -> TradingSignal | None:
    """Relative strength: stock meaningfully outperforms XLK over 20 and 5 days."""
    try:
        min_outperform = cfg.get("min_outperformance_pct", 5.0)
        lookback = cfg.get("lookback_days", 20)

        close = row["Close"]
        rsi = row["rsi"]
        sma_50 = row["sma_50"]
        high_20 = row["high_20"]

        if _has_nan(rsi, sma_50):
            return None

        # Align on common trading dates
        common = df.index.intersection(df_benchmark.index)
        if len(common) < lookback + 1:
            return None
        stk = df["Close"].reindex(common)
        bench = df_benchmark["Close"].reindex(common)

        stk_ret_20 = (stk.iloc[-1] - stk.iloc[-lookback]) / stk.iloc[-lookback] * 100
        bench_ret_20 = (bench.iloc[-1] - bench.iloc[-lookback]) / bench.iloc[-lookback] * 100
        outperf_20 = stk_ret_20 - bench_ret_20

        # Mandatory: meaningful 20-day outperformance
        if outperf_20 < min_outperform:
            return None

        stk_ret_5 = (stk.iloc[-1] - stk.iloc[-6]) / stk.iloc[-6] * 100 if len(stk) >= 6 else 0
        bench_ret_5 = (bench.iloc[-1] - bench.iloc[-6]) / bench.iloc[-6] * 100 if len(bench) >= 6 else 0
        outperf_5 = stk_ret_5 - bench_ret_5

        # Mandatory: above 50-day SMA
        if close < sma_50:
            return None

        reasons: list[str] = []
        score = 0

        reasons.append(f"Outperforms XLK by {outperf_20:.1f}% over {lookback} days")
        score += 1

        if outperf_5 > 2.0:
            reasons.append(f"Recent strength: outperforming XLK by {outperf_5:.1f}% (5-day)")
            score += 1

        reasons.append(f"Price above 50-day SMA (${sma_50:.2f})")
        score += 1

        if rsi > 55:
            reasons.append(f"RSI at {rsi:.0f} — momentum confirmed")
            score += 1

        if not pd.isna(high_20) and close >= high_20 * 0.97:
            reasons.append("Within 3% of 20-day high — acting as a market leader")
            score += 1

        if score < 4:
            return None

        rr = risk_cfg.get("risk_reward_ratio", 2.0)
        entry = round(close, 2)
        raw_stop = sma_50 * 0.99
        stop, target = _rr_levels(entry, raw_stop, rr)
        if stop == 0.0:
            return None

        return TradingSignal(
            ticker=ticker, signal_type=SignalType.RELATIVE_STRENGTH,
            price=close, reasons=reasons, entry=entry, stop=stop, target=target,
            rsi=round(rsi, 1),
        )
    except Exception as e:
        logger.warning(f"{ticker} relative strength check error: {e}")
        return None
