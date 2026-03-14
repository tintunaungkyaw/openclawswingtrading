#!/usr/bin/env python3
"""
OpenClaw Swing Trading Bot
==========================
Scans top 50 US tech stocks after market close and sends high-quality
swing trading signals to Telegram. Signals only — no trade execution.

Scheduled jobs:
  09:00 ET  Mon–Fri  →  Pre-market morning briefing
  16:30 ET  Mon–Fri  →  Daily signal scan (after market close)
  08:00 ET  Mondays  →  Weekly performance report

Usage:
    python main.py             # Start scheduler
    python main.py --run-now   # Run an immediate scan, then start scheduler
"""
import argparse
import os
import sys

import yaml
from dotenv import load_dotenv
from loguru import logger

from infra.logging_setup import setup_logging
from data.data_provider import DataProvider
from data.cache_manager import CacheManager
from core.scanner import Scanner
from core.performance_tracker import PerformanceTracker
from integration.telegram_notifier import TelegramNotifier
from infra.scheduler import create_scheduler


def load_config(path: str = "config/config.yaml") -> dict:
    with open(path) as fh:
        return yaml.safe_load(fh)


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="OpenClaw Swing Trading Bot")
    parser.add_argument(
        "--run-now", action="store_true",
        help="Run an immediate scan before starting the scheduler"
    )
    args = parser.parse_args()

    config = load_config()
    setup_logging(
        log_file=config.get("log_file", "logs/openclaw.log"),
        log_level=config.get("log_level", "INFO"),
    )

    logger.info("=" * 60)
    logger.info("OpenClaw Swing Trading Bot — starting up")

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip() or str(
        config.get("telegram", {}).get("chat_id", "")
    )

    if not bot_token:
        logger.error("TELEGRAM_BOT_TOKEN is not set — aborting.")
        sys.exit(1)
    if not chat_id:
        logger.error("TELEGRAM_CHAT_ID is not set — aborting.")
        sys.exit(1)

    cache = CacheManager(
        db_path="data/cache.db",
        expiry_hours=config.get("cache_expiry_hours", 23),
    )
    dp = DataProvider(
        universe_size=config.get("stock_universe_size", 50),
        request_delay=0.5,
    )
    notifier = TelegramNotifier(
        bot_token=bot_token,
        chat_id=chat_id,
        rate_limit_seconds=config.get("telegram", {}).get("rate_limit_seconds", 2),
    )
    tracker = PerformanceTracker(db_path="data/cache.db")

    logger.info("Testing Telegram connection…")
    if not notifier.test_connection():
        logger.error("Telegram connection failed — check token and chat ID.")
        sys.exit(1)
    logger.info("Telegram connection OK ✓")

    scanner = Scanner(dp, cache, notifier, tracker, config)

    if args.run_now:
        logger.info("--run-now: running immediate scan")
        scanner.run_scan()

    scan_time = config.get("scan_time", "16:30")
    scheduler = create_scheduler(
        scanner=scanner,
        notifier=notifier,
        data_provider=dp,
        cache_manager=cache,
        performance_tracker=tracker,
        config=config,
        scan_time=scan_time,
    )

    logger.info(f"Bot running. Scan at {scan_time} ET. Ctrl+C to stop.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutdown signal received.")
        scheduler.shutdown(wait=False)
        logger.info("OpenClaw stopped cleanly.")


if __name__ == "__main__":
    main()
