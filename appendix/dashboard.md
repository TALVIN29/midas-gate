# `site/` — the public dashboard

> **In plain terms:** a single web page that shows what the agent is doing and why.
> No server behind it — it just reads one file that the audit step writes.

## Purpose

The hackathon requires a hosted app URL, and it is judged partly on presentation. But
the dashboard has a job beyond being a submission checkbox: it is the only way anyone
— Talvin, his teammate, a judge — can see what happened without reading code or
logging into Alpaca.

The design constraint that shapes everything: **it is completely static.** Two HTML
files' worth of content and one JSON file, served by Netlify. No backend, no database,
no API layer.

That is not laziness, it is a security property. A backend would need our Alpaca
credentials in order to fetch anything live, and any credential reachable from a public
URL is a credential at risk. Here there is nothing to leak. The page reads a file that
was already written by a trusted process. Even if the entire site were compromised, an
attacker would gain a read-only copy of results that are public anyway.

It is also the honesty mechanism. The page shows what `audit.py` verified — including
violations and halts. It is not a marketing page for the agent; it is the record.

## Where it sits

**At the end, on the other side of the wall.**

```
audit.py → writes site/state.json → git commit
                                      ↓
                                   Netlify redeploys
                                      ↓
                              site/index.html reads state.json
```

Nothing in `site/` can affect trading. Traffic could arrive by the thousand and the
agent would neither know nor care.

## Inputs

One file: `site/state.json`, written by `audit.py` and fetched by the page on load.

That file is the contract between the two halves of the project. As long as its shape
holds, the page and the Python can be changed independently.

## The `state.json` schema

```json
{
  "updated_at": "2026-09-02T13:12:08Z",
  "competition": {
    "start": "2026-08-28",
    "end": "2026-09-04",
    "account_id": "PA3XXXXXXXXX"
  },
  "status": {
    "state": "ACTIVE",
    "halt_reason": null,
    "regime": "NEUTRAL",
    "regime_reason": "Gold up while stocks slipped, but modestly. Dollar firm."
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
    "risk_budget_usd": 2000
  },
  "positions": [
    {
      "strategy": "put_credit_spread",
      "underlying": "SPY",
      "short_leg": {"strike": 640, "expiry": "2026-09-04", "type": "put"},
      "long_leg": {"strike": 635, "expiry": "2026-09-04", "type": "put"},
      "contracts": 1,
      "credit_received": 0.62,
      "max_loss": 438,
      "unrealised_pnl": 62.50,
      "computed_greeks": {"theta": 0.29, "delta": -0.11}
    }
  ],
  "runs": [
    {
      "timestamp": "2026-09-02T13:12:08Z",
      "regime": "NEUTRAL",
      "envelope_allowed": true,
      "agent_action": "placed",
      "envelope_compliance": "PASS",
      "violations": [],
      "reasoning": "SPY at 651. The 640 put is 1.7% below spot..."
    }
  ]
}
```

`status.state` is one of `ACTIVE`, `HALTED_TODAY`, `HALTED_COMPETITION`, or
`CLOSED_OUT`. It drives the banner colour and is the first thing a reader sees.

`runs` is a full history, newest first — including runs that traded nothing and runs
that were halted. A record that only shows the interesting days is not a record.

## What the page shows

Top to bottom, in order of what matters:

1. **Status banner.** Green for active, red for halted, grey when closed out. Carries
   the halt reason in plain words when there is one.
2. **Profit and loss.** The headline number, split into banked and still-open. Judges
   score on this, so it is large and unambiguous.
3. **Regime badge.** Today's mood with the sentence explaining it. This is where the
   gold angle becomes visible to a reader who has not read the write-up.
4. **Risk used.** "$438 of $2,000" and "1 of 2 positions", as bars. Shows at a glance
   that the system operates well inside its limits — which is more reassuring than any
   description of the limits would be.
5. **Open positions.** One card each: the spread, what we collected, the worst case,
   where it stands now, and the locally-computed time decay with its footnote.
6. **Run history.** Newest first, each with the agent's own reasoning. **This is the
   most interesting part of the page** and the thing that separates this from a
   dashboard any trading bot could produce. Anyone can show a profit figure; showing
   the agent's stated reasoning next to what it actually did, verified, is different.
7. **How it works.** A short explanation of the envelope idea, linking back to these
   docs and the repository.

Design brief in one line: this should read like a trading desk's status board, not a
consumer fintech app. Dense, factual, no celebration of a profit figure that is four
days old and might reverse tomorrow.

## User experience flow

**A judge opens the URL, cold.**

1. Page loads instantly. It is static.
2. It fetches `state.json` — one small file, same origin.
3. Green banner: **ACTIVE**. Profit: **+$402.50 (0.40%)**.
4. Regime badge: **NEUTRAL**, with the gold sentence beneath it. Within about five
   seconds they have understood there is a real thesis here, not just a bot.
5. Risk bars show it running at roughly a fifth of its allowance. That reads as
   discipline.
6. They scroll to the run history and read the agent's reasoning on the most recent
   trade — the strikes it considered, the one it chose, why it rejected the others.
7. They see a `PASS` badge on that run and click through to `audit.md` to find out what
   was checked. The claim is backed rather than asserted.
8. Total time: under two minutes, no code read, no questions needed.

**Talvin checks in over breakfast.**

1. 08:00 Malaysia time. He opens the page on his phone.
2. Banner green, number up, one position open, no violations.
3. He closes the phone. Ten seconds. Nothing to do.
4. The page is deliberately built so that the normal outcome of checking it is doing
   nothing. If it demanded attention, the system would not be autonomous.

**Something went wrong.**

1. He opens it and the banner is red: **HALTED FOR TODAY — down 2.25%, limit 2.0%.**
2. Underneath, the run history shows the halt with its timestamp, and the last trade
   before it with the agent's reasoning still readable.
3. He can see exactly what happened and that the system stopped itself correctly.
4. Nothing is required of him. Tomorrow's first run re-reads the account and resumes on
   its own if the day opens above the line. The page says so.

**The data is stale.**

1. `state.json` has an `updated_at` timestamp. The page compares it against now.
2. If the most recent update is older than about six hours during market days, an
   amber notice appears: **Last updated 9 hours ago — a scheduled run may have
   failed.**
3. This matters more than it sounds. A dashboard showing yesterday's profit as though
   it were live is worse than a dashboard showing an error, and a static page has no
   other way to know it has gone stale.

## Failure modes

| What goes wrong | What happens |
|---|---|
| `state.json` missing | Show a clear "no data yet" state, not a broken page or a blank screen. |
| `state.json` malformed | Catch it and show "could not read the latest state". Never render half a page of numbers from a partial parse. |
| Data is stale | Amber staleness notice, as above. |
| Netlify has not redeployed | Same as stale. The timestamp catches it either way. |
| A field is missing from the JSON | Render everything else. One absent panel must not blank the page. |

Every case above shows the reader something true. There is no failure mode where the
page displays a confident number it cannot support.

## Verification

- Open the deployed URL and confirm the numbers match `site/state.json` in the
  repository.
- Confirm those numbers also match the Alpaca paper dashboard. Three sources agreeing
  is the real test; two agreeing proves only that one process ran.
- View source and search for `key`, `secret`, and `token`. There must be nothing. The
  page has no credentials because it needs none.
- Rename `state.json` temporarily and reload — the "no data yet" state must appear
  rather than a broken layout.
- Hand-edit `updated_at` to a day ago and reload — the staleness notice must appear.
- Check it on a phone. Talvin will read it on a phone every morning.

## Open questions

1. Should there be a chart of the account value over time? Four days is roughly eight
   data points, which is not really a chart. A simple sparkline is probably the honest
   amount of visualisation for the amount of data.
2. Should the site auto-refresh? A refresh every few minutes would keep a judge's open
   tab current during the demo. Cheap to add, small benefit. Leaning yes.
3. Should the account ID be shown publicly? It is a required submission field and a
   paper account, so there is no real risk, and showing it is a small credibility win —
   it says the results are checkable. `ASSUMPTION:` show it.
