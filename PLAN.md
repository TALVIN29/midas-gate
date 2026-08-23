# Midas Gate — Alpaca AI Trading Agents Hackathon

## Context

lablab.ai x Alpaca hackathon. Kickoff Aug 28 23:00 MYT, submissions close **Sep 4 23:00 MYT**.
Team of 2 (Talvin + friend). Neither codes; friend is an experienced **gold trader**.

Hard requirements from the brief:
- Autonomous AI trading agent on Alpaca's Trading API
- Must use Alpaca's **MCP server or CLI**
- **Must trade options**
- Fresh paper account, balance set to **$100,000**, account ID submitted
- Public GitHub repo + hosted app URL + video + slides + one-page write-up

Judging: **P&L performance**, technology implementation, creativity, presentation, social engagement.

### The two facts that drive every decision

1. **There are only ~4 trading days.** Aug 29 (Fri), Sep 1 is US Labor Day (market closed),
   Sep 2, Sep 3, and Sep 4 until ~11:00 ET (submissions close 23:00 MYT = 11:00 ET).
   A directional strategy over 4 days is a coin flip. **Selling defined-risk credit spreads**
   wins ~75-80% of the time per trade because theta decays daily regardless of direction.
   This converts "P&L" from luck into an engineering choice.
2. **Free Alpaca data = "indicative" options feed; greeks/IV are unreliable.**
   ([docs](https://docs.alpaca.markets/us/docs/about-market-data-api)) So: **never select strikes by delta.**
   Select by **% distance from spot**, compute our own Black-Scholes greeks for display only.
   Removes a $99/mo dependency.

### Confirmed decisions
| Decision | Choice |
|---|---|
| Risk posture | Sell defined-risk credit spreads / iron condors, small size |
| Gold angle | Gold **decides**, SPY **executes** — friend's gold/dollar read sets regime + sizing; trades placed on liquid SPY options |
| Friend's role | Sets the regime rules up front, then hands off (fully autonomous) |
| Who codes | Claude Code writes all of it |
| Runtime | GitHub Actions cron (free, autonomous, nobody stays up for 21:30-04:00 MYT) |
| LLM brain | Claude API, `claude-sonnet-5`. ~$3 total for the whole competition. NOT Max OAuth — that token expires in ~1 day and cannot drive Actions |
| Hosting | Netlify, static |
| Social | Both Talvin and friend post — doubles reach on the engagement criterion |

---

## Architecture

Three layers. The key idea: **the deterministic Python risk gate runs BEFORE the LLM sees
anything**, and hands the LLM a pre-computed *legal trade envelope*. The agent picks within
the envelope. It is structurally incapable of exceeding a risk limit — much stronger than
telling an LLM "please don't."

```
GitHub Actions cron (weekdays, 2 fires/day)
  │
  ├─ 1. regime.py    — reads GLD, GDX, UUP, TLT bars via alpaca-py.
  │                    Applies friend's gold rules → RISK_ON | NEUTRAL | RISK_OFF
  │                    Emits: max_contracts, min_strike_distance_pct, max_positions
  │
  ├─ 2. gates.py     — reads account + open positions. Computes the LEGAL ENVELOPE:
  │                    which expiries, which strike bands, max size, remaining daily loss budget.
  │                    Returns a hard JSON envelope. Refuses to emit one at all if a
  │                    drawdown halt has tripped.
  │
  ├─ 3. agent.py     — Claude Agent SDK. Gets the envelope in its system prompt.
  │                    Tools = the Alpaca MCP server (uvx alpaca-mcp-server):
  │                      get_option_chain, get_option_snapshot, get_stock_bars,
  │                      get_positions, place_option_order (multi-leg), close_position
  │                    Reasons about WHICH spread inside the envelope, places it, writes
  │                    its reasoning to state.json.
  │
  └─ 4. audit.py     — re-reads what was actually filled, verifies it obeyed the envelope,
                       recomputes P&L, writes site/state.json, commits it back to the repo.
```

Netlify serves `site/` as a static site reading `state.json`. No backend, no exposed keys.

### Why this satisfies the requirements cleanly
- **Autonomous**: cron-fired, no human in the loop during the 4 days.
- **MCP**: the agent's *only* way to touch the market is the official Alpaca MCP server.
- **Options**: every trade is a multi-leg options spread. Nothing else is placeable.
- **Creativity**: gold-regime-driven options sizing is a genuinely unusual framing, and it is
  backed by a real human expert rather than invented.

---

## The strategy (what the friend must define)

**Base trade:** SPY put credit spread or iron condor, 1-3 DTE, short strike ~1.0-1.5% OTM,
long strike $5 further out. Max loss per spread = $500 minus credit received.

**Gold regime overlay** — this is the part the friend owns. He must give concrete thresholds for:
- What GLD behaviour means "fear is rising" (e.g. GLD up >X% while SPY down)
- What gold/miners divergence (GLD vs GDX) tells him
- What dollar strength (UUP) does to his read
- Which condition means "do not sell puts today"

| Regime | Effect |
|---|---|
| RISK_ON  | Iron condors, strikes ~1.0% OTM, up to 3 positions |
| NEUTRAL  | Put credit spreads only, ~1.5% OTM, up to 2 positions |
| RISK_OFF | Call credit spreads only (or stand down), ~2.5% OTM, 1 position |

**Hard gates (non-negotiable, in `gates.py`):**
- Max $500 defined risk per spread; max $2,000 total risk open
- Max 2% account drawdown in a day → halt for the day
- Max 4% total drawdown → halt for the competition
- No new positions after 15:30 ET; no positions opened Sep 4 (submission day)
- Close everything by 15:45 ET on the final day so P&L is realised, not paper-open

---

## Build order

**Now → Aug 28 (prebuild on a throwaway paper account):**
1. Repo `midas-gate` (Talvin creates, gives me the URL). Python. `uv` for deps.
2. Alpaca MCP server verified running locally from Claude Code — smoke test:
   fetch a SPY option chain, confirm the indicative feed actually returns usable bid/ask.
   **This is the single biggest technical risk. Do it first.** If the chain is unusable,
   the fallback is placing spreads off `get_stock_bars` + our own BS pricing.
3. `regime.py` + `gates.py` + `bs.py` (Black-Scholes greeks, ~30 lines) with an
   assert-based self-check. These are pure functions — testable without the market.
4. `agent.py` + system prompt.
5. Dry-run mode end to end: everything except the final `place_option_order`.
6. Netlify site + `state.json` schema.
7. Backtest script (adapt `alpacahq/alpaca-skills` → `alpaca-trading-backtest`) over the last
   ~6 months of SPY to produce a win-rate number for the write-up. This is evidence, not decoration.

**Aug 28, after kickoff:**
8. Talvin opens the **fresh** paper account, sets balance to $100,000, swaps the GitHub secrets.
   Record the account ID immediately — it is a required submission field.
9. First live paper run, manually triggered, watched.

**Aug 29 → Sep 4:**
10. Cron runs. Talvin/friend check `state.json` each morning MYT. No intervention.
11. Video + slides + one-page write-up on Sep 3.
12. Sep 4: final close-out run, screenshot P&L, submit.

**Throughout — 5 social posts (both accounts, tagging @lablabai + @AlpacaHQ):**
thesis → the indicative-feed setback → the risk gates → first live trade → final P&L.

---

## Files

| File | Purpose |
|---|---|
| `regime.py` | Gold rules → regime label + sizing knobs |
| `gates.py` | Account state → hard legal trade envelope, or a halt |
| `bs.py` | Black-Scholes greeks (free tier gives no reliable greeks) |
| `agent.py` | Claude Agent SDK loop, Alpaca MCP as its toolset |
| `audit.py` | Verify fills obeyed the envelope, write `site/state.json` |
| `backtest.py` | Historical win-rate evidence for the write-up |
| `.github/workflows/trade.yml` | Cron, secrets, commits state back |
| `site/index.html` | Static Netlify dashboard |
| `WRITEUP.md` | The required one-pager |
| `docs/` | Plain-language spec per module — see [`docs/README.md`](docs/README.md) |

Secrets in GitHub: `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `ANTHROPIC_API_KEY`.
`ALPACA_PAPER=true` hardcoded in the workflow, not a secret — it must never be flippable.

---

## Verification

- `python gates.py` — self-check asserts: an oversized trade is rejected, a drawdown halt
  blocks the envelope, an after-15:30 request returns no envelope.
- `python bs.py` — assert a known-value option price against a textbook figure.
- `DRY_RUN=1 python agent.py` — full loop, logs the order it *would* place, places nothing.
- Manual `workflow_dispatch` on the Actions workflow before Aug 29 to prove the cron path works
  end to end in CI, not just on the desktop.
- After the first real run: confirm the fill appears in the Alpaca paper dashboard AND in
  `state.json` AND on the Netlify page.

## Open items needing you

1. **Repo URL** once you create `midas-gate`.
2. **Friend's gold rules** — the concrete thresholds listed above. Without these, `regime.py`
   is my guess rather than his edge, and the originality score is the thing that suffers.
3. **Anthropic API key** with a few dollars of credit (separate from your Max subscription).
