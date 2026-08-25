# `macro-calendar` — memory schema

**Schema only. The record lives in `site/state.json` under
`learning.seat_calibration.macro-calendar`.** Nothing writes to this folder at runtime.

## What it remembers

```json
{
  "n": 6, "hit_rate": 0.67, "n_neutral": 0, "n_abstain": 121,
  "by_regime": { "RISK_ON": {"n": 4, "hit_rate": 0.75}, "...": {} },

  "abstain_rate": 0.95,
  "by_tier": { "1": {"n": 5, "hit_rate": 0.60}, "2": {"n": 1, "hit_rate": 1.00} },
  "fabrication_flags": 0,
  "calendar_provenance": "hand-compiled 2026-08-26 by <name> from BLS/BEA/Federal Reserve calendars"
}
```

**This seat will have the smallest `n` of the four, by design.** Six months contains maybe
20–30 sessions with a tier-1 event before a 1–3 DTE expiry. Its record will read `n: 6` and
that is the honest number, not a shortfall to be padded.

| Counter | Why it exists |
|---|---|
| `abstain_rate` | Expected around **0.90 or higher**. If this drops, the seat is drifting toward `NEUTRAL` on empty calendars — the failure mode named in `soul.md`. This is the number to watch. |
| `by_tier` | Whether tier-1 events actually predict breaches. If tier-1 scores no better than tier-2, the tiering is decoration. |
| `fabrication_flags` | Count of runs where an `evidence` entry could not be traced to an event-list field. **Should be zero. A non-zero value is a defect, not a statistic** — surface it as an error, not a percentage. |
| `calendar_provenance` | Who compiled the event list, from which primary sources, when. Carried in the record so a stale calendar is visible in the audit trail rather than discovered afterwards. |

## What it may never remember

- Anything about what past events *showed*, or how the market reacted. That is the analyst
  drift in `soul.md`, and a memory of it would make the drift permanent and self-reinforcing.
- Any blackout window, learned or inferred. Not approved, not this seat's, and a memory
  encoding "we should stand down 24h before CPI" is an unapproved rule wearing a memory's
  clothes.
- Prices, candidates, regimes, or another seat's record.

## Update rule

Appended by `audit.py` after `classify`, using the single scoring function in
`CALIBRATION.md`. `ABSTAIN` runs increment `n_abstain` and the abstain rate but are never
scored for accuracy.

## How it re-enters the system

Shown to the **synthesis step only**, as evidence. The seat never sees its own record.
Nothing auto-adjusts.

Two figures deserve to reach the dashboard directly rather than only the synthesis prompt:
`abstain_rate`, because a seat that knows when to stay silent is the most defensible thing in
this design; and `fabrication_flags`, because it should read `0` and a reader should be able
to check that.
