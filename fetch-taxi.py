#!/usr/bin/env python3
import argparse
import json
import os
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path

from traffic_oracle.common import (
    RoutePair,
    ApiError,
    TAXI_PRICES_HEADER,
    add_common_arguments,
    ensure_timezone,
    load_dotenv,
    read_pairs,
    read_token_state,
    run_routes,
    write_token_state,
)

SNAPP_URL = "https://app.snapp.taxi/api/v3/price"
TAPSI_URL = "https://api.tapsi.cab/api/v2.4/ride/preview"

TOKEN_STATE_PATH = "token-state.json"

# Sourced from Snapp's own public web app bundle (app.snapp.taxi), not a project secret.
SNAPP_OAUTH_URL = "https://app.snapp.taxi/api/api-passenger-oauth/v2/auth"
SNAPP_OAUTH_CLIENT_ID = "ios_sadjfhasd9871231hfso234"
SNAPP_OAUTH_CLIENT_SECRET = "23497shjlf982734-=1031nln"

SNAPP_BROWSER_HEADERS = {
    "Origin": "https://app.snapp.taxi",
    "Referer": "https://app.snapp.taxi/pre-ride",
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64; rv:153.0) " "Gecko/20100101 Firefox/153.0"
    ),
    "locale": "fa-IR",
    "App-Version": "pwa",
    "x-app-version": "v18.42.0",
    "x-app-name": "passenger-pwa",
}


@dataclass
class TokenState:
    access: str
    refresh: str


def request_json(url: str, headers: dict, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            **headers,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ApiError(f"request failed with HTTP {exc.code}", status_code=exc.code) from exc
    except (urllib.error.URLError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ApiError(f"request failed: {exc}") from exc


def refresh_snapp_token(refresh_token: str) -> tuple[str, str]:
    response = request_json(
        SNAPP_OAUTH_URL,
        SNAPP_BROWSER_HEADERS,
        {
            "grant_type": "refresh_token",
            "client_id": SNAPP_OAUTH_CLIENT_ID,
            "client_secret": SNAPP_OAUTH_CLIENT_SECRET,
            "device_id": str(uuid.uuid4()),
            "refresh_token": refresh_token,
        },
    )
    try:
        return response["access_token"], response["refresh_token"]
    except KeyError as exc:
        raise ApiError("Snapp token refresh returned an unsupported response") from exc


def fetch_snapp_price(pair: RoutePair, api_key: str) -> int:
    response = request_json(
        SNAPP_URL,
        {
            "Authorization": f"Bearer {api_key}",
            **SNAPP_BROWSER_HEADERS,
        },
        {
            "points": [
                {"lat": str(pair.origin[0]), "lng": str(pair.origin[1])},
                {"lat": str(pair.destination[0]), "lng": str(pair.destination[1])},
            ],
            "price_ride_recom": False,
            "options": {},
            "locale": "fa-IR",
            "os": 6,
            "version": 0,
            "categories": [1],
            "voucher_code": "",
            "flexi_step": 0,
        },
    )
    try:
        service = next(
            service
            for service in response["data"]["services"]
            if service["category_id"] == 1
        )
        return int(service["price"]["final"]) // 10
    except (KeyError, IndexError, StopIteration, TypeError, ValueError) as exc:
        raise ApiError("Snapp API returned an unsupported response") from exc


def fetch_tapsi_price(pair: RoutePair, api_key: str) -> int:
    response = request_json(
        TAPSI_URL,
        {
            "Cookie": f"accessToken={api_key}",
            "x-agent": "v2.2|passenger|WEBAPP|6.8.2||5.0",
        },
        {
            "origin": {
                "latitude": pair.origin[0],
                "longitude": pair.origin[1],
            },
            "destinations": [
                {
                    "latitude": pair.destination[0],
                    "longitude": pair.destination[1],
                }
            ],
        },
    )
    try:
        return int(
            response["data"]["categories"][0]["services"][0]["prices"][0][
                "passengerShare"
            ]
        )
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ApiError("Tapsi API returned an unsupported response") from exc


def main() -> int:
    ensure_timezone()
    load_dotenv()
    parser = argparse.ArgumentParser()
    add_common_arguments(parser, "runtime/static/taxi-prices.csv")
    args = parser.parse_args()
    state = read_token_state(TOKEN_STATE_PATH)
    snapp = TokenState(
        state.get("snapp_access") or os.environ["SNAPP_API_KEY"],
        state.get("snapp_refresh") or os.environ["SNAPP_API_REFRESH_TOKEN"],
    )
    tapsi_key = os.environ["TAPSI_API_KEY"]
    pairs = read_pairs(Path(args.yaml_file))

    def snapp_price(pair: RoutePair) -> int:
        try:
            return fetch_snapp_price(pair, snapp.access)
        except ApiError as exc:
            if exc.status_code != 401:
                raise
            snapp.access, snapp.refresh = refresh_snapp_token(snapp.refresh)
            write_token_state(
                TOKEN_STATE_PATH,
                {"snapp_access": snapp.access, "snapp_refresh": snapp.refresh},
            )
            return fetch_snapp_price(pair, snapp.access)

    def fetch(pair: RoutePair, now: int):
        errors: list[str] = []
        snapp_value = tapsi_value = None
        try:
            snapp_value = snapp_price(pair)
        except ApiError as exc:
            errors.append(f"snapp: {exc}")
        try:
            tapsi_value = fetch_tapsi_price(pair, tapsi_key)
        except ApiError as exc:
            errors.append(f"tapsi: {exc}")
        if errors:
            raise ApiError("; ".join(errors))
        return {
            "origin": pair.origin_name,
            "destination": pair.destination_name,
            "snapp_price": snapp_value,
            "tapsi_price": tapsi_value,
            "ts": now,
        }

    run_routes(pairs, fetch, Path(args.output_csv), TAXI_PRICES_HEADER, args.print_only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
