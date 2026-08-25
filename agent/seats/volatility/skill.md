# Seat: `volatility` — is the premium worth the risk?

**Status: inputs ready, one upstream change required** (`legal_candidates` must stop
discarding IV and greeks — see `INTEGRATION.md`).

## Question this seat answers

Given that every candidate is already legal, **is any of them actually paying enough for the
risk it carries, and can it be traded without giving the premium back to the spread?**

This is the only seat that reads the option chain. It is also the seat with the most to say
at a 1–3 day horizon, because that is the horizon at which premium and decay dominate.

## Inputs — exactly these, nothing else

Per candidate in the list it is given:

| Field | Source | Note |
|---|---|---|
| `short_strike`, `long_strike` | `agent.py:163` | width is always 5.0 |
| `credit` | `agent.py:157` | `bid_short − ask_long`, already conservative |
| `max_loss` | `agent.py:160` | `(5.0 − credit) × 100` |
| `return_on_risk_pct` | `agent.py:168` | |
| `distance_pct` | `agent.py:167` | how far OTM, versus spot at build |
| `short_spread` | `agent.py:169` | `ask − bid` on the short leg — the liquidity read |
| `iv` | **to be added** | `snap["impliedVolatility"]`, or `None` |
| `delta`, `theta` | **to be added** | `snap["greeks"]`, or `None` |
| `iv_is_modelled` | **to be added** | `true` when the value came from `bs.greeks()` rather than the feed |

Plus, once per run:

| Field | Source |
|---|---|
| `expiries` | `envelope["expiries"]` — the legal DTE window |
| `spot` | `envelope["spot_at_build"]` |
| `min_distance_pct` | `envelope["short_strike_min_distance_pct"]` |

**Not given:** account, equity, P&L, positions, halts, regime name, any other seat's view,
its own calibration.

## Method

1. **Liquidity first.** `short_spread` above `$0.10` means crossing the spread eats a
   material share of the credit. The existing deterministic baseline refuses these outright
   (`agent.py:181`); this seat should treat it as a strong `AGAINST` rather than a silent
   filter, and say so, because *why* a trade was refused is what goes on the dashboard.
2. **Premium quality.** `return_on_risk_pct` against `distance_pct`. A spread paying 1% of
   the risk taken is a bad trade even when legal — this is stated in the current system
   prompt (`agent.py:213-215`) and remains true.
3. **Decay working for us.** `theta` on the short leg should dominate. `bs.spread_theta_per_day`
   (`bs.py:72`) is the existing local computation for this.
4. **IV context.** Elevated IV means richer premium *and* a market pricing a larger move.
   High IV alone is neither bullish nor bearish for this seat; IV that is rich relative to
   what the distance implies is what makes a candidate attractive.
5. **Term structure.** Where more than one legal expiry exists, compare. A steep near-term
   IV usually means an event is priced — note it, but do not attempt to identify the event.
   That is the `macro-calendar` seat's job and this seat must not duplicate it.

## Output

Standard stance object (`PANEL.md`). This seat is expected to use
`preferred_candidate_index` frequently — it is the seat best placed to discriminate between
candidates rather than between trading and not trading.

## Must refuse to opine on

- **Market direction.** This seat has no directional inputs and must not infer any. If it
  finds itself reasoning about whether SPY will fall, it has left its domain.
- **Whether the regime is right.** It does not see the regime and does not get to second-guess it.
- **Position sizing.** Owned by `gates.py`.
- **Identifying what event is priced into a skew.** Note the shape; name no cause.

## `ABSTAIN` when

- The candidate list is empty.
- `credit` or `short_spread` is missing across all candidates — it cannot see price quality.

Note it does **not** abstain merely because `iv` and `delta` are `None`. Credit, distance,
liquidity and max loss are enough for a stance; the greeks sharpen it. When they are absent
or `iv_is_modelled` is true, conviction should drop, not the stance disappear.
