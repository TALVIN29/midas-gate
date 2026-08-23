# `audit.py` — the check on the AI

> **In plain terms:** after the AI has traded, this file goes and looks at what
> actually happened, confirms the AI stayed inside its limits, works out how much money
> we made or lost, and publishes it all to the website.

## Purpose

Two jobs, and the first one is the one people underestimate.

**It marks the AI's homework.** `gates.py` decides what is allowed and `agent.py`
chooses within it — but neither of them checks the result. An order can be modified in
flight, partially filled, or filled at a worse price than expected. So `audit.py`
re-reads the position from Alpaca *as it actually exists* and compares it against the
envelope that was in force. If they disagree, that is recorded as a violation, in
public, on the dashboard.

This is deliberately uncomfortable. A system that can only report its successes is not
evidence of anything. A system that publishes its own violations is.

**It is the only thing that publishes.** Nothing else writes `state.json`, and
`state.json` is the entire website. If the audit does not run, the outside world sees
nothing new — which is the correct behaviour, because unaudited results should not be
shown as though they were verified.

## Where it sits

**Last.** It runs every time, including on runs where nothing was traded and runs that
were halted.

`regime.py` → `gates.py` → `agent.py` → **`audit.py`**

It reads everything and places no orders. Its side effects are one file written and
one commit pushed.

## Inputs

| Input | Detail |
|---|---|
| The envelope | What was permitted, including a refusal |
| The agent's output | What it says it did, and why |
| Real positions | Read fresh from Alpaca, not taken on trust |
| Real order history | Fill prices and times for this run |
| Account snapshot | Current value, for the profit and loss figure |
| Previous `state.json` | To append to rather than overwrite the history |
| `bs.py` | For the display-only greeks |

The distinction between "what the agent says it did" and "what Alpaca says happened"
is the whole point. If those two ever differ, the second one is the truth and the
difference is the finding.

## Outputs

`site/state.json`, committed back to the repository. Full schema in
[dashboard.md](dashboard.md). The audit-specific part:

```json
{
  "run": {
    "timestamp": "2026-09-02T13:12:08Z",
    "regime": "NEUTRAL",
    "envelope_allowed": true,
    "agent_action": "placed",
    "envelope_compliance": "PASS",
    "violations": []
  },
  "pnl": {
    "account_value": 100402.50,
    "starting_value": 100000.00,
    "total_pnl": 402.50,
    "total_pnl_pct": 0.40,
    "day_pnl": 62.50,
    "realised": 340.00,
    "unrealised": 62.50
  }
}
```

A failed check looks like:

```json
{
  "envelope_compliance": "FAIL",
  "violations": [
    {
      "rule": "short_strike_min_distance_pct",
      "required": 1.5,
      "actual": 1.31,
      "detail": "Short strike 642 is 1.31% below spot 650.5. Envelope required at least 1.5%."
    }
  ]
}
```

## Logic

1. Read what the account actually holds now, and the orders filled during this run.
2. For each new position, check it against the envelope that was in force:
   - Was this strategy allowed?
   - Is the short strike far enough from where the market was?
   - Is the expiry in the allowed window?
   - Is the size within the contract cap?
   - Is the worst case within $500, and the total within $2,000?
3. Record every mismatch as a violation. Do not stop at the first one.
4. Recompute profit and loss from the account value, split into realised (closed and
   banked) and unrealised (still open and still able to move).
5. Call `bs.py` for the display greeks on each open position.
6. Assemble the new `state.json`, appending this run to the history.
7. Write it and commit it back to the repository. The commit is what makes Netlify
   redeploy.

Note step 2 measures against **where the market was when the order filled**, not where
it is now. Judging a decision by information that arrived after it is a classic
analysis error and would produce fake violations.

## User experience flow

**A clean run.**

1. 13:12 ET. The agent placed a 640/635 put spread three minutes ago.
2. `audit.py` reads positions from Alpaca. Two legs, short 640, long 635, one
   contract, filled for $0.62 credit.
3. It pulls the envelope: put credit spreads, at least 1.5% out, up to 2 contracts.
4. SPY was 651.20 at fill. The 640 strike is 1.72% below that. Clears the floor.
5. Worst case: the $5 gap between strikes, less the $0.62 collected, times 100. That is
   $438. Under the $500 cap. Total open risk $438, under $2,000.
6. Every check passes. `envelope_compliance: PASS`, `violations: []`.
7. Account is at $100,402.50. Up $402.50 overall, $62.50 of it from today.
8. It calls `bs.py` and gets about $29 a day of time decay in our favour.
9. It writes `site/state.json` and commits: `audit: 2026-09-02 13:12 — PASS, +$402.50`.
10. Netlify sees the commit and redeploys in under a minute.
11. Talvin opens the site next morning: a green **PASS** badge, the running profit,
    the trade card, and the agent's reasoning. Roughly ten seconds to understand the
    whole day. Nothing needed doing.

**A violation is found.**

1. Same run, but the fill came back on the 642 strike rather than 640.
2. `audit.py` measures: 642 is 1.31% below the fill price. The envelope required 1.5%.
3. It records the violation shown above. `envelope_compliance: FAIL`.
4. It does **not** hide it, and it does **not** unwind the position. Trading to correct
   an accounting finding is how a small problem becomes a large one. The position keeps
   its own capped worst case regardless.
5. `state.json` carries the FAIL. The commit message says so.
6. The dashboard shows an amber banner: **Envelope violation on this run** with the
   required and actual numbers side by side.
7. Talvin sees amber, reads the two numbers, and knows exactly which rule slipped and
   by how much — without reading any code.
8. In the write-up, this is a strength. "Our agent broke a rule once and our own audit
   caught it and published it" is a far more credible claim than an unblemished record
   nobody verified.

**A halted run.**

1. `gates.py` refused. The agent never ran.
2. `audit.py` still runs. It records the halt, its reason, and the current profit and
   loss.
3. `state.json` gets a run entry with `envelope_allowed: false` and
   `agent_action: "none"`.
4. The dashboard shows the red halt banner and the unchanged profit figure.
5. The history stays complete. Every scheduled run appears, including the ones where
   the right answer was to do nothing.

## Failure modes

| What goes wrong | What happens |
|---|---|
| Positions unreadable | Write a run entry with `envelope_compliance: "UNKNOWN"` and an explanation. Never write `PASS` for a check that did not happen. |
| Greeks calculation fails | Skip that panel, publish everything else. A display extra must not block the record. |
| Commit rejected (branch moved) | Pull, reapply, retry once. If it fails again, log loudly — a stale dashboard is misleading and needs to be noticed. |
| `state.json` is malformed | Do not overwrite it. Write alongside it and log. Losing the history mid-competition would be unrecoverable. |
| Audit itself crashes | The trade already happened and is real in Alpaca either way. The GitHub Actions run goes red, which is the alert. |

The rule here is the opposite of the rest of the system. Elsewhere, when in doubt, do
less. Here, when in doubt, **publish the doubt**.

## Verification

```
python audit.py
```

`assert`-based self-checks against hand-made fills and envelopes:

- A compliant fill produces `PASS` and an empty violations list.
- A strike 1.31% out against a 1.5% requirement produces exactly one violation with
  both numbers present.
- An oversized position produces a violation naming the size rule.
- Multiple breaches produce multiple violations, not just the first.
- A halted run produces a valid entry with `agent_action: "none"`.
- Profit splits correctly into realised and unrealised.

After the first live run, three things must agree: the Alpaca paper dashboard, the
`state.json` in the repository, and the Netlify page. If any two disagree, the
publishing chain is broken and nothing downstream can be trusted.

## Open questions

1. Should a violation trigger an automatic halt for the rest of the day? Cautious, and
   arguably right. But a single borderline strike is a poor reason to stop trading for
   a day when we only have four. `ASSUMPTION:` record it, do not halt, revisit if it
   happens more than once.
2. How much history does `state.json` keep? Over four days, all of it. This becomes a
   real question only if the file gets large, which it will not.
3. Should each run commit separately, or should the day be squashed? Separate commits
   make a clean visible timeline in the repository, which is itself evidence of
   autonomy. Leaning toward separate.
