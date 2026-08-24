# `agent.py` — the AI that picks and places the trade

> **In plain terms:** this is the actual AI. It is handed a short list of trades it is
> allowed to make, it looks at the real market, picks one, places it, and writes down
> why it chose that one.

## Purpose

The hackathon requires an autonomous AI trading agent that uses Alpaca's MCP server
and trades options. This file is that agent.

Its job is narrow on purpose. By the time it runs, `gates.py` has already decided what
is permitted. The agent is not asked "what should we do today" — it is asked "here are
the trades you may make, look at the current market and choose the best one, or choose
none."

That is a question a language model is genuinely good at. Comparing a handful of real
option prices, judging which strike offers decent premium for the distance, noticing
that the market looks thin today and standing down — that is judgement, and judgement
is what the model is for. Arithmetic and risk limits are not; those already happened
in Python.

The reasoning it writes down matters as much as the trade. It goes on the public
dashboard. A judge should be able to read, in the agent's own words, why it sold the
640 put and not the 638.

## Where it sits

**Third.** After `gates.py`, before `audit.py`.

`regime.py` → `gates.py` → **`agent.py`** → `audit.py`

It is the only file that places orders. If the envelope was refused, it exits
immediately and never contacts the model at all.

## Inputs

| Input | Detail |
|---|---|
| The envelope | From `gates.py`. Goes into the system prompt |
| `ANTHROPIC_API_KEY` | Environment variable. Claude API, model `claude-sonnet-5` |
| `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` | Passed through to the MCP server |
| `ALPACA_PAPER=true` | Hardcoded in the workflow, never a secret |
| `DRY_RUN` | Optional. `DRY_RUN=1` means log the order, place nothing |

Not an LLM subscription token. A Max-plan OAuth token expires in about a day and
cannot drive a scheduled job. This needs a real API key with a few dollars of credit.
Total expected cost for the whole competition is around $3.

## Its tools

The agent's **only** way to touch the market is the official Alpaca MCP server, run
via `uvx alpaca-mcp-server`. It has no other network access and no shell.

| Tool | What it does |
|---|---|
| `get_option_chain` | The list of available contracts for an expiry |
| `get_option_snapshot` | Current bid and ask for a specific contract |
| `get_stock_bars` | Recent price history for SPY |
| `get_positions` | What we currently hold |
| `place_option_order` | Place a multi-leg options order |
| `close_position` | Close something we hold |

This is a hard hackathon requirement, not a preference — the brief demands the MCP
server or CLI. It is also good design: every market action the agent takes goes
through one auditable, official interface, which is exactly what makes `audit.py` able
to check its work afterwards.

## Outputs

Appended to `state.json` by way of `audit.py`:

```json
{
  "timestamp": "2026-09-02T13:07:41Z",
  "action": "placed",
  "strategy": "put_credit_spread",
  "underlying": "SPY",
  "short_leg": {"strike": 640, "expiry": "2026-09-04", "type": "put"},
  "long_leg": {"strike": 635, "expiry": "2026-09-04", "type": "put"},
  "contracts": 1,
  "credit_received": 0.62,
  "max_loss": 438,
  "order_id": "a1b2c3d4-...",
  "reasoning": "SPY at 651. The 640 put is 1.7% below spot, clearing the 1.5% floor with room to spare. It pays $0.62 against $4.38 of risk. The 642 strike pays more but sits only 1.4% out, outside the envelope. Two days to expiry means most of the decay lands before the weekend."
}
```

`reasoning` is required. An agent that trades without explaining itself is a black box
and scores badly on both technology and presentation.

## Logic

1. Read the envelope. If `allowed` is false, log the reason and exit. **The model is
   never called.**
2. Build the system prompt: the envelope verbatim, the strategy rules, and the
   instruction that choosing nothing is a valid and sometimes correct answer.
3. Start the Claude Agent SDK loop with the MCP tools attached.
4. The agent looks at the market: current SPY price, the option chain for the allowed
   expiries, the bids and asks on candidate strikes.
5. It picks a spread that sits inside the envelope, or decides nothing is worth doing.
6. If `DRY_RUN=1`, it logs the order it would have placed and stops.
7. Otherwise it calls `place_option_order` with both legs as one order.
8. It writes its reasoning and the order details out for `audit.py`.

### What the prompt tells it

- The envelope, copied in exactly as JSON.
- That the envelope is the complete set of what is legal, and that anything outside it
  will be rejected by the broker and caught by the audit afterwards.
- The base trade: sell a spread, collect premium, cap the loss with the far leg.
- That premium must be worth the risk — a spread paying $0.05 against $5 of risk is a
  bad trade even though it is a legal one.
- That **placing no trade is a legitimate outcome**, and it will not be judged for
  standing down. This matters. An agent that feels obliged to trade will find a bad
  trade.
- To explain its choice in two or three plain sentences, including what it rejected.

## User experience flow

**A trade gets placed.**

1. 13:05 ET. The envelope arrived: put credit spreads, at least 1.5% out, up to 2
   contracts, $1,540 of risk budget left.
2. The agent asks for the current SPY price. It is 651.20.
3. It pulls the option chain for the two allowed expiry dates.
4. It works out where 1.5% below spot falls — about 641.4 — and looks at strikes below
   that: 641, 640, 639.
5. It checks bids on each. The 640 pays $0.62. The 639 pays $0.48 and is barely safer.
   The 641 pays more but is only 1.57% out, cutting the margin fine.
6. It picks the 640/635 spread, one contract. Worst case $438, comfortably under the
   $500 cap.
7. It calls `place_option_order` with both legs together. Alpaca confirms.
8. It writes its reasoning.
9. `audit.py` runs, checks the fill against the envelope, and publishes.
10. Ten minutes later the dashboard shows a new card: **SPY 640/635 put credit spread,
    $62 collected, $438 at risk, expires Sep 4** — and underneath, the agent's own
    paragraph explaining the choice.
11. Talvin's teammate reads it over breakfast and can immediately tell whether the
    agent is thinking like a trader. That feedback loop is the point.

**Nothing worth trading.**

1. Same setup, valid envelope.
2. SPY has been drifting sideways all morning and premiums have collapsed. The best
   legal strike pays $0.11 against $4.89 of risk.
3. The agent judges that ratio not worth taking and places no order.
4. It writes: `"Premiums are unusually thin. Best legal strike pays $0.11 against
   $4.89 of risk — roughly 2%. Not worth the exposure. Standing down this run."`
5. The dashboard shows a **No trade** card with that sentence.
6. This is a *good* outcome, and it should read as one. The system passing on a bad
   trade is the strategy working, and it makes a far better story in the write-up than
   a forced trade would.

**When the envelope was refused.**

1. `gates.py` returned `allowed: false` — the daily loss limit tripped.
2. `agent.py` reads it, logs `HALTED: DAILY_DRAWDOWN_HALT — no agent invocation`, and
   exits.
3. No API call, no cost, no possibility of the model reasoning its way past the halt.
4. The dashboard shows the red halt banner from `gates.py`, not an agent card.

## Failure modes

| What goes wrong | What happens |
|---|---|
| Envelope refused | Exit before the model is called. Costs nothing, risks nothing. |
| MCP server will not start | Log the failure and exit without trading. Never fall back to placing orders another way — MCP is a requirement, and a fallback path would be an unaudited one. |
| Option chain empty or unusable | The agent reports it and places nothing. This is the biggest known technical risk in the project; see PLAN.md build step 2. |
| Order rejected by Alpaca | Log the rejection with its reason. Do not retry blindly — a rejection usually means our understanding of the account is wrong, and repeating a misunderstanding is worse than stopping. |
| The model tries something outside the envelope | Alpaca rejects it, and `audit.py` records the attempt as a violation. Both the guard and the evidence exist. |
| Model API unavailable | Exit without trading. Missing a run costs nothing; trading blind costs money. |

## Verification

```
DRY_RUN=1 python agent.py
```

Runs the entire loop — envelope, market data, model reasoning, choice — and stops
right before placing the order. It logs the exact order it would have submitted.

Passing looks like: a full reasoning paragraph, a named spread with both legs, a
worst-case figure under $500, both strikes inside the envelope's distance rule, and a
final line reading `DRY_RUN: order not placed`.

Also verified:

- With a refused envelope, the run exits with no model call in the log at all.
- The MCP tool list in the log matches the six tools above, with nothing extra.

Then, before Aug 29, a manual `workflow_dispatch` run in GitHub Actions to prove the
whole path works in CI and not just on a desktop.

## Open questions

1. Should the agent be allowed to close an existing position early, or only open new
   ones? Closing a winner early locks in profit and is what a real trader would do.
   Adding it also widens what the agent can do, which needs its own gate. Leaning
   toward allowing it with a rule: close only at a profit, never at a loss.
2. Should the second daily run see the first run's reasoning? Continuity is nice; it
   also risks the agent talking itself into consistency with a bad earlier call.
   `ASSUMPTION:` start without it.
3. How many tool-call rounds should it get before we cut it off? Enough to check a few
   strikes properly, low enough to bound cost and runtime. Around 15 seems right,
   pending the first live run.
