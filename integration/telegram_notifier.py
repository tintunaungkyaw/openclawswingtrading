"""
Telegram Notifier
-----------------
Sends formatted swing trading signals and text messages via the Telegram
Bot API (HTTP, no python-telegram-bot dependency).
"""
from __future__ import annotations
import time
from datetime import datetime

import pytz
import requests
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from core.signal_model import TradingSignal

# ── Design constants ──────────────────────────────────────────────────────────
_ET = pytz.timezone("America/New_York")
_DIV  = "▬" * 33          # main section divider
_THIN = "· " * 16 + "·"   # lighter sub-divider

# Signal-specific identity
_SIG_IDENTITY: dict[str, tuple[str, str, str]] = {
    "Breakout":              ("💥", "BREAKOUT",         "Momentum is surging — price escaped supply"),
    "Trend Pullback":        ("🎯", "TREND PULLBACK",   "Prime re-entry within a healthy uptrend"),
    "Momentum Continuation": ("⚡", "MOMENTUM SURGE",   "Trend accelerating — strength begets strength"),
    "Volume Expansion":      ("🔥", "VOLUME BREAKOUT",  "Smart money is moving — volume doesn't lie"),
    "Relative Strength":     ("💎", "STRENGTH LEADER",  "Outperforming the market — leaders lead"),
}

# Risk notes by signal type
_RISK: dict[str, list[str]] = {
    "Breakout": [
        "Low-volume breakouts often fail — confirm elevated volume",
        "Watch for a pullback retest of the breakout level",
    ],
    "Trend Pullback": [
        "Invalidated if price closes below the 20-day SMA",
        "Confirm with a positive candle before committing",
    ],
    "Momentum Continuation": [
        "Exit early if MACD histogram turns negative",
        "Trail your stop as price advances",
    ],
    "Volume Expansion": [
        "Confirm with next session's follow-through",
        "Unusual volume can reverse sharply — size appropriately",
    ],
    "Relative Strength": [
        "Monitor XLK — sector weakness will drag this stock",
        "Relative strength works best in bull market conditions",
    ],
}
_RISK_COMMON = [
    "Cancel the setup if price closes below the stop",
    "Position size based on the stop distance, not the target",
]


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str, rate_limit_seconds: float = 2.0):
        self.chat_id = str(chat_id)
        self.rate_limit = rate_limit_seconds
        self._api = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    def send_signal(self, signal: TradingSignal):
        self._post(_format_signal(signal))
        time.sleep(self.rate_limit)

    def send_text(self, text: str):
        self._post(text)

    def test_connection(self) -> bool:
        try:
            self._post("🤖 <b>OpenClaw</b> — online and scanning.")
            return True
        except Exception as e:
            logger.error(f"Telegram connection test failed: {e}")
            return False

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=3, max=30), reraise=True)
    def _post(self, text: str):
        resp = requests.post(
            self._api,
            json={"chat_id": self.chat_id, "text": text, "parse_mode": "HTML"},
            timeout=15,
        )
        if resp.status_code != 200:
            logger.error(f"Telegram {resp.status_code}: {resp.text[:200]}")
            resp.raise_for_status()
        logger.debug(f"Telegram OK — {text[:55]}…")


# ── Formatter ─────────────────────────────────────────────────────────────────

def _format_signal(s: TradingSignal) -> str:
    sig_type  = s.signal_type.value
    emoji, label, tagline = _SIG_IDENTITY.get(
        sig_type, ("📊", sig_type.upper(), "")
    )

    # ── derived values ──────────────────────────────────────────────────────
    risk       = s.entry - s.stop
    rr         = (s.target - s.entry) / risk if risk > 0 else 0
    stop_pct   = (s.stop   - s.entry) / s.entry * 100   # negative
    target_pct = (s.target - s.entry) / s.entry * 100   # positive
    rr_emoji   = "✅" if rr >= 2 else "⚡" if rr >= 1.5 else "⚠️"
    ts         = datetime.now(_ET).strftime("%a %b %d · %I:%M %p ET")

    # ── RSI bar (10-char monospace) ─────────────────────────────────────────
    rsi_bar = ""
    if s.rsi is not None:
        filled   = min(10, max(0, round(s.rsi / 10)))
        bar_str  = "█" * filled + "░" * (10 - filled)
        if s.rsi < 30:   rsi_zone = "Oversold"
        elif s.rsi < 45: rsi_zone = "Weak    "
        elif s.rsi < 55: rsi_zone = "Neutral "
        elif s.rsi < 70: rsi_zone = "Bullish "
        else:             rsi_zone = "Overbought"
        rsi_bar = f"RSI  {s.rsi:>5.1f}  [{bar_str}]  {rsi_zone}"

    vol_bar = ""
    if s.volume_ratio is not None:
        vr        = s.volume_ratio
        vol_label = "🔊 Very High" if vr >= 2 else "🔔 Elevated" if vr >= 1.3 else "  Normal"
        filled_v  = min(10, max(1, round(vr * 5)))
        vol_str   = "█" * filled_v + "░" * (10 - filled_v)
        vol_bar   = f"Vol  {vr:>5.1f}×  [{vol_str}]  {vol_label}"

    tech_lines = [l for l in [rsi_bar, vol_bar] if l]
    tech_pre   = ("<pre>" + "\n".join(tech_lines) + "</pre>") if tech_lines else ""

    # ── Trade levels ────────────────────────────────────────────────────────
    lvl_pre = (
        "<pre>"
        f"🟢 Entry   ${s.entry:>9.2f}\n"
        f"🔴 Stop    ${s.stop:>9.2f}  ({stop_pct:.1f}%)\n"
        f"🏆 Target  ${s.target:>9.2f}  (+{target_pct:.1f}%)\n"
        f"⚖️  R:R       {rr:.1f}×           {rr_emoji}"
        "</pre>"
    )

    # ── AI / Semiconductor badge ────────────────────────────────────────────
    if s.ai_exposure == "YES":
        ai_block = (
            f"\n{_THIN}\n"
            f"🤖  <b>AI / SEMICONDUCTOR PLAY</b>\n"
            f"    <i>{s.ai_category}</i>"
        )
    else:
        ai_block = ""

    # ── Reasons ─────────────────────────────────────────────────────────────
    reasons_text = "\n".join(f"  ◆ {r}" for r in s.reasons)

    # ── Risk notes ──────────────────────────────────────────────────────────
    sig_risk   = _RISK.get(sig_type, [])
    all_risk   = _RISK_COMMON + sig_risk
    risk_text  = "\n".join(f"  ▸ {n}" for n in all_risk)

    # ── Assemble ─────────────────────────────────────────────────────────────
    return (
        # ═══ HEADER ═══
        f"{_DIV}\n"
        f"{emoji}  <b>{label}</b>\n"
        f"{_DIV}\n"
        f"\n"
        f"<b>Ticker</b>   ${s.ticker}\n"
        f"<b>Price</b>    ${s.price:.2f}\n"
        f"<i>{tagline}</i>"
        f"{ai_block}\n"
        f"\n"
        # ═══ TRADE SETUP ═══
        f"{_DIV}\n"
        f"🎯  <b>TRADE SETUP</b>\n"
        f"{_DIV}\n"
        f"\n"
        f"{lvl_pre}\n"
        f"\n"
        # ═══ TECHNICALS ═══
        f"{_DIV}\n"
        f"📊  <b>TECHNICALS</b>\n"
        f"{_DIV}\n"
        f"\n"
        f"{tech_pre if tech_pre else '  (No indicator data)'}\n"
        f"\n"
        # ═══ WHY THIS TRADE ═══
        f"{_DIV}\n"
        f"🧠  <b>WHY THIS TRADE</b>\n"
        f"{_DIV}\n"
        f"\n"
        f"{reasons_text}\n"
        f"\n"
        # ═══ RISK ═══
        f"{_DIV}\n"
        f"⚠️  <b>RISK NOTES</b>\n"
        f"{_DIV}\n"
        f"\n"
        f"{risk_text}\n"
        f"\n"
        # ═══ FOOTER ═══
        f"{_DIV}\n"
        f"⏰  {ts}  ·  <i>Not financial advice</i>\n"
        f"{_DIV}"
    )
