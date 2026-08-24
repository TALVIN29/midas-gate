# `gates.py` — what is legal right now, and the check before the order

> **In plain terms:** before the AI is allowed to think about anything, this file works
> out every trade it would be permitted to make and hands it only that. After the AI has
> answered, the same file checks the answer again against fresh data. If we have lost too
> much today, it hands over nothing at all.

> **What changed since v1** ([appendix/gates.md](../appendix/gates.md)): total open risk is
> now regime-scaled ($10k / $5k / $0) instead of a flat $2,000. Added: the data-health
> gate, the persisted operating state, latched halts, run-id duplicate protection, the
> order-rejection policy, and — the big one — the **deterministic pre-trade validator**
> that re-checks the AI's proposal after the model answers and before the order is sent.

## Purpose

This is the most important file in the project.

The obvious way to keep an AI safe is to tell it the rules in its instructions and trust
it. That is not a guarantee, it is a request. Language models are persuadable, they
miscount, and a bad day in a trading account is not recoverable by apologising.

So we invert it. `gates.py` is ordinary Python — no AI anywhere near it. It reads the
account, applies fixed arithmetic and produces an **envelope**: the exact expiry dates,
strike ranges and maximum size that are allowed at this moment. The AI is then asked to
choose *within* that envelope. Breaking a limit is not something it is discouraged from
doing; it is something it has no way to express.

And because the market moves while the model is thinking, the same rules run a second
time on the AI's actual proposal against freshly refreshed data. **The AI's answer never
reaches Alpaca unchecked.**

## Where it sits

**Twice — before the agent, and after it.**

```
state → data health → regime.py → gates.py (envelope) → agent.py
                                        ↓
                              gates.py (validator) → execution → audit.py
```

It reads the account but never places an order. It is the only file that can stop the day.

## Inputs

| Input | Detail |
|---|---|
| Persisted state | Operating state, latched halts, the run ids that already placed an order, this morning's regime |
| The regime block | From `regime.py` — regime, risk budget, allowed strategies, distance, position cap, `put_spreads_allowed` |
| Account snapshot | Cash, buying power, current value, starting value. Via `alpaca-py` |
| Open positions | What we hold, and what each one could still lose |
| Order state | Anything working, rejected or partially filled |
| Current time | US Eastern, read from a timezone library — never the machine clock |
| Run id | `YYYY-MM-DD-0935` or `-1305`, passed in by the workflow |
| `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` | Environment variables |

## Outputs

Either an envelope, or a refusal. Never a partial one.

**An envelope:**

```json
{
  "allowed": true,
  "run_id": "2026-09-02-1305",
  "operating_state": "ACTIVE",
  "regime": "NEUTRAL",
  "strategies": ["PUT_CREDIT_SPREAD"],
  "expiries": ["2026-09-03", "2026-09-04"],
  "short_strike_min_distance_pct": 1.5,
  "long_strike_offset": 5.0,
  "max_contracts": 2,
  "max_risk_per_spread_usd": 500,
  "risk_budget_usd": 5000,
  "remaining_risk_budget_usd": 4062,
  "remaining_daily_loss_budget_usd": 1420.50,
  "open_positions": 1,
  "max_positions": 2,
  "spot_at_build": 651.20,
  "underlying": "SPY"
}
```

**A refusal:**

```json
{
  "allowed": false,
  "operating_state": "HALTED",
  "reason": "DAILY_DRAWDOWN_HALT",
  "detail": "Down 2.3% today, limit is 2.0%. Latched — no new positions until tomorrow.",
  "latched_until": "next_trading_day"
}
```

When `allowed` is false there are **no other envelope fields**. There is nothing to
partially obey and nothing for the AI to negotiate with. `agent.py` reads the refusal and
exits without ever contacting a model.

`spot_at_build` is not decoration: the validator needs to know how far the market has
moved since the envelope was built.

## Logic

### The hard gates

Absolute. Not affected by the regime, and there is no override.

| Gate | Limit | Why |
|---|---|---|
| Risk per trade | $500 maximum possible loss on any single spread | One bad trade cannot matter much |
| Total risk open | The regime's budget — $10,000 / $5,000 / $0, ceiling $10,000 | The gold thesis sets money at risk, not just strike distance |
| Daily loss | Down 2% in a day → no new positions, **latched for the day** | Stops a bad day compounding |
| Competition loss | Down 4% overall → latched halt **and** `REVIEW_REQUIRED` | A floor under the whole thing. Human reset only |
| Late in the day | No new positions after 15:30 ET | The last half hour is jumpy and there is no time to react |
| Final day | No new positions on Sep 4 | Submission day. Nothing new to babysit |
| Final close-out | Close everything by 15:45 ET on the last trading day | Profit that is still open is not profit. Judges score realised results |
| Duplicate run | One order per run id, ever | A workflow rerun must not double the risk |

$500 per trade against $100,000 is 0.5%. Deliberately small. The strategy wins by being
repeatedly, boringly right.

### Latching

A halt that clears itself the moment P&L ticks back over the line is not a halt.

```
P&L reaches -2.0%  → DAILY_HALT = true
later P&L is -1.6% → DAILY_HALT is still true
```

The daily halt resets at the first run of the next trading day. The competition halt does
not reset at all: it sets `REVIEW_REQUIRED` and waits for a logged human decision. Same
for an `AUDIT_FAIL` escalation arriving from [audit.md](audit.md).

### How the envelope gets built

1. **Read persisted state.** Competition halt, daily halt or `REVIEW_REQUIRED` still
   latched? Refuse immediately. Nothing below runs, and the AI is not called.
2. **Data health.** Account, positions and order state readable? Critical market data
   fresh? No → `HALTED`, refuse. A secondary gap → `DEGRADED`, continue with the regime's
   cautious fallback.
3. **Duplicate check.** Has this run id already submitted an order? Yes → refuse with
   `DUPLICATE_RUN`.
4. **Clock.** Past 15:30 ET, or is it Sep 4? → refuse, `NO_NEW_POSITIONS`.
5. **Apply the intraday caution rule.** If this morning was more cautious than the current
   regime, use this morning's permissions.
6. **Take the regime's permissions:** strategies, `put_spreads_allowed`, minimum distance,
   position cap, risk budget. If `risk_budget_usd` is 0 or `put_spreads_allowed` is false
   with no other strategy permitted, the envelope is empty → `NO_TRADE`.
7. **Count what is open.** At the position cap → refuse.
8. **Add up the worst case of everything held.** Subtract from the regime budget. Under
   $500 left → nothing fits → refuse.
9. **Work out which expiries** fall in the 1–3 day window.
10. **Emit the envelope**, recording `spot_at_build` and the operating state.

Step 8 is the one that matters most and it is pure arithmetic. There is no judgement in
it and therefore nothing to talk it out of.

An empty envelope is **not** an error. It produces a clean `NO_TRADE` that is audited,
logged and published like any other outcome.

### The pre-trade validator

Runs after `agent.py` answers, before anything is submitted. It refreshes critical market
and account data first, then re-checks:

| Check | Fails if |
|---|---|
| Strategy | The proposed strategy is not in `allowed_strategies` |
| Put permission | It is a put spread and `put_spreads_allowed` is false |
| Strike distance | Measured against the **refreshed** spot, the short strike is inside the minimum distance |
| Expiry | Outside the allowed list |
| Size | Contracts above `max_contracts` |
| Max loss | Worst case above $500 |
| Total risk | Worst case plus existing open risk above the regime budget |
| Position count | Would exceed `max_positions` |
| Account | Equity or buying power has materially changed since the envelope was built |
| State | The system has become `HALTED` or `REVIEW_REQUIRED` since the envelope was built |
| Duplicate | This run id already has a submitted order |

Any failure:

```
REJECT PROPOSAL
DO NOT SEND ORDER
```

The AI is **not** asked to fix an illegal trade in place. A patched-up proposal has not
been through a decision cycle. The run records `VALIDATION_REJECTED` with the specific
check that failed, and ends.

The strike-distance re-check is the one that earns its keep: the model may take a minute
to think, and a minute is plenty for SPY to move a legal strike into an illegal one.

### Order rejection

```
Order rejected by Alpaca
    → refresh market + account state
    → rebuild the envelope
    → at most ONE controlled retry, if a legal trade still exists
    → second failure → HALT this run
```

No free-form retries. A rejection usually means our understanding of the account is
wrong, and repeating a misunderstanding is worse than stopping.

### Partial fill / unknown exposure

If the intended result was a defined-risk spread but the broker shows only one leg, a
mismatched quantity, an unexpected leg, or a fill state inconsistent with the order:

```
REVIEW_REQUIRED
```

No new trades until a human understands it. Any corrective action must itself be
pre-defined and deterministic — the AI does not freestyle its way out of unknown
portfolio exposure.

## User experience flow

**A normal midday run.**

1. The clock fires with run id `2026-09-02-1305`. `regime.py` returned `NEUTRAL`, budget
   $5,000.
2. State is clean, no latched halts, and this run id has placed nothing.
3. Account $100,340, up $340 today. Time 13:05 ET, before the cutoff, not Sep 4.
4. One position open risking $438. Cap is 2 positions, so there is room.
5. Remaining budget: $5,000 − $438 = $4,562. More than $500, so a trade fits.
6. It emits the envelope and logs:
   `ENVELOPE ok run=2026-09-02-1305 PUT_CREDIT_SPREAD >=1.5% OTM <=2ct budget_left=$4562`
7. The AI answers with a 640/635 spread. The validator refreshes: SPY now 650.90, the 640
   strike is 1.68% out, still clear. Size, loss, totals, state, duplicate — all pass.
8. The order goes to Alpaca.
9. On the dashboard, the Risk panel shows $876 of $5,000 used and 2 of 2 positions filled.

**The market moves while the model thinks.**

1. Same setup, envelope built at spot 651.20 with a 1.5% floor.
2. The AI proposes the 641 short strike — 1.57% out at build time, legal.
3. Ninety seconds pass. The validator refreshes: SPY is now 648.10. The 641 strike is
   1.10% out. Below the floor.
4. `VALIDATION_REJECTED — short_strike_min_distance_pct: required 1.5, actual 1.10`.
   **No order is sent.** The AI is not asked to try again this run.
5. The dashboard shows a **Rejected before order** card with both numbers. This is the
   control architecture working in public, and it is worth more in the write-up than the
   trade would have been.

**A bad day.**

1. 13:05 ET. Stocks dropped hard, our open spreads are underwater.
2. Account $97,750 — down 2.25% today, limit 2%.
3. Step 1 refuses: `DAILY_DRAWDOWN_HALT`, latched. `agent.py` exits without a model call —
   no tokens spent, no chance of a clever workaround.
4. `audit.py` still runs and records the halt.
5. The dashboard turns red: **HALTED FOR TODAY — down 2.25%, limit 2.0%.**
6. Talvin wakes, sees red, reads the reason. Nothing is required of him. Tomorrow's first
   run reads the account fresh and, if the day resets above the line, trading resumes.

Existing positions are **not** force-closed by a halt. The halt blocks *new* trades.
Panic-closing into a falling market is usually the more expensive mistake, and every
position already has a capped worst case by construction.

## Failure modes

| What goes wrong | What happens |
|---|---|
| Account data unreadable | `HALTED`, refusal `NO_ACCOUNT_DATA`. Blind means no trading |
| Position list unreadable | `HALTED`. Remaining risk cannot be computed without it |
| Critical market data stale | `HALTED`. Freshness is checked in ordinary code, not judged by the AI |
| Secondary indicator missing | `DEGRADED`, cautious fallback, continue |
| Clock or timezone wrong | Eastern time is read explicitly from a timezone library. The runner is on UTC; assuming otherwise would silently move every time gate |
| AI proposes an illegal strike, size or strategy | Validator rejects. No order |
| Market invalidates the distance | Validator rejects on refreshed spot. No stale order |
| Duplicate workflow run | Run-id check. No second order |
| First broker rejection | Refresh, rebuild, one controlled retry |
| Repeated broker rejection | Halt this run |
| Partial or unknown spread | `REVIEW_REQUIRED` |
| Empty envelope | `NO_TRADE`, audited and published |
| Numbers do not add up | Refuse. An envelope is emitted only when every check passed. There is no "mostly fine" |

Every failure path leads to the same place: no trade. That is the design.

## Verification

```
python gates.py
```

`assert`-based self-checks against hand-made state, account snapshots and proposals:

**Envelope**

- A spread risking $600 is rejected — over the $500 per-trade cap.
- An account down 2.5% today produces `allowed: false` with `DAILY_DRAWDOWN_HALT`.
- An account down 4.5% overall halts for the competition **and** sets `REVIEW_REQUIRED`.
- A latched daily halt stays latched when P&L later recovers to −1.6%.
- A request at 15:45 ET returns no envelope. A request dated Sep 4 returns no envelope.
- With $4,700 of a $5,000 budget already at risk, no new trade fits — refusal.
- `RISK_OFF` (budget $0) produces an empty envelope and a clean `NO_TRADE`.
- Stand-down (`put_spreads_allowed: false`) blocks put spreads specifically.
- A run id that already placed an order places nothing.
- Every refusal has `allowed: false` and **no** envelope fields beside it.

**Validator**

- A proposal outside the distance floor on refreshed spot is rejected.
- An oversized proposal, a forbidden strategy, and an over-budget proposal are each
  rejected, each naming the specific failed check.
- A proposal that arrives after the state flipped to `HALTED` is rejected.
- A valid proposal passes and is unchanged by validation.

Passing looks like silence and exit code 0.

## Open questions

1. Is the daily loss measured against yesterday's close, or the account value at the
   first run of the day? Yesterday's close is the more standard reading and is the
   assumption here. `ASSUMPTION:` confirm before the live account is used.
2. Should the final-day close-out live here or in `agent.py`? It is an action, not a
   permission, so it more likely belongs to the agent, with `gates.py` supplying
   `must_close_all: true`. Not settled.
3. On a competition-wide halt, do we close everything or hold to expiry? Holding is
   cheaper; closing makes the final number real. Leaning toward closing — but under the
   handoff rules that is a human decision, since a competition halt is `REVIEW_REQUIRED`.
