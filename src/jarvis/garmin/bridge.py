"""Isolated Python 3.12 Garmin client; never print credentials or raw Garmin data.

Run ``login`` only in a trusted local terminal. ``summary`` emits a bounded,
normalized view for Core. Tokens live in Windows Credential Locker.
"""

from __future__ import annotations

import ctypes
import getpass
import json
import logging
import math
import os
import stat
import sys
from base64 import b64decode, b64encode
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

_SERVICE = "JARVIS Garmin read-only"
_ACCOUNT = "local-owner"
_CHUNK_SIZE = 900  # ASCII chars: safely below Windows' UTF-16 credential blob limit.
_TOKEN_LIMIT = 65_536
_TOKEN_FIELDS = frozenset({"di_token", "di_refresh_token", "di_client_id"})
_ACTIVITY_TYPES = frozenset(
    {
        "walking",
        "running",
        "trail_running",
        "treadmill_running",
        "hiking",
        "cycling",
        "road_biking",
        "mountain_biking",
        "indoor_cycling",
        "swimming",
        "lap_swimming",
        "open_water_swimming",
        "strength_training",
        "cardio_training",
        "yoga",
        "elliptical",
        "stair_climbing",
        "rowing",
        "golf",
        "other",
    }
)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate Garmin session field")
        result[key] = value
    return result


def _validate_token_json(raw: bytes | str) -> str:
    """Validate the shared 0.3.16/0.3.17 format without importing upstream code."""
    data = raw.encode("utf-8") if isinstance(raw, str) else raw
    if not data or len(data) > _TOKEN_LIMIT:
        raise ValueError("invalid Garmin session size")
    value = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_object)
    if not isinstance(value, dict) or set(value) != _TOKEN_FIELDS:
        raise ValueError("unsupported Garmin session format")
    for key, item in value.items():
        if (
            not isinstance(item, str)
            or not item
            or any(not 33 <= ord(char) <= 126 for char in item)
            or (key == "di_client_id" and len(item) > 256)
        ):
            raise ValueError("invalid Garmin session field")
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    if len(canonical.encode("utf-8")) > _TOKEN_LIMIT:
        raise ValueError("invalid Garmin session size")
    return canonical


def _checked_source(path: Path) -> dict[Path, os.stat_result]:
    if (
        not path.is_absolute()
        or path.anchor.startswith("\\\\")
        or path.suffix.lower() != ".json"
        or any(part == ".." or ":" in part for part in path.parts[1:])
    ):
        raise ValueError("explicit local Garmin JSON file required")
    if sys.platform == "win32" and ctypes.windll.kernel32.GetDriveTypeW(path.anchor) != 3:
        raise ValueError("fixed local Garmin session drive required")
    entries: dict[Path, os.stat_result] = {}
    for entry in (*reversed(path.parents), path):
        info = entry.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(
            stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400
        ):
            raise ValueError("linked Garmin session source rejected")
        entries[entry] = info
    if not stat.S_ISREG(entries[path].st_mode):
        raise ValueError("regular Garmin session file required")
    return entries


def _read_saved_session(path: Path) -> str:
    """Bounded explicit source read; never discover, follow links, or write files."""
    entries = _checked_source(path)
    original = entries[path]
    if not 0 < original.st_size <= _TOKEN_LIMIT:
        raise ValueError("invalid Garmin session size")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "rb") as source:
        opened = os.fstat(source.fileno())
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (
            original.st_dev,
            original.st_ino,
        ):
            raise ValueError("changed Garmin session source")
        raw = source.read(_TOKEN_LIMIT + 1)
        after = os.fstat(source.fileno())
        if (opened.st_size, opened.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError("changed Garmin session source")
    current = _checked_source(path)
    if any(
        (info.st_dev, info.st_ino) != (current[entry].st_dev, current[entry].st_ino)
        for entry, info in entries.items()
    ):
        raise ValueError("changed Garmin session source")
    return _validate_token_json(raw)


def _import_session(path: Path) -> None:
    """Owner-authorized offline copy into Locker; never refresh or replace a session."""
    vault = _vault()
    if _manifest(vault) is not None:
        raise RuntimeError("Garmin already connected; review existing session first")
    token = _read_saved_session(path)
    _store_token(vault, token)
    print("Garmin session imported into Windows Credential Locker. Live validity unverified.")


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
    if not raw or len(raw) > _TOKEN_LIMIT:
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
        kind = item.get("activityType")
        kind = kind.get("typeKey") if isinstance(kind, dict) else None
        kind = kind if isinstance(kind, str) and kind in _ACTIVITY_TYPES else "other"
        started = item.get("startTimeLocal")
        try:
            started = datetime.fromisoformat(started if isinstance(started, str) else "").strftime(
                "%Y-%m-%dT%H:%M:%S"
            )
        except (TypeError, ValueError):
            started = ""
        rows.append(
            {
                "name": kind.replace("_", " ").title() if kind != "other" else "Activity",
                "type": kind,
                "started": started,
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

    # Fresh interactive login must never load or overwrite an ambient file store.
    os.environ.pop("GARMINTOKENS", None)
    email = input("Garmin email: ").strip()
    password = getpass.getpass("Garmin password: ")
    client = Garmin(email, password, prompt_mfa=lambda: input("Garmin MFA code: ").strip())
    client.login()
    token_json = _validate_token_json(client.client.dumps())
    _store_token(_vault(), token_json)
    print("Garmin connected. Refresh token stored in Windows Credential Locker.")


def _summary() -> None:
    from garminconnect import Garmin, GarminConnectTooManyRequestsError

    vault = _vault()
    token_json = _read_token(vault)
    if not token_json:
        raise RuntimeError("garmin_not_connected")
    token_json = _validate_token_json(token_json)
    client = Garmin(retry_attempts=0)
    # Requests otherwise consults the owner's .netrc and can replace Bearer auth.
    client.client._api_session.trust_env = False
    client.client.cs.trust_env = False
    try:
        client.login(token_json)
        result = _collect_summary(client, GarminConnectTooManyRequestsError)
    finally:
        # Login/profile or category failures can follow a successful token rotation.
        # Preserve the renewed session even when no summary can be emitted.
        renewed = _validate_token_json(client.client.dumps())
        if renewed != token_json:
            _store_token(vault, renewed)
    print(json.dumps(result, separators=(",", ":")))


def _collect_summary(client: Any, rate_error: type[Exception]) -> dict[str, Any]:
    today = datetime.now(UTC).astimezone().date()
    day = today.isoformat()
    successful_reads = 0
    rate_limited = False

    def available(call: Any) -> Any:
        nonlocal successful_reads, rate_limited
        if rate_limited:
            return None
        try:
            result = call()
            if result is None or len(json.dumps(result)) > 1_000_000:
                return None
            successful_reads += 1
            return result
        except rate_error:
            rate_limited = True
            return None
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
    return result


def _disconnect() -> None:
    _delete_token(_vault())
    print("Local Garmin token removed. Revoke Garmin-side access separately if needed.")


def main() -> int:
    command = sys.argv[1] if len(sys.argv) >= 2 else ""
    if not (
        (len(sys.argv) == 2 and command in {"login", "summary", "disconnect"})
        or (len(sys.argv) == 3 and command == "import-session")
    ):
        print(
            "Usage: bridge.py login|summary|disconnect or import-session ABSOLUTE_JSON_FILE",
            file=sys.stderr,
        )
        return 2
    # Third-party diagnostic logging can include raw URLs/provider exception data.
    previous_logging_level = logging.root.manager.disable
    previous_netrc = os.environ.get("NETRC")
    os.environ["NETRC"] = os.devnull
    logging.disable(logging.CRITICAL)
    try:
        if command == "import-session":
            _import_session(Path(sys.argv[2]))
        else:
            {"login": _login, "summary": _summary, "disconnect": _disconnect}[command]()
    except Exception:
        print("Garmin operation unavailable; check trusted local setup.", file=sys.stderr)
        return 1
    finally:
        logging.disable(previous_logging_level)
        if previous_netrc is None:
            os.environ.pop("NETRC", None)
        else:
            os.environ["NETRC"] = previous_netrc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
