# Gold Rules V2-validation - same-timestamp validation

Window `2026-02-23` .. `2026-08-24`, **127 sessions**. Sampled at **09:35 and 13:05 ET** on Alpaca SIP minute bars, using the live convention `latest available price / previous regular-session close - 1`. Rules imported from `regime.py` (`rules_version: V2-validation`), not reimplemented.

## Signal frequency

| Signal | Unique days |
|---|---:|
| `STAND_DOWN` (rule 1) | 3 |
| fear-only `RISK_OFF` (rule 2) | 5 |
| divergence downgrades (rule 3) | 9 |
| strong-dollar downgrades (rule 4) | 0 |
| weak-dollar notes (context only) | 18 |
| sessions with 2+ executable rules overlapping | 0 |
| degraded (a secondary input unreadable) | 0 |

| Intraday | Sessions |
|---|---:|
| 09:35 reads that were not `RISK_ON` | 7 |
| 13:05 measured **more** cautious than 09:35 | 10 |
| 13:05 measured calmer but stayed latched | 5 |
| early closes (no 13:05 sample exists) | 0 |

## Regime distribution

`effective` is the state the day actually traded under: the 13:05 read where one exists, otherwise the morning.

| State | 09:35 | 13:05 | effective | % of sessions |
|---|---:|---:|---:|---:|
| `RISK_ON` | 120 | 112 | 112 | 88.2% |
| `NEUTRAL` | 4 | 7 | 7 | 5.5% |
| `RISK_OFF` | 3 | 5 | 5 | 3.9% |
| `STAND_DOWN` | 0 | 3 | 3 | 2.4% |
| `HALTED` | 0 | 0 | 0 | 0.0% |

## Trading impact (SPY proxies)

No fill history and no cheap historical option chain exist for this window, so option-level P&L by regime is **not** reported - the handoff scopes that "where supported". These are the honest substitutes: how SPY actually behaved after each call, measured from the 09:35 sample price.

| State | days | 09:35 -> same-day close | 09:35 -> next close | max adverse intraday | permitted open risk |
|---|---:|---|---|---|---:|
| `RISK_ON` | 112 | +0.07% avg, -1.95% worst | +0.16% avg, -2.62% worst | -0.49% avg, -2.91% worst | $2,500 |
| `NEUTRAL` | 7 | -0.33% avg, -1.43% worst | -0.18% avg, -0.91% worst | -0.74% avg, -1.91% worst | $1,500 |
| `RISK_OFF` | 5 | +0.26% avg, -0.51% worst | +0.21% avg, -0.18% worst | -0.31% avg, -1.14% worst | $1,000 |
| `STAND_DOWN` | 3 | -0.57% avg, -1.00% worst | -0.15% avg, -1.26% worst | -0.85% avg, -1.29% worst | $0 |
| `HALTED` | 0 | n/a | n/a | n/a | $0 |

**Stand-down days, split by what the tape did next.** A short put spread is hurt when SPY falls, so:

- losing put spreads plausibly avoided: **2** of 3 (SPY fell after the call)
- profitable opportunities plausibly skipped: **1** (SPY rose or was flat)

## Verdict against the handoff's sanity ranges

These are validation ranges, not optimisation targets.

| Check | Observed | Target | |
|---|---:|---|---|
| unique `STAND_DOWN` days | 3 | 2-4 | PASS |
| fear-only `RISK_OFF` days | 5 | 3-6 | PASS |
| total days at `RISK_OFF` or worse | 8 | 0-10 | PASS |

A **FLAG** is not permission to move a threshold. Per handoff section 12, return the evidence first; any V3 is documented as `V2 result -> observed failure -> human-approved amendment`.

## Not covered here

- **Event-calendar gate** (handoff section 9) is not implemented. The handoff forbids inventing a blackout window without sign-off, so it awaits a decision on the window and is deliberately not another regime vote.
- **Option-level P&L, win rate and realised open risk** need fills that do not exist yet. The SPY proxies above are what this window can honestly support.

## Every session where something fired

| Date | 09:35 | 13:05 | effective | why |
|---|---|---|---|---|
| 2026-02-23 | RISK_ON | STAND_DOWN | `STAND_DOWN` | stand-down: GLD +2.20% with SPY -1.00% |
| 2026-02-26 | NEUTRAL | NEUTRAL | `NEUTRAL` | measured RISK_ON; permissions held at NEUTRAL from earlier today |
| 2026-02-27 | RISK_ON | RISK_OFF | `RISK_OFF` | fear rising: gold bid while stocks fell |
| 2026-03-02 | RISK_OFF | RISK_OFF | `RISK_OFF` | divergence: GLD-GDX 3.17 pp, miners not confirming. measured NEUTRAL; permissions held at RISK_OFF from earlier today |
| 2026-03-04 | RISK_ON | NEUTRAL | `NEUTRAL` | divergence: GLD-GDX 1.03 pp, miners not confirming |
| 2026-03-06 | NEUTRAL | STAND_DOWN | `STAND_DOWN` | stand-down: GLD +1.38% with SPY -1.07% |
| 2026-03-13 | NEUTRAL | NEUTRAL | `NEUTRAL` | measured RISK_ON; permissions held at NEUTRAL from earlier today |
| 2026-03-27 | RISK_OFF | STAND_DOWN | `STAND_DOWN` | stand-down: GLD +3.39% with SPY -1.06% |
| 2026-05-01 | RISK_ON | NEUTRAL | `NEUTRAL` | divergence: GLD-GDX 1.37 pp, miners not confirming |
| 2026-05-29 | NEUTRAL | NEUTRAL | `NEUTRAL` | measured RISK_ON; permissions held at NEUTRAL from earlier today |
| 2026-07-01 | RISK_OFF | RISK_OFF | `RISK_OFF` | measured RISK_ON; permissions held at RISK_OFF from earlier today |
| 2026-07-02 | RISK_ON | RISK_OFF | `RISK_OFF` | fear rising: gold bid while stocks fell. context: dollar weak (UUP -0.60%) - no permission change |
| 2026-07-06 | RISK_ON | NEUTRAL | `NEUTRAL` | divergence: GLD-GDX 0.97 pp, miners not confirming |
| 2026-07-17 | RISK_ON | RISK_OFF | `RISK_OFF` | fear rising: gold bid while stocks fell |
| 2026-07-29 | RISK_ON | NEUTRAL | `NEUTRAL` | divergence: GLD-GDX 1.64 pp, miners not confirming |
