# `regime.py` — today's risk mood

> **In plain terms:** it looks at what gold is doing this morning and decides whether
> today is a calm day, a normal day, or a scared day — and therefore how carefully we
> should trade.

## Purpose

Our teammate is an experienced gold trader. Gold is the market's fear gauge: when
people get nervous, they buy it. That read is real expertise and it is the part of
this project that no one else in the hackathon has.

But an expert cannot sit and watch the screen for four days, and the competition
requires the agent to be autonomous. So we do the next best thing: he writes his read
down as **concrete numeric rules, once, up front**, and this file executes those rules
every single run without him.

The output is deliberately small — a label and three numbers. Everything downstream
depends only on those, so his rules can be rewritten without touching any other file.

## Where it sits

**First.** Nothing runs before it. Its output feeds straight into `gates.py`, which
turns the mood into actual limits.

`regime.py` → `gates.py` → `agent.py` → `audit.py`

It touches no account data and places no orders. It only reads prices. It is safe to
run at any time, as often as we like.

## Inputs

| Input | Detail |
|---|---|
| Price history | Daily bars for `GLD`, `GDX`, `UUP`, `TLT`, and `SPY`, read via the `alpaca-py` library |
| `ALPACA_API_KEY` | Environment variable |
| `ALPACA_SECRET_KEY` | Environment variable |

Roughly 30 days of daily bars — enough to compute a few days of change and a short
average. No options data, no account access.

## Outputs

A plain dictionary, also written into the run log so the reasoning is visible later:

```json
{
  "regime": "NEUTRAL",
  "max_contracts": 2,
  "min_strike_distance_pct": 1.5,
  "max_positions": 2,
  "signals": {
    "gld_change_pct": 0.42,
    "spy_change_pct": -0.18,
    "gld_gdx_divergence": true,
    "uup_change_pct": 0.31
  },
  "reason": "Gold up while stocks slipped, but modestly. Dollar firm. Not enough to call it fear."
}
```

`signals` and `reason` exist so a human reading the dashboard can see *why* the day
was labelled the way it was. Judges will look at this.

## Logic

Three moods, in order of how much freedom they give us:

| Mood | What it means | What we are allowed to do |
|---|---|---|
| `RISK_ON` | Calm. Gold quiet, stocks steady. | Iron condors. Strikes ~1.0% away from spot. Up to 3 positions. |
| `NEUTRAL` | Ordinary. Nothing decisive. | Put credit spreads only. ~1.5% away. Up to 2 positions. |
| `RISK_OFF` | Fear rising. | Call credit spreads only, or nothing at all. ~2.5% away. 1 position. |

Notice the direction of the safety valve: the more nervous the mood, the **further
out** the strikes and the **fewer** the positions. Fear does not make us trade
harder; it makes us trade smaller and further away.

### The rules themselves — NOT YET FINAL

> **PLACEHOLDER — replace with the teammate's actual thresholds.**
> Everything in this block is a stand-in so the code can be built and tested. It is
> a guess, not expertise. Shipping the guess would throw away the single most
> original thing about this project.

```
RISK_OFF  if  GLD up more than 0.8% while SPY is down
          or  GLD up more than 1.5% on its own
NEUTRAL   if  GLD moved between 0.3% and 0.8%
          or  GLD and GDX disagree in direction
RISK_ON   otherwise
```

### The four questions the teammate must answer

He does not need to write code. He needs to give a number for each of these:

1. **Fear rising.** Gold up by *how much*, while stocks are down by *how much*, before
   you call it fear?
2. **Gold vs the miners.** GLD is gold itself, GDX is the companies that dig it up.
   When those two disagree, what does that tell you, and how big must the gap be?
3. **The dollar.** UUP is dollar strength. Gold and the dollar usually move opposite.
   How does a strong dollar change your read of a gold move?
4. **Stand down.** Which single condition means "do not sell puts today, full stop"?

Question 4 is the most valuable one. A rule that tells us when *not* to trade is
worth more over four days than any rule about when to trade.

## User experience flow

**A normal morning.**

1. The clock fires at 09:35 ET (21:35 Malaysia time). Nobody is watching; that is the
   point.
2. `regime.py` pulls the last month of daily prices for the five funds.
3. It measures today's move in each, and compares gold against stocks and against the
   miners.
4. Gold is up 0.42%, stocks down 0.18%. Real, but small. It lands on `NEUTRAL`.
5. It prints one line to the run log:
   `REGIME=NEUTRAL max_contracts=2 dist=1.5% reason="Gold up while stocks slipped..."`
6. It hands the dictionary to `gates.py` and exits.
7. Next morning in Malaysia, Talvin opens the dashboard and sees a **NEUTRAL** badge
   with that sentence underneath it. He knows in three seconds what the system thought
   yesterday and why. Nothing needed doing.

**When the data does not arrive.**

1. Same 09:35 trigger.
2. The price request fails — Alpaca is briefly down, or the key is wrong.
3. `regime.py` does **not** guess and does **not** default to the permissive mood. It
   returns `RISK_OFF` with `reason: "price data unavailable — defaulting to most
   cautious mood"`.
4. Because `RISK_OFF` is the tightest setting, the worst outcome of a data outage is
   that we trade small and far away, or not at all. It can never be that we trade
   aggressively while blind.
5. The dashboard shows the `RISK_OFF` badge with that reason. Anyone reading it can
   tell the difference between "the market was scary" and "we could not see".

## Failure modes

| What goes wrong | What happens |
|---|---|
| Price data unavailable | Return `RISK_OFF` with an explanatory reason. Fail toward caution. |
| One of the five funds is missing | Use the rest, note it in `reason`. Gold alone is enough to produce a mood. |
| A rule contradicts another | Order of evaluation is fixed: `RISK_OFF` is checked first, then `NEUTRAL`, then `RISK_ON`. The most cautious matching rule wins. |
| Bad API key | Same as data unavailable — `RISK_OFF`. The real failure will be caught downstream when `gates.py` also cannot read the account. |

The rule for this whole system: **when in doubt, do less.**

## Verification

```
python regime.py
```

Runs a set of `assert`-based self-checks against hand-made price data, no market
connection needed:

- A big gold spike alongside falling stocks produces `RISK_OFF`.
- A flat, quiet day produces `RISK_ON`.
- Every mood returns all three sizing numbers, and each is within its allowed band.
- Missing price data produces `RISK_OFF`, never `RISK_ON`.

Passing looks like silence and exit code 0. Any failed assert prints the case that
broke.

## Open questions

1. **The real thresholds** (PLAN.md open item 2). Blocking. Everything else can be
   built and tested around the placeholder, but the placeholder must not ship.
2. Should the mood be measured against today's move so far, or yesterday's close? At
   09:35 ET the day is only five minutes old, so probably yesterday's close plus the
   opening move. Needs the teammate's view.
3. Should the second run of the day re-evaluate the mood, or inherit the morning's?
   Re-evaluating is more responsive; inheriting is more stable. Leaning toward
   re-evaluating, since a mood shift mid-day is exactly the thing a gold trader would
   catch.
