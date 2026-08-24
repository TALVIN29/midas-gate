# `agent.py` — the AI that ranks and picks

> **In plain terms:** this is the actual AI. It is handed a short list of trades it is
> allowed to make plus a few lessons from what happened recently, it looks at the real
> market, picks one — or picks none — and writes down why.

> **What changed since v1** ([appendix/agent.md](appendix/agent.md)): the agent now
> receives a compact **learning memory** alongside the envelope, and its proposal goes to
> the **pre-trade validator** rather than straight to the broker. `NO_TRADE` is promoted
> from "allowed" to an explicitly valid autonomous outcome that is audited and published
> like any trade. Added: the explicit list of things the agent cannot do, and what happens
> when its proposal is rejected.

## Purpose

The hackathon requires an autonomous AI trading agent that uses Alpaca's MCP server and
trades options. This file is that agent.

Its job is narrow on purpose. By the time it runs, `gates.py` has already decided what is
permitted. The agent is not asked "what should we do today" — it is asked *"here are the
trades you may make, here is what we have learned this week, look at the live market and
choose the best one, or choose none."*

That is a question a language model is genuinely good at. Comparing a handful of real
option prices, judging which strike offers decent premium for the distance, noticing the
market looks thin today and standing down — that is judgement, and judgement is what the
model is for. Arithmetic and risk limits are not; those already happened in Python, and
they happen again afterwards.

The reasoning it writes matters as much as the trade. It goes on the public dashboard. A
judge should be able to read, in the agent's own words, why it sold the 640 put and not
the 638.

## Where it sits

**In the middle, fenced on both sides.**

```
gates.py (envelope) → agent.py → gates.py (validator) → execution → audit.py
```

It never places an order directly. If the envelope was refused, or the system is
deterministically halted, it does not run at all and the model is never called.

## Inputs

| Input | Detail |
|---|---|
| The legal envelope | From `gates.py`. Copied verbatim into the system prompt |
| The regime block | Regime, reason, signals — context for the choice |
| Learning memory | 3–5 active lessons, last 5–10 outcomes. From `state.json` |
| Live market data | Via MCP tools, at its own request |
| `ANTHROPIC_API_KEY` | Environment variable. Claude API |
| `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` | Passed through to the MCP server |
| `ALPACA_PAPER=true` | Hardcoded in the workflow, never a secret |
| `DRY_RUN` | Optional. `DRY_RUN=1` means log the proposal, place nothing |

Not an LLM subscription token. A Max-plan OAuth token expires in about a day and cannot
drive a scheduled job. This needs a real API key with a few dollars of credit. Total
expected cost for the whole competition is a few dollars.

## Its tools

The agent's **only** way to touch the market is the official Alpaca MCP server, run via
`uvx alpaca-mcp-server`. No other network access, no shell.

| Tool | What it does |
|---|---|
| `get_option_chain` | The contracts available for an expiry |
| `get_option_snapshot` | Current bid and ask for a specific contract |
| `get_stock_bars` | Recent price history for SPY |
| `get_positions` | What we currently hold |
| `place_option_order` | Place a multi-leg options order |
| `close_position` | Close something we hold |

MCP-or-CLI is a hard hackathon requirement, not a preference. It is also good design:
every market action goes through one auditable official interface, which is exactly what
makes `audit.py` able to check the work afterwards.

## What it may and may not do

| May | May not |
|---|---|
| Rank the legal candidates | Change any risk threshold |
| Select one | Change any regime threshold |
| Explain the choice | Expand the allowed strategies |
| Prefer better liquidity or a slightly wider strike inside the allowed range | Increase permitted size |
| Take a lesson from memory into account when ranking | Override or clear a halt |
| Return `NO_TRADE` | Bypass the pre-trade validator |
| | Improvise a recovery from a critical exception |
| | Modify its own permissions |

This is the bounded-autonomy rule made concrete: **the agent may optimise decisions
within the envelope; only humans may redefine the envelope.**

## Outputs

A proposal, handed to the validator, and — after execution — recorded by `audit.py`:

```json
{
  "timestamp": "2026-09-02T13:07:41Z",
  "run_id": "2026-09-02-1305",
  "action": "PLACE",
  "strategy": "PUT_CREDIT_SPREAD",
  "underlying": "SPY",
  "short_leg": {"strike": 640, "expiry": "2026-09-04", "type": "put"},
  "long_leg":  {"strike": 635, "expiry": "2026-09-04", "type": "put"},
  "contracts": 1,
  "credit_expected": 0.62,
  "max_loss": 438,
  "candidates_considered": [
    {"short": 641, "credit": 0.71, "distance_pct": 1.57, "rejected": "margin too fine against the 1.5% floor"},
    {"short": 639, "credit": 0.48, "distance_pct": 1.87, "rejected": "premium sacrifice not justified"}
  ],
  "lesson_applied": "Prefer additional OTM distance in NEUTRAL when the premium difference is small.",
  "reasoning": "SPY at 651. The 640 put is 1.7% below spot, clearing the 1.5% floor with room to spare. It pays $0.62 against $4.38 of risk. The 642 strike pays more but sits only 1.4% out, outside the envelope. Two days to expiry means most of the decay lands before the weekend."
}
```

Or:

```json
{
  "action": "NO_TRADE",
  "reasoning": "Premiums are unusually thin. Best legal strike pays $0.11 against $4.89 of risk — roughly 2%. Not worth the exposure. Standing down this run."
}
```

`reasoning` is required in both cases. An agent that trades without explaining itself is a
black box and scores badly on both technology and presentation. `candidates_considered`
is what turns "it picked something" into "it compared things" — for the dashboard, and as
the raw material the outcome classifier needs to tell `SELECTION_ERROR` from `NO_ERROR`.

## Logic

1. Read the envelope. If `allowed` is false, log the reason and exit. **The model is
   never called.**
2. Load the learning memory — at most 3–5 lessons and 5–10 recent outcomes, no more.
3. Build the system prompt: the envelope verbatim, the regime and its reason, the lessons,
   the strategy rules, and the instruction that choosing nothing is valid and sometimes
   correct.
4. Start the Claude Agent SDK loop with the MCP tools attached.
5. The agent looks at the market: SPY spot, the chain for the allowed expiries, bids and
   asks on candidate strikes.
6. It ranks the legal candidates and picks one, or returns `NO_TRADE`.
7. If `DRY_RUN=1`, log the proposal and stop.
8. Otherwise hand the proposal to the **validator**. If the validator rejects, the run
   ends with `VALIDATION_REJECTED` — the agent is not asked to patch it.
9. On pass, submit both legs as one order through MCP. On rejection by Alpaca, the
   controlled-retry policy in [gates.md](gates.md) applies — at most one rebuild and
   retry, then halt the run.
10. Write the proposal, the candidates and the reasoning out for `audit.py`.

### What the prompt tells it

- The envelope, copied in exactly as JSON, described as the complete set of what is legal.
- That a deterministic validator will re-check its answer against fresh data, and that an
  out-of-envelope answer will simply be rejected — there is nothing to be gained by
  pushing.
- The base trade: sell a spread, collect premium, cap the loss with the far leg.
- That premium must be worth the risk. A spread paying $0.05 against $5 of risk is a bad
  trade even though it is a legal one.
- The current lessons, framed as preferences, with the explicit note that they cannot
  override the envelope.
- That **placing no trade is a legitimate outcome** and it will not be judged for standing
  down. This matters. An agent that feels obliged to trade will find a bad trade.
- To explain its choice in two or three plain sentences, including what it rejected.

## User experience flow

**A trade gets placed.**

1. 13:05 ET. Envelope: put credit spreads, at least 1.5% out, up to 2 contracts, $4,562 of
   budget left. One lesson in memory about preferring distance in `NEUTRAL`.
2. It asks for SPY: 651.20. It pulls the chain for the two allowed expiries.
3. 1.5% below spot is about 641.4, so it looks at 641, 640, 639.
4. The 640 pays $0.62. The 639 pays $0.48 and is barely safer. The 641 pays more but is
   only 1.57% out — and the lesson says the margin is not worth the few cents.
5. It picks 640/635, one contract, worst case $438.
6. The validator re-checks on refreshed data and passes it. The order goes in.
7. Ten minutes later the dashboard shows a card: **SPY 640/635 put credit spread, $62
   collected, $438 at risk, expires Sep 4** — with the agent's own paragraph, the two
   rejected candidates, and the lesson it applied.
8. Talvin's teammate reads it over breakfast and can tell immediately whether the agent is
   thinking like a trader. That feedback loop is the point.

**Nothing worth trading.**

1. Valid envelope. SPY has drifted sideways all morning and premiums have collapsed.
2. The best legal strike pays $0.11 against $4.89 of risk.
3. The agent judges that ratio not worth taking and returns `NO_TRADE` with its sentence.
4. The dashboard shows a **No trade** card with that sentence, and the audit records it as
   a normal outcome, not a failure.
5. This is a *good* outcome and it should read as one. Passing on a bad trade is the
   strategy working, and it makes a far better story than a forced trade.

**When the envelope was refused.**

1. `gates.py` returned `allowed: false` — the daily loss limit tripped and latched.
2. `agent.py` logs `HALTED: DAILY_DRAWDOWN_HALT — no agent invocation` and exits.
3. No API call, no cost, no possibility of the model reasoning its way past the halt.
4. The dashboard shows the red halt banner, not an agent card.

## Failure modes

| What goes wrong | What happens |
|---|---|
| Envelope refused, or system halted | Exit before the model is called. Costs nothing, risks nothing |
| MCP server will not start | Log and exit without trading. Never fall back to another route — MCP is a requirement, and a fallback path would be an unaudited one |
| Option chain empty or unusable | Report it, place nothing. This is the largest known technical risk in the project; smoke-tested at Stage 0 in `BUILD_PLAN.md` |
| Proposal fails validation | Run ends with `VALIDATION_REJECTED` naming the failed check. The agent is not asked to fix it in place |
| Order rejected by Alpaca | One controlled refresh-and-retry, then halt the run. No free-form retrying |
| Model tries something outside the envelope | The validator stops it before it is sent; if anything still slips through, `audit.py` records a violation and halts trading. Guard and evidence both exist |
| Model API unavailable | Exit without trading. Missing a run costs nothing; trading blind costs money |
| Model returns malformed output | Treat as `NO_TRADE`, log the raw output. An unparseable proposal is not a trade |

## Verification

```
DRY_RUN=1 python agent.py
```

Runs the entire loop — envelope, memory, market data, reasoning, choice — and stops right
before submitting. It logs the exact order it would have placed.

Passing looks like: a full reasoning paragraph, a named spread with both legs, a worst
case under $500, both strikes inside the envelope's distance rule, the candidates it
rejected, and a final line reading `DRY_RUN: order not placed`.

Also verified:

- With a refused envelope, the run exits with **no model call at all** in the log.
- The MCP tool list in the log matches the six tools above, nothing extra.
- A proposal that violates the envelope is rejected by the validator, not executed.
- An empty envelope produces a clean `NO_TRADE` record.
- With a lesson in memory, the chosen candidate and `lesson_applied` are consistent.

Then, before Aug 28, a manual `workflow_dispatch` run in GitHub Actions to prove the whole
path works in CI and not just on a desktop.

## Open questions

1. Should the agent be allowed to close an existing position early? Closing a winner locks
   in profit and is what a real trader would do — but it widens what the agent can do and
   needs its own gate. Leaning toward allowing it with one rule: close only at a profit,
   never at a loss.
2. Should the second daily run see the first run's reasoning? Continuity is nice; it also
   risks the agent talking itself into consistency with a bad earlier call. `ASSUMPTION:`
   start without it — the learning memory already carries forward what matters.
3. How many tool-call rounds before we cut it off? Enough to check a few strikes properly,
   low enough to bound cost and runtime. Around 15, pending the first live run.
