"""gates.py - what is legal right now, and the check before the order.

Spec: docs/gates.md. Two jobs, both deterministic and both AI-free:

  build_envelope()  runs BEFORE agent.py - the complete set of legal trades,
                    or a refusal with no envelope fields beside it.
  validate()        runs AFTER agent.py, against freshly refreshed data - the
                    AI's proposal never reaches Alpaca unchecked.

Run `python gates.py` for the self-checks; nothing here places an order.
"""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# Hard limits. Never regime-scaled, no override. See docs/gates.md.
MAX_LOSS_PER_CONTRACT_USD = 500
DAILY_HALT_PCT = -2.0
COMPETITION_HALT_PCT = -4.0
COMPETITION_START_EQUITY = 100_000.0
NO_NEW_POSITIONS_AFTER = time(15, 30)
CLOSE_OUT_AT = time(15, 45)
LAST_TRADING_DAY = date(2026, 9, 4)  # submission day - close out only
DTE_MIN, DTE_MAX = 1, 3


def refuse(reason: str, detail: str, state: str = "HALTED", **extra) -> dict:
    """A refusal carries no envelope fields - there is nothing to partially obey."""
    return {"allowed": False, "operating_state": state, "reason": reason,
            "detail": detail, **extra}


def spread_max_loss(width: float, credit: float, contracts: int = 1) -> float:
    """Worst case on a vertical credit spread, in dollars."""
    return (width - credit) * 100 * contracts


def legal_expiries(today: date, calendar: list[date] | None = None) -> list[str]:
    """Expiries DTE_MIN..DTE_MAX days out. Calendar-aware when one is supplied."""
    days = calendar or [today + timedelta(days=n) for n in range(DTE_MIN, DTE_MAX + 1)]
    return [d.isoformat() for d in days
            if DTE_MIN <= (d - today).days <= DTE_MAX and d.weekday() < 5]


def build_envelope(regime_block: dict, account: dict, positions: list[dict],
                   now_et: datetime, run_id: str, state: dict | None = None,
                   spot: float | None = None, event_block: dict | None = None) -> dict:
    """The legal envelope, or a refusal. Order matters: see docs/gates.md."""
    state = state or {}

    # 1. Persisted latched halts. Checked first so the AI is never invoked.
    if state.get("competition_halt"):
        return refuse("COMPETITION_HALT", "Down 4% or more overall. Latched - human "
                      "review required before trading resumes.", "REVIEW_REQUIRED")
    if state.get("review_required"):
        return refuse("REVIEW_REQUIRED", state.get("review_reason",
                      "A critical inconsistency is unresolved."), "REVIEW_REQUIRED")
    if state.get("daily_halt") and state.get("daily_halt_date") == now_et.date().isoformat():
        return refuse("DAILY_DRAWDOWN_HALT", "Daily halt latched earlier today. No new "
                      "positions until tomorrow.", latched_until="next_trading_day")

    # 2. Data health. Blind is not a trading condition.
    if regime_block.get("operating_state") == "HALTED" or not regime_block.get("regime"):
        return refuse("NO_REGIME", regime_block.get("reason", "regime unavailable"))
    if account is None or positions is None or spot is None:
        return refuse("NO_ACCOUNT_DATA", "Account, positions or spot unreadable - "
                      "remaining risk cannot be computed.")

    # 3. Duplicate run. A rerun must not double the risk.
    if run_id in set(state.get("runs_with_orders", [])):
        return refuse("DUPLICATE_RUN", "Run %s already submitted an order." % run_id)

    # 4. Drawdown, measured now. ASSUMPTION: the day is measured against
    #    yesterday's close (account.last_equity); confirm before going live.
    equity = float(account["equity"])
    day_start = float(account.get("last_equity") or equity)
    day_pct = (equity / day_start - 1) * 100 if day_start else 0.0
    comp_pct = (equity / COMPETITION_START_EQUITY - 1) * 100
    if comp_pct <= COMPETITION_HALT_PCT:
        return refuse("COMPETITION_HALT", "Down %.2f%% overall, limit %.1f%%. Latched - "
                      "human reset only." % (comp_pct, COMPETITION_HALT_PCT),
                      "REVIEW_REQUIRED")
    if day_pct <= DAILY_HALT_PCT:
        return refuse("DAILY_DRAWDOWN_HALT", "Down %.2f%% today, limit %.1f%%. Latched - "
                      "no new positions until tomorrow." % (day_pct, DAILY_HALT_PCT),
                      latched_until="next_trading_day")

    # 5. Clock and calendar.
    today = now_et.date()
    if today >= LAST_TRADING_DAY:
        return refuse("NO_NEW_POSITIONS", "Submission day - close-out only.",
                      "ACTIVE", must_close_all=True)
    if now_et.time() >= NO_NEW_POSITIONS_AFTER:
        return refuse("NO_NEW_POSITIONS", "After %s ET - too late to react."
                      % NO_NEW_POSITIONS_AFTER.strftime("%H:%M"), "ACTIVE")

    # 5.5 Scheduled-event gate. Separate from the regime - it does not rewrite
    #     it (handoff section 3). An approved catalyst still ahead this session
    #     makes the legal envelope empty: a clean NO_TRADE, not an error.
    if event_block and event_block.get("blocked"):
        name = event_block.get("event_name") or "an approved event"
        et = event_block.get("event_time_et")
        detail = ("Blocked by scheduled-event gate: %s%s still ahead this session."
                  % (name, " at %s ET" % et if et else ""))
        return refuse("NO_TRADE", detail,
                      regime_block.get("operating_state", "ACTIVE"),
                      event_gate=event_block)

    # 6. Regime permissions, after the stand-down has already stripped strategies.
    strategies = list(regime_block.get("allowed_strategies") or [])
    budget = float(regime_block.get("risk_budget_usd") or 0)
    if not strategies or budget <= 0:
        return refuse("NO_TRADE", "No strategy is permitted in %s%s."
                      % (regime_block["regime"],
                         " (stand-down latched)" if regime_block.get("stand_down") else ""),
                      regime_block.get("operating_state", "ACTIVE"))

    # 7. Position count.
    if len(positions) >= regime_block["max_positions"]:
        return refuse("POSITION_CAP", "Holding %d of %d permitted positions."
                      % (len(positions), regime_block["max_positions"]),
                      regime_block.get("operating_state", "ACTIVE"))

    # 8. Remaining risk budget. Pure arithmetic - nothing to talk out of.
    open_risk = sum(float(p.get("max_loss", 0)) for p in positions)
    remaining = budget - open_risk
    if remaining < MAX_LOSS_PER_CONTRACT_USD:
        return refuse("RISK_BUDGET_EXHAUSTED",
                      "$%.0f of $%.0f budget already at risk; no further contract fits."
                      % (open_risk, budget), regime_block.get("operating_state", "ACTIVE"))

    contracts = min(regime_block["max_contracts"],
                    int(remaining // MAX_LOSS_PER_CONTRACT_USD))
    return {
        "allowed": True,
        "run_id": run_id,
        "operating_state": regime_block.get("operating_state", "ACTIVE"),
        "regime": regime_block["regime"],
        "strategies": strategies,
        "expiries": legal_expiries(today),
        "short_strike_min_distance_pct": regime_block["min_strike_distance_pct"],
        "max_contracts": contracts,
        "max_risk_per_contract_usd": MAX_LOSS_PER_CONTRACT_USD,
        "risk_budget_usd": budget,
        "remaining_risk_budget_usd": round(remaining, 2),
        "remaining_daily_loss_budget_usd": round(
            day_start * (1 + DAILY_HALT_PCT / 100) * -1 + equity, 2),
        "open_positions": len(positions),
        "max_positions": regime_block["max_positions"],
        "put_spreads_allowed": regime_block.get("put_spreads_allowed", True),
        "spot_at_build": spot,
        # Carried so the validator can tell whether the account moved materially
        # while the model was thinking. Without it that check cannot fire.
        "equity_at_build": equity,
        "underlying": "SPY",
    }


def validate(proposal: dict, envelope: dict, spot_now: float, account_now: dict,
             state: dict | None = None) -> tuple[bool, str]:
    """Deterministic re-check of the AI's answer against refreshed data.

    Returns (ok, reason). A failure never sends an order and never asks the AI
    to patch the trade in place - that would skip a decision cycle.
    """
    state = state or {}
    if not envelope.get("allowed"):
        return False, "no envelope in force"
    if proposal.get("action") == "NO_TRADE":
        return True, "no trade proposed"

    if state.get("competition_halt") or state.get("review_required") or state.get("daily_halt"):
        return False, "system halted since the envelope was built"
    if envelope["run_id"] in set(state.get("runs_with_orders", [])):
        return False, "duplicate run: %s already submitted an order" % envelope["run_id"]

    if proposal.get("strategy") not in envelope["strategies"]:
        return False, "strategy %s is not permitted" % proposal.get("strategy")
    if "PUT" in str(proposal.get("strategy")) and not envelope.get("put_spreads_allowed", True):
        return False, "put spreads are stood down"
    if proposal.get("expiry") not in envelope["expiries"]:
        return False, "expiry %s is outside the legal window" % proposal.get("expiry")

    contracts = int(proposal.get("contracts", 0))
    if contracts < 1 or contracts > envelope["max_contracts"]:
        return False, "size %d outside 1..%d" % (contracts, envelope["max_contracts"])

    # Distance is re-measured against the REFRESHED spot. This is the check that
    # earns its keep: the market moves while the model is thinking.
    short = float(proposal["short_strike"])
    distance = (spot_now - short) / spot_now * 100
    required = envelope["short_strike_min_distance_pct"]
    if distance < required:
        return False, ("short strike %.0f is %.2f%% from spot %.2f; envelope required %.2f%%"
                       % (short, distance, spot_now, required))

    width = abs(short - float(proposal["long_strike"]))
    per_contract = spread_max_loss(width, float(proposal.get("credit", 0)))
    if per_contract > MAX_LOSS_PER_CONTRACT_USD:
        return False, "max loss $%.0f per contract exceeds $%d" % (
            per_contract, MAX_LOSS_PER_CONTRACT_USD)
    total = per_contract * contracts
    if total > envelope["remaining_risk_budget_usd"]:
        return False, "total risk $%.0f exceeds remaining budget $%.0f" % (
            total, envelope["remaining_risk_budget_usd"])

    # Account materially changed since the envelope was built?
    equity_then = float(envelope.get("equity_at_build") or account_now["equity"])
    equity_now = float(account_now["equity"])
    if equity_then and abs(equity_now / equity_then - 1) > 0.01:
        return False, "account equity moved %.2f%% since the envelope was built" % (
            (equity_now / equity_then - 1) * 100)

    return True, "ok"


def _self_check() -> None:
    now = datetime(2026, 9, 2, 13, 5, tzinfo=ET)
    # V2 sizing. Built from regime.PERMISSIONS so the fixture cannot drift away
    # from the frozen table it is meant to represent.
    from regime import PERMISSIONS

    neutral = {"regime": "NEUTRAL", "operating_state": "ACTIVE", "stand_down": False,
               "put_spreads_allowed": True, **PERMISSIONS["NEUTRAL"]}
    acct = {"equity": "100340", "last_equity": "100000"}
    env = build_envelope(neutral, acct, [], now, "2026-09-02-1305", spot=651.20)
    assert env["allowed"] and env["max_contracts"] == 3, env
    assert env["remaining_risk_budget_usd"] == 1500

    # Oversized single contract is rejected by the per-contract cap.
    assert spread_max_loss(width=6.0, credit=0.20) > MAX_LOSS_PER_CONTRACT_USD

    # Drawdown halts, and the competition halt escalates.
    down = build_envelope(neutral, {"equity": "97700", "last_equity": "100000"}, [], now,
                          "r", spot=651.2)
    assert down["allowed"] is False and down["reason"] == "DAILY_DRAWDOWN_HALT", down
    assert "envelope" not in down and "max_contracts" not in down
    comp = build_envelope(neutral, {"equity": "95500", "last_equity": "96000"}, [], now,
                          "r", spot=651.2)
    assert comp["reason"] == "COMPETITION_HALT" and comp["operating_state"] == "REVIEW_REQUIRED"

    # A latched daily halt stays latched after P&L recovers.
    latched = build_envelope(neutral, {"equity": "98400", "last_equity": "100000"}, [], now,
                             "r", spot=651.2,
                             state={"daily_halt": True, "daily_halt_date": "2026-09-02"})
    assert latched["reason"] == "DAILY_DRAWDOWN_HALT", latched

    # Clock and calendar.
    late = build_envelope(neutral, acct, [], datetime(2026, 9, 2, 15, 45, tzinfo=ET), "r",
                          spot=651.2)
    assert late["reason"] == "NO_NEW_POSITIONS", late
    last = build_envelope(neutral, acct, [], datetime(2026, 9, 4, 10, 0, tzinfo=ET), "r",
                          spot=651.2)
    assert last["reason"] == "NO_NEW_POSITIONS" and last["must_close_all"] is True

    # Budget arithmetic: $1,200 of the $1,500 already at risk leaves no room.
    full = build_envelope(neutral, acct, [{"max_loss": 1200}], now, "r", spot=651.2)
    assert full["reason"] == "RISK_BUDGET_EXHAUSTED", full
    # Partial room caps the contract count rather than refusing.
    partial = build_envelope(neutral, acct, [{"max_loss": 400}], now, "r", spot=651.2)
    assert partial["allowed"] and partial["max_contracts"] == 2, partial

    # V2: RISK_OFF still trades, at reduced size. It is NOT a stand-down.
    off = {"regime": "RISK_OFF", "operating_state": "ACTIVE", "stand_down": False,
           "put_spreads_allowed": True, **PERMISSIONS["RISK_OFF"]}
    off_env = build_envelope(off, acct, [], now, "r", spot=651.2)
    assert off_env["allowed"] and off_env["max_contracts"] == 2, off_env
    assert off_env["risk_budget_usd"] == 1000 and off_env["put_spreads_allowed"] is True

    # Stand-down is the state that produces a clean NO_TRADE, not an error.
    sd = {"regime": "STAND_DOWN", "operating_state": "ACTIVE", "stand_down": True,
          "put_spreads_allowed": False, **PERMISSIONS["STAND_DOWN"]}
    sd_env = build_envelope(sd, acct, [], now, "r", spot=651.2)
    assert sd_env["reason"] == "NO_TRADE" and sd_env["allowed"] is False, sd_env
    assert "stand-down latched" in sd_env["detail"], sd_env

    # Position cap and duplicate run.
    capped = build_envelope(neutral, acct, [{"max_loss": 400}, {"max_loss": 400}], now, "r",
                            spot=651.2)
    assert capped["reason"] == "POSITION_CAP", capped
    dup = build_envelope(neutral, acct, [], now, "R1", state={"runs_with_orders": ["R1"]},
                         spot=651.2)
    assert dup["reason"] == "DUPLICATE_RUN", dup

    # Scheduled-event gate: an approved catalyst still ahead makes the envelope
    # a clean NO_TRADE, regardless of regime, and the block rides along for audit.
    blocked = build_envelope(neutral, acct, [], now, "r", spot=651.2, event_block={
        "blocked": True, "event_name": "FOMC Rate Decision", "event_time_et": "14:00"})
    assert blocked["allowed"] is False and blocked["reason"] == "NO_TRADE", blocked
    assert blocked["event_gate"]["event_name"] == "FOMC Rate Decision", blocked
    assert "scheduled-event gate" in blocked["detail"], blocked
    # A non-blocking event_block leaves the envelope exactly as it was without one.
    clear = {"blocked": False, "event_name": None, "event_time_et": None}
    assert build_envelope(neutral, acct, [], now, "r", spot=651.2, event_block=clear) \
        == build_envelope(neutral, acct, [], now, "r", spot=651.2)

    # A halted regime produces no envelope at all.
    halted = build_envelope({"operating_state": "HALTED", "regime": None,
                             "reason": "critical price data unavailable (SPY)"},
                            acct, [], now, "r", spot=651.2)
    assert halted["allowed"] is False and halted["reason"] == "NO_REGIME"

    # --- validator ---
    good = {"action": "PLACE", "strategy": "PUT_CREDIT_SPREAD", "expiry": env["expiries"][0],
            "short_strike": 640, "long_strike": 635, "credit": 0.62, "contracts": 1}
    ok, why = validate(good, env, 651.20, acct)
    assert ok, why

    # The market moved: a strike that was legal at build time no longer is.
    ok, why = validate(dict(good, short_strike=641), env, 648.10, acct)
    assert not ok and "required" in why, why

    for bad, expect in (
        (dict(good, strategy="IRON_CONDOR"), "not permitted"),
        (dict(good, contracts=9), "outside 1..3"),
        (dict(good, expiry="2026-12-18"), "outside the legal window"),
        (dict(good, long_strike=629), "per contract"),
    ):
        ok, why = validate(bad, env, 651.20, acct)
        assert not ok and expect in why, (expect, why)

    # Panel-shaped output remains fenced by the unchanged validator.
    panel_bad = dict(good, short_strike=641, decided_by="panel", candidate_index=0)
    ok, why = validate(panel_bad, env, 648.10, acct)
    assert not ok and "required" in why, why

    # Halted since the envelope was built, and duplicate submission.
    ok, _ = validate(good, env, 651.20, acct, state={"review_required": True})
    assert not ok
    ok, _ = validate(good, env, 651.20, acct,
                     state={"runs_with_orders": ["2026-09-02-1305"]})
    assert not ok

    # NO_TRADE is valid, never an error.
    ok, _ = validate({"action": "NO_TRADE"}, env, 651.20, acct)
    assert ok

    # The account moved materially between envelope and order.
    ok, why = validate(good, env, 651.20, {"equity": "98000", "last_equity": "100000"})
    assert not ok and "equity moved" in why, why

    # Stand-down is enforced by the validator too, not only by the empty
    # strategy list - the field must survive into the envelope for that to work.
    sd_env = dict(env, put_spreads_allowed=False)
    ok, why = validate(good, sd_env, 651.20, acct)
    assert not ok and "stood down" in why, why


if __name__ == "__main__":
    _self_check()
    from regime import PERMISSIONS
    print(json.dumps(build_envelope(
        {"regime": "NEUTRAL", "operating_state": "ACTIVE", "stand_down": False,
         "put_spreads_allowed": True, **PERMISSIONS["NEUTRAL"]},
        {"equity": "100340", "last_equity": "100000"}, [],
        datetime.now(ET), datetime.now(ET).strftime("%Y-%m-%d-%H%M"), spot=651.20),
        indent=2))
