# Midas Gate

**Gold decides. SPY executes.**

An autonomous options-trading agent built on Alpaca's MCP server for the
[lablab.ai × Alpaca](https://lablab.ai) AI Trading Agents hackathon.

It sells defined-risk credit spreads on SPY. It does not bet on direction. A gold
trader's read of GLD, GDX and UUP sets how cautious the system is each day, and a
deterministic risk gate decides what is legal *before* the AI is ever asked anything.

---

## Why this design

**We had about four trading days.** Aug 29, Sep 2, Sep 3, and Sep 4 up to roughly
11:00 ET. Labor Day closes Sep 1.

Four days is far too short for a directional bet to mean anything. Guessing the market
correctly over four days is a coin flip, and the competition scores on P&L — so a coin
flip is not a strategy, it is a hope.

So we do not bet on direction. We **sell defined-risk credit spreads**: collect
premium, let time decay pay us daily whichever way the market moves, and cap the worst
case with a second bought leg. That wins roughly 75–80% of the time per trade, and it
turns P&L from luck into an engineering problem.

**The free data feed is "indicative".** Alpaca's free plan
[labels its options data indicative](https://docs.alpaca.markets/us/docs/about-market-data-api),
and the greeks that come with it are not dependable. The reliable feed is $99/month.

So we never select strikes by delta. We select by **percentage distance from spot** — a
direct measurement that cannot be wrong — and compute our own Black-Scholes greeks
locally, for display only, never as an input to a decision. This removed a $99/month
dependency and is the single most consequential design choice in the project.

**The gold angle is a real person's expertise, not an invented gimmick.** One of us
trades gold professionally. Gold is the market's fear gauge, and his read of it sets
the day's risk regime — how far out of the money we sell, how many positions we hold.
More fear means smaller and further out, never bigger. He writes his rules down once,
as concrete numeric thresholds, and then the system runs them for four days without
him.

---

## The safety property we are actually proud of

The usual way to keep a trading AI safe is to write the limits into its prompt and
trust it. That is not a guarantee. It is a request, made to something that can be
talked out of things.

So we inverted it.

```
regime.py  →  gates.py  →  agent.py  →  audit.py
   gold        THE LEGAL      the AI       verify and
   read        ENVELOPE       chooses      publish
```

Ordinary Python (`gates.py`) reads the account and computes the **envelope**: the exact
expiries, strike bands, and maximum size that are permitted at this moment. *Only then*
is the AI called, and it is asked to pick something from inside that envelope.

The agent is not discouraged from breaching a risk limit. **It has no way to express
one.** Every number it could possibly choose was already checked before it was offered.
If a drawdown halt has tripped, `gates.py` emits no envelope at all and the model is
never invoked — no API call, no tokens, no opportunity to reason its way around it.

Then `audit.py` re-reads what actually filled, checks it against the envelope that was
in force, and **publishes violations publicly** on the dashboard if it finds any. A
system that can only report its own successes is not evidence of anything.

### Hard limits

| Limit | Value |
|---|---|
| Maximum loss per spread | $500 (0.5% of the account) |
| Maximum total risk open | $2,000 |
| Daily drawdown halt | −2% — no new positions until tomorrow |
| Competition drawdown halt | −4% — stop entirely |
| New position cutoff | 15:30 ET, and none at all on submission day |
| Final close-out | 15:45 ET on the last trading day, so P&L is realised |

---

## How it runs

GitHub Actions cron, twice each weekday — 09:35 ET and 13:05 ET. No server, no machine
left running, nobody awake. The team is in Malaysia; the US market is open from 21:30
to 04:00 local time.

Each run chains the four modules, then commits `site/state.json` back to this
repository. That commit is what redeploys the dashboard. The commit history is itself
the evidence of autonomy — results landing at hours when both of us were provably
asleep.

The dashboard is completely static. It has no backend and therefore no credentials to
leak: it reads one JSON file that a trusted process already wrote.

---

## Documentation

Every module was specified in plain English **before any code was written**. The specs
are the contract the implementation has to satisfy. They are written for a reader who
does not code — one of us doesn't.

Start with **[`docs/README.md`](docs/README.md)**, which has the full chain diagram and
a glossary.

| Doc | Module | What it does |
|---|---|---|
| [regime.md](docs/regime.md) | `regime.py` | Gold prices in, today's risk mood out |
| [gates.md](docs/gates.md) | `gates.py` | Account state in, the legal envelope out |
| [bs.md](docs/bs.md) | `bs.py` | Our own option maths, display only |
| [agent.md](docs/agent.md) | `agent.py` | The AI that picks and places the trade |
| [audit.md](docs/audit.md) | `audit.py` | Checks the AI, publishes the results |
| [backtest.md](docs/backtest.md) | `backtest.py` | Historical evidence the strategy works |
| [workflow.md](docs/workflow.md) | `trade.yml` | The clock that runs it all |
| [dashboard.md](docs/dashboard.md) | `site/` | The public page |

[`PLAN.md`](PLAN.md) holds the strategy, the schedule, and the decisions behind both.

Each doc covers purpose, inputs, outputs with literal JSON, the logic, an end-to-end
walkthrough of both a normal run and a failure run, failure modes, and a verification
command. Where `PLAN.md` was silent, the doc marks an explicit `ASSUMPTION:` rather
than inheriting a silent guess.

---

## Status

**Specification complete. Implementation in progress.**

Honest current state, so nothing here is mistaken for more than it is:

- [x] Architecture and strategy decided
- [x] Nine module specifications written
- [ ] Alpaca MCP server smoke test — confirming the indicative feed returns usable
      bid/ask on an option chain. **This is the largest open technical risk.** If the
      chain is unusable, strike selection falls back to `get_stock_bars` plus our own
      pricing
- [ ] `regime.py` — currently ships a clearly marked **PLACEHOLDER** rule set. It is a
      guess and must be replaced with the teammate's real thresholds before going live
- [ ] `gates.py`, `bs.py`, `agent.py`, `audit.py`
- [ ] Backtest over ~6 months of SPY, for a win-rate figure with a method attached
- [ ] Dashboard

No performance numbers are claimed here yet. When there are some, they will come from
the backtest and from the audited `state.json`, both of which show their working.

---

## Requirements checklist

| Requirement | How it is met |
|---|---|
| Autonomous agent | GitHub Actions cron. No human in the loop across the competition |
| Alpaca MCP server or CLI | The MCP server is the agent's **only** route to the market. No fallback path exists, by design — a fallback would be an unaudited one |
| Must trade options | Every trade is a multi-leg options spread. Nothing else is placeable |
| Fresh paper account at $100,000 | Opened at kickoff, account ID in the submission |
| Public repo | This one |
| Hosted app | Static dashboard on Netlify |

---

## Team

Two people. One trades gold professionally and owns the regime rules. One built the
system. Neither writes production code by hand — the implementation is written by
Claude Code from the specifications in `docs/`, which is precisely why those
specifications are as detailed as they are.

## Licence

MIT.
