import sys
from pathlib import Path
from loguru import logger


def setup_logging(log_file: str = "logs/openclaw.log", log_level: str = "INFO"):
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    logger.remove()

    logger.add(
        sys.stdout,
        level=log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level:<8}</level> | "
            "<cyan>{module}</cyan> — <level>{message}</level>"
        ),
        colorize=True,
    )

    logger.add(
        log_file,
        level=log_level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {module}:{line} — {message}",
        rotation="50 MB",
        retention="30 days",
        compression="gz",
        enqueue=True,
    )

    logger.info(f"Logging ready — level={log_level}, file={log_file}")
