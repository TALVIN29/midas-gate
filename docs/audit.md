# `audit.py` — the check on the AI, and the only thing that learns

> **In plain terms:** after the AI has traded, this file goes and looks at what actually
> happened, confirms the AI stayed inside its limits, decides whether anything that went
> wrong was a genuine mistake, writes down at most a handful of lessons, and publishes it
> all to the website.

> **What changed since v1** ([appendix/audit.md](appendix/audit.md)): an `AUDIT_FAIL` is
> no longer merely displayed — it **latches a halt** and escalates to `REVIEW_REQUIRED`.
> Added: the outcome/mistake taxonomy, bounded lesson generation, partial-fill escalation,
> and persistence of the operating state and exception history.

## Purpose

Three jobs. The first is the one people underestimate.

**It marks the AI's homework.** `gates.py` decides what is allowed, the validator checks
the proposal, `agent.py` chooses — but none of them sees the result. An order can be
modified in flight, partially filled, or filled at a worse price than expected. So
`audit.py` re-reads the position from Alpaca *as it actually exists* and compares it
against the envelope that was in force. If they disagree, that is recorded as a
violation, in public, and it stops the system.

This is deliberately uncomfortable. A system that can only report its successes is not
evidence of anything. A system that publishes its own violations, and halts on them, is.

**It decides what, if anything, was learned.** Not every loss is a mistake. A correctly
selected defined-risk spread that lost because the market moved is not an error and must
not change behaviour. Separating `BAD OUTCOME` from `BAD DECISION` is the whole reason
this system can have a learning loop without becoming self-modifying.

**It is the only thing that publishes.** Nothing else writes `state.json`, and
`state.json` is the entire website. If the audit does not run, the outside world sees
nothing new — correct behaviour, because unaudited results should not be shown as though
they were verified.

## Where it sits

**Last, and it runs every time** — including runs where nothing traded, runs that were
halted, and runs where the validator rejected the proposal.

```
… → validator → execution → audit.py → state.json → dashboard
```

It reads everything and places no orders. Its side effects are one file written and one
commit pushed.

## Inputs

| Input | Detail |
|---|---|
| The envelope | What was permitted, including a refusal |
| The validator result | Pass, or the specific check that failed |
| The agent's output | What it says it did, its candidates, and why |
| Real positions | Read fresh from Alpaca, not taken on trust |
| Real order history | Fill prices, times and states for this run |
| Account snapshot | Current value, for P&L |
| Previous `state.json` | Operating state, latched halts, learning memory, history |
| `bs.py` | Display-only greeks |

The distinction between "what the agent says it did" and "what Alpaca says happened" is
the whole point. If those ever differ, the second is the truth and the difference is the
finding.

## Outputs

`site/state.json`, committed back to the repository. Full schema in
[dashboard.md](dashboard.md). The audit-specific part:

```json
{
  "run": {
    "run_id": "2026-09-02-1305",
    "timestamp": "2026-09-02T13:12:08Z",
    "operating_state": "ACTIVE",
    "regime": "NEUTRAL",
    "envelope_allowed": true,
    "validation": "PASS",
    "agent_action": "PLACE",
    "audit_result": "AUDIT_PASS",
    "violations": [],
    "outcome_class": "NO_ERROR",
    "lesson_written": null
  },
  "pnl": {
    "account_value": 100402.50,
    "starting_value": 100000.00,
    "total_pnl": 402.50,
    "total_pnl_pct": 0.40,
    "day_pnl": 62.50,
    "realised": 340.00,
    "unrealised": 62.50,
    "open_risk": 876.00,
    "risk_budget": 5000
  }
}
```

A failed check looks like:

```json
{
  "audit_result": "AUDIT_FAIL",
  "operating_state": "REVIEW_REQUIRED",
  "violations": [
    {
      "rule": "short_strike_min_distance_pct",
      "required": 1.5,
      "actual": 1.31,
      "detail": "Short strike 642 is 1.31% below spot 650.5 at fill. Envelope required at least 1.5%."
    }
  ],
  "outcome_class": "RISK_VIOLATION",
  "escalation": "Autonomous trading halted. Human review required before the next run."
}
```

## Logic

1. Read what the account actually holds now, and the orders filled during this run.
2. **Consistency check.** Does the broker state match our records? Is every intended
   spread complete? A missing leg, a mismatched quantity, an unexpected leg or an
   inconsistent fill state is a critical exception → `REVIEW_REQUIRED`, immediately.
3. For each new position, check it against the envelope in force:
   - Was this strategy allowed?
   - Is the short strike far enough from where the market was *at fill*?
   - Is the expiry in the allowed window?
   - Is the size within the contract cap?
   - Is the worst case within $500, and total open risk within the regime budget?
   - Is the position count within the cap?
4. Record **every** mismatch as a violation. Do not stop at the first.
5. If there is any violation: `AUDIT_FAIL` → publish it → latch a halt on autonomous
   trading → `REVIEW_REQUIRED`. It stays latched until a human clears it, and the clearing
   is itself logged.
6. Recompute P&L from the account value, split into realised and unrealised. Update the
   latched daily and competition halt flags.
7. **Classify the outcome** (below).
8. **Update the learning memory** (below).
9. Call `bs.py` for display greeks on each open position.
10. Assemble the new `state.json`, appending this run to the history and carrying the
    operating state forward.
11. Write it and commit it back. The commit is what makes Netlify redeploy.

Step 3 measures against **where the market was when the order filled**, not where it is
now. Judging a decision by information that arrived after it is a classic analysis error
and would manufacture fake violations.

### The outcome / mistake taxonomy

Every run gets exactly one class:

| Class | Meaning | Learning? |
|---|---|---|
| `NO_ERROR` | Decision and execution were reasonable. The outcome may still be a loss | No |
| `MARKET_MOVE` | A legal, well-chosen trade lost because the market moved against it | No |
| `SELECTION_ERROR` | A poorer legal candidate was chosen when a better one was available | Yes |
| `LIQUIDITY_ERROR` | Order quality was harmed by a thin or wide market | Yes |
| `EXECUTION_ERROR` | Rejection, fill problem, or order-state issue | Yes |
| `DATA_ERROR` | Stale, missing or inconsistent input data | Yes — and usually a `DEGRADED`/`HALTED` record too |
| `REGIME_MISS` | The regime looks too optimistic or too cautious in hindsight | Not by the fast loop. Goes to the slow loop and the gold trader |
| `RISK_VIOLATION` | The actual state violated the deterministic envelope | Not a lesson — an escalation. `REVIEW_REQUIRED` |

`NO_ERROR` and `MARKET_MOVE` are the expected majority. A system that treats every losing
trade as a mistake will thrash itself into a worse strategy inside a week — over six days
it would simply be noise-chasing.

### Lesson generation, bounded

A lesson is a short preference with evidence attached:

```json
{
  "type": "selection",
  "lesson": "Prefer additional OTM distance in NEUTRAL when the premium difference is small.",
  "evidence_count": 3,
  "confidence": "MEDIUM",
  "last_observed": "2026-09-02T13:12:08Z"
}
```

Hard limits, enforced in code:

- **At most 3–5 active lessons.** A new one displaces the weakest.
- **At most the last 5–10 outcomes** kept as supporting evidence.
- Old or contradicted lessons expire or are consolidated.
- One observation is not a lesson. A lesson needs repeated evidence before its confidence
  rises, and it never becomes a rule.

**What a lesson may influence:** ranking between legal candidates, liquidity preference,
strike-distance preference *inside* the allowed range, whether a little more premium is
worth a little less distance, and the choice of `NO_TRADE`.

**What a lesson may never touch:** the $500 per-spread cap, the regime risk budgets, the
−2% and −4% halts, the gold thresholds, the permitted strategy families, position limits,
the validation requirements, or the escalation policy.

> **Learning changes preferences, not permissions.**

Structural changes — a threshold that looks wrong, a rule that keeps missing — are not the
fast loop's business. They are written up as a proposal for the slow loop, reviewed by the
gold trader and Talvin, and land as a version-controlled change. See
[backtest.md](backtest.md).

## User experience flow

**A clean run.**

1. 13:12 ET. The agent placed a 640/635 put spread three minutes ago.
2. Positions read from Alpaca: two legs, short 640, long 635, one contract, filled for
   $0.62 credit. Both legs present — no partial.
3. Envelope in force: put credit spreads, at least 1.5% out, up to 2 contracts, $5,000
   budget.
4. SPY was 651.20 at fill. The 640 strike is 1.72% below that. Clears the floor.
5. Worst case: the $5 strike gap less the $0.62 collected, times 100 = $438. Under the
   $500 cap. Total open risk $876, under $5,000.
6. Every check passes. `AUDIT_PASS`, no violations, `outcome_class: NO_ERROR`.
7. Account $100,402.50. Up $402.50 overall, $62.50 today.
8. `bs.py` returns about $29/day of time decay in our favour, for display.
9. It writes `site/state.json` and commits:
   `audit: 2026-09-02 13:12 — AUDIT_PASS, +$402.50`.
10. Netlify redeploys in under a minute.
11. Talvin opens the site next morning: green **AUDIT_PASS**, running profit, the trade
    card, the agent's reasoning. Ten seconds to understand the day. Nothing needed doing.

**A violation is found.**

1. Same run, but the fill came back on the 642 strike rather than 640.
2. Measured at fill: 642 is 1.31% below spot. The envelope required 1.5%.
3. `AUDIT_FAIL`. The violation is recorded with both numbers, `outcome_class:
   RISK_VIOLATION`, and the operating state moves to `REVIEW_REQUIRED`.
4. Autonomous trading is **halted and latched**. The next scheduled run will read that
   state, refuse before anything else happens, and never call the model.
5. It does **not** hide the finding and it does **not** unwind the position. Trading to
   correct an accounting finding is how a small problem becomes a large one, and the
   position keeps its own capped worst case regardless.
6. The dashboard shows an amber banner: **Envelope violation — autonomous trading halted,
   human review required**, with the required and actual numbers side by side.
7. Talvin reads two numbers and knows exactly which rule slipped and by how much, without
   reading any code. He investigates, records what he found and what he changed, and
   clears the state deliberately. The clearing appears in the history.
8. In the write-up this is a strength. "Our agent broke a rule once, our own audit caught
   it, published it and stopped trading" is a far more credible claim than an unblemished
   record nobody verified.

**A halted or no-trade run.**

1. `gates.py` refused, or the envelope was empty, or the validator rejected the proposal.
2. `audit.py` still runs. It records the reason, the P&L and the operating state.
3. `state.json` gets a run entry with `agent_action: "NO_TRADE"` or `"NONE"` and the
   specific cause.
4. The dashboard shows the state banner and the unchanged P&L.
5. The history stays complete. Every scheduled run appears, including the ones where the
   right answer was to do nothing.

## Failure modes

| What goes wrong | What happens |
|---|---|
| Positions unreadable | Write `audit_result: "UNKNOWN"` with an explanation, and set `REVIEW_REQUIRED`. Never write `AUDIT_PASS` for a check that did not happen |
| Partial spread / unexpected leg | `REVIEW_REQUIRED`. No new trades until a human understands the exposure |
| Broker state ≠ our records | `REVIEW_REQUIRED`. Same reasoning |
| Greeks calculation fails | Skip that panel, publish everything else. A display extra must not block the record |
| Commit rejected (branch moved) | Pull, reapply, retry once. If it fails again, log loudly — a stale dashboard is misleading and must be noticed |
| `state.json` malformed | Do not overwrite it. Write alongside and log. Losing the history mid-competition would be unrecoverable |
| Learning memory would exceed its limits | Displace the weakest lesson. The cap is enforced, not advisory |
| Audit itself crashes | The trade already happened and is real in Alpaca either way. The Actions run goes red, which is the alert |

The rule here is the opposite of the rest of the system. Elsewhere, when in doubt, do
less. Here, when in doubt, **publish the doubt**.

## Verification

```
python audit.py
```

`assert`-based self-checks against hand-made fills, envelopes and prior state:

- A compliant fill produces `AUDIT_PASS` and an empty violations list.
- A strike 1.31% out against a 1.5% requirement produces exactly one violation with both
  numbers present, `AUDIT_FAIL`, and `REVIEW_REQUIRED`.
- An oversized position produces a violation naming the size rule.
- Multiple breaches produce multiple violations, not just the first.
- A single-leg fill of an intended spread produces `REVIEW_REQUIRED` and no lesson.
- A halted run and a `NO_TRADE` run each produce a valid, complete history entry.
- A losing but compliant trade classifies as `MARKET_MOVE` and writes **no** lesson.
- A repeated liquidity problem raises an existing lesson's `evidence_count`, and a sixth
  lesson displaces the weakest rather than growing the list.
- No lesson can alter any field in the envelope — asserted directly.
- P&L splits correctly into realised and unrealised.
- A latched `REVIEW_REQUIRED` in the prior state is still latched afterwards.

After the first live run, three things must agree: the Alpaca paper dashboard, the
`state.json` in the repository, and the Netlify page. If any two disagree, the publishing
chain is broken and nothing downstream can be trusted.

## Open questions

1. Superseded from v1: a violation *does* now halt trading, per the handoff. The old
   assumption ("record it, do not halt") is gone deliberately — a system whose audit has
   no teeth is a reporting feature, not a control.
2. How much history does `state.json` keep? Over six days, all of it. This becomes a real
   question only if the file gets large, which it will not.
3. Should each run commit separately, or should the day be squashed? Separate commits make
   a visible timeline in the repository, which is itself evidence of autonomy. Leaning
   toward separate.
4. Who clears `REVIEW_REQUIRED` — Talvin alone, or Talvin plus the teammate for anything
   regime-related? Ownership table in the handoff §32 says risk and execution are Talvin's,
   regime is the teammate's. Confirm before the first live day.
