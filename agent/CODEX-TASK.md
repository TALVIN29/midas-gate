# Codex task — aggregation function

Give your Codex this prompt:

```
Repo: Midas Gate, an options-trading agent (E:\Portfolio\Midas_Gate).

Read agent/PANEL.md Rule 4 and Rule 4's "Decision floors" table, and the
worked examples A and B near the bottom of that file. Also read
agent/INTEGRATION.md, assertion 9 under "Protocol".

Task: implement the deterministic aggregation function described there, in a
new file `aggregate.py` at the repo root (not under agent/). Do not touch
agent.py, gates.py, regime.py, or anything else — this file stands alone and
nothing imports it yet.

Requirements:
- One pure function, `aggregate(stances: list[dict]) -> dict`, implementing
  exactly the score/weight/consensus/dissent/hard_objection formula in
  PANEL.md Rule 4, plus the three decision floors in the table right below
  it (all-abstain -> NO_TRADE, consensus <= 0 -> NO_TRADE, hard_objection ->
  flagged but synthesis still runs).
- Also return `voting_seats` (count) and `abstained` (list of seat names),
  as PANEL.md Rule 4 requires them reported alongside the figures.
- No network, no clock, no imports from the rest of this repo — same
  stances in, same figures out, every time.
- Follow the self-check convention already used in this repo: look at
  gates.py around line 210 (`_self_check()` with plain `assert`s) and the
  `if __name__ == "__main__": _self_check()` block at the bottom of that
  file. Match that style exactly — no pytest, no test framework.
- Your self-check must include, as fixtures: worked example A from
  PANEL.md (expect consensus +0.50, dissent 1, no hard objection), worked
  example B from PANEL.md (expect consensus 0.00, dissent 2, hard_objection
  true), an all-abstain case (expect voting_seats 0), and an all-favour
  case. If your numbers disagree with PANEL.md's worked examples, the spec
  is right and your code is wrong — fix the code.

Do not wire this into agent.py. Do not add a seat implementation, a
synthesis call, or anything else from PANEL.md — just this one function and
its self-check.
```

Verify: `python aggregate.py` runs clean (all asserts pass), fixtures match PANEL.md's numbers.
