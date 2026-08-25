# Seat: `positioning` — is the market braced, or complacent?

**Status: weakest sourcing of the four. This is the seat to cut if 2026-08-28 is at risk —
the panel is specified to work with three. Do not let it delay the other three.**

## Why this seat is hard, and what it is not

Talvin's original brief asked for **sentiment**. The honest position is that free
news-sentiment feeds are SEO-farm and LLM-generated content, and his own standing research
rules reject exactly that class of source. Social and KOL sentiment is unverified by
definition and would have to be labelled as such, which strips it of decision value.

So this seat does **not** read news, headlines or social media. It reads **positioning** —
what the market has actually paid to protect itself, which is sentiment expressed in prices
rather than in words. That is a narrower claim and a defensible one.

Say this out loud on the dashboard. A seat labelled "sentiment" that reads volatility futures
is misleading; one labelled "positioning" that says what it reads is not.

## Question this seat answers

**Is the market pricing more or less risk than it has recently, and is it paying up for
near-term protection specifically?**

## Inputs — exactly these, nothing else

| Field | Source | Status |
|---|---|---|
| `vix_short` | `VIXY` percentage change and level versus trailing 20-session mean | Available — Alpaca equities, same client as `regime.fetch_signals` |
| `vix_term` | `VXX` versus `VIXY` — a crude near-versus-further volatility slope | Available, **proxy** |
| `realised_vol_5d` | SPY 5-session realised volatility, from cached daily bars | Available |
| `realised_vol_20d` | SPY 20-session realised volatility | Available |
| `iv_minus_realised` | short-leg `iv` from the chain minus `realised_vol_5d` | Depends on the `legal_candidates` change in `INTEGRATION.md` |
| `proxy_flags` | which of the above are proxies rather than direct measures | Required |

**Not given:** candidates' pricing detail, the regime, the calendar, the account, other
seats, its own calibration.

## Honesty requirements — not optional

1. **`VIXY`/`VXX` are ETF proxies for VIX term structure, not the index.** They carry roll
   decay and track imperfectly. Every stance that leans on `vix_term` must carry
   `proxy: vix_term` in its evidence, and conviction is capped at **2** when it does.
2. **A better source exists and was not used.** CBOE put/call ratios and the actual VIX/VIX9D
   term structure are the right inputs. They were not available on the free Alpaca feed
   inside the deadline. Record that decision here rather than letting a future reader assume
   VIXY was preferred on the merits.
3. **This seat cannot be fully backtest-seeded**, because `iv_minus_realised` needs
   historical chains that the free feed does not provide. Its record ships `partial: true`
   with `missing_inputs: ["iv_minus_realised"]`, or `n: 0`. See `CALIBRATION.md`.

## Method

1. **Is volatility bid?** `vix_short` versus its trailing mean. Rising volatility into a
   short-premium trade is a warning regardless of how rich the premium looks.
2. **Near versus further.** `vix_term` inverting — near-dated bid above further-dated — means
   the market is buying protection *now*, not in general. At a 1–3 day horizon this is the
   most relevant shape available to this seat.
3. **Implied versus realised.** `iv_minus_realised` positive and wide is the ordinary
   condition for selling premium profitably. Narrow or negative means being paid little for
   real movement.
4. **Complacency cuts both ways.** Very low volatility with no term premium is a good
   environment for this strategy *and* the condition preceding sharp moves. State which
   reading is being taken and why — do not present the ambiguity as a conclusion.

## Output

Standard stance object (`PANEL.md`). `preferred_candidate_index` is **always `null`** — this
seat sees no per-candidate fields except one derived IV. It votes on the environment.

## Must refuse to opine on

- **News, headlines, geopolitics, social sentiment.** Not its inputs. Not anyone's inputs in
  this system.
- **Scheduled events.** If volatility is bid because of a print, that is the
  `macro-calendar` seat's observation. Note the shape; name no cause.
- **Candidate selection or premium quality.** The `volatility` seat's domain.
- **Direction.** Volatility is not a directional signal and must not be smuggled into one.

## `ABSTAIN` when

- `vix_short` is unavailable — its primary input is gone.
- Only proxy inputs are available *and* they disagree with each other. Two proxies
  contradicting is not a signal.
- `realised_vol_5d` cannot be computed from the cached bars.
