# Seat: `macro-calendar` — is a known shock scheduled before expiry?

**Status: needs sourcing. Read the boundary section below before building — this seat
overlaps a gate the teammate owns.**

## The boundary — read this first

The teammate has already specified a **deterministic** event gate and stated the constraint
in both `docs/regime.md` and the V2 handoff §9:

> The event calendar is **not** another Gold Regime vote.

That gate is not built and is explicitly *report-only pending sign-off* — the source, the
covered events, the blackout window and the restriction are all unapproved
(`docs/regime.md`, "Separate event-calendar gate").

So this seat is constrained more tightly than the others:

| It may | It may not |
|---|---|
| Describe event proximity as evidence | Block a trade |
| Push the panel toward `NO_TRADE` | Be the mechanism that prevents one |
| Report which event, when, relative to which expiry | Define or apply a blackout window |
| Say the market appears to be pricing an event | Change any threshold or budget |

**When the teammate's deterministic gate ships, it runs before the panel and this seat
becomes advisory commentary on a decision already made.** Build it so that is a
non-event — the seat has no authority to lose.

If in doubt: this seat is a *witness*, not a *judge*.

## Question this seat answers

**Is a scheduled US macro or Fed event due before any legal expiry, and how close is it?**

A 1–3 DTE put credit spread that straddles a CPI print is a different trade from the same
spread on a quiet Wednesday, even when every deterministic check passes identically.

## Inputs — exactly these, nothing else

| Field | Source |
|---|---|
| `expiries` | `envelope["expiries"]` — the legal DTE window |
| `now_et` | run timestamp |
| `events` | the event list, below |

Each event: `{"date": "2026-09-02", "time_et": "08:30", "name": "CPI", "tier": 1}`.

Tiers: **1** = CPI, PCE, NFP/Employment Situation, FOMC decision, Powell press conference.
**2** = other approved high-impact US macro releases. Only the events named in the handoff
§9 list, plus anything explicitly approved. Nothing invented.

**Not given:** prices, the chain, candidates, regime, account, other seats, its own
calibration. This seat's whole job is the calendar, and mixing price data in would let it
form a market view it has no business forming.

## Source — decide before building

For the six-day competition window (2026-08-28 to 09-04), a **hand-maintained JSON file** of
known event dates is sufficient, correct, and carries no API risk. Six days of US macro
releases can be enumerated by hand from the BLS, BEA and Federal Reserve calendars in
minutes, and verified by a second person.

Ship that. Record in the file itself: who compiled it, from which primary sources, and on
what date. A scraped calendar that silently goes stale mid-competition is strictly worse than
a checked-in list somebody signed.

A real source (FRED release calendar, or the Fed's own schedule) is future work, and belongs
with the teammate's deterministic gate rather than here.

## Method

1. For each legal expiry, list tier-1 and tier-2 events falling between `now_et` and that
   expiry's close.
2. If there are none: `ABSTAIN`. This will be most days.
3. If there are: report the event, its scheduled time, and which expiries it precedes.
   Conviction rises with tier and with how much of the spread's life sits after the event.
4. An event landing **after** every legal expiry is worth one line and no stance change.

## Output

Standard stance object (`PANEL.md`). `preferred_candidate_index` is **always `null`** — this
seat has no candidate-level inputs and cannot prefer one strike over another. If it ever
returns a non-null index, that is a bug.

Its `evidence` entries cite the event list: `"event: CPI 2026-09-02 08:30 ET, before expiry 2026-09-03"`.

## Must refuse to opine on

- **What the event will show, or how the market will react.** It knows a date, not an
  outcome. Any sentence predicting a print or a reaction is out of domain.
- **Option pricing.** If a skew is steep, that is the `volatility` seat's observation.
- **Anything unscheduled.** Geopolitics, headlines, breaking news. This seat reads a
  calendar. Unscheduled risk is not on a calendar and pretending otherwise is the failure
  mode below.
- **Defining a blackout window.** Not approved. Not this seat's.

## `ABSTAIN` when

- No tier-1 or tier-2 event falls before any legal expiry. **Expected on most days — this is
  correct behaviour, not a bug.** Do not add a fallback that makes this seat say something
  anyway.
- The event list is missing, empty or stale. A stale calendar must abstain loudly, never
  assert "no events scheduled" — absence of data is not evidence of a quiet week.
