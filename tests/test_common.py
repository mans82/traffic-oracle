from pathlib import Path

from traffic_oracle.common import read_token_state, write_token_state


def test_read_token_state_missing_file_returns_empty(tmp_path: Path) -> None:
    assert read_token_state(tmp_path / "token-state.json") == {}


def test_read_token_state_empty_file_returns_empty(tmp_path: Path) -> None:
    state_path = tmp_path / "token-state.json"
    state_path.write_text("", encoding="utf-8")

    assert read_token_state(state_path) == {}


def test_write_then_read_token_state_round_trips(tmp_path: Path) -> None:
    state_path = tmp_path / "token-state.json"

    write_token_state(state_path, {"snapp_access": "a", "snapp_refresh": "b"})

    assert read_token_state(state_path) == {"snapp_access": "a", "snapp_refresh": "b"}
