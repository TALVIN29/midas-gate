# `regime.py` — today's risk regime

> **In plain terms:** it looks at what gold is doing, decides whether today is a calm
> day, a normal day or a scared day — and issues the permissions that everything
> downstream is allowed to work inside.

> **What changed since v1** ([appendix/regime.md](../appendix/regime.md)): the placeholder
> thresholds are gone, replaced by the teammate's own numbers. The output
> is now a full machine-readable permission block (risk budget, allowed strategies, a
> put-spread permission flag), not just a label and three numbers. Added: an explicit
> measurement convention, the day-latched stand-down, asymmetric intraday caution, and
> the split between critical inputs (missing → `HALTED`) and secondary inputs (missing →
> `DEGRADED`).

> **What changed in V2** (teammate handoff, `MIDAS_GATE_GOLD_RULES_V2_VALIDATION_HANDOFF.md`):
> sizing dropped from `$10,000 / $5,000 / $0` to `$2,500 / $1,500 / $1,000 / $0`;
> **`STAND_DOWN` became a state of its own** so it is machine-distinguishable from
> `RISK_OFF`, which now keeps a `$1,000` budget and **keeps trading at reduced size**;
> the divergence gate tightened from `GLD > 0` to `GLD >= +0.25%`; and the strong-dollar
> modifier gained a `SPY <= 0` guard so it cannot fire while stocks are clearly positive.

## Purpose

Our teammate is an experienced gold trader. Gold is the market's fear gauge: when people
get nervous, they buy it. That read is real expertise and it is the part of this project
that no one else in the hackathon has.

But an expert cannot watch the screen for six days, and the competition requires the
agent to be autonomous. So he writes his read down as **concrete numeric rules, once, up
front**, and this file executes those rules every run without him.

The output is deliberately small and deliberately explicit. Everything downstream depends
only on the permission block, so his rules can be rewritten without touching another
file — and no permission exists only as prose that some component has to interpret.

## Where it sits

**After the data-health gate, before the envelope.**

```
state → data health → regime.py → event_gate.py → gates.py → agent.py → validator → execution → audit.py
```

It touches no account data and places no orders. It only reads prices. Safe to run at any
time, as often as we like.

## Inputs

| Input | Criticality | Detail |
|---|---|---|
| `SPY` price | **Critical** — missing or stale → `HALTED` | Both the trading underlying and half the fear test |
| `GLD` price | **Critical** — missing → `HALTED` | The thesis does not exist without it |
| `GDX` price | Secondary — missing → `DEGRADED`, note it in `reason` | Divergence test is skipped |
| `UUP` price | Secondary — missing → `DEGRADED` | Dollar modifier is skipped |
| `TLT` price | Display only | Zero voting power. Never changes a decision |
| `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` | — | Environment variables |
| Persisted state | — | Yesterday's/this morning's regime, for the intraday caution rule and the stand-down latch |

Roughly 30 days of daily bars plus the latest available price, via `alpaca-py`. No options
data, no account access.

### Measurement convention

Used identically in live logic **and** in the backtest, or the backtest is measuring a
different strategy:

```
return = latest available price / previous regular-session close − 1
```

This matters because we run at 09:35 ET, five minutes into the session. There is no
completed daily candle to use and the system must not pretend there is.

## Outputs

A plain dictionary, also written into the run log and into `state.json` so the reasoning
is visible later:

```json
{
  "regime": "NEUTRAL",
  "regime_measured": "NEUTRAL",
  "operating_state": "ACTIVE",
  "stand_down": false,
  "put_spreads_allowed": true,
  "risk_budget_usd": 1500,
  "max_contracts": 3,
  "min_strike_distance_pct": 1.5,
  "max_positions": 2,
  "allowed_strategies": ["PUT_CREDIT_SPREAD"],
  "rules_version": "V2-validation",
  "signals": {
    "SPY": -0.18,
    "GLD": 0.62,
    "GDX": 0.05,
    "UUP": 0.31,
    "TLT": -0.10
  },
  "reason": "dollar firm with gold bid and stocks soft - caution upgraded"
}
```

`signals` is keyed by ticker, one percentage change per symbol, exactly the shape
`classify()` takes as input — so a stored block can be replayed through the rules
unchanged. The GLD−GDX divergence is not stored; it is `GLD − GDX`, derived where needed.

`signals` and `reason` exist so a human reading the dashboard can see *why* the day was
labelled the way it was. Judges will look at this. `rules_version` exists so that a
result can never be attributed to the wrong set of thresholds.

### Machine-readable states

`RISK_OFF` and `STAND_DOWN` are different permissions and downstream logic must never
have to infer the difference from prose. Every consumer reads the fields, not the text:

```json
{ "regime": "RISK_OFF",   "stand_down": false, "risk_budget_usd": 1000, "put_spreads_allowed": true  }
{ "regime": "STAND_DOWN", "stand_down": true,  "risk_budget_usd": 0,    "put_spreads_allowed": false }
```

The first still trades — smaller, further out, one position. The second trades nothing.

## Logic

Four states, in order of how much freedom they give:

| Regime | What it means | What we are allowed to do |
|---|---|---|
| `RISK_ON` | Calm. Gold quiet, stocks steady | Iron condors and put spreads. Strikes ~1.0% away. Up to 3 positions. **$2,500** open risk |
| `NEUTRAL` | Ordinary. Nothing decisive | Put credit spreads only. ~1.5% away. Up to 2 positions. **$1,500** |
| `RISK_OFF` | Fear rising | Put credit spreads, reduced size. ~2.5% away. 1 position. **$1,000** |
| `STAND_DOWN` | Confirmed flight to safety | Nothing. No new risk, put spreads forbidden. **$0** |

`max_contracts` is always `risk_budget_usd ÷ $500` — 5 / 3 / 2 / 0 — because `$500` is the
hard per-spread loss cap in `gates.py` and is never regime-scaled.

Note the direction of the safety valve: the more nervous the regime, the **further out**
the strikes, the **fewer** the positions and the **smaller** the money at risk. Fear does
not make us trade harder.

**`STAND_DOWN` is reachable only by rule 1 (or its latch).** The divergence modifier, the
dollar modifier and the missing-secondary-input downgrade all clamp at `RISK_OFF`. Two
reasons: the handoff forbids requiring GDX divergence for a stand-down, and a data outage
is not a market signal — refusing to trade all day is a decision the market has to earn.

### Gold Rules V2

> **Status: frozen for validation** (`rules_version: V2-validation`). These thresholds and
> budgets **must not be tuned from backtest output.** Record results first; any amendment
> requires explicit teammate sign-off, a new rules version, and a separate reviewed change.
> These numbers came from the teammate — they are his, not invented, and not a
> placeholder. `backtest.py` validates them, it does not tune them.
> Any V3 must be documented as `V2 result → observed failure → human-approved amendment`,
> never as a threshold quietly moved to improve historical P&L.

Evaluated **most-cautious-first**. Where rules overlap, the most cautious result wins.

**1. Stand-down** — `STAND_DOWN`, `stand_down: true`, `put_spreads_allowed: false`, `$0`

```
GLD >= +1.00%  AND  SPY <= -1.00%
```

**Latched for the rest of the trading day.** Once set, a recovery in either number does
not clear it, and the 13:05 run cannot release it. This is the single most valuable rule
in the set: a rule that says when *not* to trade is worth more over six days than any rule
about when to trade. When it fires, rules 3 and 4 are not evaluated — there is nothing
left to downgrade.

**2. Fear rising** — `RISK_OFF`, `stand_down: false`, `$1,000`

```
GLD >= +0.75%  AND  SPY <= -0.50%
```

Reduced size, **not** a stand-down. Put spreads are still permitted; the budget, the
position count and the strike distance do the work. Making this equivalent to a stand-down
is explicitly forbidden by the handoff.

**3. Divergence** — caution

```
GLD − GDX >= 0.75 percentage points,  with GLD >= +0.25% and GDX <= 0
```

Gold rising while the miners do not confirm reads as flight-to-safety buying rather than
a healthy gold move. Downgrades the regime one level (`RISK_ON→NEUTRAL`,
`NEUTRAL→RISK_OFF`). The `GLD >= +0.25%` floor is V2's tightening of V1's `GLD > 0`: a
gold move of two basis points is noise, and pairing it with a soft GDX should not cost us
a caution level.

**4. Dollar modifier** — asymmetric, never a promoter

```
UUP >= +0.30%  AND  GLD >= +0.50%  AND  SPY <= 0%
    → upgrade caution one level (RISK_ON→NEUTRAL, NEUTRAL→RISK_OFF). Never the reverse.

UUP <= -0.30%
    → explanatory context only. Recorded in `reason`. No permission change, ever.
```

Gold and the dollar usually move opposite. Gold *and* the dollar rising together is a
stronger fear signal than gold alone — but only while stocks are not clearly positive,
which is what the `SPY <= 0` term buys us. A firm dollar on a green tape is ordinary
market mechanics, not fear.

The weak-dollar half is **note-only by design**. Gold rising on a falling dollar may be
nothing more than currency mechanics, and that is worth telling the reader — but it must
never cancel a warning that rules 1 or 2 have already confirmed.

**5. Otherwise** — `RISK_ON`

**6. TLT** — recorded in `signals`, shown on the dashboard, and given **zero voting
power**. It is context for a human reader, nothing more.

### Separate event-calendar gate

Major scheduled US macro and Fed events are **not** Gold Regime signals. A separate,
deterministic execution/risk gate checks whether a signed-off major event falls before a
proposed spread expires and can restrict new risk without changing `regime.py`'s measured
regime or V2 thresholds.

**Status: report-only pending sign-off.** The event source, covered events, blackout
window, and exact restriction have not been approved. Do not invent or activate a blackout
window from this document; record the event context and require explicit sign-off before
the gate can block a trade.

### Separate event-calendar gate

Major scheduled US macro and Fed events are **not** Gold Regime signals. A separate,
deterministic execution/risk gate checks whether a signed-off major event falls before a
proposed spread expires and can restrict new risk without changing `regime.py`'s measured
regime or the V2 thresholds.

**Status: not built — report-only pending sign-off.** The event source, covered events,
blackout window, and exact restriction have not been approved. Do not invent or activate a
blackout window from this document; record the event context and require explicit sign-off
before the gate can block a trade. Nothing in `regime.py`, `gates.py` or `backtest.py`
implements it today, and the pipeline diagram above marks it as absent.

### Intraday caution is asymmetric

The 13:05 run re-evaluates the regime — a mid-day shift is exactly the thing a gold
trader would catch. But the result is applied one-way:

- 09:35 `RISK_ON` → 13:05 `RISK_OFF` — **applies immediately.**
- 09:35 `RISK_OFF` → 13:05 `RISK_ON` — **does not apply.** The morning's more cautious
  permissions stand until the next trading day.

The measured regime is still recorded and displayed either way, so the dashboard shows
"measured RISK_ON, permissions held at RISK_OFF from this morning" rather than hiding the
change. The stand-down latch behaves the same way.

## User experience flow

**A normal morning.**

1. The clock fires at 09:35 ET (21:35 Malaysia). Nobody is watching; that is the point.
2. The data-health gate confirms SPY and GLD are fresh. State is `ACTIVE`.
3. `regime.py` measures each fund against its previous regular-session close.
4. Gold is up 0.62%, stocks down 0.18%. Real, but small: below the stand-down bar
   (+1.00% / −1.00%) and below the fear bar (+0.75% / −0.50%). GDX is up 0.05%, a 0.57 pp
   gap — under the 0.75 pp divergence bar, so that rule does not fire either. Base regime:
   `RISK_ON`. But UUP is up 0.31% with gold above +0.50%, so the dollar modifier upgrades
   caution one level: **`NEUTRAL`**.
5. It prints one line: `REGIME=NEUTRAL budget=$1500 dist=1.5% puts=allowed rules=V2-validation`.
6. It hands the permission block to `gates.py` and exits.
7. Next morning in Malaysia, Talvin opens the dashboard: a **NEUTRAL** badge, the five
   signal numbers, and that sentence underneath. Three seconds to understand yesterday.

**A stand-down day.**

1. 09:35. Gold up 1.2%, SPY down 1.4%. Rule 1 fires.
2. Output: `STAND_DOWN`, `stand_down: true`, `put_spreads_allowed: false`,
   `risk_budget_usd: 0`, latched.
3. `gates.py` produces no envelope. `agent.py` is never called. No model cost.
4. 13:05: markets have calmed, gold back to +0.3%. The rule re-measures as `RISK_ON` —
   and is ignored, because the latch holds for the day.
5. The dashboard reads: **STAND_DOWN (latched) — stand-down triggered 09:35: GLD +1.2%,
   SPY −1.4%. Measured regime at 13:05 was RISK_ON; permissions held.**
6. This is the system's best day even though it made no money. It is also the best social
   post of the week.

**When the data does not arrive.**

1. Same trigger. The SPY request fails — Alpaca briefly down, or a bad key.
2. `regime.py` does **not** guess and does **not** default to the permissive regime. SPY
   is critical, so the run goes to `HALTED` with
   `reason: "critical price data unavailable (SPY) — halted, no envelope built"`.
3. If instead only `UUP` were missing: state `DEGRADED`, the dollar modifier is skipped,
   the regime is computed from the rest, and `reason` says so.
4. The dashboard shows the state badge with that reason. Anyone reading it can tell the
   difference between "the market was scary" and "we could not see".

## Failure modes

| What goes wrong | What happens |
|---|---|
| SPY or GLD missing/stale | `HALTED`. No envelope, no model call. Blind is not a trading condition |
| GDX or UUP missing | `DEGRADED`. Skip that test and note it in `reason`; do not invent a signal |
| TLT missing | Nothing. It has no vote |
| Event-calendar policy not signed off | Report-only. It cannot silently create a blackout window |
| Two rules match | Most-cautious-first evaluation. Stand-down beats fear beats divergence beats dollar |
| Regime looks more aggressive than this morning | Ignored until the next trading day. Recorded and displayed, not applied |
| Bad API key | Same as critical data unavailable — `HALTED`. `gates.py` would fail on the account read anyway |

The rule for this whole system: **when in doubt, do less.**

## Verification

```
python regime.py
```

`assert`-based self-checks against hand-made price data, no market connection needed:

- One calm case produces `RISK_ON` with the $2,500 budget and 5 contracts.
- One fear case (`GLD +0.9%`, `SPY −0.7%`) produces `RISK_OFF` with a **$1,000** budget,
  `stand_down: false` and put spreads still allowed — the assertion that pins "`RISK_OFF`
  is not a stand-down".
- The stand-down case produces `STAND_DOWN` with a $0 budget and an empty strategy list,
  and stays there when re-evaluated later the same day with calm inputs — recording
  `regime_measured: RISK_ON` while refusing to act on it.
- `RISK_OFF` and `STAND_DOWN` differ in fields, not prose.
- A missing **critical** input produces `HALTED`, never a regime.
- A missing **secondary** input produces `DEGRADED` and still produces a regime — and can
  never manufacture a `STAND_DOWN`, nor loosen a latched one.
- The dollar modifier only ever upgrades caution, and not at all while `SPY > 0`.
- Divergence needs `GLD ≥ +0.25%`; `GLD +0.10%` against a soft GDX does not fire.
- Weak dollar appears in `reason` and changes no permission, including on a fear day.
- Modifiers can stack to `RISK_OFF` but never past it.
- Every regime returns a complete permission block, every number in it is inside its
  allowed band, and `max_contracts == risk_budget_usd ÷ $500` in every row.

Passing looks like silence and exit code 0. Any failed assert prints the case that broke.

## Open questions

1. **Event-calendar gate sign-off.** Approve an authoritative source, covered events,
   blackout window, and whether the gate blocks or reduces new risk before activation.
2. **V2 validation review.** Review same-timestamp 09:35 ET / 13:05 ET evidence before
   changing any V2 threshold or budget.
