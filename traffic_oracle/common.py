from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

import yaml

LOGGER = logging.getLogger("traffic_oracle")

TRAVEL_TIMES_HEADER = [
    "origin",
    "destination",
    "duration_value",
    "ts",
    "duration_diff",
    "ts_diff",
    "eta_8h_return_value",
]
TAXI_PRICES_HEADER = ["origin", "destination", "snapp_price", "tapsi_price", "ts"]


class ApiError(RuntimeError):
    """An expected external API failure that should not stop other routes."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def app_version() -> str:
    version_file = Path(__file__).resolve().parents[1] / "version.yaml"
    data = yaml.safe_load(version_file.read_text(encoding="utf-8"))
    return str(data["version"])


@dataclass(frozen=True)
class RoutePair:
    origin_name: str
    origin: tuple[float, float]
    destination_name: str
    destination: tuple[float, float]


def load_dotenv(path: str | Path = ".env") -> None:
    """Load simple KEY=VALUE entries without overriding the process environment."""
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:]
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def read_token_state(path: str | Path) -> dict[str, str]:
    """Read a JSON token-state file, tolerating a missing or empty file."""
    state_path = Path(path)
    if not state_path.exists() or state_path.stat().st_size == 0:
        return {}
    return json.loads(state_path.read_text(encoding="utf-8"))


def write_token_state(path: str | Path, state: dict[str, str]) -> None:
    Path(path).write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def ensure_timezone() -> None:
    os.environ.setdefault("TZ", "Asia/Tehran")
    if hasattr(time, "tzset"):
        time.tzset()


def add_common_arguments(parser: argparse.ArgumentParser, default_output: str) -> None:
    parser.add_argument("yaml_file", nargs="?", default="./origins.yaml")
    parser.add_argument("output_csv", nargs="?", default=default_output)
    parser.add_argument("--version", action="version", version=f"%(prog)s {app_version()}")
    parser.add_argument(
        "--print-only", action="store_true", help="Print rows as JSON without writing CSV."
    )


def parse_coordinate_pair(value: Any) -> tuple[float, float]:
    latitude, longitude = map(float, str(value).split(","))
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError(f"Coordinate out of range: {value!r}")
    return latitude, longitude


def parse_endpoint(endpoint: dict[str, Any]) -> tuple[str, tuple[float, float]]:
    return endpoint["name"].strip(), parse_coordinate_pair(endpoint["location"])


def read_pairs(yaml_file: Path) -> list[RoutePair]:
    with yaml_file.open("r", encoding="utf-8") as stream:
        pairs = yaml.safe_load(stream)["pairs"]
    return [
        RoutePair(*parse_endpoint(pair["origin"]), *parse_endpoint(pair["destination"]))
        for pair in pairs
    ]


def ensure_csv_header(output_csv: Path, header: list[str]) -> None:
    if not output_csv.exists() or output_csv.stat().st_size == 0:
        with output_csv.open("w", newline="", encoding="utf-8") as stream:
            csv.DictWriter(stream, fieldnames=header).writeheader()
        return
    with output_csv.open("r", newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        current = reader.fieldnames or []
        if current == header:
            return
    raise ValueError(
        f"Unexpected CSV header in {output_csv}: expected {header!r}, found {current!r}"
    )


def append_row(output_csv: Path, header: list[str], row: dict[str, Any]) -> None:
    with output_csv.open("a", newline="", encoding="utf-8") as stream:
        csv.DictWriter(stream, fieldnames=header).writerow(row)


def emit_row(
    row: dict[str, Any], output_csv: Path, header: list[str], print_only: bool
) -> None:
    if print_only:
        print(json.dumps(row, ensure_ascii=False))
    else:
        append_row(output_csv, header, row)


def run_routes(
    pairs: Iterable[RoutePair],
    fetch_row: Callable[[RoutePair, int], dict[str, Any]],
    output_csv: Path,
    header: list[str],
    print_only: bool,
) -> None:
    now = int(time.time())
    if not print_only:
        ensure_csv_header(output_csv, header)
    for index, pair in enumerate(pairs, start=1):
        try:
            row = fetch_row(pair, now)
        except ApiError as exc:
            LOGGER.error(
                "route %d (%s -> %s) failed: %s",
                index,
                pair.origin_name,
                pair.destination_name,
                exc,
            )
            continue
        emit_row(row, output_csv, header, print_only)
