# `site/` — the public record

> **In plain terms:** a single web page that shows what the agent is doing, what it was
> allowed to do, whether it obeyed, and what it learned. No server behind it — it just
> reads one file that the audit step writes.

> **What changed since v1** ([appendix/dashboard.md](appendix/dashboard.md)): the page now
> surfaces the whole control architecture, not just P&L. Added: the four operating states
> and the reason for the current one, the legal envelope summary, the pre-trade validation
> result, the outcome classification, the active learning lessons, and any human review or
> reset. The status vocabulary changed from `ACTIVE / HALTED_TODAY / HALTED_COMPETITION /
> CLOSED_OUT` to the four handoff states plus a latched-halt detail field.

## Purpose

The hackathon requires a hosted app URL and is judged partly on presentation. But the
dashboard has a job beyond being a submission checkbox: it is the only way anyone —
Talvin, his teammate, a judge — can see what happened without reading code or logging into
Alpaca.

The design constraint that shapes everything: **it is completely static.** One HTML page
and one JSON file, served by Netlify. No backend, no database, no API layer.

That is not laziness, it is a security property. A backend would need our Alpaca
credentials to fetch anything live, and any credential reachable from a public URL is a
credential at risk. Here there is nothing to leak. The page reads a file written by a
trusted process. Even if the entire site were compromised, an attacker would gain a
read-only copy of results that are public anyway.

It is also the honesty mechanism. The page shows what `audit.py` verified — including
violations, halts, rejected proposals and runs that did nothing. It is not a marketing
page for the agent; it is the record. The handoff is explicit: exceptions are never hidden
from the public dashboard.

## Where it sits

**At the end, on the other side of the wall.**

```
audit.py → writes site/state.json → git commit
                                      ↓
                                   Netlify redeploys
                                      ↓
                              site/index.html reads state.json
```

Nothing in `site/` can affect trading. Traffic could arrive by the thousand and the agent
would neither know nor care.

## Inputs

One file: `site/state.json`, written by `audit.py` and fetched by the page on load. That
file is the contract between the two halves of the project. As long as its shape holds,
the page and the Python can change independently.

## The `state.json` schema

```json
{
  "updated_at": "2026-09-02T13:12:08Z",
  "competition": {
    "start": "2026-08-28",
    "end": "2026-09-04",
    "account_id": "PA3XXXXXXXXX",
    "rules_version": "V1-pending-signoff"
  },
  "status": {
    "operating_state": "ACTIVE",
    "state_reason": "All critical data fresh. No latched halts.",
    "daily_halt": false,
    "competition_halt": false,
    "review_required": false,
    "regime": "NEUTRAL",
    "regime_measured": "NEUTRAL",
    "regime_reason": "Gold up while stocks slipped, but modestly. Dollar firm.",
    "put_spreads_allowed": true,
    "signals": {
      "gld_change_pct": 0.62,
      "spy_change_pct": -0.18,
      "gdx_change_pct": 0.05,
      "uup_change_pct": 0.31,
      "tlt_change_pct": -0.10
    }
  },
  "envelope": {
    "allowed": true,
    "strategies": ["PUT_CREDIT_SPREAD"],
    "expiries": ["2026-09-03", "2026-09-04"],
    "short_strike_min_distance_pct": 1.5,
    "max_contracts": 2,
    "max_risk_per_spread_usd": 500,
    "risk_budget_usd": 5000,
    "remaining_risk_budget_usd": 4062
  },
  "pnl": {
    "account_value": 100402.50,
    "starting_value": 100000.00,
    "total_pnl": 402.50,
    "total_pnl_pct": 0.40,
    "day_pnl": 62.50,
    "realised": 340.00,
    "unrealised": 62.50
  },
  "risk": {
    "open_positions": 1,
    "max_positions": 2,
    "risk_used_usd": 438,
    "risk_budget_usd": 5000,
    "daily_drawdown_pct": -0.10,
    "competition_drawdown_pct": 0.40
  },
  "positions": [
    {
      "strategy": "PUT_CREDIT_SPREAD",
      "underlying": "SPY",
      "short_leg": {"strike": 640, "expiry": "2026-09-04", "type": "put"},
      "long_leg":  {"strike": 635, "expiry": "2026-09-04", "type": "put"},
      "contracts": 1,
      "credit_received": 0.62,
      "max_loss": 438,
      "unrealised_pnl": 62.50,
      "computed_greeks": {"theta": 0.29, "delta": -0.11}
    }
  ],
  "learning": {
    "active_lessons": [
      {
        "type": "selection",
        "lesson": "Prefer additional OTM distance in NEUTRAL when the premium difference is small.",
        "evidence_count": 3,
        "confidence": "MEDIUM",
        "last_observed": "2026-09-02T13:12:08Z"
      }
    ],
    "recent_outcomes": ["NO_ERROR", "MARKET_MOVE", "NO_ERROR"]
  },
  "human_actions": [
    {
      "timestamp": "2026-09-01T22:40:00Z",
      "actor": "Talvin",
      "action": "CLEARED_REVIEW_REQUIRED",
      "note": "Single-leg fill was an Alpaca-side partial. Leg closed manually, exposure confirmed flat."
    }
  ],
  "runs": [
    {
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
      "lesson_applied": "Prefer additional OTM distance in NEUTRAL when the premium difference is small.",
      "reasoning": "SPY at 651. The 640 put is 1.7% below spot..."
    }
  ]
}
```

`status.operating_state` is one of `ACTIVE`, `DEGRADED`, `HALTED`, `REVIEW_REQUIRED`. It
drives the banner colour and is the first thing a reader sees. `state_reason` is always
populated — a state without a stated reason is not information.

`regime` vs `regime_measured` exist so the asymmetric-caution rule is visible rather than
hidden: when they differ, the page says **measured RISK_ON, permissions held at RISK_OFF
from this morning**.

`runs` is a full history, newest first — including runs that traded nothing, runs that
were halted, and proposals the validator rejected. A record that only shows the
interesting days is not a record.

Nothing in this file is a credential and nothing in it is sensitive broker information.
The account ID is a paper account and a required submission field.

## What the page shows

Top to bottom, in order of what matters:

1. **State banner.** Green `ACTIVE`, amber `DEGRADED`, red `HALTED`, purple
   `REVIEW_REQUIRED`. Always carries `state_reason` in plain words, and names any latched
   halt with the number that triggered it.
2. **Profit and loss.** The headline number, split into banked and still-open. Judges
   score on this, so it is large and unambiguous.
3. **Regime badge.** Today's regime with the sentence explaining it, the five signal
   numbers underneath, and the `V1` rules label. This is where the gold angle becomes
   visible to a reader who has not read the write-up. When permissions are held from a
   more cautious earlier run, it says so.
4. **The envelope.** What was legal on this run: strategy, minimum distance, max
   contracts, budget. Directly beside the trade that was chosen. This is the single panel
   that communicates bounded autonomy without a paragraph of explanation — a reader sees
   the constraint and the choice side by side.
5. **Risk used.** "$438 of $5,000" and "1 of 2 positions", as bars, plus the distance to
   the −2% and −4% halts. Shows at a glance that the system operates well inside its
   limits, which is more reassuring than any description of the limits.
6. **Open positions.** One card each: the spread, what we collected, the worst case, where
   it stands now, and the locally-computed time decay with its footnote.
7. **Run history.** Newest first, each with: the operating state, the validation result,
   the agent's own reasoning, the audit result, and the outcome classification. **This is
   the most interesting part of the page.** Anyone can show a profit figure; showing the
   agent's stated reasoning next to what it actually did, verified and classified, is
   different.
8. **What we have learned.** The active lessons with their evidence counts, and a line
   stating plainly that lessons reorder legal choices and can never change a limit.
9. **Human actions.** Any review, reset or intervention, with who and why. Visible
   governance is the point — a system that quietly self-heals from a critical exception
   is not the system described in these docs.
10. **How it works.** A short explanation of the envelope idea and the four states,
    linking back to these docs and the repository.

Design brief in one line: this should read like a trading desk's status board, not a
consumer fintech app. Dense, factual, no celebration of a profit figure that is four days
old and might reverse tomorrow.

## User experience flow

**A judge opens the URL, cold.**

1. Page loads instantly. It is static.
2. It fetches `state.json` — one small file, same origin.
3. Green banner: **ACTIVE**. Profit: **+$402.50 (0.40%)**.
4. Regime badge: **NEUTRAL**, with the gold sentence and the five signals beneath it.
   Within about five seconds they have understood there is a real thesis here, not a bot.
5. The envelope panel sits next to the trade: *allowed — put spreads, ≥1.5% out, ≤2
   contracts, $5,000 budget* against *chose — 640/635, 1 contract, $438 at risk*. The
   control story lands without being explained.
6. Risk bars show it running at under a tenth of its allowance. That reads as discipline.
7. They scroll to the run history and read the agent's reasoning on the most recent trade
   — the strikes it considered, the one it chose, why it rejected the others — then the
   `AUDIT_PASS` badge and `NO_ERROR` classification beside it.
8. They click through to `audit.md` to find out what was checked. The claim is backed
   rather than asserted.
9. Total time: under two minutes, no code read, no questions needed.

**Talvin checks in over breakfast.**

1. 08:00 Malaysia. He opens the page on his phone.
2. Banner green, number up, one position open, no violations, no human action needed.
3. He closes the phone. Ten seconds.
4. The page is deliberately built so that the normal outcome of checking it is doing
   nothing. If it demanded attention, the system would not be autonomous.

**Something needs him.**

1. The banner is purple: **REVIEW REQUIRED — single-leg fill on the 640/635 spread.
   Autonomous trading halted.**
2. The run history shows the fill, the audit finding, and the last clean trade before it.
3. This is the one case where the page *is* asking for something. It says exactly what is
   inconsistent and what will not resume until he looks.
4. After he resolves it, his action appears in the Human actions panel with his note. The
   history shows the halt, the review and the resumption as three separate, dated facts.

**The data is stale.**

1. `state.json` carries `updated_at`. The page compares it against now.
2. If the most recent update is older than about six hours on a trading day, an amber
   notice appears: **Last updated 9 hours ago — a scheduled run may have failed.**
3. This matters more than it sounds. A dashboard showing yesterday's profit as though it
   were live is worse than one showing an error, and a static page has no other way to
   know it has gone stale.

## Failure modes

| What goes wrong | What happens |
|---|---|
| `state.json` missing | Show a clear "no data yet" state, not a broken page or a blank screen |
| `state.json` malformed | Catch it and show "could not read the latest state". Never render half a page of numbers from a partial parse |
| Data is stale | Amber staleness notice, as above |
| Netlify has not redeployed | Same as stale. The timestamp catches it either way |
| A field is missing from the JSON | Render everything else. One absent panel must not blank the page |
| A run has `audit_result: "UNKNOWN"` | Render it as unknown, never as a pass |

Every case above shows the reader something true. There is no failure mode where the page
displays a confident number it cannot support.

## Verification

- Open the deployed URL and confirm the numbers match `site/state.json` in the repository.
- Confirm those numbers also match the Alpaca paper dashboard. Three sources agreeing is
  the real test; two agreeing proves only that one process ran.
- View source and search for `key`, `secret`, `token`. There must be nothing. The page has
  no credentials because it needs none.
- Hand-edit the state to each of the four operating states and reload — each must render
  its own banner, colour and reason.
- Hand-edit a run to `AUDIT_FAIL` with a violation and reload — the violation numbers must
  be visible without expanding anything.
- Rename `state.json` temporarily and reload — the "no data yet" state must appear rather
  than a broken layout.
- Hand-edit `updated_at` to a day ago and reload — the staleness notice must appear.
- Check it on a phone. Talvin will read it on a phone every morning.

## Open questions

1. A chart of account value over time? About eleven data points across the window, which
   is not really a chart. A sparkline is probably the honest amount of visualisation for
   the amount of data.
2. Auto-refresh? A refresh every few minutes keeps a judge's open tab current during the
   demo. Cheap, small benefit. Leaning yes.
3. Show the account ID publicly? Required submission field, paper account, no real risk,
   and showing it says the results are checkable. `ASSUMPTION:` show it.
4. How much of the learning memory to show — the active lessons only, or the outcome
   history too? Currently both, since the outcome classes are what prove the system does
   not treat every loss as a mistake.
