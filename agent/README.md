# `agent/` — the evidence panel

Specification only. No code here. Implementation is codex's.

## What this replaces

Today the AI layer is one model call. `ask_model` (`agent.py:231`) receives seven envelope
keys, one sentence of regime reasoning, the spot price and twelve pre-filtered candidates.
It returns a strike and two sentences. That is the entire "agent".

This spec replaces that single call with **four seats that each see a different slice of
evidence, answer independently, and are then aggregated by deterministic Python** before one
constrained synthesis call picks the trade.

## Why four seats and not one persona

The seats differ by **evidence domain**, not by personality. A `volatility` seat sees option
pricing and nothing else; a `cross-asset` seat sees the five ETF returns and nothing else.
They disagree because they are looking at different things, and that disagreement is a
measurement.

This is the load-bearing decision in the whole design. Four personas reading the same data
in different voices produce four paraphrases and a disagreement number that is noise. Four
seats with disjoint inputs produce a disagreement number that means something and can be
scored against what the market actually did.

Two things were considered and rejected:

- **Named real investors** (Buffett, Soros, Munger, Dalio). They are not 1–3 DTE traders.
  Their doctrines have nothing to say about a 48-hour SPY put credit spread, so a model
  asked to channel them produces confident, empty prose. Separately, publishing invented
  opinions attributed to living people on a public dashboard is not something to ship.
- **PESTEL and SWOT.** Strategic frameworks over quarters to years. A PESTEL read of the US
  economy is identical on Tuesday and Thursday, so it cannot move a two-day decision. If it
  is wanted later, its honest home is a slow weekly context note — not a per-run seat.

## The one ownership rule

> **The panel may only choose among candidates that Python has already declared legal, or
> choose `NO_TRADE`.**
>
> Every other number — risk budget, strike distance, contract count, expiry window, halts,
> regime — is owned by `regime.py` and `gates.py`. No seat, no synthesis step and no memory
> may address them.

This is `docs/agent.md:108-122` unchanged: *the agent may optimise decisions within the
envelope; only humans may redefine the envelope.* Every constraint in this folder is a
consequence of that one rule. `gates.validate` (`gates.py:152`) re-checks the panel's answer
against refreshed prices exactly as it checks the current model's, and is not modified.

## How to read this folder

| File | What it settles |
|---|---|
| `PANEL.md` | The protocol: stance schema, aggregation maths, synthesis contract |
| `CALIBRATION.md` | How seats are scored, seeded from backtest, and updated live |
| `INTEGRATION.md` | Named seams in existing code, and the constraints as assertions |
| `INHERITED-BUGS.md` | Defects in the code the panel replaces — read before building |
| `seats/<name>/skill.md` | The seat's exact inputs, method and output |
| `seats/<name>/soul.md` | Its doctrine, priors, and known failure mode |
| `seats/<name>/memory.md` | The schema and update rules for what it remembers |

## `memory.md` is schema, not state

Each seat's `memory.md` defines *what* the seat remembers and *how* it updates. The
accumulated memory itself lives in `site/state.json` via `audit.publish` (`audit.py:292`),
next to the existing `learning` block.

Nothing in `agent/` is written at runtime. If a run modifies a file in this folder, the
implementation is wrong: every run would dirty the git tree and codex would be refining a
file the system overwrites.

## Deadline context

The competition runs 2026-08-28 to 2026-09-04 (`audit.py:25`), two runs a day — roughly
**12 live runs total**. That number drives two design decisions:

- Calibration cannot be learned from the competition week. It is seeded offline from six
  months of cached bars. See `CALIBRATION.md`.
- The `positioning` seat is the one to cut if time runs short. Its inputs are the least
  well-sourced. The panel must work with three seats.
