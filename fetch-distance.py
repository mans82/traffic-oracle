#!/usr/bin/env python3
import argparse
import csv
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from traffic_oracle.common import (
    RoutePair,
    ApiError,
    TRAVEL_TIMES_HEADER,
    add_common_arguments,
    ensure_timezone,
    load_dotenv,
    read_pairs,
    run_routes,
)

BASE_URL = "https://api.neshan.org/v1/distance-matrix"
EIGHT_HOURS = 8 * 60 * 60


def fetch_duration(pair: RoutePair, api_key: str) -> int:
    origins = urllib.parse.quote(f"{pair.origin[0]},{pair.origin[1]}", safe=",")
    destinations = urllib.parse.quote(f"{pair.destination[0]},{pair.destination[1]}", safe=",")
    request = urllib.request.Request(
        f"{BASE_URL}?origins={origins}&destinations={destinations}",
        headers={"Api-Key": api_key},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ApiError(f"Neshan request failed with HTTP {exc.code}") from exc
    except (urllib.error.URLError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ApiError(f"Neshan request failed: {exc}") from exc
    try:
        return int(payload["rows"][0]["elements"][0]["duration"]["value"])
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ApiError("Neshan returned an unsupported response") from exc


def load_history(
    output: Path,
) -> tuple[
    dict[tuple[str, str], tuple[int, int]],
    dict[tuple[str, str], list[tuple[int, int]]],
]:
    previous: dict[tuple[str, str], tuple[int, int]] = {}
    history: dict[tuple[str, str], list[tuple[int, int]]] = {}
    if not output.exists():
        return previous, history

    with output.open("r", newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            key = row["origin"], row["destination"]
            timestamp = int(row["ts"])
            duration = int(row["duration_value"])
            previous[key] = duration, timestamp
            history.setdefault(key, []).append((timestamp, duration))

    for values in history.values():
        values.sort()
    return previous, history


def latest_duration_at_or_before(
    values: list[tuple[int, int]], target: int
) -> int | None:
    return next(
        (duration for timestamp, duration in reversed(values) if timestamp <= target),
        None,
    )


def main() -> int:
    ensure_timezone()
    load_dotenv()
    parser = argparse.ArgumentParser()
    add_common_arguments(parser, "runtime/static/travel-times.csv")
    args = parser.parse_args()
    api_key = os.environ["NESHAN_API_KEY"]
    pairs = read_pairs(Path(args.yaml_file))
    output = Path(args.output_csv)
    previous, history = load_history(output) if not args.print_only else ({}, {})

    def fetch(pair: RoutePair, now: int):
        duration = fetch_duration(pair, api_key)
        key = (pair.origin_name, pair.destination_name)
        old_duration, old_ts = previous.get(key, (duration, now))
        previous[key] = (duration, now)

        reverse = history.get((pair.destination_name, pair.origin_name), [])
        reverse_eta = latest_duration_at_or_before(
            reverse, now - EIGHT_HOURS - duration
        )
        history.setdefault(key, []).append((now, duration))
        return {
            "origin": pair.origin_name,
            "destination": pair.destination_name,
            "duration_value": duration,
            "ts": now,
            "duration_diff": duration - old_duration,
            "ts_diff": now - old_ts,
            "eta_8h_return_value": (
                duration + EIGHT_HOURS + reverse_eta
                if reverse_eta is not None
                else ""
            ),
        }

    run_routes(pairs, fetch, output, TRAVEL_TIMES_HEADER, args.print_only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
