# Defects in the code the panel replaces

Found while mapping `ask_model` for this spec. The panel inherits all of them unless they are
fixed. Ordered by consequence, not by effort.

Read this before building. Item 1 has money attached.

---

## 1. Model-supplied `credit` is never re-quoted, and becomes the limit price

`agent.py:264-272` — the model's returned `credit` is used as-is. `gates.validate`
(`gates.py:192`) computes worst-case loss as `(width − credit) × 100`, so **a higher claimed
credit makes a trade look safer to the validator**, not riskier. The same unverified number
is then the limit price on the order at `agent.py:381`.

Nothing re-quotes the legs against the chain between the model answering and the order being
sent. This is the one place where a wrong number from the model reaches money.

**The panel design closes this**: synthesis returns `candidate_index` only, and `credit` is
read from `candidates[index]`, which took it from the live quote at
`agent.py:157` (`bid_short − ask_long`, deliberately conservative). Do not reintroduce a
model-supplied credit.

## 2. `SYSTEM_PROMPT` never mentions the `lessons` key

`lessons` is assembled (`agent.py:350`) and lands in the payload (`agent.py:250`), but the
system prompt (`agent.py:205-228`) never tells the model what it is or how to weigh it. The
model receives an unexplained JSON array.

`docs/agent.md:192` promises lessons are "framed as preferences, with the explicit note that
they cannot override the envelope." That framing does not exist in the code.

Fix while building the synthesis prompt — it has the same failure available to it with the
calibration scorecard.

## 3. `_stub_rank` takes `lessons` and never reads it

`agent.py:174-202`. The parameter is accepted and ignored. With no `ANTHROPIC_API_KEY` the
system trades with **no memory whatsoever**, and nothing on the dashboard says so.

Keep the stub — `agent.py:16-18` is right that it is the baseline to beat — but make its
memorylessness visible rather than silent.

## 4. `candidates_considered` never reaches `state.json`

`docs/agent.md:159-161` calls this field the thing that *"turns 'it picked something' into
'it compared things'"*. `_stub_rank` emits it (`agent.py:196`). But `audit.build_state`'s
`run_entry` (`audit.py:224-237`) never copies it, and the model path never produces it at all
— the reply schema has no such field.

So the dashboard cannot render the one thing that demonstrates comparison. For the panel this
matters more, not less: the stance objects **are** the comparison, and they must reach
`state.json` or the panel is invisible to a judge.

## 5. `LIQUIDITY_ERROR` is unreachable

`audit.py:31` lists it in `TEACHES`, but `audit.classify` (`audit.py:110-130`) can never
return it. One of four possible lesson types is dead code, so the effective lesson vocabulary
is three.

Relevant because the `volatility` seat is precisely the one that should be learning about
liquidity — `short_spread` is already computed per candidate (`agent.py:169`).

## 6. `IRON_CONDOR` is permitted but unreachable

`regime.PERMISSIONS["RISK_ON"]` allows it (`regime.py:44`), and `gates.validate` will accept
it (`gates.py:170`). But `legal_candidates` only ever emits put credit spreads, so no
candidate can carry that strategy and it can never be chosen.

Either build condor candidates or drop it from the permission list. Leaving a permission that
cannot be exercised makes the envelope look more permissive than it is.

## 7. `recent_outcomes` is maintained and never sent

`audit.py:216-217` keeps up to `MAX_OUTCOMES = 10`. `docs/agent.md:51` promises the model
sees "3–5 active lessons, last 5–10 outcomes." It sees the lessons and never the outcomes.

## 8. `docs/agent.md:171` describes a loop that does not exist

It states: *"Start the Claude Agent SDK loop with the MCP tools attached."*

There is no loop. Python drives every MCP call and the model gets exactly one shot at a JSON
reply (`agent.py:242-259`). The model never calls a tool.

This is worth knowing precisely because it is a **security property, not a shortfall**:
`mcp.call` hard-whitelists six tools (`agent.py:105-108`), and `agent.py:113-122` strips the
server's untrusted-output wrapper before Python sees it, so instructions injected into tool
output never reach a prompt. The panel must preserve this — seats receive assembled data
structures, never raw tool output.

Fix the doc, not the code.

---

## Not a bug, but worth knowing

`legal_candidates` hard-codes `SPREAD_WIDTH = 5.0` (`agent.py:48`). Every candidate is a
$5-wide spread. Seats should not reason about width as though it varies; it does not.
