from __future__ import annotations
from loguru import logger
from datetime import datetime

from data.data_provider import DataProvider
from data.cache_manager import CacheManager
from core.indicators import calculate_indicators
from core.strategy_engine import evaluate_signals
from core.signal_model import TradingSignal
from core.market_regime import detect_regime, MarketRegime
from core.earnings_filter import is_near_earnings
from core.performance_tracker import PerformanceTracker
from core.sector_classifier import classify
from integration.telegram_notifier import TelegramNotifier

# Minimum number of reasons required to send a signal in CAUTION market
_CAUTION_MIN_REASONS = 5


class Scanner:
    def __init__(
        self,
        data_provider: DataProvider,
        cache_manager: CacheManager,
        notifier: TelegramNotifier,
        performance_tracker: PerformanceTracker,
        config: dict,
    ):
        self.dp = data_provider
        self.cache = cache_manager
        self.notifier = notifier
        self.tracker = performance_tracker
        self.config = config
        self._benchmark_df = None

    def run_scan(self) -> int:
        """Run a full daily scan. Returns number of signals sent."""
        logger.info("=" * 60)
        logger.info(f"Scan started at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")

        # ── 1. Market regime check ──────────────────────────────────────────
        regime, regime_desc = detect_regime(self.dp, self.cache)
        logger.info(f"Market regime: {regime.value}")

        if regime == MarketRegime.BEAR:
            msg = (
                f"⚠️ <b>Market in RISK OFF mode</b>\n"
                f"Scan suppressed — no signals sent in bear market.\n\n"
                f"<b>Benchmarks:</b>\n{regime_desc}"
            )
            self.notifier.send_text(msg)
            logger.warning("Bear market detected — scan suppressed.")
            return 0

        if regime == MarketRegime.CAUTION:
            logger.info(f"Caution mode — only signals with {_CAUTION_MIN_REASONS}+ reasons will be sent")

        # ── 2. Refresh benchmark data ───────────────────────────────────────
        self._benchmark_df = self._get_data("XLK")
        if self._benchmark_df is not None:
            self._benchmark_df = calculate_indicators(self._benchmark_df)

        # ── 3. Scan universe ────────────────────────────────────────────────
        universe = self.dp.get_stock_universe()
        logger.info(f"Universe: {len(universe)} stocks")

        cooldown = self.config.get("signal_cooldown_hours", 72)
        signals_sent = 0

        for i, ticker in enumerate(universe, 1):
            try:
                logger.debug(f"[{i}/{len(universe)}] {ticker}")
                signals = self._scan_ticker(ticker)

                for signal in signals:
                    key = signal.signal_type.value

                    # Deduplication
                    if self.cache.is_duplicate(ticker, key, cooldown):
                        logger.info(f"Duplicate skipped: {ticker} / {key}")
                        continue

                    # Earnings filter
                    blocked, reason = is_near_earnings(ticker)
                    if blocked:
                        logger.info(f"Earnings filter: {ticker} — {reason}")
                        continue

                    # Caution-mode: require more confirming reasons
                    if regime == MarketRegime.CAUTION and len(signal.reasons) < _CAUTION_MIN_REASONS:
                        logger.info(
                            f"Caution mode: {ticker} {key} has only "
                            f"{len(signal.reasons)} reasons — skipped"
                        )
                        continue

                    # AI / Semiconductor classification
                    signal.ai_exposure, signal.ai_category = classify(ticker)

                    # Send and record
                    self.notifier.send_signal(signal)
                    self.cache.record_signal(ticker, key)
                    self.tracker.record(signal)
                    signals_sent += 1
                    logger.info(f"Signal sent: {ticker} — {key}")

            except Exception as e:
                logger.error(f"Error scanning {ticker}: {e}")

        logger.info(f"Scan complete — {signals_sent} signal(s) sent.")
        logger.info("=" * 60)
        return signals_sent

    def _passes_filters(self, ticker: str, df) -> bool:
        """Return False if ticker fails price, volume, or market cap thresholds."""
        flt = self.config.get("filters", {})
        min_price      = flt.get("min_price", 0.0)
        min_avg_volume = flt.get("min_avg_volume", 0)
        min_mcap_b     = flt.get("min_market_cap_b", 0.0)
        mcap_cache_days = flt.get("market_cap_cache_days", 7)

        # Price check (last close)
        last_close = float(df["Close"].iloc[-1])
        if last_close < min_price:
            logger.info(f"Filter: {ticker} price ${last_close:.2f} < ${min_price} — skipped")
            return False

        # Average volume check (20-day)
        avg_vol = float(df["Volume"].tail(20).mean())
        if avg_vol < min_avg_volume:
            logger.info(f"Filter: {ticker} avg vol {avg_vol:,.0f} < {min_avg_volume:,} — skipped")
            return False

        # Market cap check (cached; fallback to yfinance info)
        if min_mcap_b > 0:
            mcap = self.cache.get_market_cap(ticker, expiry_days=mcap_cache_days)
            if mcap is None:
                try:
                    import yfinance as yf
                    info = yf.Ticker(ticker).info
                    mcap = info.get("marketCap") or info.get("market_cap")
                    if mcap:
                        self.cache.set_market_cap(ticker, float(mcap))
                except Exception as e:
                    logger.warning(f"Market cap fetch failed ({ticker}): {e}")
                    mcap = None
            if mcap is not None:
                mcap_b = mcap / 1e9
                if mcap_b < min_mcap_b:
                    logger.info(f"Filter: {ticker} market cap ${mcap_b:.1f}B < ${min_mcap_b}B — skipped")
                    return False

        return True

    def _scan_ticker(self, ticker: str) -> list[TradingSignal]:
        df = self._get_data(ticker)
        if df is None:
            return []
        df = calculate_indicators(df)
        if not self._passes_filters(ticker, df):
            return []
        return evaluate_signals(ticker, df, self._benchmark_df, self.config)

    def _get_data(self, ticker: str):
        cached = self.cache.get_ohlcv(ticker)
        if cached is not None:
            logger.debug(f"Cache hit: {ticker}")
            return cached
        df = self.dp.fetch_ohlcv(ticker)
        if df is not None:
            self.cache.set_ohlcv(ticker, df)
        return df
