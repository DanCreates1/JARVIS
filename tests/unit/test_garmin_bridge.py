"""Garmin normalization rejects implausible fields and raw account details."""

import json
import sys
from datetime import date
from types import ModuleType, SimpleNamespace

import pytest

from jarvis.garmin import bridge
from jarvis.garmin.bridge import normalize_summary


class FakeVault:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, account: str) -> str | None:
        return self.values.get((service, account))

    def set_password(self, service: str, account: str, token: str) -> None:
        self.values[(service, account)] = token

    def delete_password(self, service: str, account: str) -> None:
        del self.values[(service, account)]


def test_garmin_vault_chunks_large_tokens_and_disconnects() -> None:
    vault = FakeVault()
    token = "secret-token-" * 1000
    bridge._store_token(vault, token)
    assert bridge._read_token(vault) == token
    assert all(len(value) <= 900 for value in vault.values.values())
    assert token not in str(vault.values)
    bridge._store_token(vault, "renewed-token")
    assert bridge._read_token(vault) == "renewed-token"
    assert len(vault.values) == 2
    bridge._delete_token(vault)
    assert bridge._read_token(vault) is None
    assert vault.values == {}


def test_garmin_login_keeps_credentials_out_of_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class Garmin:
        def __init__(self, email: str, password: str, *, prompt_mfa: object) -> None:
            assert email == "owner@example.test"
            assert password == "private-password"
            assert callable(prompt_mfa) and prompt_mfa() == "private-mfa"
            self.client = SimpleNamespace(dumps=lambda: "private-token")

        def login(self) -> None:
            pass

    module = ModuleType("garminconnect")
    module.Garmin = Garmin  # type: ignore[attr-defined]
    vault = FakeVault()
    responses = iter(["owner@example.test", "private-mfa"])
    monkeypatch.setitem(sys.modules, "garminconnect", module)
    monkeypatch.setattr(bridge, "_vault", lambda: vault)
    monkeypatch.setattr("builtins.input", lambda _prompt: next(responses))
    monkeypatch.setattr(bridge.getpass, "getpass", lambda _prompt: "private-password")
    bridge._login()
    assert bridge._read_token(vault) == "private-token"
    output = capsys.readouterr().out
    assert "private-password" not in output and "private-mfa" not in output
    assert "owner@example.test" not in output and "private-token" not in output


def test_garmin_summary_allowlists_bounded_values() -> None:
    summary = normalize_summary(
        day=date(2026, 9, 30),
        stats={"totalSteps": 6543, "preciseLocation": "private"},
        heart={"restingHeartRate": 56, "heartRateValues": [1, 2, 3]},
        sleep={"dailySleepDTO": {"sleepTimeSeconds": 7 * 3600 + 30 * 60}},
        stress={"avgStressLevel": 24},
        battery=[
            {
                "bodyBatteryValuesArray": [["2026-09-30T09:00", 55], ["2026-09-30T12:00", 82]],
                "rawEvents": ["private"],
            }
        ],
        activities=[
            {
                "activityName": "Morning walk",
                "activityType": {"typeKey": "walking"},
                "startTimeLocal": "2026-09-30T07:30:00",
                "latitude": 43.6,
            }
        ],
    )
    assert summary["steps"] == 6543
    assert summary["resting_heart_rate"] == 56
    assert summary["sleep_minutes"] == 450
    assert summary["activities"] == [
        {"name": "Morning walk", "type": "walking", "started": "2026-09-30T07:30:00"}
    ]
    assert "private" not in str(summary) and "latitude" not in str(summary)


def test_garmin_summary_rejects_invalid_values() -> None:
    summary = normalize_summary(
        day=date(2026, 9, 30),
        stats={"totalSteps": -1},
        heart={"restingHeartRate": True},
        sleep={"dailySleepDTO": {"sleepTimeSeconds": 100_000}},
        stress={"avgStressLevel": 999},
        battery=[{"bodyBatteryValuesArray": [["2026-09-30T09:00", float("nan")]]}],
        activities=[{"activityName": "A" * 1000, "activityType": {"typeKey": "run"}}],
    )
    assert summary["steps"] is None
    assert summary["resting_heart_rate"] is None
    assert summary["sleep_minutes"] is None
    assert summary["stress"] is None
    assert summary["body_battery"] is None
    assert len(summary["activities"][0]["name"]) == 80


def test_garmin_bridge_emits_only_allowlisted_data_and_refreshes_vault(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class Garmin:
        def __init__(self, *, retry_attempts: int) -> None:
            assert retry_attempts == 0
            self.client = SimpleNamespace(dumps=lambda: "private-renewed-token")

        def login(self, token: str) -> None:
            assert token == "private-original-token"

        def get_stats(self, _day: str) -> dict[str, object]:
            return {"totalSteps": 8000, "latitude": 43.6}

        def get_heart_rates(self, _day: str) -> dict[str, int]:
            return {"restingHeartRate": 54}

        def get_sleep_data(self, _day: str) -> dict[str, dict[str, int]]:
            return {"dailySleepDTO": {"sleepTimeSeconds": 25200}}

        def get_stress_data(self, _day: str) -> dict[str, int]:
            return {"avgStressLevel": 26}

        def get_body_battery(self, _day: str) -> list[dict[str, object]]:
            return [{"bodyBatteryValuesArray": [["now", 71]]}]

        def get_activities(self, _start: int, _limit: int) -> list[dict[str, object]]:
            return [{"activityName": "Walk", "preciseLocation": "private"}]

    vault = FakeVault()
    bridge._store_token(vault, "private-original-token")
    module = ModuleType("garminconnect")
    module.Garmin = Garmin  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "garminconnect", module)
    monkeypatch.setattr(bridge, "_vault", lambda: vault)
    bridge._summary()
    output = capsys.readouterr().out
    result = json.loads(output)
    assert result["steps"] == 8000
    assert result["body_battery"] == 71
    assert result["activities"][0]["name"] == "Walk"
    assert bridge._read_token(vault) == "private-renewed-token"
    assert "private" not in output and "latitude" not in output


def test_garmin_bridge_fails_closed_when_all_reads_fail(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class Garmin:
        def __init__(self, *, retry_attempts: int) -> None:
            self.client = SimpleNamespace(dumps=lambda: "private-token")

        def login(self, _token: str) -> None:
            pass

        def __getattr__(self, _name: str) -> object:
            def fail(*_args: object) -> None:
                raise RuntimeError("private Garmin error")

            return fail

    module = ModuleType("garminconnect")
    module.Garmin = Garmin  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "garminconnect", module)
    vault = FakeVault()
    bridge._store_token(vault, "token")
    monkeypatch.setattr(bridge, "_vault", lambda: vault)
    monkeypatch.setattr(sys, "argv", ["bridge.py", "summary"])
    assert bridge.main() == 1
    captured = capsys.readouterr()
    assert "private" not in captured.out + captured.err
