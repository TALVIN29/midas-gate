# `volatility` — memory schema

**This file defines what the seat remembers. It is not where memory is stored.**
The record lives in `site/state.json` under `learning.seat_calibration.volatility`, written
by `audit.py`. Nothing writes to this folder at runtime.

## What it remembers

The standard calibration block (`CALIBRATION.md`), plus two seat-specific counters that exist
because this seat has a known, named failure mode worth measuring:

```json
{
  "n": 40, "hit_rate": 0.62, "n_neutral": 6, "n_abstain": 2,
  "partial": true, "missing_inputs": ["iv", "delta"],
  "by_regime": { "RISK_ON": {"n": 31, "hit_rate": 0.65}, "...": {} },

  "favour_on_rich_premium": {"n": 9, "hit_rate": 0.44},
  "against_on_wide_spread": {"n": 12, "hit_rate": 0.75}
}
```

| Counter | Filled when | Why it exists |
|---|---|---|
| `favour_on_rich_premium` | stance `FAVOUR` and the chosen candidate's `return_on_risk_pct` was in the top quartile of that session's list | Directly measures the failure mode in `soul.md`: does this seat like the days that hurt? If `hit_rate` here is materially below the seat's overall rate, the failure mode is real and the dashboard should say so. |
| `against_on_wide_spread` | stance `AGAINST` and the reason cited `short_spread` | Tests whether the liquidity prior earns its keep, or whether it is refusing tradeable candidates. |

## What it may never remember

- Any threshold. This seat does not learn that `short_spread > 0.13` is the new floor and
  then apply it. Thresholds are `gates.py`'s and `regime.py`'s, and this seat has no
  thresholds of its own to move.
- Anything about the account, P&L or position history — it never sees them, so it cannot
  remember them.
- Another seat's stances or record.

## Update rule

Appended by `audit.py` after `classify` lands the outcome, using the single scoring function
in `CALIBRATION.md`. Backtest-seeded and live entries are scored identically or the record
measures two different things.

Both seat-specific counters are derived from the stored stance object and the session's
candidate list — no extra state is kept beyond what the run record already holds.

## How it re-enters the system

**It does not re-enter this seat.** The seat never sees its own record; a seat told it has
been unreliable hedges, which corrupts the stance being measured (`CALIBRATION.md`).

The record is shown to the **synthesis step only**, as evidence, in prose. Nothing
auto-adjusts.
