# `cross-asset` — memory schema

**Schema only. The record lives in `site/state.json` under
`learning.seat_calibration.cross-asset`.** Nothing writes to this folder at runtime.

## What it remembers

Standard calibration block (`CALIBRATION.md`), plus counters that test this seat's two named
failure modes:

```json
{
  "n": 127, "hit_rate": 0.58, "n_neutral": 11, "n_abstain": 64,
  "by_regime": {
    "RISK_ON":    {"n": 112, "hit_rate": 0.55},
    "NEUTRAL":    {"n": 7,   "hit_rate": 0.71},
    "RISK_OFF":   {"n": 5,   "hit_rate": 0.80},
    "STAND_DOWN": {"n": 3,   "hit_rate": 1.00}
  },

  "abstain_rate": 0.50,
  "tlt_divergence_calls": {"n": 6, "hit_rate": 0.83},
  "near_miss_calls": {"n": 14, "hit_rate": 0.50}
}
```

| Counter | Filled when | Why |
|---|---|---|
| `abstain_rate` | every session | Directly measures the "sees stories in noise" failure. Expected around 0.5 or higher. Materially lower means it is over-reading quiet days. |
| `tlt_divergence_calls` | the stance cited `TLT` moving with `SPY` rather than against it | This is the seat's unique claim — the observation no other part of the system can make. If it does not score well, the seat's main justification is weak and that should be visible. |
| `near_miss_calls` | the stance cited a signal within 0.15pp of a rule threshold without crossing it | Tests whether reading between the thresholds adds information or just noise. |

This seat is expected to have the **largest and most complete backtest sample** of the four,
because all five signals exist for every cached session. It carries no `partial` flag.

## The one that matters most

`by_regime` for `RISK_OFF` and `STAND_DOWN` will have tiny `n` — 5 and 3 in the six-month
window. Those are the sessions where this seat matters most and where it has least evidence.

**Display those cells with their `n` adjacent, always.** `hit_rate: 1.00, n: 3` must not be
allowed to read as a strong result on a dashboard a judge is scanning.

## What it may never remember

- Any regime threshold, or any adjustment to one. Gold Rules V2 are frozen and human-owned.
  A memory that effectively encodes "the divergence rule should be 0.60 not 0.75" is a rule
  change wearing a memory's clothes.
- Option pricing or candidate history — never among its inputs.
- Another seat's record.

## Update rule

Appended by `audit.py` after `classify`, using the single scoring function in
`CALIBRATION.md`. Identical rule for backtest-seeded and live entries.

## How it re-enters the system

Shown to the **synthesis step only**, as evidence. The seat never sees its own record.
Nothing auto-adjusts.
