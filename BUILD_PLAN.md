# Midas Gate — build plan (post-handoff brainstorm)

## Context

Midas Gate is Talvin's entry for the lablab.ai × Alpaca *AI Trading Agents* hackathon
(online, Aug 28 – Sep 4 2026, submission Sep 4 15:00 UTC, $6,000 pool). Nine plain-English
module specs and `PLAN.md` exist; **no Python has been written**. A fresh Alpaca paper
account exists. The teammate returned
`MIDAS_GATE_ARCHITECTURE_HANDOFF_FOR_TALVIN_AND_CLAUDE.md`, a large control-architecture
upgrade (bounded autonomy, four operating states, pre-trade validator, latched halts,
audit escalation, fast/slow learning loops).

This session's job: work out what actually wins, correct wrong assumptions, and turn the
handoff into an executable build order. Talvin chose to accept the **full handoff scope**,
be **live on the first real trading day**, and ship the **full dashboard**.

### Facts verified this session (from the hackathon page screenshots)

- **Five judging criteria, no published weights:** P&L Performance · Technology
  Implementation (Alpaca Trading API / MCP / CLI) · Creativity & Originality ·
  Presentation & Execution · Social engagement (post quality *and* likes/comments/shares).
- **Hard requirements:** autonomous agent · MCP **or** CLI · options must be in the
  strategy · brand-new dedicated paper account at exactly **$100,000** (reused account =
  not eligible) · **one-page write-up** covering AI logic, risk gates, Alpaca infra ·
  up to **5 social post links**, tagging @lablabai / @AlpacaHQ on X and LinkedIn.

### Corrections to existing docs (must be fixed as part of the work)

1. **Trading calendar is wrong in `README.md` and `PLAN.md`.** Aug 29 2026 is a
   **Saturday**; US Labor Day 2026 is **Sep 7**, not Sep 1. Real window:
   **Fri Aug 28, Mon Aug 31, Tue Sep 1, Wed Sep 2, Thu Sep 3, Fri Sep 4 to 11:00 ET**
   — ~5.5 trading days, no holiday gap. Every "4 trading days" claim needs updating.
2. **P&L expectation was never sized.** At the documented $2,000 total open risk, realistic
   4-day capture is ~+0.25% on $100k. That concedes the P&L criterion. See sizing below.

---

## Decisions taken in this session

| Decision | Choice | Why |
|---|---|---|
| Risk sizing | **Regime-scaled**, ceiling $10,000 open risk: RISK_ON $10k / NEUTRAL $5k / RISK_OFF $0. Per-spread cap stays **$500** | Makes the gold thesis load-bearing rather than decorative — the regime sets money at risk, not just strike distance. Realistic ~+0.6–1.2%, tail ~−2%, −4% halt won't trip on noise |
| Gold thresholds | Adopt the numbers from the teammate's own GPT interview as **V1**, clearly labelled, teammate amends by **Aug 27** | Unblocks the build; the numbers are his, not invented |
| Scope | **Full handoff architecture**, built in an order where a working agent exists first | Talvin's call; staging protects the submission |
| First live day | **Aug 28** | ~20% more of the trading window; more autonomy evidence in the commit log |
| Dashboard | **Full handoff dashboard** (operating state, exception reason, pre-trade validation, learning lesson, review history) | Presentation criterion |
| Social | Claude drafts all 5 posts; Talvin + teammate post from both accounts | It is a whole judging criterion and cheap |

### Gold Regime Rules V1 (pending teammate sign-off, mark as such in code)

Measurement convention everywhere, live and backtest: `return = latest price / previous
regular-session close − 1`.

- **Fear rising:** `GLD ≥ +0.75%` AND `SPY ≤ −0.50%`
- **Divergence:** `GLD − GDX ≥ 0.75 pp`, with `GLD > 0` and `GDX ≤ 0` → caution
- **Dollar modifier:** `UUP ≥ +0.30%` AND `GLD ≥ +0.50%` → upgrade caution **one level**
  (RISK_ON→NEUTRAL, NEUTRAL→RISK_OFF), never the reverse.
  `UUP ≤ −0.30%` with GLD rising → gold alone cannot trigger RISK_OFF; SPY/GDX must confirm
- **Stand-down (`put_spreads_allowed: false`):** `GLD ≥ +1.00%` AND `SPY ≤ −1.00%`,
  **latched for the rest of the trading day**
- **TLT:** display/context only, zero voting power
- Rules evaluated **most-cautious-first**

---

## Build order

Each stage leaves a working system. If time runs out, features are lost, not the submission.

**Stage 0 — tonight, before any other code.** Alpaca MCP smoke test: fetch a SPY option
chain via `uvx alpaca-mcp-server`, confirm the free indicative feed returns usable bid/ask
and expiries. **Largest technical risk in the project.** If unusable, fall back to
`get_stock_bars` + local Black-Scholes pricing for strike selection, and record it as a
documented setback (it is also social post #2).

**Stage 1 — trade path (must exist by Aug 28 open).**
- `regime.py` — V1 rules above, emitting the machine-readable permission block
  (`regime`, `risk_budget_usd`, `max_contracts`, `min_strike_distance_pct`,
  `max_positions`, `allowed_strategies`, `put_spreads_allowed`, `signals`, `reason`)
- `gates.py` — legal envelope + data-health gate + latched halts + duplicate-run guard
  (run id `YYYY-MM-DD-0935` / `-1305`) + deterministic pre-trade validator
- `bs.py` — Black-Scholes greeks, display only, ~30 lines, assert self-check
- `agent.py` — Claude Agent SDK, Alpaca MCP as its only toolset, picks inside the envelope,
  may return `NO_TRADE`
- `audit.py` — re-read fills, compare against the envelope in force, `AUDIT_PASS` /
  `AUDIT_FAIL`, write `site/state.json`
- `.github/workflows/trade.yml` — cron 09:35 and 13:05 ET, commits state back

**Stage 2 — safety architecture (immediately after first live trade).**
Four operating states `ACTIVE / DEGRADED / HALTED / REVIEW_REQUIRED` persisted in state;
asymmetric intraday caution (tighten now, loosen only next day); order-rejection policy
(one controlled retry, then halt the run); partial-fill / unknown-exposure →
`REVIEW_REQUIRED`; `AUDIT_FAIL` latches and halts autonomous trading.

**Stage 3 — story surface.**
Full dashboard on Netlify reading `state.json`; `WRITEUP.md` one-pager; 5 social posts
(thesis → indicative-feed setback → the risk gates → first live trade → final P&L).

**Stage 4 — if time allows.**
Outcome/mistake taxonomy + bounded learning memory (3–5 active lessons, last 5–10 outcomes;
may reorder legal candidates, may never touch permissions); 6-month regime backtest with
V1 frozen before any tuning, reporting days/win rate/avg P&L/worst loss per regime plus
stand-down trade-offs.

**Sep 4:** final close-out run, realise P&L, screenshot, submit (repo URL, hosted app,
account ID, write-up, social links).

---

## Files

New: `regime.py`, `gates.py`, `bs.py`, `agent.py`, `audit.py`, `state.json`,
`.github/workflows/trade.yml`, `site/index.html`, `WRITEUP.md`,
later `backtest.py`.
Edit: `README.md` + `PLAN.md` (calendar, sizing, scope), `docs/*.md` per handoff §34.
Secrets: `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `ANTHROPIC_API_KEY`; `ALPACA_PAPER=true`
hardcoded in the workflow, never a secret.

## Verification

- `python bs.py` — assert a known textbook option value
- `python gates.py` — asserts: oversized trade rejected · drawdown halt emits no envelope ·
  after 15:30 ET no envelope · duplicate run id places nothing · stand-down blocks put spreads
- `python regime.py` — asserts one calm case, one fear case, missing critical input → HALTED,
  missing secondary input → DEGRADED
- `DRY_RUN=1 python agent.py` — full chain, logs the order it *would* place, places nothing
- Manual `workflow_dispatch` in Actions before Aug 28, proving the cron path works in CI
- After first live run: same fill visible in the Alpaca paper dashboard, in `state.json`,
  and on the Netlify page

## Open items needing Talvin

1. Confirm the corrected trading calendar
2. Teammate's amended thresholds by **Aug 27** (otherwise V1 ships as-is, labelled)
3. `ANTHROPIC_API_KEY` with a few dollars of credit (not the Max OAuth token)
