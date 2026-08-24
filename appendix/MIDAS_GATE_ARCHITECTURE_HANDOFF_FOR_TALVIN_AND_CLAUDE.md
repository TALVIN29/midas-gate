# Midas Gate — Architecture Upgrade Handoff for Talvin + Claude

## Purpose of this file

This document is the handoff for the next design revision of **Midas Gate**.

Talvin should give this file to Claude together with the existing project documentation.

Claude should treat the current repository documentation as the base design, and use this file only to **upgrade the control architecture**. The original trading thesis and project scope must remain intact unless explicitly changed below.

---

# 1. What stays unchanged

Do **not** change the core Midas Gate strategy.

The original concept remains:

> **Gold decides. SPY executes.**

The system trades **defined-risk SPY credit spreads**.

The market inputs remain:

- `GLD` — gold
- `GDX` — gold miners
- `UUP` — US dollar strength
- `TLT` — long-duration US Treasuries
- `SPY` — S&P 500 ETF

The system still uses the gold/macro read to determine how cautious the SPY options strategy should be.

The existing high-level chain remains:

```text
regime.py
    ↓
gates.py
    ↓
agent.py
    ↓
audit.py
```

The improved architecture should extend this chain rather than replace the thesis.

---

# 2. Original trading design to preserve

The strategy continues to use:

- defined-risk SPY credit spreads
- percentage distance from SPY spot instead of option delta for strike selection
- Black-Scholes Greeks for dashboard/display purposes only
- deterministic Python risk controls before AI decision-making
- AI selection only inside a pre-approved legal envelope
- Alpaca as the execution route
- automated post-trade audit
- GitHub Actions for autonomous runs
- a public dashboard driven by audited state

The free/indicative options data constraint remains part of the project story.

Do **not** redesign the strategy around delta selection.

---

# 3. Hard limits to preserve

Unless Talvin explicitly changes them later, retain the current hard limits:

| Control | Limit |
|---|---:|
| Maximum loss per spread | $500 |
| Maximum total open risk | $2,000 |
| Daily drawdown halt | -2% |
| Competition drawdown halt | -4% |
| New position cutoff | 15:30 ET |
| Submission/final-day rules | Follow current PLAN/workflow specification |
| Final close-out | Follow current PLAN/workflow specification |

These are **hard deterministic limits**.

The AI must never be able to change, reinterpret, override, or negotiate them.

---

# 4. Core design principle for the upgrade

The improved architecture should use:

> **Bounded autonomy**

The AI is autonomous, but only inside a deterministic safety envelope.

The key governance rule is:

> **The agent may optimise decisions within the envelope, but only humans may redefine the envelope.**

A second rule:

> **Learning may change preferences, but not permissions.**

This distinction must be preserved throughout implementation.

---

# 5. Human involvement model

Do **not** convert the system into traditional HITL where a human approves every trade.

Normal trading should remain fully autonomous.

Human involvement should be **exception-based and governance-based**.

Use the following model:

```text
NORMAL OPERATION
Market data
    ↓
Regime
    ↓
Risk gates
    ↓
AI selects legal trade
    ↓
Automatic execution
    ↓
Automatic audit
```

Human involvement occurs only when:

- a critical exception occurs
- an audit violation occurs
- broker state does not match system state
- a partial/unknown position exists
- the competition-level halt is triggered
- structural regime/risk rules are being changed
- a regime miss is being reviewed after backtesting

This is closer to **human-on-the-loop / human-governed autonomy**, not HITL trade approval.

---

# 6. Add explicit operating states

The upgraded system should have four explicit operating states:

## `ACTIVE`

Everything required for safe operation is healthy.

Autonomous trading is permitted subject to the legal envelope.

## `DEGRADED`

Something non-critical is uncertain or unavailable.

Examples:

- a secondary indicator is missing
- a non-critical supporting feed is unavailable
- a secondary signal is stale

Behaviour should become more cautious.

Possible actions:

- default regime toward caution
- reduce position allowance
- disable new positions if uncertainty is too high
- continue only if all critical execution data remains valid

## `HALTED`

No new orders may be placed.

Examples:

- daily drawdown halt
- stale critical SPY data
- critical broker/API failure
- repeated order failure
- pre-trade validation cannot establish safe state

The AI should not be called if the system is already deterministically halted.

## `REVIEW_REQUIRED`

A critical system inconsistency exists that must not be automatically ignored.

Examples:

- partial spread / unexpected leg
- audit violation
- broker position does not match internal records
- competition-level drawdown halt
- unknown exposure
- unexplained execution mismatch

A human must investigate before the system returns to normal operation.

---

# 7. State transition principle

Use caution asymmetrically.

The system should be able to become **more cautious immediately**.

It should not become materially more aggressive intraday without a deliberate rule.

Recommended principle:

> **Risk can tighten immediately; permission to become more aggressive should reset slowly.**

For example:

```text
09:35 → RISK_OFF
13:05 → apparent RISK_ON
```

Do not automatically jump straight to full RISK_ON permissions unless the specification explicitly allows that.

A conservative default is to keep the more cautious intraday state until the next trading day.

This should be documented and made deterministic.

---

# 8. Data-health gate

Before regime classification or trading, add a deterministic data-health check.

The system should distinguish between:

- critical data
- secondary/context data

Recommended critical data:

- current/fresh `SPY`
- account state
- open positions
- order state
- whatever minimum market inputs are required by the regime rules once finalised

Recommended behaviour:

```text
Critical data missing/stale
→ HALTED

Secondary data missing
→ DEGRADED or cautious fallback
```

Do not let the AI decide whether stale or missing data is “probably fine.”

Data validity must be checked in ordinary code.

---

# 9. Regime engine responsibilities

`regime.py` remains the component that converts the gold/macro read into:

- `RISK_ON`
- `NEUTRAL`
- `RISK_OFF`

Its output should explicitly contain all permissions downstream needs.

Recommended output fields:

```json
{
  "regime": "NEUTRAL",
  "max_contracts": 2,
  "min_strike_distance_pct": 1.5,
  "max_positions": 2,
  "allowed_strategies": ["PUT_CREDIT_SPREAD"],
  "put_spreads_allowed": true,
  "signals": {},
  "reason": ""
}
```

The exact final structure may differ, but strategy permission should not exist only as prose.

The downstream gate should be able to read explicit machine-enforceable permissions.

---

# 10. IMPORTANT: regime thresholds are not final yet

Claude must **not invent final gold-regime thresholds**.

The current threshold block in `regime.md` is explicitly a placeholder.

The human gold trader still needs to finalise:

1. Fear-rising threshold:
   - GLD up by what percentage?
   - SPY down by what percentage?

2. GLD vs GDX divergence:
   - what direction matters?
   - what percentage-point gap matters?

3. UUP modifier:
   - what counts as meaningful dollar strength/weakness?
   - how should it amplify or reduce the gold signal?

4. Stand-down rule:
   - what single condition means **do not sell puts today**

Until those numbers are explicitly provided:

> **DO NOT replace the placeholder with guessed values.**

Claude may structure the code/specification to make the thresholds configurable, but it must clearly mark them as pending human input.

---

# 11. Measurement convention for regime inputs

The regime needs an explicit definition of “today's move.”

Recommended convention:

```text
latest available price
compared with
previous regular-session close
```

This matters because the system runs at:

- 09:35 ET
- 13:05 ET

At 09:35, the regular session has only been open for five minutes.

The system must not pretend a completed daily candle exists.

Document the exact measurement convention and use it consistently in both live logic and backtesting.

---

# 12. Risk gate / legal envelope

`gates.py` remains the deterministic authority that decides what is legal.

It should evaluate, at minimum:

- system operating state
- account equity
- daily P&L
- competition P&L/drawdown
- current open risk
- open positions
- current time
- regime output
- allowed strategy
- minimum OTM distance
- maximum contracts
- maximum positions
- maximum loss per spread
- total portfolio risk
- expiry constraints
- duplicate-order state

Output:

> **The legal envelope**

The AI must receive only legal choices or legal ranges.

---

# 13. Pre-trade revalidation

Add a deterministic pre-trade validator between `agent.py` and broker submission.

The AI proposal must **never go directly to Alpaca**.

Flow:

```text
agent.py
   ↓
AI proposal
   ↓
PRE-TRADE VALIDATOR
   ↓
Alpaca
```

The validator should re-check:

- selected strategy is still allowed
- selected strike is still inside the legal envelope
- selected expiry is legal
- size is legal
- maximum loss remains within limits
- total risk remains within limits
- SPY has not moved enough to invalidate minimum distance
- account state has not materially changed
- the workflow is not duplicating a previous order
- system has not become HALTED since the envelope was built

If any check fails:

```text
REJECT PROPOSAL
DO NOT SEND ORDER
```

Do not ask the AI to “fix” an illegal trade in place unless the specification deliberately performs a fresh new decision cycle.

---

# 14. Duplicate-order protection / idempotency

The system needs explicit duplicate-run protection.

GitHub Actions, API retries, workflow reruns, or network failures must not accidentally double risk.

Each execution cycle should have a unique run identity, for example:

```text
YYYY-MM-DD-0935
YYYY-MM-DD-1305
```

Before submitting an order, verify whether that run has already submitted/executed one.

If yes:

```text
DO NOT PLACE ANOTHER ORDER
```

This protection must be deterministic.

---

# 15. Order rejection handling

Do not allow unlimited AI improvisation after a broker rejection.

Recommended control:

```text
Order rejected
    ↓
Refresh market/account state
    ↓
Rebuild legal envelope
    ↓
At most one controlled retry if still allowed
    ↓
Second failure
    ↓
HALT current run
```

The exact retry count may be adjusted by Talvin, but repeated free-form retries should not be allowed.

---

# 16. Partial fill / unexpected exposure handling

A partial or inconsistent multi-leg position is a critical exception.

If the intended result is a defined-risk spread but the broker state shows:

- only one leg
- mismatched quantity
- unknown exposure
- unexpected leg
- fill state inconsistent with the submitted order

then:

```text
REVIEW_REQUIRED
```

No new trades should be placed until the state is understood.

Any automatic corrective action must itself be explicitly pre-defined and deterministic.

Do not let the AI freestyle its way out of unknown portfolio exposure.

---

# 17. Audit upgrade

`audit.py` should continue reading the actual broker state after execution.

It must compare:

```text
LEGAL ENVELOPE AT DECISION/EXECUTION TIME
            vs
ACTUAL FILLED POSITION
```

Verify:

- strategy
- expiry
- strike distance
- size
- maximum loss
- total open risk
- position count
- any other hard rule

Possible result:

```text
AUDIT_PASS
```

or

```text
AUDIT_FAIL
```

An `AUDIT_FAIL` should not merely be displayed.

Recommended behaviour:

```text
AUDIT_FAIL
    ↓
publish violation
    ↓
HALT future autonomous trading
    ↓
REVIEW_REQUIRED
```

This should be latched until reviewed.

---

# 18. Drawdown halts should latch

The daily -2% halt should remain active for the rest of that trading day even if P&L later recovers above -2%.

Example:

```text
P&L reaches -2.0%
→ DAILY_HALT = true

Later P&L improves to -1.6%
→ DAILY_HALT remains true
```

Reset only according to the next-day rule.

The -4% competition halt should be treated as stronger.

Recommended behaviour:

```text
COMPETITION_HALT = true
→ REVIEW_REQUIRED
→ no automatic reset
```

Only a deliberate human recovery should be able to re-enable trading.

---

# 19. Learning-from-mistakes loop

Add a controlled feedback loop.

Do **not** make the system self-modifying.

The learning architecture should be:

```text
Trade / no-trade decision
        ↓
Execution
        ↓
Audit
        ↓
Outcome classification
        ↓
Lesson generation
        ↓
Limited learning memory
        ↓
Next AI decision sees relevant lessons
```

The key rule:

> **Learning may influence candidate preference, but never hard permissions.**

---

# 20. Not every loss is a mistake

The system must distinguish:

```text
BAD OUTCOME
```

from:

```text
BAD DECISION
```

A correctly selected defined-risk credit spread may still lose because markets moved unexpectedly.

The learning loop must not automatically change behaviour after every losing trade.

---

# 21. Mistake / outcome taxonomy

Add a simple classification taxonomy.

Recommended categories:

| Classification | Meaning |
|---|---|
| `NO_ERROR` | Decision and execution were reasonable; outcome may still lose |
| `MARKET_MOVE` | Legal trade lost because market moved adversely |
| `SELECTION_ERROR` | AI chose a poorer legal candidate when better alternatives existed |
| `LIQUIDITY_ERROR` | Spread/order quality was harmed by poor liquidity |
| `EXECUTION_ERROR` | Rejection, fill issue, or order-state problem |
| `DATA_ERROR` | Stale, missing, or inconsistent input data |
| `REGIME_MISS` | Regime appears too optimistic or insufficiently cautious in hindsight |
| `RISK_VIOLATION` | Actual state violated the deterministic envelope |

The exact labels may be adjusted, but keep the conceptual separation.

---

# 22. Fast learning loop

The fast loop operates during the competition.

It may learn preferences such as:

- prefer tighter bid/ask conditions
- avoid repeating a recent liquidity failure
- prefer slightly more OTM distance when premium sacrifice is small
- avoid candidate characteristics that repeatedly caused rejected orders
- prefer candidates similar to recent successful legal selections

Example:

```text
Recent lesson:
"In NEUTRAL conditions, candidates barely above the minimum OTM threshold performed poorly when a slightly further OTM candidate offered nearly the same premium."
```

The next AI decision may use that information when ranking legal candidates.

But it still cannot choose outside the envelope.

---

# 23. Learning memory limits

Do not pass unlimited trading history back into the AI.

Keep memory compact and evidence-based.

Recommended:

- last 5–10 relevant recent outcomes
- maximum 3–5 active lessons
- each lesson should identify:
  - lesson type
  - evidence count
  - last observed time
  - confidence or support level

Example:

```json
{
  "type": "selection",
  "lesson": "Prefer additional OTM distance in NEUTRAL when the premium difference is small.",
  "evidence_count": 3,
  "confidence": "MEDIUM"
}
```

Old or contradictory lessons should expire or be consolidated.

---

# 24. What the fast learning loop may change

Allowed to influence:

- ranking between legal candidates
- liquidity preference
- relative strike-distance preference inside the allowed range
- whether premium improvement is worth accepting less distance
- entry preference
- choice of `NO_TRADE`

Not allowed to change autonomously:

- $500 max loss
- $2,000 total open risk
- -2% daily halt
- -4% competition halt
- gold regime thresholds
- permitted strategy families
- maximum position limits
- deterministic validation requirements
- exception escalation policy

---

# 25. Slow learning / research loop

Structural strategy changes should happen through a separate slow loop.

Flow:

```text
Historical + live outcomes
        ↓
backtest / analysis
        ↓
identify repeated regime miss or rule weakness
        ↓
generate proposed change
        ↓
human review
        ↓
accept or reject
        ↓
version-controlled new rule
```

The agent may propose a change.

It may **not deploy the change itself**.

This is where the gold trader and Talvin remain governors of the strategy.

---

# 26. Regime-rule backtesting principle

When the human gold trader supplies the final thresholds:

1. Record them as **V1 before backtesting**
2. Backtest V1 over the historical period
3. Measure performance by regime
4. Identify obvious failure modes
5. If justified, create one documented V2
6. Keep V1 results for comparison

Do not continuously optimise thresholds until the historical result looks attractive.

Avoid obvious overfitting.

Recommended outputs:

- number of RISK_ON days
- number of NEUTRAL days
- number of RISK_OFF days
- win rate by regime
- average P&L by regime
- worst result by regime
- maximum adverse SPY move after each regime classification
- number of losing put spreads avoided by stand-down rule
- number of winning opportunities skipped by stand-down rule

The objective is not only maximum win rate.

The overlay should be evaluated on whether it reduces downside in a useful way.

---

# 27. Agent responsibilities after upgrade

`agent.py` should receive:

- legal envelope
- current market data needed for legal candidate comparison
- regime output
- compact recent learning memory

The AI may:

- rank legal candidates
- select one
- explain its choice
- choose `NO_TRADE`

The AI may not:

- change risk thresholds
- change regime thresholds
- expand allowed strategies
- increase permitted size
- override halts
- bypass the pre-trade validator
- recover from critical exceptions by improvisation
- modify its own permissions

---

# 28. No-trade is a valid autonomous action

The system must preserve the ability to return:

```text
NO_TRADE
```

This is not an error.

It may occur because:

- legal envelope is empty
- available credits are unattractive
- liquidity is poor
- risk/reward is insufficient
- uncertainty is high
- current learning memory suggests avoiding the available setup
- the system is DEGRADED and conservative logic disables new trades

This is important for the four-day hackathon.

Not trading can be the correct decision.

---

# 29. Recommended end-to-end execution order

Every live run should conceptually follow:

```text
1. Read persistent system state

2. Is competition halt active?
   YES → STOP

3. Is daily halt active?
   YES → STOP

4. Did previous critical audit require review?
   YES → STOP

5. Read account + broker state

6. Verify account/system state consistency

7. Read market data

8. Data-health validation

9. Determine regime

10. Apply cautious intraday state rules

11. Build deterministic legal envelope

12. If envelope empty:
    → NO_TRADE
    → audit/log state
    → publish

13. Load limited learning memory

14. Ask AI to choose from legal candidates

15. Deterministically validate AI proposal

16. Refresh critical market/account data

17. Revalidate strike distance + risk immediately before order

18. Duplicate-order / idempotency check

19. Submit order through Alpaca

20. Monitor execution state

21. Verify actual fills/positions

22. Audit actual state against envelope

23. Classify outcome / mistake

24. Generate or update limited learning lesson

25. Update persistent system state

26. Publish dashboard/state.json
```

---

# 30. Failure-handling matrix

Claude should add or update tests for cases similar to:

| Scenario | Expected response |
|---|---|
| SPY data missing | HALT current run |
| SPY data stale | HALT current run |
| Secondary indicator missing | DEGRADED / cautious fallback |
| Account state unavailable | HALT |
| AI proposes illegal strike | Reject proposal; no order |
| AI proposes too many contracts | Reject proposal; no order |
| AI proposes forbidden strategy | Reject proposal; no order |
| Market moves and invalidates OTM distance | Reject/rebuild; no stale order |
| Duplicate workflow run | No duplicate order |
| First broker rejection | Controlled refresh/re-evaluation |
| Repeated broker rejection | HALT current run |
| Partial/unknown spread | REVIEW_REQUIRED |
| Audit violation | Publish + HALT + REVIEW_REQUIRED |
| Daily drawdown reaches -2% | Latched daily halt |
| Competition drawdown reaches -4% | Latched competition halt + REVIEW_REQUIRED |
| Empty envelope | NO_TRADE |
| No attractive legal trade | NO_TRADE |

---

# 31. Dashboard additions

Keep the dashboard static/public design.

Add visibility for the improved control architecture.

Recommended fields:

- current regime
- operating state:
  - ACTIVE
  - DEGRADED
  - HALTED
  - REVIEW_REQUIRED
- reason for current state
- legal envelope summary
- selected trade or NO_TRADE
- AI reasoning
- pre-trade validation result
- actual fill
- audit PASS/FAIL
- exception reason
- current risk usage
- daily/competition drawdown status
- latest learning lesson
- whether human review was required
- whether a human reset/change occurred

Do not expose private credentials or sensitive broker information.

---

# 32. Human governance responsibilities

Suggested ownership:

| Area | Gold trader | Talvin / system owner |
|---|---|---|
| Gold regime thresholds | Owner | Implement |
| GLD/GDX/UUP interpretation | Owner | Support |
| Review `REGIME_MISS` | Owner | Provide data |
| Hard portfolio limits | Consult | Owner |
| Execution safeguards | Consult | Owner |
| Broker/API handling | Not primary | Owner |
| Audit violations | Market-context input | Owner |
| Structural strategy change | Joint review | Joint review |
| Normal trade approval | None | None |

Normal trades should remain autonomous.

---

# 33. Human reset policy

Do not give the AI authority to clear critical safety states.

Recommended:

## Automatically recoverable

Potential examples:

- transient secondary data issue
- next-day reset of daily halt
- non-critical DEGRADED state after data health recovers

## Human reset required

Recommended for:

- competition-level halt
- audit violation
- unexplained partial position
- broker/system state mismatch
- unknown portfolio exposure
- serious risk-rule inconsistency

Human recovery should be logged and visible in system history.

---

# 34. Implementation guidance for Claude

Claude should update the specifications **before** silently changing production logic.

The documentation-first approach is one of Midas Gate's strengths.

Recommended spec files to revise:

### `PLAN.md`

Add:

- bounded autonomy principle
- operating states
- exception-based human involvement
- controlled learning-loop philosophy
- human governance boundaries

### `docs/README.md`

Update architecture diagram and glossary.

Explain:

- bounded autonomy
- legal envelope
- operating states
- human-on-the-loop governance
- fast vs slow learning

### `docs/regime.md`

Add:

- explicit machine-readable permissions
- measurement convention
- intraday caution/latching behaviour
- no-put permission field
- pending human thresholds

Do **not** invent the final thresholds.

### `docs/gates.md`

Add:

- data-health gating
- state-manager checks
- duplicate-order protection
- latched halts
- deterministic pre-trade validation
- empty-envelope NO_TRADE behaviour

### `docs/agent.md`

Add:

- compact learning memory as input
- explicit no-trade capability
- strict inability to modify permissions
- invalid proposal handling

### `docs/audit.md`

Add:

- automatic halt on critical audit failure
- mistake/outcome taxonomy
- lesson generation
- persistent exception state
- human-review escalation

### `docs/backtest.md`

Add:

- V1 → evidence → V2 discipline
- regime-level performance analysis
- stand-down tradeoff analysis
- slow-learning / human-approved structural changes

### `docs/workflow.md`

Add:

- persistent operating state
- latched halt behaviour
- duplicate-run protection
- learning-memory persistence
- no AI invocation while deterministically halted

### `docs/dashboard.md`

Add:

- operating state
- exception reason
- pre-trade validation
- learning lesson
- human-review/reset visibility

### `docs/bs.md`

No major architecture change expected.

Preserve:

- local BS calculations
- display-only Greeks
- Greeks must not become decision gates unless explicitly redesigned

---

# 35. Do not over-modularise unless necessary

The architecture introduces concepts such as:

- state management
- exception management
- pre-trade validation
- learning memory
- outcome classification

These do not automatically require a separate Python file each.

Claude should prefer the simplest maintainable design that preserves clear responsibility.

For example:

```text
gates.py
→ may own deterministic pre-trade gate functions

audit.py
→ may own outcome classification + lesson generation

state.json / state storage
→ may persist operating/learning state
```

Create new modules only where separation materially improves safety, testing, or maintainability.

---

# 36. Testing expectations

Before live paper trading, add deterministic tests for:

## Regime

- obvious calm case
- obvious fear case
- missing critical market input
- missing secondary input
- intraday caution escalation
- pending/final human thresholds

## Gates

- max loss exceeded
- total risk exceeded
- max position count exceeded
- daily halt
- competition halt
- forbidden strategy
- insufficient strike distance
- empty envelope
- duplicate run

## Agent

- legal proposal
- illegal strike
- illegal size
- forbidden strategy
- NO_TRADE
- learning memory present
- malformed AI output

## Execution

- broker rejection
- retry limit
- partial fill
- unknown fill
- market moved before submission

## Audit

- exact legal fill
- strike-distance violation
- size violation
- risk violation
- unexpected leg
- audit failure causes REVIEW_REQUIRED

## Learning

- normal market loss does not become a false “mistake”
- liquidity error creates relevant lesson
- selection error creates relevant lesson
- learning cannot modify hard rules
- learning memory remains bounded

---

# 37. Recommended dry-run sequence

Before enabling broker order submission:

```text
Real market data
    ↓
regime.py
    ↓
gates.py
    ↓
AI candidate selection
    ↓
pre-trade validator
    ↓
SIMULATED execution only
    ↓
audit simulation
    ↓
outcome classification
    ↓
learning memory
    ↓
dashboard
```

Verify the full chain first.

Then enable Alpaca paper execution.

---

# 38. What NOT to do

Claude should **not**:

- redesign the project into multi-asset trading
- add XAUUSD, USDJPY, BTCUSD, etc.
- replace SPY credit spreads with another main strategy
- switch strike selection back to delta-based rules
- invent final gold thresholds
- allow AI to rewrite risk limits
- allow AI to clear critical halts
- require human approval for every normal trade
- let audit failures be informational only
- treat every losing trade as a mistake
- allow unlimited learning memory
- let the AI send orders directly without deterministic revalidation
- silently change the documented hard limits
- hide exceptions from the public dashboard
- continuously optimise regime thresholds until the backtest looks good

---

# 39. What the final architecture should communicate

The project should be explainable in one sentence:

> **Midas Gate is a human-governed, deterministically constrained autonomous SPY options trading agent that uses a gold/macro regime to control risk, learns from audited outcomes inside its approved envelope, fails toward caution under uncertainty, and escalates only safety-critical exceptions to human review.**

And the control philosophy should be explainable with two lines:

> **The AI chooses. Deterministic code permits.**

> **Learning changes preferences, not permissions.**

---

# 40. Immediate next actions

Claude/Talvin should proceed in this order:

1. Review this architecture handoff
2. Decide which upgrades are accepted
3. Update the documentation/specifications
4. Keep all unfinished gold thresholds clearly marked as pending
5. Freeze architecture before substantial implementation proceeds
6. Obtain the gold trader's final numeric regime thresholds
7. Record those rules as V1
8. Backtest V1
9. Review results without overfitting
10. Implement the final accepted specification
11. Run deterministic failure simulations
12. Run end-to-end simulated/dry execution
13. Enable Alpaca paper trading only after controls pass

---

# 41. Critical pending item — human gold thresholds

This architecture handoff does **not** finalise `regime.py`.

That remains a separate human decision.

The gold trader will still provide concrete numbers for:

```text
1. Fear rising
   GLD >= +___%
   AND SPY <= -___%

2. GLD/GDX divergence
   meaningful gap = ___ percentage points
   interpretation = __________________

3. UUP modifier
   strong dollar >= +___%
   weak dollar <= -___%
   regime modification = __________________

4. Stand-down
   exact condition for:
   PUT_SPREADS_ALLOWED = false
```

Do not fill these blanks automatically.

---

# Final instruction to Claude

Use the current Midas Gate repository specifications as the base.

Apply the architecture upgrades in this document **without changing the original strategy thesis**.

Prioritise:

1. deterministic safety
2. explicit operating states
3. exception handling
4. pre-trade revalidation
5. post-trade audit escalation
6. bounded learning memory
7. human governance of structural changes
8. preservation of full autonomy during normal operation

Where this document introduces a new concept but does not specify an exact numeric threshold, do not invent one silently.

Mark assumptions explicitly.

Where a safety decision is ambiguous:

> **fail toward caution and do less.**
