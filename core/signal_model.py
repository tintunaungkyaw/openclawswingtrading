from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class SignalType(str, Enum):
    BREAKOUT = "Breakout"
    TREND_PULLBACK = "Trend Pullback"
    MOMENTUM_CONTINUATION = "Momentum Continuation"
    VOLUME_EXPANSION = "Volume Expansion"
    RELATIVE_STRENGTH = "Relative Strength"


@dataclass
class TradingSignal:
    ticker: str
    signal_type: SignalType
    price: float
    reasons: list[str]
    entry: float
    stop: float
    target: float
    rsi: float | None = None
    volume_ratio: float | None = None
    # AI / Semiconductor classification (populated by sector_classifier)
    ai_exposure: str = "NO"     # "YES" or "NO"
    ai_category: str = ""       # e.g. "AI Networking Infrastructure"
    narrative: str = ""         # GPT-generated trade thesis
    generated_at: datetime = field(default_factory=datetime.utcnow)
