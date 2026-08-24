# `regime.py` — today's risk regime

> **In plain terms:** it looks at what gold is doing, decides whether today is a calm
> day, a normal day or a scared day — and issues the permissions that everything
> downstream is allowed to work inside.

> **What changed since v1** ([appendix/regime.md](../appendix/regime.md)): the placeholder
> thresholds are gone, replaced by **Gold Regime Rules V1** from the teammate. The output
> is now a full machine-readable permission block (risk budget, allowed strategies, a
> put-spread permission flag), not just a label and three numbers. Added: an explicit
> measurement convention, the day-latched stand-down, asymmetric intraday caution, and
> the split between critical inputs (missing → `HALTED`) and secondary inputs (missing →
> `DEGRADED`).

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
state → data health → regime.py → gates.py → agent.py → validator → execution → audit.py
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
  "risk_budget_usd": 5000,
  "max_contracts": 2,
  "min_strike_distance_pct": 1.5,
  "max_positions": 2,
  "allowed_strategies": ["PUT_CREDIT_SPREAD"],
  "put_spreads_allowed": true,
  "rules_version": "V1-pending-signoff",
  "signals": {
    "gld_change_pct": 0.62,
    "spy_change_pct": -0.18,
    "gdx_change_pct": 0.05,
    "gld_gdx_divergence_pp": 0.57,
    "uup_change_pct": 0.31,
    "tlt_change_pct": -0.10
  },
  "reason": "Gold up while stocks slipped, but modestly. Dollar firm — caution upgraded one level from RISK_ON. Not enough to call it fear."
}
```

`signals` and `reason` exist so a human reading the dashboard can see *why* the day was
labelled the way it was. Judges will look at this. `rules_version` exists so that a
result can never be attributed to the wrong set of thresholds.

## Logic

Three regimes, in order of how much freedom they give:

| Regime | What it means | What we are allowed to do |
|---|---|---|
| `RISK_ON` | Calm. Gold quiet, stocks steady | Iron condors and put spreads. Strikes ~1.0% away. Up to 3 positions. $10,000 open risk |
| `NEUTRAL` | Ordinary. Nothing decisive | Put credit spreads only. ~1.5% away. Up to 2 positions. $5,000 |
| `RISK_OFF` | Fear rising | No new risk. ~2.5% away. 1 position. $0 |

Note the direction of the safety valve: the more nervous the regime, the **further out**
the strikes, the **fewer** the positions and the **smaller** the money at risk. Fear does
not make us trade harder.

### Gold Regime Rules V1

> **Status: V1, pending teammate sign-off by Aug 27.** These numbers came from the
> teammate's own interview answers — they are his, not invented, and not a placeholder.
> If he amends them, this block and `rules_version` change together and nothing else
> moves. If he does not, V1 ships as-is, labelled as V1 on the dashboard and in the
> write-up.

Evaluated **most-cautious-first**. The first matching rule wins.

**1. Stand-down** — `put_spreads_allowed: false`

```
GLD >= +1.00%  AND  SPY <= -1.00%
```

**Latched for the rest of the trading day.** Once set, a recovery in either number does
not clear it. This is the single most valuable rule in the set: a rule that says when
*not* to trade is worth more over six days than any rule about when to trade.

**2. Fear rising** — `RISK_OFF`

```
GLD >= +0.75%  AND  SPY <= -0.50%
```

**3. Divergence** — caution

```
GLD − GDX >= 0.75 percentage points,  with GLD > 0 and GDX <= 0
```

Gold rising while the miners do not confirm reads as flight-to-safety buying rather than
a healthy gold move. Downgrades the regime one level.

**4. Dollar modifier** — asymmetric, never a promoter

```
UUP >= +0.30%  AND  GLD >= +0.50%
    → upgrade caution one level (RISK_ON→NEUTRAL, NEUTRAL→RISK_OFF). Never the reverse.

UUP <= -0.30%  with GLD rising
    → gold alone cannot trigger RISK_OFF; SPY or GDX must confirm.
```

Gold and the dollar usually move opposite. Gold *and* the dollar rising together is a
stronger fear signal than gold alone. Gold rising on a falling dollar may be nothing more
than currency mechanics.

**5. Otherwise** — `RISK_ON`

**6. TLT** — recorded in `signals`, shown on the dashboard, and given **zero voting
power**. It is context for a human reader, nothing more.

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
5. It prints one line: `REGIME=NEUTRAL budget=$5000 dist=1.5% puts=allowed rules=V1`.
6. It hands the permission block to `gates.py` and exits.
7. Next morning in Malaysia, Talvin opens the dashboard: a **NEUTRAL** badge, the five
   signal numbers, and that sentence underneath. Three seconds to understand yesterday.

**A stand-down day.**

1. 09:35. Gold up 1.2%, SPY down 1.4%. Rule 1 fires.
2. Output: `RISK_OFF`, `put_spreads_allowed: false`, `risk_budget_usd: 0`, latched.
3. `gates.py` produces no envelope. `agent.py` is never called. No model cost.
4. 13:05: markets have calmed, gold back to +0.3%. The rule re-measures as `RISK_ON` —
   and is ignored, because the latch holds for the day.
5. The dashboard reads: **RISK_OFF (latched) — stand-down triggered 09:35: GLD +1.2%,
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
| GDX or UUP missing | `DEGRADED`. Skip that test, note it in `reason`, continue more cautiously |
| TLT missing | Nothing. It has no vote |
| Two rules match | Most-cautious-first evaluation. Stand-down beats fear beats divergence beats dollar |
| Regime looks more aggressive than this morning | Ignored until the next trading day. Recorded and displayed, not applied |
| Bad API key | Same as critical data unavailable — `HALTED`. `gates.py` would fail on the account read anyway |

The rule for this whole system: **when in doubt, do less.**

## Verification

```
python regime.py
```

`assert`-based self-checks against hand-made price data, no market connection needed:

- One calm case produces `RISK_ON` with the $10,000 budget.
- One fear case (`GLD +0.9%`, `SPY −0.7%`) produces `RISK_OFF` with a $0 budget.
- The stand-down case sets `put_spreads_allowed: false` and stays false when re-evaluated
  later in the same day with calm inputs.
- A missing **critical** input produces `HALTED`, never a regime.
- A missing **secondary** input produces `DEGRADED` and still produces a regime.
- The dollar modifier only ever upgrades caution, never downgrades it.
- Every regime returns a complete permission block, and every number in it is inside its
  allowed band.

Passing looks like silence and exit code 0. Any failed assert prints the case that broke.

## Open questions

1. **Teammate sign-off on V1 by Aug 27.** Not blocking — V1 ships labelled if he is
   silent — but his amendment is worth more than our defaults.
2. Should the divergence rule downgrade one level, or only add a note? V1 downgrades.
   Cheap to change, and it is his call.
3. Should the 13:05 run be allowed to *raise* the budget on the second day of a sustained
   calm stretch? Currently no: permissions loosen only at the next day's first run.
