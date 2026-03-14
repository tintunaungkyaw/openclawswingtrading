"""Generates a 2-3 sentence analyst-style trade thesis via OpenAI."""
import os
from loguru import logger
from core.signal_model import TradingSignal


def generate_narrative(signal: TradingSignal) -> str:
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a concise equity research analyst. "
                        "Write sharp, factual trade narratives. "
                        "No fluff. No disclaimers. No filler phrases."
                    ),
                },
                {"role": "user", "content": _build_prompt(signal)},
            ],
            max_tokens=120,
            temperature=0.7,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.warning(f"Narrative generation failed ({signal.ticker}): {e}")
        return ""


def _build_prompt(s: TradingSignal) -> str:
    rr = (s.target - s.entry) / (s.entry - s.stop) if s.entry != s.stop else 0
    parts = [
        f"Stock: {s.ticker}",
        f"Signal: {s.signal_type.value}",
        f"Price: ${s.price:.2f}",
        f"Entry: ${s.entry:.2f} | Stop: ${s.stop:.2f} | Target: ${s.target:.2f} (R:R {rr:.1f}x)",
    ]
    if s.rsi is not None:
        parts.append(f"RSI: {s.rsi:.1f}")
    if s.volume_ratio is not None:
        parts.append(f"Volume: {s.volume_ratio:.1f}x 20-day avg")
    if s.ai_exposure == "YES":
        parts.append(f"Theme: {s.ai_category}")
    parts.append(f"Technical reasons: {'; '.join(s.reasons)}")
    parts.append("\nWrite a 2-3 sentence trade thesis. Be specific and analytical.")
    return "\n".join(parts)
