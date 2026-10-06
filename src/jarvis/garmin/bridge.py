"""Isolated Python 3.12 Garmin client; never print credentials or raw Garmin data.

Run ``login`` only in a trusted local terminal. ``summary`` emits a bounded,
normalized view for Core. Tokens live in Windows Credential Locker.
"""

from __future__ import annotations

import getpass
import json
import math
import sys
from base64 import b64decode, b64encode
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

_SERVICE = "JARVIS Garmin read-only"
_ACCOUNT = "local-owner"
_CHUNK_SIZE = 900  # ASCII chars: safely below Windows' UTF-16 credential blob limit.


def _vault() -> Any:
    if sys.platform != "win32":
        raise RuntimeError("Windows Credential Locker is required")
    from keyring.backends.Windows import WinVaultKeyring  # type: ignore[import-not-found]

    return WinVaultKeyring()


def _manifest(vault: Any) -> tuple[str, int] | None:
    raw = vault.get_password(_SERVICE, _ACCOUNT)
    if not raw:
        return None
    value = json.loads(raw)
    generation = value["generation"]
    count = value["count"]
    if (
        value.get("version") != 1
        or not isinstance(generation, str)
        or UUID(generation).hex != generation
        or type(count) is not int
        or not 1 <= count <= 100
    ):
        raise ValueError("invalid Garmin vault manifest")
    return generation, count


def _chunk_key(generation: str, index: int) -> str:
    return f"{_ACCOUNT}:{generation}:{index}"


def _read_token(vault: Any) -> str | None:
    manifest = _manifest(vault)
    if manifest is None:
        return None
    generation, count = manifest
    chunks = [vault.get_password(_SERVICE, _chunk_key(generation, i)) for i in range(count)]
    if any(chunk is None for chunk in chunks):
        raise ValueError("incomplete Garmin vault token")
    encoded = "".join(chunks)
    if len(encoded) > 100 * _CHUNK_SIZE:
        raise ValueError("oversized Garmin vault token")
    return b64decode(encoded, validate=True).decode("utf-8")


def _store_token(vault: Any, token: str) -> None:
    raw = token.encode("utf-8")
    if not raw or len(raw) > 65_536:
        raise ValueError("invalid Garmin token size")
    old = _manifest(vault)
    generation = uuid4().hex
    encoded = b64encode(raw).decode("ascii")
    chunks = [encoded[i : i + _CHUNK_SIZE] for i in range(0, len(encoded), _CHUNK_SIZE)]
    written = 0
    try:
        for index, chunk in enumerate(chunks):
            vault.set_password(_SERVICE, _chunk_key(generation, index), chunk)
            written += 1
        vault.set_password(
            _SERVICE,
            _ACCOUNT,
            json.dumps({"version": 1, "generation": generation, "count": len(chunks)}),
        )
    except Exception:
        for index in range(written):
            vault.delete_password(_SERVICE, _chunk_key(generation, index))
        raise
    if old is not None:
        for index in range(old[1]):
            vault.delete_password(_SERVICE, _chunk_key(old[0], index))


def _delete_token(vault: Any) -> None:
    old = _manifest(vault)
    if old is None:
        return
    vault.delete_password(_SERVICE, _ACCOUNT)
    for index in range(old[1]):
        vault.delete_password(_SERVICE, _chunk_key(old[0], index))


def _number(value: Any, minimum: float, maximum: float) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not minimum <= value <= maximum or not math.isfinite(value):
        return None
    return int(value)


def normalize_summary(
    *,
    day: date,
    stats: Any,
    heart: Any,
    sleep: Any,
    stress: Any,
    battery: Any,
    activities: Any,
) -> dict[str, Any]:
    """Allowlist only small, plausible health values; discard raw account data."""
    stats = stats if isinstance(stats, dict) else {}
    heart = heart if isinstance(heart, dict) else {}
    sleep = sleep if isinstance(sleep, dict) else {}
    stress = stress if isinstance(stress, dict) else {}
    battery = battery if isinstance(battery, list) else []
    activities = activities if isinstance(activities, list) else []
    sleep_daily = sleep.get("dailySleepDTO")
    sleep_daily = sleep_daily if isinstance(sleep_daily, dict) else {}
    battery_day = battery[0] if battery and isinstance(battery[0], dict) else {}
    battery_values = battery_day.get("bodyBatteryValuesArray")
    battery_values = battery_values if isinstance(battery_values, list) else []
    latest_battery = None
    for pair in battery_values[-500:]:
        if isinstance(pair, list) and len(pair) >= 2:
            level = _number(pair[1], 0, 100)
            if level is not None:
                latest_battery = level
    rows: list[dict[str, str]] = []
    for item in activities[:3]:
        if not isinstance(item, dict):
            continue
        name = item.get("activityName")
        kind = item.get("activityType")
        kind = kind.get("typeKey") if isinstance(kind, dict) else None
        started = item.get("startTimeLocal")
        rows.append(
            {
                "name": name[:80] if isinstance(name, str) else "Activity",
                "type": kind[:40] if isinstance(kind, str) else "other",
                "started": started[:19] if isinstance(started, str) else "",
            }
        )
    return {
        "date": day.isoformat(),
        "refreshed_at": datetime.now(UTC).isoformat(),
        "steps": _number(stats.get("totalSteps"), 0, 200_000),
        "resting_heart_rate": _number(heart.get("restingHeartRate"), 20, 240),
        "sleep_minutes": (
            None
            if (seconds := _number(sleep_daily.get("sleepTimeSeconds"), 0, 86_400)) is None
            else seconds // 60
        ),
        "stress": _number(stress.get("avgStressLevel"), 0, 100),
        "body_battery": latest_battery,
        "activities": rows,
    }


def _login() -> None:
    from garminconnect import Garmin  # type: ignore[import-not-found]

    email = input("Garmin email: ").strip()
    password = getpass.getpass("Garmin password: ")
    client = Garmin(email, password, prompt_mfa=lambda: input("Garmin MFA code: ").strip())
    client.login()
    token_json = client.client.dumps()
    _store_token(_vault(), token_json)
    print("Garmin connected. Refresh token stored in Windows Credential Locker.")


def _summary() -> None:
    from garminconnect import Garmin

    token_json = _read_token(_vault())
    if not token_json:
        raise RuntimeError("garmin_not_connected")
    client = Garmin(retry_attempts=0)
    client.login(token_json)
    today = datetime.now(UTC).astimezone().date()
    day = today.isoformat()
    successful_reads = 0

    def available(call: Any) -> Any:
        nonlocal successful_reads
        try:
            result = call()
            if result is None or len(json.dumps(result)) > 1_000_000:
                return None
            successful_reads += 1
            return result
        except Exception:
            return None

    result = normalize_summary(
        day=today,
        stats=available(lambda: client.get_stats(day)),
        heart=available(lambda: client.get_heart_rates(day)),
        sleep=available(lambda: client.get_sleep_data(day)),
        stress=available(lambda: client.get_stress_data(day)),
        battery=available(lambda: client.get_body_battery(day)),
        activities=available(lambda: client.get_activities(0, 3)),
    )
    if successful_reads == 0:
        raise RuntimeError("garmin_reads_failed")
    _store_token(_vault(), client.client.dumps())
    print(json.dumps(result, separators=(",", ":")))


def _disconnect() -> None:
    _delete_token(_vault())
    print("Local Garmin token removed. Revoke Garmin-side access separately if needed.")


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"login", "summary", "disconnect"}:
        print("Usage: bridge.py login|summary|disconnect", file=sys.stderr)
        return 2
    try:
        {"login": _login, "summary": _summary, "disconnect": _disconnect}[sys.argv[1]]()
    except Exception:
        print("Garmin operation unavailable; check trusted local setup.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
