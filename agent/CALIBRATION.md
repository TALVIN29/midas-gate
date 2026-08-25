# Calibration — how a seat earns credibility

## The problem this solves

Talvin's requirement: *"the agent must have the learning curve so that they know what makes
this win a win and what makes it a loss and why."*

The obstacle is arithmetic. The competition is 2026-08-28 to 09-04, two runs a day — about
**12 live runs**. You cannot learn per-seat reliability from 12 samples, and any claim built
on 12 samples can be taken apart by one question from a judge who knows statistics.

So calibration is **seeded offline from six months of cached bars, then updated live**. The
live week refines a prior; it does not create one.

## What "correct" means for a seat

A put credit spread wins when SPY stays above the short strike for the life of the spread.
The backtest has no fills, so seat stances are scored against the tape instead.

**Definition.** For a stance taken at sample time `t` on session `d`:

```
horizon      = close of session d+1            (spreads are 1-3 DTE; 2 sessions is the modal life)
breach_pct   = (min SPY low from t to horizon) / SPY(t) - 1, as a percentage
BREACHED     = breach_pct <= -DISTANCE_FLOOR_PCT
```

| Stance | Correct when |
|---|---|
| `FAVOUR` | not `BREACHED` |
| `AGAINST` | `BREACHED` |
| `NEUTRAL` | never scored — excluded from hit rate, counted in `n_neutral` |
| `ABSTAIN` | never scored — counted in `n_abstain` |

**`DISTANCE_FLOOR_PCT` is an assumption and must be stated as one, not buried.** Set it to
the regime's own `min_strike_distance_pct` for that session — 1.0 / 1.5 / 2.5 — so the seat
is scored against the distance it would actually have been trading at. Record the value used
in every calibration entry, so a later change to the sizing table does not silently
invalidate the history.

This scoring rule is a proxy. It measures whether the seat's directional read survived the
holding period, not whether a specific spread made money. Say so on the dashboard.

## Seeding from the backtest

Inputs already on disk: `data/minute_*.csv` and `data/daily_*.csv`, 127 sessions,
2026-02-23 to 2026-08-24. `backtest_report.md` lists the 15 sessions where a rule fired.

**Procedure.**

1. For each sampled session, at 09:35 ET, assemble each seat's inputs from cached bars
   exactly as `skill.md` specifies.
2. Call each seat. Record the stance object.
3. Score it by the rule above.
4. Aggregate per seat: overall, and split by the regime that session was in.

**Sampling.** All 127 sessions if the model budget allows (≈508 seat calls). Otherwise a
stratified sample: **all 15 sessions where something fired** — they are the informative ones
and they are already enumerated in `backtest_report.md` — plus a random draw of calm
sessions, seeded for reproducibility. Record the seed and the exact session list.

**The `volatility` and `positioning` seats cannot be fully seeded.** Historical option chains
are not available on the free feed, so IV and greeks for past sessions do not exist. Options,
in order of honesty:

- Seed those seats on the inputs that *do* exist historically — SPY realised volatility over
  trailing windows, and the VIXY/VXX term structure — and mark the record
  `partial: true` with a note naming the missing inputs.
- Or ship them with `n: 0` and let them earn their record live.

Do not synthesise historical option prices to fill the gap. A modelled IV scored as if it
were real is exactly the flattering wrong number the backtest doc warns about
(`docs/backtest.md`).

## The record

Stored in `site/state.json` under `learning.seat_calibration`, written by `audit.py`:

```json
{
  "volatility": {
    "n": 40, "hit_rate": 0.62, "n_neutral": 6, "n_abstain": 2,
    "partial": true, "missing_inputs": ["iv", "delta"],
    "distance_floor_used": "per-session regime floor",
    "by_regime": {
      "RISK_ON":  {"n": 31, "hit_rate": 0.65},
      "NEUTRAL":  {"n": 6,  "hit_rate": 0.50},
      "RISK_OFF": {"n": 3,  "hit_rate": 0.33}
    },
    "seeded_from": "backtest 2026-02-23..2026-08-24, stratified, seed 20260825",
    "live_runs_included": 4
  }
}
```

**`n` is mandatory and may never be displayed without it.** `hit_rate: 0.62` is a claim;
`hit_rate: 0.62, n: 40` is evidence; `hit_rate: 1.00, n: 2` is noise and must look like
noise on the dashboard.

## Live update

After `audit.classify` lands an outcome for a run (`audit.py:110`), each seat's stance from
that run is scored by the same rule — the tape is now known — and folded into the record.
`live_runs_included` increments.

Backtest and live entries use one identical scoring rule. If they ever diverge, the record
is measuring two different things and is worthless.

## What the panel is shown, and what it must not do

The synthesis call receives the scorecard as **evidence**:

> `volatility` has been right 62% of the time (n=40); in RISK_OFF specifically, 33% (n=3).

Nothing auto-adjusts. Weights are not recomputed. A seat that has been wrong is *told to the
panel*, and the synthesis step may reason about it in prose.

This is deliberate and it is the same boundary the rest of the system holds:
`audit.py:135` — *"Bounded learning memory. Preferences only — never permissions."* A panel
that silently reweights its own voices based on its own scorecard is a decision rule that
modifies itself, which is both harder to audit and easy to overfit on n=12.

**Individual seats never see their own or anyone's calibration.** Only synthesis does. A seat
told it has been unreliable will hedge, which corrupts the very stance being measured.

## What this does not claim

Write this on the dashboard, not just here:

- 12 live runs is not a sample. The live portion of every figure is labelled with its `n`.
- The scoring rule is a directional proxy, not realised P&L.
- Seats seeded `partial` are marked as such wherever their number appears.
