"""audit.py - the check on the AI, and the only thing that publishes.

Spec: docs/audit.md. Three jobs:

  1. Mark the AI's homework. Re-read what actually filled and compare it with
     the envelope that was in force. A violation does not merely get displayed:
     it latches a halt and escalates to REVIEW_REQUIRED.
  2. Decide what, if anything, was learned. Not every loss is a mistake, and a
     system that treats each losing trade as one will thrash itself into a
     worse strategy inside a week.
  3. Write site/state.json. Nothing else publishes, so an unaudited result is
     never shown as though it were verified.

Run `python audit.py` for the self-checks.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import gates

STATE_PATH = os.environ.get("STATE_PATH", "site/state.json")
COMPETITION = {"start": "2026-08-28", "end": "2026-09-04"}

# Outcome taxonomy (docs/audit.md). Only the middle group teaches anything.
NO_LESSON = ("NO_ERROR", "MARKET_MOVE")
TEACHES = ("SELECTION_ERROR", "LIQUIDITY_ERROR", "EXECUTION_ERROR", "DATA_ERROR")
ESCALATES = ("RISK_VIOLATION",)
MAX_LESSONS = 5
MAX_OUTCOMES = 10


def check_fills(envelope: dict, proposal: dict, positions: list[dict],
                spot_at_fill: float) -> tuple[str, list[dict]]:
    """Compare what actually filled against the envelope in force.

    Distance is measured against the spot AT FILL, not the spot now. Judging a
    decision by information that arrived after it manufactures fake violations.
    """
    violations = []
    if not positions:
        return "AUDIT_PASS", violations

    for pos in positions:
        legs = pos.get("legs") or []
        if len(legs) == 1:
            violations.append({
                "rule": "complete_spread",
                "required": 2, "actual": 1,
                "detail": "Only one leg of an intended spread is present. Exposure is "
                          "not defined-risk until this is understood.",
                "critical": True,
            })
            continue

        strategy = pos.get("strategy")
        if strategy and strategy not in envelope.get("strategies", []):
            violations.append({"rule": "allowed_strategies",
                               "required": envelope.get("strategies"), "actual": strategy,
                               "detail": "Filled strategy was not permitted."})

        short = pos.get("short_strike")
        if short is not None and spot_at_fill:
            distance = (spot_at_fill - short) / spot_at_fill * 100
            required = envelope["short_strike_min_distance_pct"]
            if distance < required - 1e-9:
                violations.append({
                    "rule": "short_strike_min_distance_pct",
                    "required": required, "actual": round(distance, 2),
                    "detail": "Short strike %s is %.2f%% below spot %.2f at fill. "
                              "Envelope required at least %.2f%%."
                              % (short, distance, spot_at_fill, required),
                })

        if pos.get("expiry") and pos["expiry"] not in envelope.get("expiries", []):
            violations.append({"rule": "expiries", "required": envelope.get("expiries"),
                               "actual": pos["expiry"],
                               "detail": "Filled expiry was outside the legal window."})

        contracts = int(pos.get("contracts", 0))
        if contracts > envelope["max_contracts"]:
            violations.append({"rule": "max_contracts",
                               "required": envelope["max_contracts"], "actual": contracts,
                               "detail": "Filled size exceeded the contract cap."})

        per_contract = float(pos.get("max_loss", 0)) / max(contracts, 1)
        if per_contract > envelope["max_risk_per_contract_usd"] + 1e-9:
            violations.append({"rule": "max_risk_per_contract_usd",
                               "required": envelope["max_risk_per_contract_usd"],
                               "actual": round(per_contract, 2),
                               "detail": "Worst case per contract exceeded the cap."})

    total_risk = sum(float(p.get("max_loss", 0)) for p in positions)
    if total_risk > envelope["risk_budget_usd"] + 1e-9:
        violations.append({"rule": "risk_budget_usd",
                           "required": envelope["risk_budget_usd"],
                           "actual": round(total_risk, 2),
                           "detail": "Total open risk exceeded the regime budget."})
    if len(positions) > envelope["max_positions"]:
        violations.append({"rule": "max_positions", "required": envelope["max_positions"],
                           "actual": len(positions),
                           "detail": "More positions open than permitted."})

    return ("AUDIT_FAIL" if violations else "AUDIT_PASS"), violations


def classify(record: dict, audit_result: str, violations: list[dict],
             pnl_delta: float | None = None) -> str:
    """One outcome class per run. See the taxonomy in docs/audit.md.

    The default is NO_ERROR, deliberately. A losing but compliant trade is
    MARKET_MOVE, not a mistake - the distinction is what lets this system have
    a learning loop without becoming self-modifying.
    """
    if violations:
        return "RISK_VIOLATION"
    if record.get("regime", {}).get("operating_state") == "HALTED":
        return "DATA_ERROR"
    if record.get("order") == "REJECTED":
        return "EXECUTION_ERROR"
    if record.get("validation") not in (None, "PASS", "ok", "no trade proposed"):
        # The model proposed something the validator refused. That is the
        # control working, but it is also a poorer selection than was available.
        return "SELECTION_ERROR"
    if pnl_delta is not None and pnl_delta < 0:
        return "MARKET_MOVE"
    return "NO_ERROR"


def update_lessons(lessons: list[dict], outcome: str, note: str,
                   now: str | None = None) -> list[dict]:
    """Bounded learning memory. Preferences only - never permissions.

    A lesson can reorder legal candidates. It can never change what is legal,
    which is why nothing here is allowed to touch an envelope field.
    """
    if outcome not in TEACHES:
        return lessons  # NO_ERROR, MARKET_MOVE and escalations teach nothing
    now = now or datetime.now(timezone.utc).isoformat()
    kind = {"SELECTION_ERROR": "selection", "LIQUIDITY_ERROR": "liquidity",
            "EXECUTION_ERROR": "execution", "DATA_ERROR": "data"}[outcome]

    for lesson in lessons:
        if lesson["type"] == kind:
            lesson["evidence_count"] += 1
            lesson["last_observed"] = now
            lesson["confidence"] = ("HIGH" if lesson["evidence_count"] >= 4
                                    else "MEDIUM" if lesson["evidence_count"] >= 2
                                    else "LOW")
            return lessons

    lessons = lessons + [{"type": kind, "lesson": note, "evidence_count": 1,
                          "confidence": "LOW", "last_observed": now}]
    if len(lessons) > MAX_LESSONS:
        # Displace the weakest rather than growing the list. The cap is
        # enforced, not advisory.
        lessons.sort(key=lambda l: (l["evidence_count"], l["last_observed"]))
        lessons = lessons[1:]
    return lessons


def build_state(record: dict, account: dict, positions: list[dict],
                previous: dict | None = None, spot_at_fill: float | None = None,
                now: datetime | None = None) -> dict:
    """Assemble site/state.json. The only thing in the project that publishes."""
    previous = previous or {}
    now = now or datetime.now(timezone.utc)
    envelope = record.get("envelope", {})
    proposal = record.get("proposal", {})
    reg = record.get("regime", {})

    if envelope.get("allowed"):
        audit_result, violations = check_fills(envelope, proposal, positions,
                                               spot_at_fill or envelope.get("spot_at_build"))
    else:
        audit_result, violations = "AUDIT_PASS", []   # nothing traded, nothing to check

    equity = float(account.get("equity", gates.COMPETITION_START_EQUITY))
    day_start = float(account.get("last_equity") or equity)
    day_pnl = equity - day_start
    total_pnl = equity - gates.COMPETITION_START_EQUITY
    unrealised = sum(float(p.get("unrealised_pnl", 0)) for p in positions)

    outcome = classify(record, audit_result, violations, day_pnl)
    critical = any(v.get("critical") for v in violations)

    prev_status = previous.get("status", {})
    state = prev_status.get("operating_state", "ACTIVE")
    reason = reg.get("reason", "")
    if violations or critical:
        state = "REVIEW_REQUIRED"
        reason = ("Envelope violation - autonomous trading halted, human review "
                  "required.") if not critical else \
                 "Incomplete spread or unknown exposure - human review required."
    elif prev_status.get("review_required"):
        state = "REVIEW_REQUIRED"
        reason = prev_status.get("state_reason", "Unresolved exception.")
    elif not envelope.get("allowed") and envelope.get("operating_state") == "HALTED":
        state = "HALTED"
        reason = envelope.get("detail", reason)
    else:
        state = reg.get("operating_state", "ACTIVE")

    daily_halt = (prev_status.get("daily_halt")
                  and prev_status.get("daily_halt_date") == now.date().isoformat()) or \
        (day_start and (equity / day_start - 1) * 100 <= gates.DAILY_HALT_PCT)
    competition_halt = bool(prev_status.get("competition_halt")) or \
        (equity / gates.COMPETITION_START_EQUITY - 1) * 100 <= gates.COMPETITION_HALT_PCT

    lessons = update_lessons(
        list(previous.get("learning", {}).get("active_lessons", [])), outcome,
        _lesson_text(outcome, record), now.isoformat())
    outcomes = ([outcome] + list(previous.get("learning", {}).get(
        "recent_outcomes", [])))[:MAX_OUTCOMES]

    runs_with_orders = list(prev_status.get("runs_with_orders", []))
    if record.get("order") and record["order"] not in ("DRY_RUN", "REJECTED"):
        if record["run_id"] not in runs_with_orders:
            runs_with_orders.append(record["run_id"])

    run_entry = {
        "run_id": record.get("run_id"),
        "timestamp": now.isoformat(),
        "operating_state": state,
        "regime": reg.get("regime"),
        "envelope_allowed": bool(envelope.get("allowed")),
        "validation": record.get("validation", "n/a"),
        "agent_action": proposal.get("action", "NONE"),
        "decided_by": proposal.get("decided_by", "n/a"),
        "audit_result": audit_result,
        "violations": violations,
        "outcome_class": outcome,
        "reasoning": proposal.get("reasoning", ""),
        "candidates_considered": proposal.get("candidates_considered", []),
        "panel": proposal.get("panel"),
    }

    return {
        "updated_at": now.isoformat(),
        "competition": dict(COMPETITION, account_id=account.get("account_number"),
                            rules_version=reg.get("rules_version")),
        "status": {
            "operating_state": state,
            "state_reason": reason,
            "daily_halt": bool(daily_halt),
            "daily_halt_date": now.date().isoformat() if daily_halt else None,
            "competition_halt": bool(competition_halt),
            "review_required": state == "REVIEW_REQUIRED",
            "regime": reg.get("regime"),
            "regime_measured": reg.get("regime_measured"),
            "regime_reason": reg.get("reason"),
            "put_spreads_allowed": reg.get("put_spreads_allowed"),
            "stand_down": reg.get("stand_down"),
            "signals": reg.get("signals", {}),
            "runs_with_orders": runs_with_orders,
        },
        "envelope": envelope,
        "pnl": {
            "account_value": equity,
            "starting_value": gates.COMPETITION_START_EQUITY,
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": round(total_pnl / gates.COMPETITION_START_EQUITY * 100, 3),
            "day_pnl": round(day_pnl, 2),
            "realised": round(total_pnl - unrealised, 2),
            "unrealised": round(unrealised, 2),
        },
        "risk": {
            "open_positions": len(positions),
            "max_positions": envelope.get("max_positions"),
            "risk_used_usd": round(sum(float(p.get("max_loss", 0)) for p in positions), 2),
            "risk_budget_usd": envelope.get("risk_budget_usd"),
        },
        "positions": positions,
        "learning": {"active_lessons": lessons, "recent_outcomes": outcomes,
                     "seat_calibration": previous.get("learning", {}).get("seat_calibration", {})},
        "human_actions": previous.get("human_actions", []),
        "runs": ([run_entry] + list(previous.get("runs", [])))[:100],
    }


def _lesson_text(outcome: str, record: dict) -> str:
    regime = record.get("regime", {}).get("regime", "this regime")
    return {
        "SELECTION_ERROR": "A proposal was rejected by the validator in %s; prefer "
                           "candidates with margin against the distance floor." % regime,
        "LIQUIDITY_ERROR": "Wide markets gave back the premium; prefer tighter bid/ask.",
        "EXECUTION_ERROR": "An order was rejected; prefer simpler, more liquid legs.",
        "DATA_ERROR": "Inputs were stale or missing; the run halted rather than guessed.",
    }.get(outcome, "")


def publish(state: dict, path: str | None = None) -> str:
    path = path or STATE_PATH
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if os.path.exists(path):
        try:
            json.load(open(path))
        except json.JSONDecodeError:
            # Never overwrite a file we cannot read - losing the history
            # mid-competition would be unrecoverable.
            path = path + ".new"
    with open(path, "w") as fh:
        json.dump(state, fh, indent=2, default=str)
    return path


def _self_check() -> None:
    env = {"allowed": True, "strategies": ["PUT_CREDIT_SPREAD"],
           "expiries": ["2026-09-04"], "short_strike_min_distance_pct": 1.5,
           "max_contracts": 5, "max_risk_per_contract_usd": 500,
           "risk_budget_usd": 5000, "max_positions": 2, "spot_at_build": 651.20,
           "operating_state": "ACTIVE"}
    good = [{"strategy": "PUT_CREDIT_SPREAD", "short_strike": 640, "long_strike": 635,
             "expiry": "2026-09-04", "contracts": 1, "max_loss": 438,
             "legs": [1, 2], "unrealised_pnl": 62.5}]
    result, viol = check_fills(env, {}, good, 651.20)
    assert result == "AUDIT_PASS" and viol == [], viol

    # A strike 1.31% out against a 1.5% floor is one violation, with both numbers.
    bad = [dict(good[0], short_strike=642)]
    result, viol = check_fills(env, {}, bad, 650.5)
    assert result == "AUDIT_FAIL" and len(viol) == 1
    assert viol[0]["required"] == 1.5 and abs(viol[0]["actual"] - 1.31) < 0.01, viol

    # Oversized position names the size rule; multiple breaches produce multiple
    # violations rather than stopping at the first.
    many = [dict(good[0], contracts=9, max_loss=5400, short_strike=642)]
    result, viol = check_fills(env, {}, many, 650.5)
    rules = {v["rule"] for v in viol}
    assert {"max_contracts", "risk_budget_usd", "short_strike_min_distance_pct"} <= rules, rules

    # A single-leg fill is critical: unknown exposure, not a measurement.
    _, viol = check_fills(env, {}, [{"legs": [1], "max_loss": 0}], 651.2)
    assert viol[0]["critical"] is True and viol[0]["rule"] == "complete_spread"

    # A compliant but losing trade is MARKET_MOVE, and teaches nothing.
    rec = {"regime": {"regime": "NEUTRAL", "operating_state": "ACTIVE"},
           "envelope": env, "proposal": {"action": "PLACE"}, "validation": "PASS"}
    assert classify(rec, "AUDIT_PASS", [], pnl_delta=-120) == "MARKET_MOVE"
    assert update_lessons([], "MARKET_MOVE", "x") == []
    assert classify(rec, "AUDIT_PASS", [], pnl_delta=40) == "NO_ERROR"
    assert classify(rec, "AUDIT_FAIL", [{"rule": "r"}]) == "RISK_VIOLATION"

    # Repeated evidence raises confidence; a sixth lesson displaces the weakest.
    lessons = []
    for _ in range(3):
        lessons = update_lessons(lessons, "LIQUIDITY_ERROR", "tighter markets", "t")
    assert len(lessons) == 1 and lessons[0]["evidence_count"] == 3
    assert lessons[0]["confidence"] == "MEDIUM"
    packed = [{"type": "t%d" % i, "lesson": "l", "evidence_count": 9,
               "confidence": "HIGH", "last_observed": "t"} for i in range(MAX_LESSONS)]
    grown = update_lessons(packed, "DATA_ERROR", "note", "t")
    assert len(grown) == MAX_LESSONS, len(grown)

    # A violation latches REVIEW_REQUIRED into the published state.
    acct = {"equity": "100402.50", "last_equity": "100340", "account_number": "PA3"}
    state = build_state({"run_id": "r1", "regime": rec["regime"], "envelope": env,
                         "proposal": {"action": "PLACE"}, "validation": "PASS",
                         "order": {"id": "o1"}}, acct, bad, spot_at_fill=650.5)
    assert state["status"]["operating_state"] == "REVIEW_REQUIRED"
    assert state["runs"][0]["audit_result"] == "AUDIT_FAIL"
    assert state["runs"][0]["outcome_class"] == "RISK_VIOLATION"
    assert "r1" in state["status"]["runs_with_orders"]

    # REVIEW_REQUIRED stays latched on the next run even when it is clean.
    nxt = build_state({"run_id": "r2", "regime": rec["regime"], "envelope": env,
                       "proposal": {"action": "NO_TRADE"}, "validation": "PASS"},
                      acct, good, previous=state, spot_at_fill=651.2)
    assert nxt["status"]["operating_state"] == "REVIEW_REQUIRED", nxt["status"]
    assert len(nxt["runs"]) == 2  # history accumulates, newest first

    # A halted run still publishes a complete entry.
    halted = build_state({"run_id": "r3", "regime": {"operating_state": "HALTED",
                                                     "reason": "no SPY"},
                          "envelope": {"allowed": False, "operating_state": "HALTED",
                                       "reason": "NO_REGIME", "detail": "no SPY"},
                          "proposal": {"action": "NO_TRADE"}}, acct, [])
    assert halted["status"]["operating_state"] == "HALTED"
    assert halted["runs"][0]["agent_action"] == "NO_TRADE"
    assert halted["pnl"]["total_pnl"] == 402.5

    # P&L splits, and the drawdown halts latch off real numbers.
    down = build_state({"run_id": "r4", "regime": rec["regime"], "envelope": env,
                        "proposal": {"action": "NO_TRADE"}},
                       {"equity": "97900", "last_equity": "100000"}, [])
    assert down["status"]["daily_halt"] is True
    comp = build_state({"run_id": "r5", "regime": rec["regime"], "envelope": env,
                        "proposal": {"action": "NO_TRADE"}},
                       {"equity": "95000", "last_equity": "95500"}, [])
    assert comp["status"]["competition_halt"] is True

    # No lesson may touch an envelope field.
    for lesson in nxt["learning"]["active_lessons"]:
        assert not set(lesson) & set(env), lesson


if __name__ == "__main__":
    _self_check()
    print("audit self-checks passed")
