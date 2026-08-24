# `.github/workflows/trade.yml` — the clock

> **In plain terms:** the US market is open while Malaysia is asleep. This is the
> scheduled job that runs the whole system twice a day on its own, remembers what state
> the system was left in, and refuses to start the AI if that state says stop.

> **What changed since v1** ([appendix/workflow.md](../appendix/workflow.md)): the workflow
> now carries a **persisted operating state** and a **run id** through the whole chain.
> Added: no AI invocation while deterministically halted, duplicate-run protection across
> reruns, learning-memory persistence, and the corrected calendar (first live day Aug 28;
> Sep 1 is a normal trading day; Labor Day is Sep 7).

## Purpose

The competition requires the agent to be autonomous. It is also simply impractical
otherwise: the US market runs 21:30 to 04:00 Malaysia time and neither team member is
sitting through that for six days.

GitHub Actions gives us a free scheduled runner that already has the repository checked
out, already holds our secrets, and can commit results straight back. No server to rent,
no machine to leave on.

It is also, incidentally, the proof of autonomy. The commit history will show runs firing
and results landing at hours when both team members were provably asleep. That is more
convincing than any claim in a slide.

## Where it sits

**Around everything.** It is the thing that runs the other things.

```
cron fires
  └─ checkout repo, install Python and uv, install dependencies
      └─ python run.py --run-id 2026-09-02-1305
           ├─ read site/state.json      (operating state, latched halts, memory)
           ├─ data-health check          → HALTED / DEGRADED / ACTIVE
           ├─ regime.py                  (skipped if already halted)
           ├─ gates.py    envelope       (refusal ends the run here)
           ├─ agent.py                   (starts the Alpaca MCP server as its toolset)
           ├─ gates.py    validator      (rejection ends the run here)
           ├─ execution                  (one controlled retry, then halt)
           └─ audit.py                   (always runs; writes site/state.json)
      └─ commit and push site/state.json
```

The commit at the end is what makes Netlify redeploy. There is no deploy step of our own.

**The AI is never started while the system is deterministically halted.** That check
happens in the first few seconds of `run.py`, before any model client exists. It saves
money, and more importantly it removes the only path by which a model could talk its way
past a halt.

## Inputs

**Repository secrets** — set in GitHub, never in the code:

| Secret | What it is |
|---|---|
| `ALPACA_API_KEY` | Paper trading account key |
| `ALPACA_SECRET_KEY` | Paper trading account secret |
| `ANTHROPIC_API_KEY` | Claude API key with a few dollars of credit |

**Written into the workflow file in plain sight, deliberately:**

```yaml
env:
  ALPACA_PAPER: "true"
```

This is not a secret and must never become one. A secret can be changed by anyone with
repository access, silently, without a commit. Hardcoding it means switching to real money
would require an obvious, reviewable change to a tracked file. It is the one setting where
visibility is worth more than configurability.

**Persisted state** — `site/state.json`, committed in the repository:

| Carried between runs | Why |
|---|---|
| `operating_state` | A `HALTED` or `REVIEW_REQUIRED` set at 09:35 must still bind at 13:05 and tomorrow |
| Latched daily / competition halts | A halt that forgets itself on the next cron tick is not a halt |
| Run ids that already submitted an order | Duplicate protection has to survive a rerun of the same workflow |
| This morning's regime | The asymmetric-caution rule needs to know whether the day started more cautious |
| Learning memory | 3–5 lessons and the last 5–10 outcomes |

The repository is the database. It is small, versioned, publicly auditable, and it costs
nothing — and because every state change lands as a commit, the audit trail is free.

## The schedule

Two runs per weekday. GitHub cron is always in UTC, which is the classic place to get this
wrong.

| What | UTC | US Eastern | Malaysia |
|---|---|---|---|
| Morning run | 13:35 | 09:35 | 21:35 |
| Afternoon run | 17:05 | 13:05 | 01:05 (next day) |

**Morning, 09:35 ET.** Five minutes after the open. Long enough for the opening chaos to
settle and for the day's direction to be visible; early enough that a 1–3 day contract
still has most of its decay ahead of it. Note the regime's measurement convention exists
precisely because the day is five minutes old at this point — see [regime.md](regime.md).

**Afternoon, 13:05 ET.** Midday. A second look, well before the 15:30 cutoff on new
positions, and far from the last-half-hour jumpiness.

Two runs, not more. Each is a chance to place a trade, and the risk budgets are sized for a
handful of positions across the window, not a stream of them.

### The live calendar

| Date | Day | Runs | Notes |
|---|---|---|---|
| Aug 28 | Fri | 09:35, 13:05 | First live day |
| Aug 31 | Mon | 09:35, 13:05 | |
| Sep 1 | Tue | 09:35, 13:05 | **Not** a holiday. Labor Day 2026 is Sep 7 |
| Sep 2 | Wed | 09:35, 13:05 | |
| Sep 3 | Thu | 09:35, 13:05 | Last day new positions may open |
| Sep 4 | Fri | 09:35 close-out only | No new positions. Everything realised by 11:00 ET. Submission 15:00 UTC |

A weekend or holiday cron tick is harmless: the market is closed, the data-health gate
sees stale data and the run halts itself without trading. But relying on that as the only
guard would be careless, so the date rules are explicit in `gates.py` too.

### Run ids

Each execution gets `YYYY-MM-DD-0935` or `YYYY-MM-DD-1305`, passed in from the workflow and
carried through every module and into `state.json`.

One order per run id, ever. A rerun of a workflow, an Actions retry, a network failure that
makes a successful submission look failed — none of these can double our risk, because the
second attempt sees its own run id already recorded and refuses.

## Outputs

- One commit per run: `audit: 2026-09-02 13:12 — AUDIT_PASS, +$402.50`.
- An updated `site/state.json` on `main`.
- A green or red Actions run. Red is the alert channel — there is no other monitoring, and
  none is needed for a six-day system.

## User experience flow

**A normal night.**

1. 21:35 Malaysia. Talvin is asleep. The cron fires.
2. The runner checks out the repository, installs Python, `uv` and dependencies — about a
   minute.
3. `run.py` reads `state.json`: `ACTIVE`, no latched halts, run id `2026-08-31-0935` has
   placed nothing.
4. Data health passes. Regime, envelope, agent, validator, execution, audit — about two
   minutes end to end.
5. The commit lands at 13:37 UTC. Netlify redeploys.
6. 08:00 the next morning, Talvin sees a green dashboard and a commit timestamped while he
   was asleep. That commit log is the autonomy evidence for the write-up.

**A halted morning.**

1. Yesterday's audit found a violation and left `REVIEW_REQUIRED` in `state.json`.
2. The cron fires as usual. `run.py` reads the state in its first second.
3. It logs `REVIEW_REQUIRED — no regime, no envelope, no agent invocation` and goes
   straight to `audit.py`, which republishes the unchanged state.
4. Zero model cost, zero market interaction. The Actions run is green — the system did
   exactly what it should.
5. The dashboard still shows purple. It will keep showing purple every run until a human
   clears it.

**A rerun.**

1. The 13:05 run placed an order, then the commit step failed on a network error. The
   Actions run goes red.
2. Someone hits "re-run job". Same run id, `2026-09-02-1305`.
3. `gates.py` sees that run id already submitted an order and refuses with `DUPLICATE_RUN`.
4. The audit runs, the state commits cleanly this time, and no second position exists.

## Failure modes

| What goes wrong | What happens |
|---|---|
| Cron fires on a market holiday | Data-health gate sees stale prices → halt. Date rules in `gates.py` catch it independently |
| GitHub Actions is down at run time | The run is missed entirely. Nothing trades, nothing breaks. Missing a run costs nothing |
| Dependencies fail to install | Run goes red before any trading code executes |
| Workflow rerun | Run-id check. No duplicate order |
| Two runs somehow overlap | Concurrency group on the workflow so only one runs at a time. Run ids differ anyway |
| `state.json` commit conflicts | Pull, reapply, retry once. If it fails again, log loudly — a stale dashboard is misleading |
| Secret missing or wrong | Data-health / account read fails → `HALTED`. Never a blind trade |
| A step crashes mid-chain | `audit.py` still runs and records what is known; anything unknown is written as unknown, and unknown exposure escalates to `REVIEW_REQUIRED` |

## Verification

- `workflow_dispatch` is enabled, and a **manual run before Aug 28** proves the whole CI
  path — checkout, install, MCP server start, model call, commit — works on the runner and
  not just on a desktop. This is on the Stage 1 checklist in `BUILD_PLAN.md`.
- A `DRY_RUN=1` manual dispatch completes end to end and commits a state file with
  `agent_action` recorded and no order placed.
- Re-running that same dispatch produces `DUPLICATE_RUN` and no second order.
- A hand-edited `state.json` with `review_required: true` produces a run whose log contains
  **no model call at all**.
- The cron times are checked against a UTC/ET converter for the specific competition dates,
  not assumed. US Eastern is UTC−4 in this window.
- After the first live run: the fill is visible in the Alpaca paper dashboard, in
  `state.json` in the repository, and on the Netlify page.

## Open questions

1. Should there be a third run near the close on days where a position is open? More
   chances to react, more chances to churn. `ASSUMPTION:` no — two runs, and the −2% halt
   is the intraday protection.
2. Should Sep 4's close-out be its own workflow rather than a mode of the main one? A
   separate file is clearer to read on submission day; a mode is less to maintain. Leaning
   toward a mode with an explicit `--close-out` flag.
3. Who gets notified when an Actions run goes red? Currently GitHub's default email to the
   repository owner. For six days that is probably enough.
