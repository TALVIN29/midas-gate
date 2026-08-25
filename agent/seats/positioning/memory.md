# `positioning` — memory schema

**Schema only. The record lives in `site/state.json` under
`learning.seat_calibration.positioning`.** Nothing writes to this folder at runtime.

## What it remembers

```json
{
  "n": 0, "hit_rate": null, "n_neutral": 0, "n_abstain": 0,
  "partial": true,
  "missing_inputs": ["iv_minus_realised"],
  "by_regime": {},

  "proxy_leaning_rate": null,
  "disagreed_with_volatility": {"n": 0, "hit_rate": null},
  "live_runs_included": 0
}
```

**This seat may legitimately ship with `n: 0`.** Historical option chains are not available
on the free feed, so `iv_minus_realised` cannot be reconstructed for past sessions. Two
honest options, both acceptable:

- Seed on the inputs that *do* exist historically — `vix_short`, `vix_term`,
  `realised_vol_5d`, `realised_vol_20d` — and set `partial: true` with `missing_inputs`
  listing what was absent.
- Ship `n: 0` and let it earn its record live, displayed as "no track record yet."

**Do not synthesise historical option prices to fill the gap.** A modelled IV scored as
though it were real is the flattering wrong number `docs/backtest.md` exists to prevent.

## Seat-specific counters

| Counter | Why it exists |
|---|---|
| `proxy_leaning_rate` | Share of stances where a proxy input was load-bearing. Expected high. Establishes upfront how much of this seat's record rests on `VIXY`/`VXX` rather than direct measurement. |
| `disagreed_with_volatility` | Sessions where this seat and the `volatility` seat took opposing stances, and who was right. **This is the most interesting number the whole panel produces.** The two seats are designed to conflict on rich-premium days; this measures whether that conflict carries information or is just two seats reading the same thing through different lenses. |

`disagreed_with_volatility` is computed by `audit.py` from the stored stance objects — it
requires no extra state, and it is the direct empirical test of the panel's core premise. If
it shows the two seats never disagree, the four-seat design has not earned its cost and that
should be said in the write-up rather than hidden.

## What it may never remember

- Any threshold — no learned "VIXY above X means stand down." Thresholds are `gates.py`'s and
  `regime.py`'s.
- News, headlines or social sentiment. Never among its inputs, so never in its memory.
- Direction. It records magnitude reads and their accuracy, never a directional track record,
  because it has no directional inputs.
- Another seat's record — except the *joint* `disagreed_with_volatility` counter, which is
  about the pair and is written by `audit.py`, not by either seat.

## Update rule

Appended by `audit.py` after `classify`, using the single scoring function in
`CALIBRATION.md`. Every entry records which inputs were present, so a record built mostly on
proxies is distinguishable later from one built on complete data.

## How it re-enters the system

Shown to the **synthesis step only**, as evidence, and always with `partial` and `n` attached.
The seat never sees its own record. Nothing auto-adjusts.

Given this seat's thin evidence base, the synthesis prompt should carry its `partial: true`
flag explicitly rather than just its hit rate — a 70% hit rate on a partially-seeded proxy
seat is not the same claim as 70% on `cross-asset`, and the synthesis step must be able to
tell them apart.
