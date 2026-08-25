# Midas Gate

**Gold decides. SPY executes.**

An autonomous options-trading agent built on Alpaca's MCP server for the
[lablab.ai × Alpaca](https://lablab.ai) AI Trading Agents hackathon.

It sells defined-risk credit spreads on SPY. It does not bet on direction. A gold
trader's read of GLD, GDX and UUP sets how cautious the system is each day, and a
deterministic risk gate decides what is legal *before* the AI is ever asked anything.

---

## Why this design

**We have about five and a half trading days.** Fri Aug 28, Mon Aug 31, Tue Sep 1, Wed
Sep 2, Thu Sep 3, and Fri Sep 4 up to roughly 11:00 ET. No holiday gap — US Labor Day
2026 falls on Sep 7, after the competition ends.

Five days is far too short for a directional bet to mean anything. Guessing the market
correctly over a week is a coin flip, and the competition scores on P&L — so a coin
flip is not a strategy, it is a hope.

So we do not bet on direction. We **sell defined-risk credit spreads**: collect
premium, let time decay pay us daily whichever way the market moves, and cap the worst
case with a second bought leg. That wins roughly 75–80% of the time per trade, and it
turns P&L from luck into an engineering problem.

**The free data feed is "indicative".** Alpaca's free plan
[labels its options data indicative](https://docs.alpaca.markets/us/docs/about-market-data-api).
It does hand you greeks and implied volatility — we confirmed that against the live chain —
but they are modelled numbers on a feed the vendor itself will not call authoritative. The
reliable feed is $99/month.

So we never select strikes by delta. We select by **percentage distance from spot** — a
direct measurement that needs no model at all — and compute our own Black-Scholes greeks
locally, for display only, never as an input to a decision. This removed a $99/month
dependency and is the single most consequential design choice in the project. The
temptation it resists is real: the feed *offers* a plausible delta, and using it would be
one line of code.

**The gold angle is a real person's expertise, not an invented gimmick.** One of us
trades gold professionally. Gold is the market's fear gauge, and his read of it sets
the day's risk regime — how far out of the money we sell, how many positions we hold,
and **how much money is at risk at all**. More fear means smaller and further out,
never bigger. He writes his rules down once, as concrete numeric thresholds, and then
the system runs them for a week without him.

---

## The safety property we are actually proud of

The usual way to keep a trading AI safe is to write the limits into its prompt and
trust it. That is not a guarantee. It is a request, made to something that can be
talked out of things.

So we inverted it.

```
regime.py  →  gates.py  →  agent.py  →  VALIDATOR  →  audit.py
   gold        THE LEGAL      the AI      re-check      verify,
   read        ENVELOPE       chooses     on fresh      classify,
                                          data         publish
```

Ordinary Python (`gates.py`) reads the account and computes the **envelope**: the exact
expiries, strike bands, and maximum size that are permitted at this moment. *Only then*
is the AI called, and it is asked to pick something from inside that envelope.

The agent is not discouraged from breaching a risk limit. **It has no way to express
one.** Every number it could possibly choose was already checked before it was offered.
If a drawdown halt has tripped, `gates.py` emits no envelope at all and the model is
never invoked — no API call, no tokens, no opportunity to reason its way around it.

The model's answer does not go to the broker either. A deterministic **pre-trade
validator** re-runs the same checks against freshly refreshed prices and account state:
a market that moved while the model was thinking cannot turn a legal strike into an
illegal fill. Fail any check and no order is sent — the agent is not asked to patch it.

Then `audit.py` re-reads what actually filled, checks it against the envelope that was
in force, and **publishes violations publicly** on the dashboard if it finds any. A
violation does not merely get displayed: it latches a halt and escalates for human
review. A system that can only report its own successes is not evidence of anything.

Two lines summarise the whole control philosophy:

> **The AI chooses. Deterministic code permits.**
>
> **Learning changes preferences, not permissions.**

### Operating states

Persisted between runs, so a halt survives a workflow rerun and a cautious morning
still binds in the afternoon.

| State | Meaning |
|---|---|
| `ACTIVE` | Everything healthy. Autonomous trading inside the envelope |
| `DEGRADED` | Something non-critical is stale or missing. Trade smaller, or not at all |
| `HALTED` | No new orders. The AI is not called at all |
| `REVIEW_REQUIRED` | Audit violation, partial fill, unknown exposure. A human must look before trading resumes |

### Hard limits

| Limit | Value |
|---|---|
| Maximum loss per contract | $500 (0.5% of the account) |
| Maximum total risk open | **Regime-scaled** (Gold Rules V2): $2,500 RISK_ON / $1,500 NEUTRAL / $1,000 RISK_OFF / $0 STAND_DOWN |
| Daily drawdown halt | −2% — latched, no new positions until tomorrow |
| Competition drawdown halt | −4% — latched, human reset only |
| New position cutoff | 15:30 ET, and none at all on submission day |
| Final close-out | 15:45 ET on the last trading day, so P&L is realised |
| Duplicate protection | One order per run id, ever |

The regime scaling is the point of the gold thesis: it sets how much money is at risk,
not just how far away the strikes are. A fear reading does not merely widen the
strikes, it takes the budget to zero.

---

## How it runs

GitHub Actions cron, twice each weekday — 09:35 ET and 13:05 ET. No server, no machine
left running, nobody awake. The team is in Malaysia; the US market is open from 21:30
to 04:00 local time.

Each run reads the persisted state first — a latched halt ends the run before any model
client is even created — then chains the modules and commits `site/state.json` back to
this repository. That commit is what redeploys the dashboard, and the repository is the
database: small, versioned, publicly auditable, free. The commit history is itself the
evidence of autonomy — results landing at hours when both of us were provably asleep.

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
| [regime.md](docs/regime.md) | `regime.py` | Gold prices in, regime and permissions out |
| [gates.md](docs/gates.md) | `gates.py` | The legal envelope, and the pre-trade validator |
| [bs.md](docs/bs.md) | `bs.py` | Our own option maths, display only |
| [agent.md](docs/agent.md) | `agent.py` | The AI that ranks legal candidates and picks one, or none |
| [audit.md](docs/audit.md) | `audit.py` | Checks the AI, classifies the outcome, publishes |
| [backtest.md](docs/backtest.md) | `backtest.py` | Historical evidence, and the slow learning loop |
| [workflow.md](docs/workflow.md) | `trade.yml` | The clock, the secrets, the persisted state |
| [dashboard.md](docs/dashboard.md) | `site/` | The public record |

Each doc covers purpose, inputs, outputs with literal JSON, the logic, an end-to-end
walkthrough of both a normal run and a failure run, failure modes, and a verification
command. Where a source document was silent, the doc marks an explicit `ASSUMPTION:`
rather than inheriting a silent guess.

[`BUILD_PLAN.md`](BUILD_PLAN.md) is the live build order — what gets built, in what
sequence, and what has to be true before the first live trade.

### The appendix

[`appendix/`](appendix/INDEX.md) holds the superseded first draft and the source
documents it came from: the original `PLAN.md`, the architecture handoff the current
design implements, and the team conversation the gold thresholds came out of.

It is kept deliberately. Three things in the first draft turned out to be wrong — the
trading calendar, a flat risk budget that quietly conceded the P&L criterion, and
placeholder gold thresholds — and the corrections are a more honest account of how this
was built than a clean tree would be.

---

## Status

**Specification complete. Implementation in progress.**

Honest current state, so nothing here is mistaken for more than it is:

- [x] Architecture and strategy decided
- [x] Nine module specifications written, then **rewritten** against the control
      architecture — bounded autonomy, four operating states, pre-trade validation,
      audit escalation, bounded learning. First draft kept in [`appendix/`](appendix/INDEX.md)
- [x] Gold Regime Rules **V1** recorded from the teammate's own numbers, labelled as
      pending his sign-off rather than presented as final
- [x] **Alpaca MCP smoke test passed (Aug 24)** — `alpaca-mcp-server 3.4.7`, 72 tools,
      account and option chain both fetched through MCP. The free feed quotes SPY puts
      two-sided at 1–5¢ spreads, so the largest open technical risk is closed and the
      local-pricing fallback is not needed. It also surfaced three errors in our own
      specs — a wrong env var name, two wrong tool names, and a risk cap that
      contradicted itself. All three fixed
- [ ] `regime.py`, `gates.py`, `bs.py`, `agent.py`, `audit.py`
- [ ] Dashboard
- [ ] Backtest over ~6 months of SPY, V1 frozen before any tuning, for a win-rate
      figure with a method attached

No performance numbers are claimed here yet. When there are some, they will come from
the backtest and from the audited `state.json`, both of which show their working.

---

## Requirements checklist

| Requirement | How it is met |
|---|---|
| Autonomous agent | GitHub Actions cron. No human approves a trade. Humans are *on* the loop, not in it — involved only on a safety-critical exception |
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
