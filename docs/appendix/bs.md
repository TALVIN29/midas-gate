# `bs.py` — our own option maths

> **In plain terms:** Alpaca's free data gives us option risk numbers it openly admits
> are unreliable. So we compute our own, using the standard textbook formula, and we
> show them on the dashboard — but we never let them choose a trade.

## Purpose

Every option has a set of numbers describing how it behaves: how fast it loses value
as time passes, how much it moves when the stock moves, and so on. Collectively these
are called **the greeks**. Normally you would use them to pick which contract to sell.

We cannot. Alpaca's free market data plan labels its options feed **"indicative"**
([their docs](https://docs.alpaca.markets/us/docs/about-market-data-api)) and the
greeks and implied volatility that come with it are not dependable. The real-time feed
that would be dependable costs $99 a month.

Two consequences, and the second one is the interesting part.

**First:** we compute the greeks ourselves. The Black-Scholes formula is public,
sixty years old, and about thirty lines of Python. Everything it needs — the stock
price, the strike, the days remaining, the interest rate — we already have reliably.

**Second, and this is the actual design decision:** we do not select trades using
greeks *at all*, not even our own. Our formula still needs an estimate of volatility
as an input, and that estimate is a guess. A number built on a guess should not be
choosing where our money goes.

Instead we select strikes by **percentage distance from the current stock price**.
That is a direct measurement, not a model output. It cannot be wrong.

**Our greeks are display-only. They are never an input to a decision.** That is worth
stating twice, because the tempting mistake is to compute a nice-looking delta and
quietly start filtering on it.

## Where it sits

**To one side.** It is a pure calculator with no connection to anything.

It takes numbers and returns numbers. It makes no network calls, reads no account,
and knows nothing about the rest of the system. `audit.py` calls it to decorate the
dashboard. Nothing else depends on it.

Because of this, it is the easiest file in the project to test and the least likely to
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

`ASSUMPTION:` `r` is hardcoded at a current short-term Treasury rate rather than
fetched. Over a 1–3 day contract the rate contributes almost nothing to the price, and
fetching it adds a network dependency to a file that has none. Revisit only if the
displayed prices look visibly off.

`sigma` is estimated from recent SPY price movement. This is the guess mentioned
above, and precisely why nothing decides anything based on the result.

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

What each one means in plain language, since these appear on the public dashboard:

- **price** — what the formula thinks the contract is worth.
- **delta** — how much the option price moves when the stock moves $1. Also a rough
  read on the chance of the contract mattering at expiry.
- **gamma** — how fast delta itself changes. High gamma means the position's behaviour
  is shifting quickly.
- **theta** — how much value the contract loses per day, purely from time passing.
  **We are the seller, so a negative theta on the contract is money flowing toward
  us.** This is the entire engine of the strategy and it is the number worth showing
  most prominently.
- **vega** — how much the price moves when the market gets more or less jumpy.

## Logic

The standard Black-Scholes formulas for European options, plus their standard
derivatives for the four greeks. Nothing invented, nothing clever. Reference values
are widely published, which is exactly why we can prove ours is right.

Guards worth having:

- If `T` is zero or negative (the contract has expired), return the value at expiry
  directly rather than dividing by zero.
- If `sigma` is zero or negative, refuse rather than produce a meaningless number.

## User experience flow

**Dashboard, after a trade is placed.**

1. `agent.py` has sold a SPY put spread: short the 640 strike, long the 635, expiring
   in 2 days.
2. `audit.py` fetches the current SPY price and works out the days remaining.
3. It calls `bs.py` once for each of the two contracts.
4. The two results are combined into a position-level view: net theta about +$0.29 per
   day per contract, in our favour.
5. `audit.py` writes those numbers into `state.json`, tagged as `computed_greeks` so
   nobody mistakes them for Alpaca's.
6. The dashboard shows a small panel:
   **Time decay working for us: about $29/day** with a footnote reading *"Computed
   locally with Black-Scholes. Alpaca's free feed is indicative, so these are our own
   figures — shown for context, not used to select trades."*
7. A judge reads that footnote and sees a team that understood a data limitation and
   engineered around it honestly. That footnote is worth more to the score than a
   fancier number would be.

**When the maths cannot be done.**

1. `audit.py` calls `bs.py` for a contract that expired an hour ago. `T` is negative.
2. `bs.py` returns the expiry value with a `note` field explaining the contract has
   expired. It does not raise and does not crash the audit.
3. The dashboard shows the greeks panel as **not available** for that position, and
   the rest of the page — the trades, the profit and loss, the reasoning — renders
   completely as normal.
4. This is deliberate: a display calculator must never be able to take down the record
   of what actually happened.

## Failure modes

| What goes wrong | What happens |
|---|---|
| Contract already expired (`T <= 0`) | Return the value at expiry with a note. No exception. |
| Volatility estimate is zero or negative | Refuse with a clear message. There is no sensible answer. |
| Volatility estimate is simply wrong | The greeks are off. Harmless, because nothing decides on them. This is the whole reason for the display-only rule. |
| Any unexpected error | `audit.py` catches it and marks the greeks unavailable. The dashboard loses one panel, nothing else. |

## Verification

```
python bs.py
```

An `assert` checking a known textbook example: `S=100, K=100, T=1, r=0.05,
sigma=0.20` gives a call price of about **$10.45**. This figure appears in every
options textbook and in every online calculator, so if ours matches it, the
implementation is right.

Also asserted:

- Put-call parity holds — call minus put equals spot minus the discounted strike. This
  catches sign errors, the most common mistake in this kind of code.
- A call's delta is between 0 and 1; a put's is between −1 and 0.
- Theta is negative for both, meaning both contracts decay as time passes.
- An expired contract returns its expiry value rather than raising.

Passing looks like silence and exit code 0.

## Open questions

1. How should volatility be estimated? Simple recent price movement is the cheap
   option and is enough for a display number. Anything fancier is effort spent on a
   figure that decides nothing.
2. Should the dashboard show greeks per contract, or summed for the whole position?
   Summed is more useful to a reader — "$29 a day in our favour" is legible in a way
   that a table of per-leg deltas is not. Leaning toward summed, with the detail
   available underneath.
3. Should Alpaca's own indicative greeks be shown alongside ours as a comparison? It
   would demonstrate the problem visually and is a strong presentation point, but it
   invites confusion about which number is real. Undecided.
