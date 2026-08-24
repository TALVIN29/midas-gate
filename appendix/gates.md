# `gates.py` — the list of trades that are legal right now

> **In plain terms:** before the AI is allowed to think about anything, this file
> works out every trade it would be permitted to make — and hands it only that. If
> we have lost too much today, it hands over nothing at all.

## Purpose

This is the most important file in the project.

The obvious way to keep an AI safe is to tell it the rules in its instructions and
trust it. That is not a guarantee, it is a request. Language models are persuadable,
they miscount, and a bad day in a trading account is not recoverable by apologising.

So we invert it. `gates.py` is ordinary Python — no AI anywhere near it. It reads the
account, applies fixed arithmetic, and produces an **envelope**: the exact expiry
dates, the exact strike ranges, and the exact maximum size that are allowed at this
moment. The AI is then asked to choose *within* that envelope.

The result is that breaking a risk limit is not something the AI is discouraged from
doing. It is something it has no way to express. Every number it could possibly pick
was already checked before it was offered.

## Where it sits

**Second.** After `regime.py`, before `agent.py`.

`regime.py` → **`gates.py`** → `agent.py` → `audit.py`

It reads the account but never places an order. It is the only file that can stop the
day.

## Inputs

| Input | Detail |
|---|---|
| The regime dictionary | From `regime.py` — mood plus the three sizing numbers |
| Account snapshot | Cash, buying power, current value, starting value. Via `alpaca-py` |
| Open positions | What we already hold, and what each one could still lose |
| The current time | In US Eastern time — several gates are clock-based |
| Today's date | To detect the final day, Sep 4 |
| `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` | Environment variables |

## Outputs

Either an envelope, or a refusal. Never a partial one.

**An envelope:**

```json
{
  "allowed": true,
  "regime": "NEUTRAL",
  "strategies": ["put_credit_spread"],
  "expiries": ["2026-09-02", "2026-09-03"],
  "short_strike_min_distance_pct": 1.5,
  "long_strike_offset": 5.0,
  "max_contracts": 2,
  "max_risk_per_spread_usd": 500,
  "remaining_risk_budget_usd": 1500,
  "remaining_daily_loss_budget_usd": 1420.50,
  "open_positions": 1,
  "max_positions": 2,
  "underlying": "SPY"
}
```

**A refusal:**

```json
{
  "allowed": false,
  "reason": "DAILY_DRAWDOWN_HALT",
  "detail": "Down 2.3% today, limit is 2.0%. No new positions until tomorrow.",
  "halt_scope": "today"
}
```

When `allowed` is false there are **no other fields**. There is no envelope to
partially obey and nothing for the AI to negotiate with. `agent.py` sees the refusal
and stops immediately without ever contacting a model.

## Logic

### The hard gates

These are absolute. They are not affected by the mood, and there is no override.

| Gate | Limit | Why |
|---|---|---|
| Risk per trade | $500 maximum possible loss on any single spread | One bad trade cannot matter much |
| Total risk open | $2,000 across everything held | Five bad trades at once cannot matter much either |
| Daily loss | Down 2% of the account in one day, stop opening trades until tomorrow | Stops a bad day compounding |
| Total loss | Down 4% overall, stop for the entire competition | A floor under the whole thing |
| Late in the day | No new positions after 15:30 ET | The last half hour is jumpy and there is no time to react |
| Final day | No new positions at all on Sep 4 | Submission day. Nothing new to babysit |
| Final close-out | Close everything by 15:45 ET on the last trading day | Profit that is still open is not profit. Judges score realised results |

$500 per trade against a $100,000 account is 0.5%. That is deliberately small. Over
four days the strategy wins by being repeatedly, boringly right, not by being big.

### How the envelope gets built

1. Is a halt in force? If yes, return the refusal and stop. Nothing below runs.
2. Is it past 15:30 ET, or is it Sep 4? If yes, refusal, reason `NO_NEW_POSITIONS`.
3. Take the sizing numbers from the mood: strategies allowed, minimum distance,
   maximum positions.
4. Count what is already open. If we are at the position cap, refusal.
5. Add up the worst case of everything currently held. Subtract from $2,000. That is
   the remaining risk budget. If it is under $500, we cannot fit another trade, so
   refusal.
6. Work out which expiry dates fall in the 1–3 day window from today.
7. Emit the envelope.

Step 5 is the one that matters most and it is pure arithmetic. There is no judgement
in it and therefore nothing to get talked out of.

## User experience flow

**A normal midday run.**

1. The clock fires. `regime.py` has already returned `NEUTRAL`.
2. `gates.py` asks Alpaca for the account. Value $100,340, up $340 today. No halts.
3. Time is 13:05 ET. Before the 15:30 cutoff. Not Sep 4. Fine.
4. One position is already open, risking $460. Cap is 2 positions, so there is room
   for one more.
5. Risk budget: $2,000 minus $460 leaves $1,540. More than $500, so a trade fits.
6. It emits the envelope above and prints one log line:
   `ENVELOPE ok: put_credit_spread, >=1.5% OTM, <=2 contracts, $1540 risk budget left`
7. `agent.py` receives it and goes to work.
8. On the dashboard, a small "Risk" panel shows $460 of $2,000 used and 1 of 2
   positions filled. Talvin can see at a glance that the system is nowhere near its
   limits.

**A bad day.**

1. 13:05 ET. Stocks have dropped hard. Our open spreads are underwater.
2. `gates.py` reads the account: $97,750. Down 2.25% today. The daily limit is 2%.
3. It stops at step 1 and returns the refusal, reason `DAILY_DRAWDOWN_HALT`.
4. `agent.py` sees `allowed: false`, logs it, and exits. **The AI is never called.**
   No model request is made, no tokens spent, no chance of a clever workaround.
5. `audit.py` still runs, and records the halt in `state.json`.
6. The dashboard turns its status banner red: **HALTED FOR TODAY — down 2.25%, limit
   2.0%.**
7. Talvin wakes up, sees red, and reads the reason without needing to ask anyone.
   Nothing is required of him. Tomorrow's first run re-reads the account fresh; if the
   day resets above the line, trading resumes on its own.

Existing positions are *not* force-closed by a halt. The halt blocks *new* trades.
Panic-closing into a falling market is usually the more expensive mistake, and every
position already has a capped worst case by construction.

## Failure modes

| What goes wrong | What happens |
|---|---|
| Account data unreadable | Refusal, reason `NO_ACCOUNT_DATA`. Blind means no trading. |
| Position list unreadable | Refusal. We cannot compute remaining risk without knowing what we hold. |
| Clock or timezone wrong | Reads Eastern time explicitly from a timezone library, never from the machine's local clock. The GitHub runner is on UTC; assuming otherwise would silently move every time gate. |
| Numbers do not add up | Refuse. An envelope is emitted only when every check passed. There is no "mostly fine". |
| Two gates conflict | Impossible by construction: any single failing gate produces a refusal, and refusals stop evaluation. |

Every single failure path leads to the same place: no trade. That is the design.

## Verification

```
python gates.py
```

`assert`-based self-checks against hand-made account snapshots, no market needed:

- A spread risking $600 is rejected, over the $500 per-trade cap.
- An account down 2.5% today produces `allowed: false` with `DAILY_DRAWDOWN_HALT`.
- An account down 4.5% overall halts for the competition, not just the day.
- A request at 15:45 ET returns no envelope.
- A request dated Sep 4 returns no envelope.
- With $1,700 of risk already open, the remaining budget is $300, so no new trade fits
  and a refusal is returned.
- Every refusal has `allowed: false` and **no** envelope fields alongside it.

Passing looks like silence and exit code 0.

## Open questions

1. Is the daily loss measured against yesterday's closing value, or the value at the
   first run of the day? Yesterday's close is the more standard reading and is the
   assumption here. `ASSUMPTION:` confirm before the live account is used.
2. Should the final-day close-out live here or in `agent.py`? It is an action, not a
   permission, so it more likely belongs to the agent, with `gates.py` supplying the
   `must_close_all: true` instruction. Not yet settled.
3. On a competition-wide halt, do we close everything or hold to expiry? Holding is
   cheaper; closing is more defensible in a write-up. Leaning toward closing, so that
   the final number is real.
