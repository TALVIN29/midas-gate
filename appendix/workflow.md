# `.github/workflows/trade.yml` — the clock

> **In plain terms:** the US market is open while Malaysia is asleep. This is the
> scheduled job that runs the whole system twice a day on its own, so nobody has to
> stay up.

## Purpose

The competition requires the agent to be autonomous. It is also simply impractical
otherwise: the US market runs 21:30 to 04:00 Malaysia time, for four days, and neither
team member is going to sit through that.

GitHub Actions gives us a free scheduled runner that already has the repository
checked out, already holds our secrets, and can commit results straight back. No
server to rent, no machine to leave on, nothing to keep alive.

It is also, incidentally, the proof of autonomy. The commit history will show runs
firing and results landing at hours when both team members were provably asleep. That
is more convincing than any claim in a slide.

## Where it sits

**Around everything.** It is the thing that runs the other things.

```
cron fires
  └─ checkout repo, install Python and uv, install dependencies
      └─ python run.py
           ├─ regime.py
           ├─ gates.py
           ├─ agent.py   (starts the Alpaca MCP server as its toolset)
           └─ audit.py   (writes site/state.json)
      └─ commit and push site/state.json
```

The commit at the end is what makes Netlify redeploy. There is no deploy step of our
own.

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
repository access, silently, without a commit. Hardcoding it means switching to real
money would require an obvious, reviewable change to a tracked file. It is the one
setting where visibility is worth more than configurability.

## The schedule

Two runs per weekday. GitHub cron is always in UTC, which is the classic place to get
this wrong.

| What | UTC | US Eastern | Malaysia |
|---|---|---|---|
| Morning run | 13:35 | 09:35 | 21:35 |
| Afternoon run | 17:05 | 13:05 | 01:05 (next day) |

**Morning, 09:35 ET.** Five minutes after the open. Long enough for the opening chaos
to settle and for the day's direction to be visible; early enough that a 1–3 day
contract still has most of its decay ahead of it.

**Afternoon, 13:05 ET.** Midday. A second look, well before the 15:30 cutoff on new
positions, and far enough from the close to avoid the last-half-hour jumpiness.

Two runs, not more. Each one is a chance to place a trade, and the risk limits are
sized for a handful of positions across four days, not a stream of them.

Note the schedule does **not** account for the market being closed. Sep 1 is Labor Day
and the job will fire into a closed market. That is fine and is handled where it
belongs: `gates.py` reads a market it cannot trade, produces no envelope, and the run
records itself as a no-op. Building a holiday calendar into the workflow would be a
second place for the same logic to live, and therefore a second place for it to be
wrong.

## Outputs

- One commit per run, touching only `site/state.json`.
- A full log in the Actions tab: the regime and why, the envelope or the refusal, the
  agent's tool calls and reasoning, the audit result.
- A red run in the Actions tab if anything crashed. That is our alerting.

Commit message format: `audit: 2026-09-02 13:12 — PASS, +$402.50`. Readable at a
glance from the commit list, without opening anything.

## Logic

1. Cron fires, or a human presses the manual button.
2. Check out the repository.
3. Install Python and `uv`, then the dependencies.
4. Run `run.py`, which chains the four modules in order with the three secrets in the
   environment.
5. If `site/state.json` changed, commit and push it.
6. If any step fails, the run goes red.

`workflow_dispatch` is enabled, giving a manual "Run workflow" button. This is used
before Aug 29 to prove the whole path works in CI rather than only on a desktop, and
during the competition if a run needs repeating.

## User experience flow

**A normal night.**

1. 01:05 Malaysia time. Everyone is asleep. Cron fires.
2. GitHub spins up a fresh machine, checks out the repository, installs dependencies.
   About 40 seconds.
3. `run.py` executes the four modules. The Alpaca MCP server starts inside the agent
   step and stops with it.
4. The agent places a spread. The audit verifies it and writes `site/state.json`.
5. The workflow commits: `audit: 2026-09-02 13:12 — PASS, +$402.50`.
6. Netlify notices the commit and redeploys within a minute.
7. Total runtime around two minutes. The machine is destroyed afterwards, taking the
   secrets with it.
8. 08:00 Malaysia time. Talvin wakes up, opens the site, sees the trade and the
   figure. If he is curious about the details, the Actions log has every tool call the
   agent made. He does nothing.

**A run fails.**

1. 21:35 Malaysia time. Cron fires. Alpaca's API is having a bad minute.
2. `regime.py` cannot get prices and returns `RISK_OFF`. `gates.py` cannot read the
   account and refuses to produce an envelope. `agent.py` exits without calling the
   model.
3. `audit.py` records a run with no trade and an explanation.
4. The workflow finishes **green**. Nothing crashed — the system correctly declined to
   trade while blind.
5. The dashboard shows a **No trade** card reading "could not read market data".
6. The afternoon run happens as normal, four hours later, on a fresh machine with a
   fresh connection. Most transient failures resolve themselves this way.

**A crash.**

1. Something genuinely breaks — a typo, a dependency that will not install.
2. The workflow goes red in the Actions tab and GitHub emails the repository owner.
3. `site/state.json` is not updated, so the dashboard keeps showing the last verified
   state rather than a half-written one.
4. Talvin sees the failure email, reads the log, and can trigger a manual re-run once
   it is fixed.

## Failure modes

| What goes wrong | What happens |
|---|---|
| Cron fires late | GitHub's scheduler is best-effort and can drift by several minutes under load. Both run times have plenty of margin before the 15:30 ET cutoff. |
| Cron does not fire at all | Rare but real. Mitigation is having two runs a day rather than one. |
| Market closed (Labor Day) | Handled by `gates.py`, not here. The run is a green no-op. |
| Secret missing or expired | The step fails, the run goes red, no trade is placed. Fails closed. |
| Two runs overlap | Cannot happen — they are four hours apart and each takes about two minutes. Concurrency is set to cancel-in-progress anyway. |
| Push rejected | Retry once after pulling. If it still fails, go red, because a stale dashboard is misleading. |

## Verification

Before Aug 29, run it manually with `workflow_dispatch`. Passing means:

- Green run.
- The log shows all four modules executing in order.
- The log shows the Alpaca MCP server starting and listing its six tools.
- A commit touching `site/state.json` appears.
- Netlify redeploys and the page reflects the new state.

Also confirm:

- Cron times converted correctly. Quickest check: after the first scheduled fire, look
  at the run timestamp and confirm it is 09:35 ET, not 09:35 UTC.
- `ALPACA_PAPER: "true"` is visible in the workflow file, not in the secrets list.
- The Actions log contains no key material anywhere.
- With `DRY_RUN=1` set, a manual run completes and places nothing.

## Open questions

1. Should there be a third run near the close, purely to manage existing positions?
   Tempting on the final day, when everything must be closed by 15:45 ET. Likely a
   separate one-off workflow for Sep 4 rather than a permanent third slot.
2. Should a red run send a notification beyond GitHub's default email? Over four days,
   probably not worth wiring up.
3. Should the run be skipped on known market holidays before it starts? Cheap, but it
   duplicates a decision `gates.py` already makes correctly. Leaning toward leaving it
   alone.
