# `backtest.py` — evidence the strategy works

> **In plain terms:** it replays the last six months of real market history and asks
> "if we had run this exact strategy every day, how often would we have won?" That
> number goes in the write-up.

## Purpose

The whole project rests on one claim: selling defined-risk credit spreads wins
roughly 75–80% of the time, because time decay pays us regardless of which way the
market goes.

Four trading days is not enough to demonstrate that. We might place six trades. Six
trades prove nothing either way — a 100% win rate over six trades is luck, and so is
a 50% one.

So we test it on history instead. Six months of real SPY prices, the same rules the
live system uses, and we count. That produces a number we can defend.

This file changes nothing about how the live system trades. It exists purely as
evidence, and it is the difference between a write-up that asserts an edge and one
that shows it. PLAN.md is explicit that this is evidence, not decoration.

## Where it sits

**Outside the chain entirely.** It never runs on the schedule and never touches the
account.

It is run by hand, once, before the competition, and its output is quoted in
`WRITEUP.md` and in the slides. If it were deleted after the number was recorded,
nothing would break.

Starting point: adapt `alpacahq/alpaca-skills` → `alpaca-trading-backtest` rather than
writing a backtester from scratch. A hand-rolled backtester is a well-known way to
produce a flattering wrong number.

## Inputs

| Input | Detail |
|---|---|
| SPY daily prices | About 6 months, via `alpaca-py` |
| Gold-related prices | `GLD`, `GDX`, `UUP` over the same window, to replay the regime rules |
| The live rules | Imported from `regime.py` and `gates.py`. Not re-typed |
| `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` | Environment variables |

Importing the real rules rather than restating them is the single most important
choice here. A backtest of a slightly different strategy than the one that actually
trades is worse than no backtest, because it produces a confident number about the
wrong thing.

## Outputs

Printed to the terminal and saved as `backtest_results.json`:

```json
{
  "period": "2026-02-20 to 2026-08-20",
  "trades": 118,
  "wins": 92,
  "losses": 26,
  "win_rate_pct": 78.0,
  "avg_win_usd": 54.20,
  "avg_loss_usd": -287.40,
  "total_pnl_usd": 2511.00,
  "max_drawdown_pct": 3.1,
  "worst_day_usd": -862.00,
  "by_regime": {
    "RISK_ON":  {"trades": 61, "win_rate_pct": 82.0},
    "NEUTRAL":  {"trades": 44, "win_rate_pct": 75.0},
    "RISK_OFF": {"trades": 13, "win_rate_pct": 69.2}
  }
}
```

Read that table honestly, because it is the interesting part. We win about four times
out of five, but the average loss is roughly five times the average win. **The
strategy makes money by being right often, not by being right big — and a run of bad
luck genuinely hurts.** Saying so plainly in the write-up is more persuasive than the
win rate alone, and a judge who trades will spot it immediately if we do not.

The `by_regime` split is the part that tests the teammate's contribution
specifically. If the gold rules add nothing, the three win rates will look the same,
and that is worth knowing before we build the presentation around them.

## Logic

1. Pull daily prices for SPY and the three gold-related funds.
2. Step through each historical trading day in order.
3. For that day, run the real `regime.py` rules on the prices as they stood — using
   only data that existed at the time.
4. Run the real `gates.py` limits against a simulated account.
5. If a trade was permitted, pick the strike by percentage distance, exactly as the
   live system does.
6. Estimate the premium with `bs.py`, since historical option prices are not available
   on the free plan.
7. Jump forward to expiry and settle: if SPY stayed on the right side of the short
   strike, we keep the premium. If not, we lose the gap between strikes, less the
   premium.
8. Record the result and continue.
9. Report totals, overall and split by regime.

Step 3 is where backtests usually go wrong. Using information the strategy could not
have had at the time produces a beautiful result and a worthless one.

Step 6 is an honest weakness and must be labelled as such in the write-up: we are
estimating what the premium would have been, not reading what it was. The estimate is
made deliberately conservative — assume we sold at a slightly worse price than the
model says — so the resulting win rate understates rather than flatters.

## User experience flow

**Running it, once, before the competition.**

1. Talvin runs `python backtest.py` on his desktop. No schedule, no CI.
2. It prints a progress line per month so a six-month run does not look frozen.
3. About a minute later it prints the summary table.
4. The headline: **78% win rate over 118 simulated trades.**
5. It writes `backtest_results.json`.
6. That number, the trade count, the date range, and the average-win-versus-average-
   loss caveat all go into `WRITEUP.md` and onto a slide.
7. When a judge asks "how do you know this strategy works, you only traded four days"
   — there is an answer, with a method attached, instead of a claim.

**When the result is disappointing.**

1. Same run, but it prints **61%**, with `RISK_OFF` at 48%.
2. This is useful, not a failure. It says the gold overlay is hurting in one mood, and
   it says so *before* the competition rather than after.
3. Either the teammate revises those thresholds, or `RISK_OFF` becomes a
   stand-down-entirely rule instead of a trade-differently rule.
4. Either way the write-up gets stronger: a strategy that was tested and adjusted
   reads as engineering. A strategy that was assumed correct reads as a guess that
   happened to work.

## Failure modes

| What goes wrong | What happens |
|---|---|
| Historical data has gaps | Skip those days, report how many were skipped. Never interpolate prices — invented data produces invented results. |
| Premium estimate is too generous | Win rate looks better than reality. Mitigated by biasing the estimate conservatively, and by stating the limitation in the write-up. |
| Fewer than ~30 trades in the window | Not enough to mean anything. Say so rather than quoting a percentage from a small sample. |
| Rules drift from the live ones | Prevented structurally by importing `regime.py` and `gates.py` instead of restating them. |
| Six months happened to be an easy market | A real limitation. State the period tested and let the reader judge. Extending the window is the fix if time allows. |

## Verification

```
python backtest.py
```

Sanity checks that must hold before the number is quoted anywhere:

- Trades plus skipped days equals the total trading days in the window. Nothing
  vanishes silently.
- Wins plus losses equals total trades.
- No trade has a loss worse than the $500 per-trade cap. If one does, the settlement
  maths is wrong.
- The regime split sums to the overall trade count.
- Re-running produces an identical result. Any randomness in a backtest is a bug.

A win rate outside roughly 60–85% deserves suspicion. Too low suggests the rules are
wrong; too high suggests the simulation is cheating somewhere.

## Open questions

1. Six months, or longer? Longer is more convincing and costs nothing but runtime. Six
   is the floor.
2. Should the estimated premium be replaced with real historical option prices? That
   needs paid data. Not worth $99 for a supporting figure, but the limitation must be
   stated.
3. Should we also backtest without the gold overlay, as a comparison? Yes, if time
   allows — "the overlay added six points of win rate" is a far stronger claim than
   "our strategy won 78%". This is the single highest-value optional item in the whole
   project.
