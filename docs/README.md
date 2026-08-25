# Midas Gate — module documentation

Plain-language specs for every part of the system. Written **before** the code, so each
file below is the contract the code has to satisfy.

The strategy and the schedule live in [`appendix/PLAN.md`](../appendix/PLAN.md); the decisions and build
order live in [`../BUILD_PLAN.md`](../BUILD_PLAN.md); the control architecture these docs
implement is [`appendix/MIDAS_GATE_ARCHITECTURE_HANDOFF_FOR_TALVIN_AND_CLAUDE.md`](../appendix/MIDAS_GATE_ARCHITECTURE_HANDOFF_FOR_TALVIN_AND_CLAUDE.md).
This folder is the "how it actually works" layer.

> **What changed since v1.** These docs are a full rewrite. The pre-handoff versions are
> kept unedited in [`appendix/`](../appendix/INDEX.md) — including the three things they got
> wrong (the trading calendar, the flat risk budget, the placeholder gold thresholds).

---

## The one sentence

> Midas Gate is a human-governed, deterministically constrained autonomous SPY options
> trading agent that uses a gold/macro regime to control risk, learns from audited
> outcomes inside its approved envelope, fails toward caution under uncertainty, and
> escalates only safety-critical exceptions to human review.

And the control philosophy in two lines:

> **The AI chooses. Deterministic code permits.**
>
> **Learning changes preferences, not permissions.**

---

## The three facts that shape everything

**1. There are about five and a half trading days.**

| Date | Day | Notes |
|---|---|---|
| Aug 28 | Fri | First live day. Hackathon opens |
| Aug 31 | Mon | |
| Sep 1 | Tue | *Not* a holiday — Labor Day 2026 is Sep 7 |
| Sep 2 | Wed | |
| Sep 3 | Thu | |
| Sep 4 | Fri | Close-out only, to 11:00 ET. Submission 15:00 UTC |

Still far too short to bet on direction and call the result skill — that is a coin flip.
So we do not bet on direction. We **sell options and collect the premium**, which pays us
a little every day simply because time passes. That works in a flat market, a mildly-up
market and a mildly-down market. It turns "did we get lucky" into "did we engineer this
properly".

**2. Alpaca's free option feed labels its prices "indicative".** It does return greeks and
implied volatility — the Stage 0 smoke test confirmed that — but they are modelled numbers
on a feed the vendor will not call authoritative, and the dependable feed is $99/month. So
we never let those numbers pick our trades. We choose contracts by **percentage distance
from where the market is trading right now** — a direct measurement, not a model output.
We compute our own greeks and show them as context only. See [bs.md](bs.md).

**3. An AI that is *asked* to obey a limit has not been constrained.** Prompts are
requests. So the limits are computed in ordinary Python before the model is called, and
re-checked in ordinary Python after it answers. The model never touches a number that
matters.

---

## Bounded autonomy

The governing rule, and the thing a judge should take away:

> **The agent may optimise decisions within the envelope. Only humans may redefine the
> envelope.**

Normal trading is **fully autonomous** — no human approves a trade. Humans are *on* the
loop, not *in* it. A person is involved only on exception: an audit violation, a
broker/system mismatch, an unknown position, a competition-level halt, or a deliberate
change to the regime or risk rules.

---

## The four operating states

Persisted in `state.json` between runs, so a state set at 09:35 still binds at 13:05 and
a halt survives a workflow rerun.

| State | Meaning | Effect |
|---|---|---|
| `ACTIVE` | Everything needed for safe operation is healthy | Autonomous trading, inside the envelope |
| `DEGRADED` | Something non-critical is missing, stale or uncertain | Regime defaults toward caution; allowances cut; may disable new positions |
| `HALTED` | No new orders may be placed | Daily drawdown halt, stale critical SPY data, broker/API failure, repeated order rejection, validator cannot establish a safe state. **The AI is not called at all** |
| `REVIEW_REQUIRED` | A critical inconsistency that must not be auto-ignored | Partial spread, audit violation, broker state ≠ our records, unknown exposure, −4% competition halt. A human must investigate before normal operation resumes |

**Caution is asymmetric.** The system may become more cautious *immediately*. It may not
become materially more aggressive intraday: if 09:35 was RISK_OFF and 13:05 looks
RISK_ON, the cautious state stands until the next trading day.

---

## How the pieces chain together

```
GitHub Actions cron (weekdays, 09:35 + 13:05 ET)
  │
  ├─ 0. state       read persisted state. Competition halt / daily halt /
  │                 REVIEW_REQUIRED still latched? → publish, exit
  │
  ├─ 1. data health read account, positions, orders, market data. Critical data
  │                 missing or stale → HALTED. Secondary missing → DEGRADED
  │
  ├─ 2. regime.py   gold/macro read → RISK_ON | NEUTRAL | RISK_OFF, plus an
  │                 explicit machine-readable permission block
  │
  ├─ 3. gates.py    account + regime → the ENVELOPE: every trade that is legal
  │                 right now. Or a refusal, and no envelope at all
  │
  ├─ 4. agent.py    the AI. Receives envelope + compact learning memory. Ranks the
  │                 legal candidates, picks one or returns NO_TRADE. Explains itself
  │
  ├─ 5. validator   deterministic re-check of the AI's proposal against a freshly
  │      (gates.py) refreshed market and account. Fails → no order is sent
  │
  ├─ 6. execution   the order goes to Alpaca via MCP. One controlled retry on
  │                 rejection, then halt the run
  │
  └─ 7. audit.py    re-read actual fills, compare against the envelope in force,
                    AUDIT_PASS / AUDIT_FAIL, classify the outcome, update the
                    bounded learning memory, write site/state.json
```

Two design choices carry the whole safety story:

- **Step 3 runs before step 4.** By the time the AI is asked anything, the only trades in
  front of it are already legal ones.
- **Step 5 runs after step 4.** The AI's answer never reaches the broker unchecked, and
  the check uses fresh data — so a market that moved while the model was thinking cannot
  smuggle an illegal trade through.

---

## Risk sizing

Maximum loss is **$500 per contract**. Total open risk is **scaled by the regime**,
because the gold thesis should set money at risk, not just strike distance:

| Regime | Total open risk budget | Strategies | Min OTM distance | Max positions | Max contracts/position |
|---|---|---|---|---|---|
| `RISK_ON` | $2,500 | Iron condor, put credit spread | ~1.0% | 3 | 5 |
| `NEUTRAL` | $1,500 | Put credit spread | ~1.5% | 2 | 3 |
| `RISK_OFF` | $1,000 | Put credit spread, reduced size | ~2.5% | 1 | 2 |
| `STAND_DOWN` | $0 | None — put spreads forbidden, latched for the day | ~2.5% | 0 | 0 |

Hard, never regime-scaled: −2% daily drawdown halt (latched for the day), −4% competition
halt (latched, human reset only), $500 per contract, no new positions after 15:30 ET, no
new positions on Sep 4, close everything by 15:45 ET on the last trading day.

> **Corrected at Stage 0 — `ASSUMPTION:` pending confirmation.** The cap was written as
> "$500 per spread" with `max_contracts: 2`. Priced against the live chain, a $5-wide SPY
> spread risks about **$479 for one contract**, so "$500 per spread" allowed roughly one
> contract per position and capped total open risk near **$958**. Reading the $500 as
> **per contract** and letting `max_contracts` carry the size resolves it. Confirm before
> the first live day.

Under V2 sizing `max_contracts` is exactly `budget ÷ $500` — 5 / 3 / 2 / 0 — so the two
limits agree by construction and neither is decorative. In `NEUTRAL`, one full position is
3 × $479 ≈ $1,437 against a $1,500 budget: the first position very nearly exhausts it and
the second is refused by `RISK_BUDGET_EXHAUSTED`. That is intended. The budget binds first;
`max_positions` is the looser of the two.

**Sizing rationale, and what V2 gave up.** V1 sized at `$10,000 / $5,000 / $0` for a
realistic band of roughly +0.6% to +1.2% on $100k. V2 cuts the budgets to roughly a
quarter of that, which cuts the expected capture to roughly a quarter with it — order
**+0.15% to +0.3%**. This is a deliberate trade, made by the teammate: the competition's
downside is latched halts and a blown thesis, and the upside of a bigger number is one
placing. Live pricing for scale: the Aug 26 751/746 spread paid $0.21 credit against $479
risk, about **4.4% return on risk over two days**, so a fully-deployed $1,500 `NEUTRAL`
budget earns on the order of **$66 per cycle**. `RISK_OFF` keeping $1,000 rather than V1's
$0 partly offsets this — V2 trades on days V1 sat out entirely.

---

## Fast and slow learning

| | Fast loop | Slow loop |
|---|---|---|
| Runs | During the competition, every run | Offline, by hand |
| Input | Audited outcomes, classified | Backtest + accumulated outcomes |
| May change | Ranking between legal candidates, liquidity preference, distance preference inside the allowed range, choosing `NO_TRADE` | Proposes a change to the regime or risk rules |
| May never change | Any hard limit, any permission, any threshold | Nothing by itself — a human accepts or rejects, and the change is version-controlled |

Memory is bounded: 3–5 active lessons, last 5–10 outcomes. See [audit.md](audit.md).

Not every loss is a mistake. A correctly selected defined-risk spread that lost because
the market moved is `MARKET_MOVE`, not an error, and must not change behaviour.

---

## The files

| Doc | Module | What it does |
|---|---|---|
| [regime.md](regime.md) | `regime.py` | Gold prices in, regime and permission block out |
| [gates.md](gates.md) | `gates.py` | Account state in, legal envelope out. Also owns the pre-trade validator |
| [bs.md](bs.md) | `bs.py` | Our own option maths, display only |
| [agent.md](agent.md) | `agent.py` | The AI that ranks legal candidates and picks one, or none |
| [audit.md](audit.md) | `audit.py` | Marks the AI's homework, classifies the outcome, publishes |
| [backtest.md](backtest.md) | `backtest.py` | Historical evidence, V1 frozen before tuning |
| [workflow.md](workflow.md) | `.github/workflows/trade.yml` | The clock, the secrets, the persisted state |
| [dashboard.md](dashboard.md) | `site/` | The public record |
| [appendix/INDEX.md](../appendix/INDEX.md) | — | The superseded v1 specs, and what changed |

Deliberately **not** one file per concept. State management, exception handling,
pre-trade validation, learning memory and outcome classification are concepts, not
modules: `gates.py` owns deterministic gating and validation, `audit.py` owns
classification and lesson generation, `state.json` owns persistence.

---

## Glossary

| Term | Plain meaning |
|---|---|
| **option** | A contract to buy or sell a stock at a fixed price by a fixed date. You can buy one, or sell one to someone else. |
| **call / put** | A call bets the price goes up. A put bets it goes down. |
| **strike** | The fixed price written into the option contract. |
| **spot** | What the stock is actually trading at right now. |
| **expiry / DTE** | The date the contract dies. DTE = "days to expiry". We use 1–3 DTE — very short-dated. |
| **premium** | The money paid for an option. When we *sell* one, this is money we receive. |
| **credit spread** | We sell one option and buy a cheaper, further-away one at the same time. We keep the difference. The bought one caps our worst case. This is our entire strategy. |
| **defined risk** | Because of that second bought option, the most we can lose on a trade is a known, fixed number. |
| **iron condor** | Two credit spreads at once — one above the market, one below. Profits when the price stays in the middle. |
| **OTM** ("out of the money") | The strike sits somewhere the stock would have to move to reach. Further out = safer, and less paid. |
| **theta** | The rate at which an option loses value purely because time passes. As sellers, theta flows toward us. |
| **the greeks** | Numbers describing how an option's price reacts to things. We compute our own — see [bs.md](bs.md). |
| **the chain** | Every option contract available on a stock for a given expiry. |
| **SPY / GLD / GDX / UUP / TLT** | Tradeable funds. SPY = US stock market. GLD = gold. GDX = gold miners. UUP = the US dollar. TLT = long-term government bonds. |
| **paper account** | A fake-money Alpaca account with real market prices. Everything here is paper. |
| **MCP** | Model Context Protocol — the standard way an AI is handed tools. Alpaca ship an official MCP server; it is the AI's only route to the market. |
| **cron** | A schedule. "Run this at 09:35 every weekday." |
| **envelope** | Our term: the complete, pre-computed set of trades that are legal at this moment. See [gates.md](gates.md). |
| **pre-trade validator** | The deterministic re-check between the AI's answer and the broker. Same rules, fresher data. |
| **operating state** | `ACTIVE` / `DEGRADED` / `HALTED` / `REVIEW_REQUIRED`. Persisted between runs. |
| **latched** | Once set, stays set until its defined reset. A later recovery in P&L does not clear it. |
| **run id** | `YYYY-MM-DD-0935` or `-1305`. One order per run id, ever. Kills duplicate-run risk. |
| **lesson** | A short, evidence-counted preference learned from audited outcomes. Can reorder legal candidates; can never change what is legal. |
| **fill** | Confirmation that an order actually executed, and at what price. |
| **drawdown** | How far the account is down from its high point. |
| **`NO_TRADE`** | A valid, deliberate autonomous outcome. Not an error. |
