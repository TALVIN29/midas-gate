# The panel protocol

## Shape

```
envelope + candidates (already legal)
        │
        ├─── volatility seat ────┐   independent,
        ├─── cross-asset seat ───┤   parallel,
        ├─── macro-calendar seat ┤   no seat sees another
        └─── positioning seat ───┘
                                 │
                    deterministic aggregation  ← Python, no model
                                 │
                    synthesis call (one)       ← picks by index, or NO_TRADE
                                 │
                    gates.validate             ← unchanged
```

## Rule 1 — seats are independent

No seat sees another seat's output. Not before, not after, not in a second round.

This is what makes the dissent figure honest. In a sequential design each seat anchors on
the ones before it, so agreement becomes an artefact of ordering rather than a property of
the evidence, and the number cannot be backtested against anything.

The four seat calls are parallelisable. Implement them concurrently if convenient; the
protocol does not depend on it.

## Rule 2 — seats return structure, not prose

Each seat returns exactly this object:

```json
{
  "seat": "volatility",
  "stance": "FAVOUR",
  "conviction": 2,
  "preferred_candidate_index": 3,
  "evidence": ["short_spread: 0.04", "iv: 0.171", "return_on_risk_pct: 4.4"],
  "reason": "Two plain sentences.",
  "would_change_if": "One sentence naming the observation that would flip this stance."
}
```

| Field | Rule |
|---|---|
| `stance` | One of `FAVOUR`, `NEUTRAL`, `AGAINST`, `ABSTAIN`. Nothing else. |
| `conviction` | Integer `0`–`3`. Must be `0` when `stance` is `ABSTAIN` or `NEUTRAL`. |
| `preferred_candidate_index` | Index into the candidate list the seat was given, or `null`. Must be `null` unless `stance` is `FAVOUR`. A seat may favour trading in general without preferring a specific candidate — then `FAVOUR` with `null`. |
| `evidence` | Non-empty unless `ABSTAIN`. Every entry must cite a field the seat was actually given, as `field: value`. A claim that cannot be traced to an input field is a protocol violation. |
| `reason` | Two or three plain sentences. Goes on the public dashboard. |
| `would_change_if` | Always required, including on `ABSTAIN`. A seat that cannot say what would change its mind is not reasoning. |

A malformed seat response is treated as `ABSTAIN` and the malformation is recorded. One
broken seat must never fail the run.

## Rule 3 — `ABSTAIN` is first-class

**A seat with no signal in its domain says nothing.** It does not manufacture an opinion to
seem useful.

This is the anti-hallucination device and the single most likely thing for an implementer to
get wrong. Specifically:

- The `macro-calendar` seat will `ABSTAIN` on most days, because most days have no scheduled
  event before expiry. **This is correct behaviour, not a bug.** Do not add a fallback that
  makes it say something anyway.
- A seat whose inputs are missing or unreadable `ABSTAIN`s. It does not guess.
- `ABSTAIN` is excluded from the aggregation denominator entirely — it does not dilute
  toward neutral, it simply is not counted.

## Rule 4 — aggregation is deterministic Python

No model call. This is the part of the system that is engineering rather than prompting, and
it must be a pure function that can be unit-tested against hand-made stances.

```
score(FAVOUR) = +1 ,  score(NEUTRAL) = 0 ,  score(AGAINST) = -1
ABSTAIN: excluded from voting entirely

voting        = [s for s in stances if s.stance != "ABSTAIN"]
weight(s)     = max(s.conviction, 1)          # NEUTRAL still counts as a body in the room
consensus     = sum(score(s) * weight(s)) / sum(weight(s))       # -1.0 .. +1.0
dissent       = max(score(s) for s in voting) - min(score(s) for s in voting)   # 0 .. 2
hard_objection = any(s.stance == "AGAINST" and s.conviction >= 2 for s in voting)
```

Report alongside them: `voting_seats` (count), `abstained` (list of seat names).

**Decision floors, applied before synthesis:**

| Condition | Result |
|---|---|
| `voting_seats == 0` (all abstained) | `NO_TRADE`. No evidence is not a reason to trade. |
| `consensus <= 0` | `NO_TRADE`. Synthesis is not called. |
| `hard_objection` is true | Synthesis is called, but must address the objection explicitly by name and may still return `NO_TRADE`. |

These floors are deterministic and are not the model's to argue with. They exist so that a
persuasive synthesis cannot talk a bad panel into a trade.

## Rule 5 — synthesis is one constrained call

Input: every stance object, the aggregation figures, the calibration scorecard
(`CALIBRATION.md`), the envelope, and the same candidate list the seats saw.

Output:

```json
{
  "action": "PLACE",
  "candidate_index": 3,
  "contracts": 1,
  "reasoning": "...",
  "dissent_addressed": "Names the strongest opposing seat and why it did or did not prevail."
}
```

Constraints:

- **`candidate_index` only.** The synthesis step never names a strike, an expiry or a
  symbol. Those are read out of `candidates[candidate_index]` by Python. This removes
  hallucinated strikes as a category — the current design can produce one
  (`INHERITED-BUGS.md` item 1's neighbour) and this design cannot.
- Index out of range → `NO_TRADE`, recorded as a synthesis error.
- `contracts` is clamped to `envelope["max_contracts"]` by Python, not trusted.
- `dissent_addressed` is required whenever `dissent > 0`. An empty one is a protocol
  violation.
- `credit` is **not** a synthesis output. It is read from the chosen candidate, which took
  it from the live quote. See `INHERITED-BUGS.md` item 1 — this is the money bug and this
  design closes it.

## Worked examples

Hand-simulated against real sessions from `backtest_report.md`. Implement these as fixtures —
if the implementation disagrees with any of them, one of the two is wrong.

**A — plain calm session** (typical of 112 of 127 backtest sessions, regime `RISK_ON`)

| Seat | Stance | Conv. | Note |
|---|---|---|---|
| `volatility` | FAVOUR | 2 | decent credit, `short_spread` 0.04 |
| `cross-asset` | NEUTRAL | 0 | signals inside the noise band |
| `macro-calendar` | ABSTAIN | 0 | no event before expiry |
| `positioning` | NEUTRAL | 0 | proxies quiet |

`voting_seats` 3 · `consensus` = (1×2 + 0×1 + 0×1) / 4 = **+0.50** · `dissent` **1** ·
no hard objection → **synthesis called.**

**B — divergence session** (2026-07-06: 09:35 `RISK_ON`, 13:05 `NEUTRAL`, GLD−GDX 0.97pp)

| Seat | Stance | Conv. | Note |
|---|---|---|---|
| `volatility` | FAVOUR | 2 | premium looks rich |
| `cross-asset` | AGAINST | 2 | gold bid, miners not confirming |
| `macro-calendar` | ABSTAIN | 0 | |
| `positioning` | NEUTRAL | 0 | |

`voting_seats` 3 · `consensus` = (1×2 − 1×2 + 0×1) / 5 = **0.00** · `dissent` **2** ·
hard objection **true** → `consensus <= 0` → **`NO_TRADE`, synthesis not called.**

This is the design working: rich premium and a non-confirming tape are the same day, and the
`volatility` seat's named failure mode (`seats/volatility/soul.md`) is exactly this. A tie
does not trade.

**C — stand-down session** (2026-03-06: `STAND_DOWN` latched)

The panel **never runs.** `gates.build_envelope` returns `NO_TRADE` and `agent.run` exits
before any model is reached. No seat is called, no tokens are spent. Assertion 4 in
`INTEGRATION.md`.

### A consequence to accept deliberately

These floors are conservative. A single opposing seat at equal conviction cancels a
supporter and produces `NO_TRADE`. Over ~12 live runs this may mean the panel trades rarely.

That is the intended trade for a system whose stated failure mode is a latched −4% halt, and
it matches the existing posture — `agent.py:217` already tells the model that standing down
is legitimate. But it is a real cost against the P&L criterion and it should be a decision,
not a surprise discovered on 2026-09-02. **Measure it during dry runs before 08-28** — if the
panel produces `NO_TRADE` on every dry session, revisit the floors with the teammate rather
than discovering it live.

## Rule 6 — what the panel never sees

Seats and synthesis alike are never given: the account, equity, P&L, open positions, halt
state, or any envelope field they are not listed as receiving in their `skill.md`. Not
because they would misuse them, but because a seat that can see P&L can reason about
recovering a loss, and that is a documented path to the worst decision an options system can
make.

## Failure behaviour

| Failure | Behaviour |
|---|---|
| One seat errors or returns malformed JSON | That seat becomes `ABSTAIN`; run continues; recorded. |
| All seats error | `NO_TRADE`, `decided_by: "panel_error"`. |
| Synthesis errors or returns unparseable JSON | `NO_TRADE`, `decided_by: "parse_error"` — matches existing behaviour at `agent.py:274`. |
| No `ANTHROPIC_API_KEY` | Fall through to `_stub_rank` (`agent.py:174`) exactly as today, with `decided_by: "stub"`. The panel is not simulated. See `INTEGRATION.md`. |

Every one of these must leave a record. A silently degraded panel that keeps trading is
worse than one that stands down.
