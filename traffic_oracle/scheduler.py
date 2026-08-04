#!/usr/bin/env python3
"""Run the distance and taxi fetchers on a fixed, non-overlapping interval."""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from traffic_oracle.common import (
    app_version,
    load_dotenv,
)

LOGGER = logging.getLogger("traffic_oracle.scheduler")
STOP = threading.Event()


def stop(_signum, _frame):
    STOP.set()


def interval_seconds() -> int:
    minutes = int(os.environ["FETCH_INTERVAL_MINUTES"])
    if minutes <= 0:
        raise ValueError("FETCH_INTERVAL_MINUTES must be positive")
    return minutes * 60


def run_cycle(root: Path) -> None:
    output_dir = root / "runtime/static"
    commands = (
        ("distance", root / "fetch-distance.py", output_dir / "travel-times.csv"),
        ("taxi", root / "fetch-taxi.py", output_dir / "taxi-prices.csv"),
    )
    for name, script, output in commands:
        LOGGER.info("starting %s fetch", name)
        subprocess.run(
            [sys.executable, str(script), str(root / "origins.yaml"), str(output)],
            cwd=root,
            check=True,
        )
        LOGGER.info("%s fetch completed", name)


def next_boundary(period: int, now: float | None = None) -> int:
    current = int(time.time() if now is None else now)
    return (current // period + 1) * period


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_dotenv()
    root = Path(__file__).resolve().parents[1]
    period = interval_seconds()

    LOGGER.info(
        "starting Traffic Oracle fetcher version %s; interval=%d minutes",
        app_version(),
        period // 60,
    )

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    next_run = next_boundary(period)
    while not STOP.is_set():
        if STOP.wait(max(0, next_run - time.time())):
            break

        run_cycle(root)

        next_run += period
        if next_run <= time.time():
            next_run = next_boundary(period)

    LOGGER.info("scheduler stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
