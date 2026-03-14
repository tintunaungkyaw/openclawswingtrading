from __future__ import annotations
from datetime import date

import pytz
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from core.scanner import Scanner


def _is_trading_day() -> bool:
    """Return True if today is a NYSE trading day (handles weekends + holidays)."""
    try:
        import pandas_market_calendars as mcal
        nyse = mcal.get_calendar("NYSE")
        today = date.today().strftime("%Y-%m-%d")
        return not nyse.schedule(start_date=today, end_date=today).empty
    except Exception as e:
        logger.warning(f"Trading calendar check failed ({e}) — assuming trading day")
        return True


def create_scheduler(
    scanner: Scanner,
    notifier,
    data_provider,
    cache_manager,
    performance_tracker,
    config: dict,
    scan_time: str = "16:30",
) -> BlockingScheduler:
    """Build a BlockingScheduler with all scheduled jobs."""
    hour, minute = map(int, scan_time.split(":"))
    et = pytz.timezone("America/New_York")
    scheduler = BlockingScheduler(timezone=et)

    # ── Job 1: Daily scan at market close ─────────────────────────────────
    def _scan_job():
        if not _is_trading_day():
            logger.info("Not a trading day — scan skipped.")
            return
        scanner.run_scan()

    scheduler.add_job(
        _scan_job,
        trigger=CronTrigger(day_of_week="mon-fri", hour=hour, minute=minute, timezone=et),
        id="daily_scan",
        name="Daily swing scan at market close",
        misfire_grace_time=300,
        coalesce=True,
    )

    # ── Job 2: Morning briefing at 9:00 AM ET ─────────────────────────────
    def _briefing_job():
        if not _is_trading_day():
            return
        try:
            from infra.briefing import send_morning_briefing
            send_morning_briefing(notifier, data_provider, cache_manager, config)
        except Exception as e:
            logger.error(f"Morning briefing failed: {e}")

    scheduler.add_job(
        _briefing_job,
        trigger=CronTrigger(day_of_week="mon-fri", hour=9, minute=0, timezone=et),
        id="morning_briefing",
        name="Pre-market morning briefing",
        misfire_grace_time=300,
        coalesce=True,
    )

    # ── Job 3: Weekly performance report — Monday 8:00 AM ET ──────────────
    def _performance_job():
        try:
            report = performance_tracker.generate_weekly_report()
            notifier.send_text(report)
            logger.info("Weekly performance report sent.")
        except Exception as e:
            logger.error(f"Performance report failed: {e}")

    scheduler.add_job(
        _performance_job,
        trigger=CronTrigger(day_of_week="mon", hour=8, minute=0, timezone=et),
        id="weekly_performance",
        name="Weekly signal performance report",
        misfire_grace_time=600,
        coalesce=True,
    )

    # ── Job 4: Weekly market summary — Sunday 18:00 ET ────────────────────
    def _weekly_summary_job():
        try:
            from infra.weekly_summary import send_weekly_summary
            send_weekly_summary(notifier, data_provider, cache_manager, config)
        except Exception as e:
            logger.error(f"Weekly summary failed: {e}")

    scheduler.add_job(
        _weekly_summary_job,
        trigger=CronTrigger(day_of_week="sun", hour=18, minute=0, timezone=et),
        id="weekly_summary",
        name="Weekly market summary",
        misfire_grace_time=1800,
        coalesce=True,
    )

    logger.info(
        f"Scheduler ready:\n"
        f"  • Scan:        {scan_time} ET  (Mon–Fri, trading days)\n"
        f"  • Briefing:    09:00 ET  (Mon–Fri, trading days)\n"
        f"  • Performance: 08:00 ET  (Mondays)\n"
        f"  • Summary:     18:00 ET  (Sundays)"
    )
    return scheduler
