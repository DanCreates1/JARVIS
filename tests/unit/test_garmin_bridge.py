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


class TooManyRequestsError(Exception):
    pass


def token_json(label: str) -> str:
    return bridge._validate_token_json(
        json.dumps({"di_token": label, "di_refresh_token": label, "di_client_id": "synthetic"})
    )


def fake_client(label: str) -> SimpleNamespace:
    return SimpleNamespace(
        dumps=lambda: token_json(label),
        _api_session=SimpleNamespace(trust_env=True),
        cs=SimpleNamespace(trust_env=True),
    )


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
            self.client = SimpleNamespace(dumps=lambda: token_json("private-token"))

        def login(self) -> None:
            import os

            assert "GARMINTOKENS" not in os.environ

    module = ModuleType("garminconnect")
    module.Garmin = Garmin  # type: ignore[attr-defined]
    vault = FakeVault()
    responses = iter(["owner@example.test", "private-mfa"])
    monkeypatch.setitem(sys.modules, "garminconnect", module)
    monkeypatch.setattr(bridge, "_vault", lambda: vault)
    monkeypatch.setattr("builtins.input", lambda _prompt: next(responses))
    monkeypatch.setattr(bridge.getpass, "getpass", lambda _prompt: "private-password")
    monkeypatch.setenv("GARMINTOKENS", "must-not-read-or-write")
    bridge._login()
    assert bridge._read_token(vault) == token_json("private-token")
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
        {"name": "Walking", "type": "walking", "started": "2026-09-30T07:30:00"}
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
    assert summary["activities"][0] == {"name": "Activity", "type": "other", "started": ""}


def test_garmin_bridge_emits_only_allowlisted_data_and_refreshes_vault(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class Garmin:
        def __init__(self, *, retry_attempts: int) -> None:
            assert retry_attempts == 0
            self.client = fake_client("private-renewed-token")

        def login(self, token: str) -> None:
            assert token == token_json("private-original-token")
            assert not self.client._api_session.trust_env and not self.client.cs.trust_env

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
    bridge._store_token(vault, token_json("private-original-token"))
    module = ModuleType("garminconnect")
    module.Garmin = Garmin  # type: ignore[attr-defined]
    module.GarminConnectTooManyRequestsError = TooManyRequestsError  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "garminconnect", module)
    monkeypatch.setattr(bridge, "_vault", lambda: vault)
    bridge._summary()
    output = capsys.readouterr().out
    result = json.loads(output)
    assert result["steps"] == 8000
    assert result["body_battery"] == 71
    assert result["activities"][0]["name"] == "Activity"
    assert bridge._read_token(vault) == token_json("private-renewed-token")
    assert "private" not in output and "latitude" not in output


def test_garmin_bridge_fails_closed_when_all_reads_fail(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class Garmin:
        def __init__(self, *, retry_attempts: int) -> None:
            self.client = fake_client("private-token")

        def login(self, _token: str) -> None:
            pass

        def __getattr__(self, _name: str) -> object:
            def fail(*_args: object) -> None:
                raise RuntimeError("private Garmin error")

            return fail

    module = ModuleType("garminconnect")
    module.Garmin = Garmin  # type: ignore[attr-defined]
    module.GarminConnectTooManyRequestsError = TooManyRequestsError  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "garminconnect", module)
    vault = FakeVault()
    bridge._store_token(vault, token_json("private-token"))
    monkeypatch.setattr(bridge, "_vault", lambda: vault)
    monkeypatch.setattr(sys, "argv", ["bridge.py", "summary"])
    assert bridge.main() == 1
    captured = capsys.readouterr()
    assert "private" not in captured.out + captured.err


@pytest.mark.parametrize("failure", ["login", "reads"])
def test_garmin_preserves_rotated_session_after_failed_summary(
    failure: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class Garmin:
        def __init__(self, *, retry_attempts: int) -> None:
            self.client = fake_client("rotated-synthetic-token")

        def login(self, _token: str) -> None:
            if failure == "login":
                raise RuntimeError("private-profile-error")

        def __getattr__(self, _name: str) -> object:
            def fail(*_args: object) -> None:
                raise RuntimeError("private-category-error")

            return fail

    module = ModuleType("garminconnect")
    module.Garmin = Garmin  # type: ignore[attr-defined]
    module.GarminConnectTooManyRequestsError = TooManyRequestsError  # type: ignore[attr-defined]
    vault = FakeVault()
    bridge._store_token(vault, token_json("original-synthetic-token"))
    monkeypatch.setitem(sys.modules, "garminconnect", module)
    monkeypatch.setattr(bridge, "_vault", lambda: vault)
    monkeypatch.setattr(sys, "argv", ["bridge.py", "summary"])
    assert bridge.main() == 1
    assert bridge._read_token(vault) == token_json("rotated-synthetic-token")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "private" not in captured.err and "token" not in captured.err


@pytest.mark.parametrize("first_success", [False, True])
def test_garmin_stops_category_reads_at_rate_limit(first_success: bool) -> None:
    calls: list[str] = []

    class Garmin:
        def __getattr__(self, name: str) -> object:
            def read(*_args: object) -> dict[str, int]:
                calls.append(name)
                if first_success and name == "get_stats":
                    return {"totalSteps": 1234}
                raise TooManyRequestsError("private rate limit")

            return read

    if first_success:
        assert bridge._collect_summary(Garmin(), TooManyRequestsError)["steps"] == 1234
        assert calls == ["get_stats", "get_heart_rates"]
    else:
        with pytest.raises(RuntimeError, match="garmin_reads_failed"):
            bridge._collect_summary(Garmin(), TooManyRequestsError)
        assert calls == ["get_stats"]


@pytest.mark.parametrize("failed_write", [1, 2, 3])
def test_vault_write_failure_preserves_previous_session(failed_write: int) -> None:
    class FailingVault(FakeVault):
        writes = 0
        armed = False

        def set_password(self, service: str, account: str, token: str) -> None:
            if self.armed:
                self.writes += 1
                if self.writes == failed_write:
                    raise RuntimeError("synthetic vault failure")
            super().set_password(service, account, token)

    vault = FailingVault()
    bridge._store_token(vault, "old-synthetic-session")
    original = dict(vault.values)
    vault.armed = True
    with pytest.raises(RuntimeError, match="synthetic vault failure"):
        bridge._store_token(vault, "new-synthetic-session" * 50)
    assert bridge._read_token(vault) == "old-synthetic-session"
    assert vault.values == original


def test_activity_free_text_never_enters_phone_summary() -> None:
    result = normalize_summary(
        day=date(2026, 10, 7),
        stats={},
        heart={},
        sleep={},
        stress={},
        battery=[],
        activities=[
            {
                "activityName": "private-location",
                "activityType": {"typeKey": "private-account"},
                "startTimeLocal": "private-address",
            },
            {
                "activityName": "private-name",
                "activityType": {"typeKey": "walking"},
                "startTimeLocal": "2026-10-07T12:00:00 private-location",
            },
        ],
    )
    assert "private" not in json.dumps(result)
    assert result["activities"] == [
        {"name": "Activity", "type": "other", "started": ""},
        {"name": "Walking", "type": "walking", "started": ""},
    ]


def test_bridge_cli_disables_ambient_netrc_and_restores_process_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import logging
    import os

    monkeypatch.setenv("NETRC", "synthetic-must-not-read")
    monkeypatch.setattr(sys, "argv", ["bridge.py", "summary"])
    previous_level = logging.root.manager.disable

    def summary() -> None:
        assert os.environ["NETRC"] == os.devnull
        assert logging.root.manager.disable == logging.CRITICAL
        raise RuntimeError("private failure")

    monkeypatch.setattr(bridge, "_summary", summary)
    assert bridge.main() == 1
    assert os.environ["NETRC"] == "synthetic-must-not-read"
    assert logging.root.manager.disable == previous_level
