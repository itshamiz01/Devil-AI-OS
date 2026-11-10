"""Trigger scheduling math (§8). Pure and timezone-aware.

Schedule specs (stored JSON on the trigger row):
* ``{"kind": "once", "at": "<iso8601>"}``
* ``{"kind": "interval", "every_seconds": 3600, "start_at": "<iso8601|null>"}``
* ``{"kind": "daily", "time": "09:30", "timezone": "Asia/Kolkata"}``
  (timezone defaults to UTC when absent or unknown)

Firing is deduplicated by a deterministic fire key per (trigger,
scheduled instant), so a tick that runs twice — or a restart that
replays a window — can never create the same run twice. Missed runs
are counted, and a missed trigger fires ONCE for the latest missed
instant (no catch-up storm), per §8's missed-run rule.
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..core.exceptions import ValidationError


def _parse_iso(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


def _aware(value: dt.datetime | None) -> dt.datetime | None:
    """SQLite round-trips strip tzinfo; every instant in this module
    is UTC, so a naive value is read back as UTC."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=dt.timezone.utc)
    return value


def _zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def validate_schedule(schedule: dict) -> dict:
    if not isinstance(schedule, dict):
        raise ValidationError("trigger schedule must be an object")
    kind = schedule.get("kind")
    if kind == "once":
        if _parse_iso(schedule.get("at")) is None:
            raise ValidationError("a 'once' schedule requires an ISO 'at' instant")
    elif kind == "interval":
        every = schedule.get("every_seconds")
        if not isinstance(every, (int, float)) or every < 10:
            raise ValidationError("an 'interval' schedule requires every_seconds >= 10")
    elif kind == "daily":
        time_part = str(schedule.get("time") or "")
        try:
            hh, mm = time_part.split(":")
            dt.time(int(hh), int(mm))
        except (ValueError, TypeError):
            raise ValidationError("a 'daily' schedule requires time 'HH:MM'") from None
        _zone(schedule.get("timezone"))
    else:
        raise ValidationError(f"unknown schedule kind '{kind}'")
    return schedule


def next_fire(schedule: dict, now: dt.datetime,
              last_fire: dt.datetime | None) -> dt.datetime | None:
    """The next scheduled instant strictly after ``now`` (or the first
    pending instant when the trigger has never fired)."""
    now = _aware(now)
    last_fire = _aware(last_fire)
    kind = schedule.get("kind")
    if kind == "once":
        at = _parse_iso(schedule.get("at"))
        if at is None or last_fire is not None:
            return None
        return at
    if kind == "interval":
        every = dt.timedelta(seconds=float(schedule["every_seconds"]))
        start = _parse_iso(schedule.get("start_at")) or last_fire
        if start is None:
            return now  # first fire is immediate, then cadence rules
        nxt = start + every
        while nxt <= now:
            nxt += every
        return nxt
    if kind == "daily":
        zone = _zone(schedule.get("timezone"))
        hh, mm = (int(p) for p in str(schedule["time"]).split(":"))
        local_now = now.astimezone(zone)
        candidate = local_now.replace(hour=hh, minute=mm, second=0,
                                      microsecond=0)
        if candidate <= local_now:
            candidate += dt.timedelta(days=1)
        return candidate.astimezone(dt.timezone.utc)
    return None


def pending_instant(schedule: dict, now: dt.datetime,
                    last_fire: dt.datetime | None,
                    stored_next: dt.datetime | None) -> tuple[dt.datetime | None, int]:
    """(instant_due, missed_count): the scheduled instant that should
    fire at this tick (<= now), and how many scheduled instants were
    missed before it. Only the LATEST missed instant fires."""
    now = _aware(now)
    last_fire = _aware(last_fire)
    stored_next = _aware(stored_next)
    if stored_next is not None:
        due = stored_next
    else:
        due = next_fire(schedule, now, last_fire)
        if due is not None and due > now and last_fire is None \
                and schedule.get("kind") == "interval":
            due = now  # interval triggers fire immediately the first time
    if due is None or due > now:
        return None, 0
    # Count missed instants between due and now.
    missed = 0
    kind = schedule.get("kind")
    if kind == "interval":
        every = float(schedule["every_seconds"])
        elapsed = (now - due).total_seconds()
        missed = int(elapsed // every)
    elif kind == "daily":
        elapsed_days = (now.date() - due.date()).days
        missed = max(0, elapsed_days)
    return due, missed


def fire_key(trigger_id: str, instant: dt.datetime) -> str:
    return f"trigger:{trigger_id}:{instant.astimezone(dt.timezone.utc).isoformat()}"
