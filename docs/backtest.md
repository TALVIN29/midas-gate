# `backtest.py` — evidence, and the slow learning loop

> **In plain terms:** it replays about six months of real market history and asks "if we
> had run these exact rules every day, what would have happened, and did the gold overlay
> actually help?" That answer goes in the write-up — and it is the only route by which the
> regime rules are ever allowed to change.

> **What changed since v1** ([appendix/backtest.md](../appendix/backtest.md)): the backtest is
> no longer only evidence for a claim. It is now the **slow learning loop** — the one
> sanctioned path from "the rules look wrong" to "the rules are different", with a human in
> the middle. Added: the V1-frozen-before-tuning discipline, per-regime reporting, the
> stand-down trade-off analysis, and the explicit rule that the agent may propose a change
> but may never deploy one. Stage 4 in `BUILD_PLAN.md` — built only if time allows.

## Purpose

The project rests on one claim: selling defined-risk credit spreads wins roughly 75–80% of
the time, because time decay pays us regardless of direction.

Five and a half trading days is not enough to demonstrate that. We might place eight
trades. Eight trades prove nothing either way — a 100% win rate over eight trades is luck,
and so is a 50% one.

So we test it on history instead. Six months of real prices, the same rules the live system
uses, and we count. That produces a number we can defend.

It has a second job the handoff added. Structural changes to the strategy — a gold
threshold that keeps missing, a stand-down rule that costs more than it saves — must not
happen because a losing trade made someone uncomfortable on Tuesday. They happen here, with
evidence, reviewed by a human, and land as a version-controlled change.

## Where it sits

**Outside the live chain entirely.** It never runs on the schedule, never touches the
account, and cannot place an order.

```
FAST LOOP  (during the competition, automatic)
  audit.py → outcome class → lesson → next decision's ranking

SLOW LOOP  (offline, human-governed)
  live outcomes + history → backtest.py → proposed change
                                              ↓
                                        human review
                                              ↓
                                    accepted → version-controlled V2
```

Run by hand, and its output is quoted in `WRITEUP.md` and the slides. If it were deleted
after the numbers were recorded, nothing would break.

Starting point: adapt `alpacahq/alpaca-skills` → `alpaca-trading-backtest` rather than
writing a backtester from scratch. A hand-rolled backtester is a well-known way to produce
a flattering wrong number.

## Inputs

| Input | Detail |
|---|---|
| SPY daily prices | About 6 months, via `alpaca-py` |
| `GLD`, `GDX`, `UUP`, `TLT` | Same window, to replay the regime rules |
| The live rules | **Imported** from `regime.py` and `gates.py`. Never re-typed |
| `rules_version` | Which threshold set is being tested — V1, or a proposed V2 |
| Live outcomes to date | From `state.json`, once the competition has started |
| `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` | Environment variables |

Importing the real rules rather than restating them is the single most important choice
here. A backtest of a slightly different strategy than the one that actually trades is
worse than no backtest, because it produces a confident number about the wrong thing.

The same applies to the measurement convention: `latest price / previous regular-session
close − 1`, identical to [regime.md](regime.md). A backtest that uses completed daily
candles is testing a system that can see the future by several hours.

## The V1 discipline

This is the part that keeps the exercise honest:

1. Record the teammate's thresholds as **V1, before running anything.** They are already
   recorded — in [regime.md](regime.md) and in `BUILD_PLAN.md`, dated and labelled.
2. Backtest V1 over the historical window.
3. Measure performance **by regime**, not just in aggregate.
4. Identify obvious failure modes.
5. If — and only if — a failure is clear and explainable, write **one** documented V2, with
   the reasoning stated before the result is known.
6. Keep the V1 results alongside V2 forever. Both go in the write-up.

**Do not continuously re-tune thresholds until the historical result looks attractive.**
That is not analysis, it is fitting the past. Over a window this short it would also be
fitting noise. One documented revision, or none.

## Outputs

A short report, and the numbers quoted in `WRITEUP.md`:

**Strategy level**

- Number of trades, win rate, average P&L per trade, worst single loss.
- Maximum drawdown, and how often the −2% daily halt would have triggered.

**Per regime** — the whole point of the overlay:

| Metric | RISK_ON | NEUTRAL | RISK_OFF |
|---|---|---|---|
| Days classified | | | |
| Win rate | | | |
| Average P&L | | | |
| Worst result | | | |
| Max adverse SPY move after classification | | | |

**Stand-down trade-off** — the honest test of the most valuable rule:

- Losing put spreads the stand-down rule **avoided**.
- Winning opportunities it **skipped**.

Both numbers are published, whichever way they fall. A stand-down rule that avoided four
losses and skipped nine winners is a rule the teammate needs to see, not one to quietly
drop from the report.

The objective is **not** maximum win rate. The question is whether the gold overlay reduces
downside in a useful way. A rule that trims the worst days while costing a little upside is
a good rule for a system whose failure mode is a −4% halt.

## User experience flow

**Before the competition — establishing the claim.**

1. Talvin runs `python backtest.py --rules V1` once, by hand, in the days before Aug 28.
2. It pulls six months of prices, replays the regime rules day by day, and simulates the
   spreads the envelope would have permitted.
3. It prints the tables above and writes them to a file.
4. The headline number goes into `WRITEUP.md`: not "credit spreads usually win" but "over
   the last six months, these rules produced N trades, an X% win rate, and the stand-down
   rule avoided Y losses at a cost of Z skipped winners."
5. That is the difference between a write-up that asserts an edge and one that shows it.

**After the competition, or mid-week — a regime miss.**

1. `audit.py` classified two runs as `REGIME_MISS`: the system read `RISK_ON` on a day that
   turned sharply against it.
2. The fast loop does nothing with that. It is explicitly not allowed to touch a threshold.
3. Talvin runs the backtest against those specific dates and looks at the per-regime table.
4. If the pattern holds historically — say, `RISK_ON` days with a rising dollar behaving
   like `NEUTRAL` days — that becomes a written proposal: what to change, why, and what the
   V1 numbers were.
5. The teammate, who owns the gold rules, accepts or rejects it.
6. If accepted, it lands as a commit with a new `rules_version`, and every subsequent
   dashboard entry carries that version. Nothing is retroactively relabelled.
7. Mid-competition, the honest default is to **not** change anything: five days is not
   enough evidence to redefine an envelope. The proposal can be written up and left for the
   write-up as future work — which reads better than a rule changed on three data points.

## Failure modes

| What goes wrong | What happens |
|---|---|
| History unavailable for a fund | Report the gap. Do not silently drop the rule that used it — a backtest with a missing input is testing different rules |
| Option prices unavailable historically | Simulate the spread from the underlying with a stated pricing assumption, and label every result as modelled. Never present a modelled fill as a real one |
| The result is unflattering | Publish it. An honest 62% is evidence; an unverifiable 80% is a claim |
| The backtest disagrees with live results | Say so, and say by how much. Five days of live data does not overturn six months, and six months does not explain away five days |
| Tempted to re-tune | One documented V2, or none. The rule exists precisely because the temptation is strongest when the number is close |

## Verification

```
python backtest.py --self-test
```

`assert`-based checks against hand-made price series, no market needed:

- The regime classifier used in the backtest is the **imported** one from `regime.py` —
  asserted by identity, not by comparing outputs.
- The measurement convention matches `regime.py` exactly on a shared fixture.
- A hand-made fear day classifies `RISK_OFF` in the backtest and in live logic identically.
- The stand-down counters increment correctly on a constructed day that triggers it.
- Per-regime day counts sum to the total number of trading days in the window.
- A window with a deliberately missing fund reports the gap rather than silently producing
  a number.

Then, on the real run: the number of `RISK_OFF` days over six months should be a small
minority. If the rules classify half the market history as fear, the thresholds are wrong
and no amount of P&L arithmetic will fix that.

## Open questions

1. How are historical option prices handled? If real historical chains are unavailable on
   the free plan, spreads must be modelled from the underlying — which weakens the claim
   and must be stated plainly wherever the number is quoted.
2. Six months, or twelve? Six covers a reasonable mix of conditions and keeps the run
   short. Twelve is more evidence but risks including a market regime that no longer
   resembles today's. `ASSUMPTION:` six, stated as a limitation.
3. Should the backtest also replay the learning loop? Interesting, and almost certainly
   overfitting dressed up as validation. `ASSUMPTION:` no — backtest the rules, not the
   preferences.
