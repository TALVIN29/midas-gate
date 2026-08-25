# Integration — seams, and constraints as assertions

## The only code-facing surface

**Replace `ask_model` (`agent.py:231`). Keep its signature and return contract identical.**

```python
def ask_model(envelope: dict, regime_block: dict, candidates: list[dict],
              lessons: list) -> dict:
```

It returns the proposal dict that `run()` (`agent.py:308-387`) then puts through
`gates.validate`. If the panel honours that contract, **nothing else in the trading path
changes** — `run.py`, `gates.py`, the validator, the order placement and the halt logic are
all untouched. That is the whole point of putting the panel here and not anywhere else.

## Required upstream change: candidates carry no volatility data

`legal_candidates` (`agent.py:131-171`) builds each candidate from `latestQuote` only —
`bp` and `ap`. **IV and greeks are read from the chain and thrown away.** The `volatility`
seat cannot exist until that changes.

Extend the candidate dict with, per leg where available:

```python
"iv": snap.get("impliedVolatility"),
"delta": (snap.get("greeks") or {}).get("delta"),
"theta": (snap.get("greeks") or {}).get("theta"),
```

`BUILD_PLAN.md:75-78` records that the free indicative feed *does* return greeks and IV,
against the original assumption. Where a field is absent, pass `None` and let `bs.greeks()`
(`bs.py:32`) supply a modelled value — **flagged as modelled**, per `docs/bs.md`. A seat must
be able to tell a quoted IV from a computed one, because its confidence should differ.

## Other seams

| Location | Role |
|---|---|
| `agent.py:242-251` | The payload dict — the only place context enters a model. Seat inputs are assembled here. |
| `audit.py:133 update_lessons` | Where per-seat calibration attaches to the existing `learning` block. |
| `audit.py:281 _lesson_text` | Currently a static lookup producing at most four strings. Natural home for seat-authored memory. |
| `audit.py:224-237 run_entry` | Must gain the stance objects and aggregation figures so the dashboard can render the panel. |
| `agent.py:174 _stub_rank` | The no-key fallback. See below. |

## No `ANTHROPIC_API_KEY`

Today: `agent.py:237-238` silently falls through to `_stub_rank` and **keeps trading**, with
no memory at all (item 3 in `INHERITED-BUGS.md`). Keep that behaviour — the docstring at
`agent.py:16-18` is right that the stub is the baseline the agent has to beat, not a
placeholder.

But: `decided_by` must say `"stub"`, the run record must state that the panel did not run,
and the dashboard must show it. A run where four seats deliberated and a run where a
sort-by-return-on-risk picked the top row must never look the same to a reader.

## Constraints, as assertions

Each of these is a checkable claim, not advice. Implement as `assert`s in the existing
in-file `_self_check()` pattern — no test framework, matching `regime.py:196`,
`gates.py:210`, `agent.py:371`.

**Ownership**

1. The envelope dict is byte-identical before and after the panel runs.
2. No seat output and no synthesis output can appear as any envelope field. Assert the
   proposal contains no keys named `risk_budget_usd`, `max_positions`,
   `min_strike_distance_pct`, `regime`, or `stand_down`.
3. `gates.validate` still rejects an out-of-envelope synthesis answer. Extend the existing
   `gates.py` self-check with a panel-shaped proposal; do not write a new suite.

**Protocol**

4. The panel is never invoked when the envelope is not allowed. `run()` already returns
   early; assert it stays that way.
5. All seats `ABSTAIN` → `NO_TRADE`, and synthesis is not called.
6. `consensus <= 0` → `NO_TRADE`, and synthesis is not called.
7. `candidate_index` outside the candidate list → `NO_TRADE`, recorded as a synthesis error.
8. `contracts` above `envelope["max_contracts"]` is clamped by Python, not rejected and not
   trusted.
9. The aggregation function is pure: same stances in, same figures out, no clock, no
   network. Unit-test it against hand-made stance lists including the all-abstain,
   all-favour, and one-hard-objection cases.
10. A seat given empty inputs returns `ABSTAIN`. Test each seat directly with `{}`.
11. A malformed seat response becomes `ABSTAIN` and does not fail the run.

**Calibration**

12. Every calibration record carries `n`.
13. Backtest-seeded and live-updated entries are produced by the same scoring function —
    assert by identity, not by comparing outputs.
14. No individual seat's prompt contains any calibration data. Assert the seat payload keys
    against an allowlist.

**Hygiene**

15. Nothing under `agent/` is opened for writing at runtime.

## Build order

Ship in this order so each step leaves a working system, matching the staging discipline in
`BUILD_PLAN.md`:

1. Extend `legal_candidates` with IV/greeks. Existing behaviour unchanged; self-checks pass.
2. Aggregation function plus its unit tests. No model calls yet — pure Python, fully
   testable.
3. Two ready seats (`cross-asset`, `volatility`) plus synthesis, behind an env flag, with
   `_stub_rank` still the default. Compare against the stub on dry runs.
4. `macro-calendar` seat with the hand-maintained event JSON.
5. Calibration seeding from the cached backtest.
6. `positioning` seat — **cut this first if 08-28 is at risk.** The panel is specified to
   work with three seats.

## Verifying before the competition

`DRY_RUN=1 python run.py` from today through 08-27 produces real panel transcripts against a
live market without placing orders (`agent.py:312, 369`). That is the only way to find out
whether the seats actually disagree with each other before it counts. If all four seats agree
on every dry run, the design has failed its core premise and needs revisiting — better to
learn that on 08-26 than on 08-31.
