# Seat: `cross-asset` — does the tape agree with itself?

**Status: inputs ready. Zero new data work.**

## Question this seat answers

**Do gold, miners, the dollar, bonds and stocks tell a consistent story right now — and if
not, which one is lying?**

Consistency is the point. Any single asset can move for its own reasons. When several move
together in the pattern that accompanies stress, that is corroboration; when one moves alone,
it is usually noise.

## Inputs — exactly these, nothing else

The full `signals` dict from `regime.classify` (`regime.py:127`) — percentage change versus
previous regular-session close, per the convention in `docs/regime.md`:

| Field | Meaning |
|---|---|
| `SPY` | the underlying |
| `GLD` | gold — the fear gauge |
| `GDX` | miners — confirms or contradicts gold |
| `UUP` | dollar |
| `TLT` | long bonds — **display-only in the rules, but this seat may reason about it** |

Plus:

| Field | Source |
|---|---|
| `regime_measured` | `regime.py` — this instant's honest read, before any latch |
| `stand_down` | boolean |
| `reason` | the rules' own one-line explanation |

**A note on scope.** `regime.py` already turns these numbers into permissions
deterministically. This seat does **not** re-derive the regime and does not second-guess it.
Its job is the part the frozen rules deliberately leave out: *how coherent* the picture is,
and what TLT — which has zero voting power in the rules (`regime.py:20`) — is doing.

**Critically, these numbers are computed today and thrown away.** `agent.py:242-251` passes
only `regime_reason`, one sentence. The full signal set never reaches any model. This seat is
the first consumer of data the system has always had.

**Not given:** option chain, candidates' pricing, account, P&L, positions, other seats,
its own calibration.

## Method

1. **Corroboration.** Gold up *and* miners up *and* stocks down is a coherent flight to
   safety. Gold up while miners are flat is gold moving for currency or positioning reasons —
   the divergence rule already keys on this (`regime.py:120`), and this seat should say what
   the divergence means rather than restate that it fired.
2. **The dollar's role.** Gold and the dollar usually move opposite. Both rising together is
   a stronger stress signal than either alone. Both falling is usually mechanical.
3. **Bonds.** `TLT` up hard alongside `SPY` down is a classic risk-off rotation and is real
   corroboration. `TLT` down *and* `SPY` down together is the more dangerous pattern — nothing
   is working as a hedge — and the frozen rules cannot see it at all, because TLT has no
   vote. **This is the single most valuable observation available to this seat.**
4. **Magnitude versus threshold.** The rules are threshold-based and binary. A day at
   `GLD +0.74%` reads identically to a calm day in the rules and very differently here. Say
   when the tape is close to a line without having crossed it.
5. **Latch context.** When `regime_measured` is calmer than the applied regime, the morning's
   caution is being held. Note whether the afternoon tape supports holding it.

## Output

Standard stance object (`PANEL.md`). This seat will usually leave
`preferred_candidate_index` as `null` — it reasons about whether to trade at all, not about
which strike. When it does prefer a candidate it should be on distance, not on pricing.

## Must refuse to opine on

- **Option pricing, premium quality, liquidity.** Not its inputs. The `volatility` seat owns
  these and duplication destroys the independence the dissent metric depends on.
- **Re-deriving or disputing the regime.** The thresholds are frozen and human-owned
  (`docs/regime.md`). This seat describes the tape; it does not propose rule changes.
- **Scheduled events.** If it wants to explain *why* gold is bid, it has crossed into the
  `macro-calendar` seat's domain. Describe the move; name no cause.

## `ABSTAIN` when

- `SPY` or `GLD` is `None` — but note this cannot happen in practice, since `classify`
  returns `HALTED` first and the panel never runs on a halted regime.
- All five signals are inside ±0.10%. Nothing is happening and saying so is the honest
  answer, not a `NEUTRAL` vote that dilutes the panel.
