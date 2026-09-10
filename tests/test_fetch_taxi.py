import json
import urllib.error

import pytest

from tests.conftest import fetch_taxi
from traffic_oracle.common import ApiError, RoutePair


def _pair() -> RoutePair:
    return RoutePair("origin", (35.7, 51.4), "destination", (35.8, 51.5))


def _http_error(status: int, body: dict) -> urllib.error.HTTPError:
    import io

    return urllib.error.HTTPError(
        url="https://example.test",
        code=status,
        msg="error",
        hdrs=None,
        fp=io.BytesIO(json.dumps(body).encode("utf-8")),
    )


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_refresh_snapp_token_parses_response(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=30):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse({"access_token": "new-access", "refresh_token": "new-refresh"})

    monkeypatch.setattr(fetch_taxi.urllib.request, "urlopen", fake_urlopen)

    access, refresh = fetch_taxi.refresh_snapp_token("old-refresh")

    assert access == "new-access"
    assert refresh == "new-refresh"
    assert captured["url"] == fetch_taxi.SNAPP_OAUTH_URL
    assert captured["body"]["grant_type"] == "refresh_token"
    assert captured["body"]["refresh_token"] == "old-refresh"
    assert captured["body"]["client_id"] == fetch_taxi.SNAPP_OAUTH_CLIENT_ID


def test_refresh_snapp_token_raises_on_bad_response(monkeypatch):
    def fake_urlopen(request, timeout=30):
        return FakeResponse({"unexpected": "shape"})

    monkeypatch.setattr(fetch_taxi.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(ApiError):
        fetch_taxi.refresh_snapp_token("old-refresh")


def test_snapp_price_refreshes_once_on_401_then_succeeds(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    price_payload = {
        "data": {"services": [{"category_id": 1, "price": {"final": 1234000}}]}
    }
    calls = {"price": 0}

    def fake_urlopen(request, timeout=30):
        if request.full_url == fetch_taxi.SNAPP_URL:
            calls["price"] += 1
            auth = request.headers.get("Authorization")
            if calls["price"] == 1:
                assert auth == "Bearer stale-access"
                raise _http_error(401, {"error": "unauthorized"})
            assert auth == "Bearer fresh-access"
            return FakeResponse(price_payload)
        if request.full_url == fetch_taxi.SNAPP_OAUTH_URL:
            return FakeResponse({"access_token": "fresh-access", "refresh_token": "fresh-refresh"})
        raise AssertionError(f"unexpected URL {request.full_url}")

    monkeypatch.setattr(fetch_taxi.urllib.request, "urlopen", fake_urlopen)

    snapp = fetch_taxi.TokenState("stale-access", "old-refresh")

    def snapp_price(pair):
        try:
            return fetch_taxi.fetch_snapp_price(pair, snapp.access)
        except ApiError as exc:
            assert exc.status_code == 401
            snapp.access, snapp.refresh = fetch_taxi.refresh_snapp_token(snapp.refresh)
            fetch_taxi.write_token_state(
                fetch_taxi.TOKEN_STATE_PATH,
                {"snapp_access": snapp.access, "snapp_refresh": snapp.refresh},
            )
            return fetch_taxi.fetch_snapp_price(pair, snapp.access)

    price = snapp_price(_pair())

    assert price == 123400
    assert snapp.access == "fresh-access"
    assert snapp.refresh == "fresh-refresh"
    persisted = fetch_taxi.read_token_state(fetch_taxi.TOKEN_STATE_PATH)
    assert persisted == {"snapp_access": "fresh-access", "snapp_refresh": "fresh-refresh"}


def test_main_attempts_both_services_and_drops_row_on_single_failure(
    monkeypatch, tmp_path, capsys
):
    (tmp_path / ".env").write_text(
        'SNAPP_API_KEY="access"\nSNAPP_API_REFRESH_TOKEN="refresh"\nTAPSI_API_KEY="tapsi-access"\n',
        encoding="utf-8",
    )
    origins = tmp_path / "origins.yaml"
    origins.write_text(
        "pairs:\n"
        "  - origin: {name: A, location: '35.7,51.4'}\n"
        "    destination: {name: B, location: '35.8,51.5'}\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    snapp_calls = {"count": 0}
    tapsi_calls = {"count": 0}
    price_payload = {
        "data": {"services": [{"category_id": 1, "price": {"final": 1000000}}]}
    }

    def fake_urlopen(request, timeout=30):
        if request.full_url == fetch_taxi.SNAPP_URL:
            snapp_calls["count"] += 1
            return FakeResponse(price_payload)
        if request.full_url == fetch_taxi.TAPSI_URL:
            tapsi_calls["count"] += 1
            raise _http_error(500, {"error": "boom"})
        raise AssertionError(f"unexpected URL {request.full_url}")

    monkeypatch.setattr(fetch_taxi.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        "sys.argv", ["fetch-taxi.py", str(origins), "unused.csv", "--print-only"]
    )

    fetch_taxi.main()

    assert snapp_calls["count"] == 1
    assert tapsi_calls["count"] == 1
    assert capsys.readouterr().out.strip() == ""
