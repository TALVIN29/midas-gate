# Appendix — v1 specifications (pre-handoff)

These are the original plain-language module specs, written before any code existed and
before the architecture handoff (`MIDAS_GATE_ARCHITECTURE_HANDOFF_FOR_TALVIN_AND_CLAUDE.md`)
and before the build decisions recorded in `BUILD_PLAN.md`.

They are **superseded**. The current contract the code must satisfy lives one level up in
[`../docs/`](../docs/README.md). Nothing here should be built from.

They are kept, unedited, for one reason: they are the record of what we believed first.
Three things in them turned out to be wrong, and the corrections are the interesting part
of the project's story:

| v1 said | Now |
|---|---|
| "About four trading days. Labor Day closes Sep 1." | Sep 1 2026 is a Tuesday; US Labor Day 2026 is **Sep 7**. Real window: Fri Aug 28, Mon Aug 31, Tue Sep 1, Wed Sep 2, Thu Sep 3, Fri Sep 4 to 11:00 ET — ~5.5 days, no holiday gap |
| Fixed $2,000 total open risk | **Regime-scaled** budget, ceiling $10,000: RISK_ON $10k / NEUTRAL $5k / RISK_OFF $0. Per-spread cap unchanged at $500 |
| Regime thresholds `PLACEHOLDER — NOT YET FINAL` | **Gold Regime Rules V1** exist, sourced from the teammate, pending his sign-off by Aug 27 |
| Envelope → agent → audit, three stages | Six: state → data-health → regime → envelope → agent → **pre-trade validator** → execution → audit → outcome classification |
| Audit violation is recorded and published | Audit violation **latches a halt** and escalates to `REVIEW_REQUIRED` |

## Source documents

Not module specs — the inputs the current docs were written from. Kept here so the live
tree holds one current layer (`docs/`) and one historical layer (this folder).

| File | What it is |
|---|---|
| [PLAN.md](PLAN.md) | The original strategy and schedule. Superseded by [`../docs/README.md`](../docs/README.md) plus [`../BUILD_PLAN.md`](../BUILD_PLAN.md). Contains the wrong calendar and the flat $2,000 sizing |
| [MIDAS_GATE_ARCHITECTURE_HANDOFF_FOR_TALVIN_AND_CLAUDE.md](MIDAS_GATE_ARCHITECTURE_HANDOFF_FOR_TALVIN_AND_CLAUDE.md) | The teammate's control-architecture upgrade. **Still the authority** on bounded autonomy, the four operating states, pre-trade revalidation, audit escalation and the learning loops — the current docs implement it rather than replacing it |
| `WHATSAPP.md` | The team conversation the gold thresholds and the division of ownership came out of. Provenance for Gold Regime Rules V1. **Local only** — gitignored, along with the two `.zip` archives beside it, because it holds private message drafts |

`BUILD_PLAN.md` stays at the repository root: it is the live build order, not history.

## Module specs

| v1 file | Superseded by |
|---|---|
| [README.md](README.md) | [../docs/README.md](../docs/README.md) |
| [regime.md](regime.md) | [../docs/regime.md](../docs/regime.md) |
| [gates.md](gates.md) | [../docs/gates.md](../docs/gates.md) |
| [bs.md](bs.md) | [../docs/bs.md](../docs/bs.md) |
| [agent.md](agent.md) | [../docs/agent.md](../docs/agent.md) |
| [audit.md](audit.md) | [../docs/audit.md](../docs/audit.md) |
| [backtest.md](backtest.md) | [../docs/backtest.md](../docs/backtest.md) |
| [workflow.md](workflow.md) | [../docs/workflow.md](../docs/workflow.md) |
| [dashboard.md](dashboard.md) | [../docs/dashboard.md](../docs/dashboard.md) |
