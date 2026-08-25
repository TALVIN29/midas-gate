# Midas Gate — Gold Rules V2 Validation Handoff for Talvin

## Status
**Gold Rules V2 is now frozen for validation.**

Do not optimise or change thresholds yet unless the same-timestamp backtest shows clearly unreasonable behaviour.

## 1. Gold Rules V2

### Stand-down
`GLD >= +1.00% AND SPY <= -1.00%`

Effect:
- `STAND_DOWN`
- `$0` new risk
- put spreads forbidden
- latched for the rest of the trading day
- 13:05 recovery does not restore permission

### Fear rising — RISK_OFF
`GLD >= +0.75% AND SPY <= -0.50%`

Effect:
- `RISK_OFF`
- maximum open risk `$1,000`
- trading remains possible at reduced size
- this is not the same as stand-down

### GLD/GDX divergence
`GLD - GDX >= 0.75 pp AND GLD >= +0.25% AND GDX <= 0%`

Effect:
- downgrade caution one level
- `RISK_ON -> NEUTRAL`
- `NEUTRAL -> RISK_OFF`

### Dollar modifier
Strong-dollar rule:
`UUP >= +0.30% AND GLD >= +0.50% AND SPY <= 0%`

Effect:
- upgrade caution one level

Weak-dollar rule:
`UUP <= -0.30%`

Effect:
- explanatory context only
- record in `signals` / `reason`
- no executable regime change

## 2. Sizing V2

| State | Maximum open risk |
|---|---:|
| `RISK_ON` | `$2,500` |
| `NEUTRAL` | `$1,500` |
| `RISK_OFF` | `$1,000` |
| `STAND_DOWN` | `$0` |

Do not ship the old `$10,000 / $5,000 / $0` structure.

The `$500` maximum loss per spread remains a hard deterministic cap unless the main spec explicitly changes it.

## 3. Measurement convention

Use the same rule in live trading and backtesting:

`return = latest available price / previous regular-session close - 1`

The final validation must use the actual system run times:
- `09:35 ET`
- `13:05 ET`

Close-to-close is only a proxy.

## 4. Evaluation order

Evaluate most-cautious-first:

1. `STAND_DOWN`
2. Fear rising -> `RISK_OFF`
3. Divergence downgrade
4. Strong-dollar downgrade
5. Otherwise `RISK_ON`

If rules overlap, the most cautious result wins.

## 5. Intraday one-way caution

More cautious intraday states apply immediately.

More aggressive intraday states do not loosen permission until the next trading day.

Examples:
- 09:35 `RISK_OFF`, 13:05 measured `RISK_ON` -> keep `RISK_OFF`
- 09:35 `STAND_DOWN`, 13:05 normalised -> remain `STAND_DOWN`

Record the calmer measurement for transparency, but do not apply it.

## 6. Close-to-close proxy already observed

Across 124 sessions:
- stand-down: `2`
- fear-only: `3`
- amended divergence: `5`
- amended dollar: `1`

These are only rough frequency checks.

## 7. Required same-timestamp backtest

Run a six-month validation at 09:35 ET and 13:05 ET.

Report at minimum:

### Signal frequency
- unique `STAND_DOWN` days
- fear-only `RISK_OFF` days
- divergence downgrades
- strong-dollar downgrades
- overlapping rules
- 09:35 signals
- 13:05 newly-more-cautious signals
- cases where 13:05 became calmer but the morning state stayed latched

### Regime distribution
- `RISK_ON`
- `NEUTRAL`
- `RISK_OFF`
- `STAND_DOWN`

### Trading impact
Where supported:
- win rate by regime
- average P&L by regime
- worst P&L by regime
- maximum adverse SPY move after each regime
- losing put spreads avoided by stand-down
- profitable opportunities skipped by stand-down
- maximum open risk actually reached under `$2,500 / $1,500 / $1,000 / $0`

## 8. Sanity-check targets

These are validation ranges, not optimisation targets.

### Stand-down
Rough target: about `2–4 unique days / six months`.

### Fear-only RISK_OFF
Rough target: about `3–6 unique days / six months`.

If same-timestamp sampling produces materially more than roughly `8–10 unique RISK_OFF days`, flag it for review before changing anything.

## 9. Separate event-calendar gate

Add a separate deterministic risk/execution gate for major scheduled US macro or Fed events occurring before spread expiry.

Examples:
- CPI
- PCE
- NFP / Employment Situation
- FOMC rate decision
- Powell press conference
- other explicitly approved high-impact US macro/Fed events

Important:
**The event calendar is not another Gold Regime vote.**

Do not invent an exact event blackout window without documenting the assumption or getting sign-off.

## 10. Documentation update

Update `docs/regime.md` to:

`Gold Rules V2 — frozen for validation`

Recommended machine-readable label:

`V2-validation`

Update old sizing to:

- `RISK_ON $2,500`
- `NEUTRAL $1,500`
- `RISK_OFF $1,000`
- `STAND_DOWN $0`

Make `RISK_OFF` and `STAND_DOWN` machine-distinguishable.

Example concept:

```json
{
  "regime": "RISK_OFF",
  "stand_down": false,
  "risk_budget_usd": 1000,
  "put_spreads_allowed": true
}
```

versus:

```json
{
  "regime": "RISK_OFF",
  "stand_down": true,
  "risk_budget_usd": 0,
  "put_spreads_allowed": false
}
```

The exact schema may differ, but downstream logic must not infer the difference from prose.

## 11. Do not do this now

Do not:
- tune thresholds repeatedly to improve historical P&L
- revert to V1 sizing
- make `RISK_OFF` equivalent to stand-down
- make weak UUP cancel a confirmed warning
- require GDX divergence for stand-down
- allow the strong-dollar modifier when SPY is clearly positive
- release a morning stand-down at 13:05
- turn the event calendar into another regime vote
- allow AI to override these rules

## 12. Decision after validation

If behaviour is reasonable:
- freeze `Gold Rules V2` for the hackathon
- proceed to implementation and failure testing

If behaviour is clearly unreasonable:
- return the evidence before changing thresholds
- document any V3 as `V2 result -> observed failure -> human-approved amendment`

## Final instruction

**Gold Rules V2 is frozen for validation, not optimisation.**

Next task:

`update docs/regime.md -> implement V2-validation -> run six-month 09:35/13:05 same-timestamp backtest -> report frequency + regime + P&L/risk impact -> do not change thresholds until review`
