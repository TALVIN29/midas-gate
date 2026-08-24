# `bs.py` — our own option maths, display only

> **In plain terms:** Alpaca's free data gives us option risk numbers it openly admits are
> unreliable. So we compute our own, using the standard textbook formula, and we show them
> on the dashboard — but we never let them choose a trade.

> **What changed since v1** ([appendix/bs.md](../appendix/bs.md)): nothing architectural, and
> that is deliberate. The handoff explicitly preserves local Black-Scholes, display-only
> greeks, and the rule that greeks must never become decision gates. What is added here is
> the tie-in to the new control chain: the greeks are not in the envelope, not in the
> pre-trade validator, and not in any audit check — stated explicitly so nobody adds them
> later by accident.

## Purpose

Every option has a set of numbers describing how it behaves: how fast it loses value as
time passes, how much it moves when the stock moves, and so on. Collectively these are
**the greeks**. Normally you would use them to pick which contract to sell.

We cannot. Alpaca's free market data plan labels its options feed **"indicative"**
([their docs](https://docs.alpaca.markets/us/docs/about-market-data-api)), and a number
the vendor itself will not call authoritative should not be choosing where our money goes.
The dependable real-time feed costs $99 a month.

> **Corrected at Stage 0.** An earlier draft assumed the free feed returned *no* greeks.
> It does — the smoke test came back with delta, gamma, theta, vega, rho and implied
> volatility on every SPY contract we asked for. The design does not change, but the
> reason does, and the honest reason is the stronger one: we avoid greeks not because
> they are missing, but because they are **modelled numbers on an indicative feed**, and a
> percentage distance from spot is a direct measurement that needs no model at all. Being
> handed a plausible delta is exactly the temptation this rule exists to resist.

Two consequences, and the second is the interesting part.

**First:** we compute the greeks ourselves. Black-Scholes is public, sixty years old, and
about thirty lines of Python. Everything it needs — stock price, strike, days remaining,
interest rate — we already have reliably.

**Second, the actual design decision:** we do not select trades using greeks *at all*, not
even our own. Our formula needs a volatility estimate as an input, and that estimate is a
guess. A number built on a guess should not be choosing where our money goes.

Instead we select strikes by **percentage distance from the current stock price** — a
direct measurement, not a model output. It cannot be wrong.

**Our greeks are display-only. They are never an input to a decision.** Worth stating
twice, because the tempting mistake is to compute a nice-looking delta and quietly start
filtering on it.

## Where it sits

**To one side of the chain, deliberately unwired.**

```
regime.py → gates.py → agent.py → validator → execution → audit.py → bs.py (display)
```

It is a pure calculator: numbers in, numbers out. No network calls, no account access, no
knowledge of the rest of the system. `audit.py` calls it to decorate the dashboard.
Nothing else depends on it.

Specifically, and by design, the greeks appear in **none** of these:

| Component | Uses greeks? |
|---|---|
| `regime.py` permission block | No |
| The legal envelope in `gates.py` | No — strike selection is percentage distance |
| The pre-trade validator | No — it re-checks distance, size, loss, budget, state |
| The agent's prompt as a selection criterion | No — the agent may read them as context, never as a rule |
| Any audit check | No |
| Any learning lesson | No |
| The dashboard | Yes, with a footnote |

If a future change wants a greek to gate something, that is a redesign that needs a paid
data feed first — not a quiet edit.

Because of all this, it is the easiest file in the project to test and the least likely to
break anything.

## Inputs

Plain function arguments, no environment, no network:

| Argument | Meaning |
|---|---|
| `S` | Current stock price |
| `K` | Strike price of the contract |
| `T` | Time to expiry, in years (2 days is about `0.0055`) |
| `r` | Risk-free interest rate, as a decimal |
| `sigma` | Volatility estimate |
| `option_type` | `"call"` or `"put"` |

`ASSUMPTION:` `r` is hardcoded at a current short-term Treasury rate rather than fetched.
Over a 1–3 day contract the rate contributes almost nothing to the price, and fetching it
would add a network dependency to a file that has none. Revisit only if displayed prices
look visibly off.

`sigma` is estimated from recent SPY price movement. This is the guess mentioned above,
and precisely why nothing decides anything based on the result.

## Outputs

```json
{
  "price": 1.42,
  "delta": -0.18,
  "gamma": 0.021,
  "theta": -0.34,
  "vega": 0.08
}
```

What each means in plain language, since these appear on the public dashboard:

- **price** — what the formula thinks the contract is worth.
- **delta** — how much the option price moves when the stock moves $1. Also a rough read
  on the chance of the contract mattering at expiry.
- **gamma** — how fast delta itself changes. High gamma means behaviour is shifting fast.
- **theta** — how much value the contract loses per day purely from time passing. **We are
  the seller, so a negative theta on the contract is money flowing toward us.** This is the
  engine of the entire strategy and the number worth showing most prominently.
- **vega** — how much the price moves when the market gets more or less jumpy.

## Logic

Standard Black-Scholes for European options, plus the standard derivatives for the four
greeks. Nothing invented, nothing clever. Reference values are widely published, which is
exactly why we can prove ours is right.

Guards worth having:

- If `T` is zero or negative (the contract has expired), return the value at expiry rather
  than dividing by zero.
- If `sigma` is zero or negative, refuse rather than produce a meaningless number.

## User experience flow

**Dashboard, after a trade is placed.**

1. The agent sold a SPY put spread: short 640, long 635, expiring in 2 days.
2. `audit.py` fetches the current SPY price and the days remaining.
3. It calls `bs.py` once per contract.
4. The two results combine into a position-level view: net theta about +$0.29 per day per
   contract, in our favour.
5. `audit.py` writes them into `state.json` tagged `computed_greeks`, so nobody mistakes
   them for Alpaca's.
6. The dashboard shows a small panel: **Time decay working for us: about $29/day**, with a
   footnote reading *"Computed locally with Black-Scholes. Alpaca's free feed is
   indicative, so these are our own figures — shown for context, not used to select
   trades."*
7. A judge reads that footnote and sees a team that understood a data limitation and
   engineered around it honestly. That footnote is worth more to the score than a fancier
   number would be.

**When the maths cannot be done.**

1. `audit.py` calls `bs.py` for a contract that expired an hour ago. `T` is negative.
2. `bs.py` returns the expiry value with a `note` field explaining it has expired. It does
   not raise, and does not crash the audit.
3. The dashboard shows the greeks panel as **not available** for that position; the rest of
   the page — trades, P&L, reasoning, audit result — renders normally.
4. Deliberate: a display calculator must never be able to take down the record of what
   actually happened, and a missing greek must never escalate an operating state.

## Failure modes

| What goes wrong | What happens |
|---|---|
| Contract already expired (`T <= 0`) | Return the value at expiry with a note. No exception |
| Volatility estimate zero or negative | Refuse with a clear message. There is no sensible answer |
| Volatility estimate simply wrong | The greeks are off. Harmless, because nothing decides on them. This is the whole reason for the display-only rule |
| Any unexpected error | `audit.py` catches it, marks the greeks unavailable, and publishes everything else. Never a `DEGRADED` or `HALTED` state — this is not critical data |

## Verification

```
python bs.py
```

An `assert` against a known textbook example: `S=100, K=100, T=1, r=0.05, sigma=0.20`
gives a call price of about **$10.45**. That figure appears in every options textbook and
every online calculator, so if ours matches, the implementation is right.

Also asserted:

- Put-call parity holds — call minus put equals spot minus the discounted strike. Catches
  sign errors, the most common mistake in this kind of code.
- A call's delta is between 0 and 1; a put's is between −1 and 0.
- Theta is negative for both, meaning both contracts decay as time passes.
- An expired contract returns its expiry value rather than raising.
- `bs` is imported by `audit.py` and by nothing else — asserted by grep in the test, so the
  display-only rule cannot rot silently.

Passing looks like silence and exit code 0.

## Open questions

1. How should volatility be estimated? Simple recent price movement is cheap and enough
   for a display number. Anything fancier is effort spent on a figure that decides nothing.
2. Greeks per contract, or summed for the position? Summed is more legible — "$29 a day in
   our favour" beats a table of per-leg deltas. Leaning summed, detail underneath.
3. Should Alpaca's own indicative greeks be shown alongside ours for comparison? It would
   demonstrate the problem visually and is a strong presentation point, but invites
   confusion about which number is real. Undecided.
