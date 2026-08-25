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
| Risk sizing | **Regime-scaled**, ceiling $2,500 open risk (Gold Rules V2): RISK_ON $2,500 / NEUTRAL $1,500 / RISK_OFF $1,000 / STAND_DOWN $0. Per-**contract** cap stays **$500** (corrected at Stage 0; was written as per-spread, which capped total risk near $958) | Makes the gold thesis load-bearing rather than decorative — the regime sets money at risk, not just strike distance. V2 deliberately trades size for survivability: realistic ~+0.15–0.3%, tail well inside the −4% halt |
| Gold thresholds | Adopt the numbers from the teammate's own GPT interview as **V1**, clearly labelled, teammate amends by **Aug 27** | Unblocks the build; the numbers are his, not invented |
| Scope | **Full handoff architecture**, built in an order where a working agent exists first | Talvin's call; staging protects the submission |
| First live day | **Aug 28** | ~20% more of the trading window; more autonomy evidence in the commit log |
| Dashboard | **Full handoff dashboard** (operating state, exception reason, pre-trade validation, learning lesson, review history) | Presentation criterion |
| Social | Claude drafts all 5 posts; Talvin + teammate post from both accounts | It is a whole judging criterion and cheap |

### Gold Rules V2 — frozen for validation (`rules_version: V2-validation`)

Measurement convention everywhere, live and backtest: `return = latest price / previous
regular-session close − 1`.

- **Stand-down (`STAND_DOWN`, `$0`, put spreads forbidden):** `GLD ≥ +1.00%` AND
  `SPY ≤ −1.00%`, **latched for the rest of the trading day**. 13:05 cannot release it
- **Fear rising (`RISK_OFF`, `$1,000`):** `GLD ≥ +0.75%` AND `SPY ≤ −0.50%`. Reduced size,
  **not** a stand-down — put spreads still permitted
- **Divergence:** `GLD − GDX ≥ 0.75 pp`, with `GLD ≥ +0.25%` and `GDX ≤ 0` → caution
- **Dollar modifier:** `UUP ≥ +0.30%` AND `GLD ≥ +0.50%` AND `SPY ≤ 0%` → upgrade caution
  **one level** (RISK_ON→NEUTRAL, NEUTRAL→RISK_OFF), never the reverse.
  `UUP ≤ −0.30%` → explanatory context only, recorded in `reason`, no permission change
- **TLT:** display/context only, zero voting power
- Rules evaluated **most-cautious-first**; where they overlap the most cautious wins
- `STAND_DOWN` is reachable **only** by the stand-down rule or its latch — never by a
  modifier and never by a missing input
- Intraday caution is one-way: tighten immediately, loosen only on the next trading day

---

## Build order

Each stage leaves a working system. If time runs out, features are lost, not the submission.

**Stage 0 — DONE, 2026-08-24.** Alpaca MCP smoke test passed; the fallback is not needed.

- `alpaca-mcp-server 3.4.7`, 72 tools, stdio handshake clean. `get_account_info` and
  `get_option_chain` both called successfully through MCP.
- Account `PA302AWTBMU1`, created 2026-08-23, ACTIVE, $100,000, **options level 3** —
  brand-new and multi-leg capable, so the eligibility requirement is satisfied.
- Free indicative feed **is usable**: SPY 2026-08-26 puts quoted two-sided with 1–5¢
  spreads, quotes seconds old. Example at spot 762.90 — 751 put bid 0.37 / ask 0.42.
- It also returns **greeks and implied volatility**, which the specs assumed it would not.
  Design unchanged (percentage distance still selects strikes) but the stated reason in
  `docs/bs.md` is corrected: modelled numbers on an indicative feed, not missing numbers.
- Tooling installed: Python 3.12.10 (already present, off PATH), `uv 0.12.5`,
  `alpaca-py 0.44.0`, `alpaca-mcp-server` at `~/.local/bin/alpaca-mcp-server.exe`.

Three spec errors found and fixed as a result:

1. `ALPACA_PAPER` does nothing. The server reads **`ALPACA_PAPER_TRADE`**
   (`server.py:117`), defaulting to paper, accepting only `true`/`1`/`yes`.
2. `get_positions` and `close_position` do not exist — they are `get_all_positions` and
   `close_all_positions`.
3. **Sizing was self-contradictory.** "$500 per spread" with `max_contracts: 2` capped
   total open risk near $958 against live prices, making the regime budgets
   unreachable. Now read as **$500 per contract** with `max_contracts` carrying size
   (V2 NEUTRAL: 3 × ~$479 ≈ $1,437, so the $1,500 budget binds on the first position). `ASSUMPTION:` confirm before Aug 28.

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
(thesis → what the smoke test taught us → the risk gates → first live trade → final P&L).

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
Secrets: `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `ANTHROPIC_API_KEY`; `ALPACA_PAPER_TRADE=True`
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
