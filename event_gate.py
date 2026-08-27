"""event_gate.py - the scheduled-event execution gate.

Spec: docs/event_gate.md. Deterministic and AI-free, like gates.py.

One question only: is an approved major catalyst still ahead later in this
session? If so, opening a fresh 1-3 DTE short-premium position is undesirable
regardless of what the regime says - so the legal envelope becomes NO_TRADE.

This does NOT rewrite the regime and does NOT touch Gold Rules V2. It only ever
subtracts permission. See handoff sections 1-3.

Run `python event_gate.py` for the self-checks; nothing here trades.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, time
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

EVENTS_PATH = os.path.join(os.path.dirname(__file__), "event_gate_events.json")

# V1 approved list - deliberately narrow (handoff section 1). Match on the
# entry's "type" field, not free text. Do not widen without human sign-off.
APPROVED_TYPES = {
    "CPI",
    "NFP",                 # Employment Situation / Non-Farm Payrolls
    "PCE",                 # PCE / Core PCE
    "FOMC_RATE_DECISION",
    "FOMC_PRESS_CONFERENCE",
    "FED_APPROVED",        # explicitly approved Powell/Fed events
}


def _clear(reason: str) -> dict:
    return {"blocked": False, "event_name": None, "event_time_et": None,
            "event_date": None, "reason": reason}


def evaluate(now_et: datetime, events_path: str = EVENTS_PATH) -> dict:
    """Return the machine-readable event-gate block for this run.

    Blocked iff an approved event is dated today with a release time strictly
    after now. An event already released today does not block - fresh prices
    and Gold Rules V2 then decide. Unreadable list -> fail toward caution.
    """
    try:
        raw = json.load(open(events_path))
        events = raw["events"] if isinstance(raw, dict) else raw
        if not isinstance(events, list):
            raise ValueError("events is not a list")
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return {"blocked": True, "event_name": None, "event_time_et": None,
                "event_date": None,
                "reason": "Event list unreadable (%s) - blocking new positions" % exc}

    today = now_et.date().isoformat()
    now_t = now_et.time()

    ahead, released = [], False
    for e in events:
        if e.get("type") not in APPROVED_TYPES or e.get("date") != today:
            continue
        try:
            hh, mm = (int(x) for x in e["time_et"].split(":"))
            et = time(hh, mm)
        except (KeyError, ValueError):
            # A malformed approved-event entry for today is not something to
            # trade through - treat it as still ahead.
            ahead.append((time(23, 59), e))
            continue
        if et > now_t:
            ahead.append((et, e))
        else:
            released = True

    if ahead:
        et, e = min(ahead, key=lambda pair: pair[0])
        return {"blocked": True, "event_name": e.get("name", e["type"]),
                "event_time_et": e.get("time_et", et.strftime("%H:%M")),
                "event_date": today,
                "reason": "Approved major event still ahead in current session"}
    if released:
        return _clear("Approved event already released earlier today")
    return _clear("No approved event ahead")


def _self_check() -> None:
    import tempfile

    events = [
        {"name": "CPI", "type": "CPI", "date": "2026-09-10", "time_et": "08:30"},
        {"name": "FOMC Rate Decision", "type": "FOMC_RATE_DECISION",
         "date": "2026-09-17", "time_et": "14:00"},
        {"name": "FOMC Press Conference", "type": "FOMC_PRESS_CONFERENCE",
         "date": "2026-09-17", "time_et": "14:30"},
        {"name": "Retail Sales", "type": "RETAIL_SALES",
         "date": "2026-09-17", "time_et": "09:00"},  # not approved
    ]
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    json.dump({"events": events}, open(path, "w"))

    def at(s):
        return datetime.fromisoformat(s).replace(tzinfo=ET)

    # event ahead -> blocked, names the earliest approved one
    r = evaluate(at("2026-09-17T13:05"), path)
    assert r["blocked"] and r["event_time_et"] == "14:00", r

    # same event now past -> not blocked
    r = evaluate(at("2026-09-17T14:45"), path)
    assert not r["blocked"] and "already released" in r["reason"], r

    # no approved event that day -> not blocked
    r = evaluate(at("2026-09-11T09:35"), path)
    assert not r["blocked"] and r["reason"] == "No approved event ahead", r

    # CPI morning: run before 08:30 -> blocked; after -> clear
    assert evaluate(at("2026-09-10T08:00"), path)["blocked"]
    assert not evaluate(at("2026-09-10T09:35"), path)["blocked"]

    # 09-17 has an unapproved 09:00 event plus approved 14:00/14:30. At 08:00
    # only the approved ones may block, and the earliest approved is 14:00.
    r = evaluate(at("2026-09-17T08:00"), path)
    assert r["blocked"] and r["event_time_et"] == "14:00", r

    # with ONLY the unapproved event ahead -> not blocked
    json.dump({"events": [events[3]]}, open(path, "w"))
    assert not evaluate(at("2026-09-17T08:00"), path)["blocked"]
    json.dump({"events": events}, open(path, "w"))

    # missing file -> fail toward caution
    assert evaluate(at("2026-09-17T13:05"), path + ".nope")["blocked"]

    # unparseable file -> fail toward caution
    open(path, "w").write("{ not json")
    assert evaluate(at("2026-09-17T13:05"), path)["blocked"]

    os.unlink(path)
    print("event_gate self-check OK")


if __name__ == "__main__":
    _self_check()
