# `event_gate.py` — the scheduled-event execution gate

> **In plain terms:** before every run it asks one question — is there a known
> big scheduled announcement (inflation, jobs, the Fed) still coming later today?
> If yes, it blocks opening any new position. It does not touch the gold regime.

## Purpose

The system sells 1–3 DTE short-premium spreads. A scheduled macro release — CPI,
the jobs report, PCE, an FOMC decision — is a binary event: the price can gap the
moment it lands. Selling premium into an unresolved binary is a bad trade no matter
how small the risk budget is, so the answer is to **not open**, not to open smaller.

This is deliberately separate from `regime.py`. The regime still describes what the
market is doing. The event gate answers a different question — *is now a bad time to
act on that read* — and the two are combined only at the envelope:

```
Market regime: RISK_ON
Scheduled-event gate: BLOCKED
Decision: NO_TRADE
```

## Where it sits

**After `regime.py`, before `gates.build_envelope`.**

```
state → data health → regime.py → event_gate.py → gates.py → agent.py → validator → execution → audit.py
```

It reads one local JSON file. No prices, no account, no network. Safe to run anytime.

## Inputs

| Input | Detail |
|---|---|
| `now_et` | The run's timestamp, ET. Supplied by `agent.run`. |
| `event_gate_events.json` | Hand-maintained approved-event list at the repo root. Human-approved edits only. This file is the *only* thing that defines the blackout. |

Each event entry: `{ "name", "type", "date": "YYYY-MM-DD", "time_et": "HH:MM" }`.
`type` must be one of the V1 approved set (`event_gate.APPROVED_TYPES`):
`CPI`, `NFP`, `PCE`, `FOMC_RATE_DECISION`, `FOMC_PRESS_CONFERENCE`, `FED_APPROVED`.
Anything else in the file is ignored. The list is **not** a generic economic calendar
and must not be widened without human sign-off (handoff §1).

## Output

A fixed-shape block, always returned:

```json
{
  "blocked": true,
  "event_name": "FOMC Rate Decision",
  "event_time_et": "14:00",
  "event_date": "2026-09-17",
  "reason": "Approved major event still ahead in current session"
}
```

When not blocked, `event_name` / `event_time_et` / `event_date` are `null` and `reason`
is either `"No approved event ahead"` or `"Approved event already released earlier today"`.

## Logic

1. Load the list. Keep entries whose `type` is approved and whose `date` is today.
2. Of those, any with `time_et` **strictly after** `now_et` → **blocked**; report the
   earliest one.
3. An approved event today whose time has passed → not blocked (Case A: the release has
   already happened; fresh prices + Gold Rules V2 decide).
4. No approved event today, or only past ones → not blocked.
5. File missing, unparseable, or a today-entry with a malformed `time_et` → **blocked**
   (fail toward caution).

Strict `>` comparison, no settle buffer: standard runs are 09:35 / 13:05 ET and real
releases are 08:30 / 14:00 ET, so the boundary case is not a live concern.

## How the block takes effect

`agent.run` passes the block to `gates.build_envelope(..., event_block=...)`. As
ordered check 5.5 — after the clock/calendar checks, before regime permissions —
a blocked block returns `refuse("NO_TRADE", ...)` with the event block attached as
`event_gate`. The envelope is empty; `agent.run` returns a `NO_TRADE` proposal; the AI
is never called. `audit.build_state` carries `event_gate` into `state["envelope"]` and
into `state["runs"][0]["event_gate"]`, so the dashboard can show *why* it was `NO_TRADE`
without parsing prose.

## What it must never do

Rewrite the regime, change any Gold Rules V2 threshold, change a risk budget or a
strike-distance minimum, or invent an event or a blackout policy not in the JSON. It
only ever subtracts permission.

## Verification

`python event_gate.py` runs the self-checks: event ahead → blocked; same event past →
clear; no event that day → clear; unapproved type ahead → clear; missing file → blocked;
unparseable file → blocked; two events ahead → earliest reported.
