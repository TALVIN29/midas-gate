"""regime.py - today's risk regime, from the gold/macro read.

Spec: docs/regime.md. Gold Regime Rules V1, pending teammate sign-off (Aug 27).
Emits the machine-readable permission block that gates.py turns into limits.

Run `python regime.py` for the self-checks; nothing here touches the account.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

RULES_VERSION = "V1-pending-signoff"

# Which inputs we cannot proceed without. TLT is display-only (spec rule 6).
CRITICAL = ("SPY", "GLD")
SECONDARY = ("GDX", "UUP")
SYMBOLS = CRITICAL + SECONDARY + ("TLT",)

# regime -> permissions. Ordered most permissive first; index is the caution level.
LADDER = ("RISK_ON", "NEUTRAL", "RISK_OFF")
PERMISSIONS = {
    "RISK_ON": {
        "risk_budget_usd": 10000,
        "max_contracts": 7,
        "min_strike_distance_pct": 1.0,
        "max_positions": 3,
        "allowed_strategies": ["PUT_CREDIT_SPREAD", "IRON_CONDOR"],
    },
    "NEUTRAL": {
        "risk_budget_usd": 5000,
        "max_contracts": 5,
        "min_strike_distance_pct": 1.5,
        "max_positions": 2,
        "allowed_strategies": ["PUT_CREDIT_SPREAD"],
    },
    "RISK_OFF": {
        "risk_budget_usd": 0,
        "max_contracts": 0,
        "min_strike_distance_pct": 2.5,
        "max_positions": 1,
        "allowed_strategies": [],
    },
}


def _more_cautious(regime: str, levels: int = 1) -> str:
    """One (or more) notches toward RISK_OFF. Never past it."""
    return LADDER[min(LADDER.index(regime) + levels, len(LADDER) - 1)]


def classify(signals: dict, prior: dict | None = None) -> dict:
    """Gold Regime Rules V1. Pure: no network, no clock, no account.

    `signals` maps symbol -> percentage change vs the previous regular-session
    close, or None when that price could not be read. `prior` is the persisted
    state from earlier the same trading day, for the stand-down latch and the
    asymmetric intraday caution rule.
    """
    prior = prior or {}
    missing = [s for s in SYMBOLS if signals.get(s) is None]

    # Data health first - never guess, never default to the permissive regime.
    if any(s in missing for s in CRITICAL):
        return _block(
            "HALTED",
            "critical price data unavailable (%s) - halted, no envelope built"
            % ", ".join(s for s in CRITICAL if s in missing),
            signals,
        )

    degraded = [s for s in SECONDARY if s in missing]
    gld, spy = signals["GLD"], signals["SPY"]
    gdx, uup = signals.get("GDX"), signals.get("UUP")
    notes = []

    # Rule 1 - stand-down. Latched for the rest of the trading day.
    latched = bool(prior.get("stand_down"))
    stand_down = latched or (gld >= 1.00 and spy <= -1.00)
    if stand_down:
        notes.append(
            "stand-down latched earlier today" if latched and not (gld >= 1.00 and spy <= -1.00)
            else "stand-down: GLD %+.2f%% with SPY %+.2f%%" % (gld, spy)
        )

    # Rules 2-5, most cautious first.
    if gld >= 0.75 and spy <= -0.50:
        regime = "RISK_OFF"
        notes.append("fear rising: gold bid while stocks fell")
    else:
        regime = "RISK_ON"
        # Rule 3 - divergence. Gold up, miners not confirming.
        if gdx is not None and gld > 0 and gdx <= 0 and (gld - gdx) >= 0.75:
            regime = _more_cautious(regime)
            notes.append("divergence: GLD-GDX %.2f pp, miners not confirming" % (gld - gdx))
        # Rule 4 - dollar modifier. Only ever increases caution.
        if uup is not None and uup >= 0.30 and gld >= 0.50:
            regime = _more_cautious(regime)
            notes.append("dollar firm with gold bid - caution upgraded one level")
        # V1's other half - "weak dollar means gold alone cannot trigger RISK_OFF" -
        # is already guaranteed by rule 2, which requires SPY <= -0.50% to confirm.
        # Gold never triggers RISK_OFF alone under V1, so there is nothing to undo.
        # Left unimplemented deliberately rather than as a branch that cannot fire;
        # flagged to the teammate in case he meant it to relax rule 2.

    if degraded:
        regime = _more_cautious(regime)
        notes.append("secondary input(s) missing (%s) - one level more cautious"
                     % ", ".join(degraded))

    # Asymmetric caution: tighten now, loosen only next trading day (spec).
    held = prior.get("regime")
    measured = regime
    if held and LADDER.index(held) > LADDER.index(regime):
        regime = held
        notes.append("measured %s; permissions held at %s from earlier today" % (measured, held))

    out = {
        "regime": regime,
        "regime_measured": measured,
        "operating_state": "DEGRADED" if degraded else "ACTIVE",
        "put_spreads_allowed": not stand_down,
        "stand_down": stand_down,
        "rules_version": RULES_VERSION,
        "signals": {s: signals.get(s) for s in SYMBOLS},
        "reason": ". ".join(notes) if notes else "Nothing decisive in gold, stocks or the dollar.",
    }
    out.update(PERMISSIONS[regime])
    if stand_down:
        # Stand-down removes put spreads specifically; with nothing else legal
        # in V1 the envelope is empty and gates.py emits a clean NO_TRADE.
        out["allowed_strategies"] = [s for s in out["allowed_strategies"] if "PUT" not in s]
        out["risk_budget_usd"] = 0
    return out


def _block(state: str, reason: str, signals: dict) -> dict:
    """No regime at all - the run stops before an envelope is built."""
    return {
        "regime": None,
        "regime_measured": None,
        "operating_state": state,
        "put_spreads_allowed": False,
        "stand_down": False,
        "rules_version": RULES_VERSION,
        "signals": {s: signals.get(s) for s in SYMBOLS},
        "reason": reason,
        **PERMISSIONS["RISK_OFF"],
    }


def fetch_signals() -> dict:
    """Latest price vs previous regular-session close, per docs/regime.md.

    Deliberately not a completed daily candle: at 09:35 ET the session is five
    minutes old. A symbol we cannot read comes back as None, and classify()
    decides whether that is fatal.
    """
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest, StockLatestTradeRequest
    from alpaca.data.timeframe import TimeFrame

    client = StockHistoricalDataClient(
        os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"]
    )
    symbols = list(SYMBOLS)
    signals = {}
    try:
        bars = client.get_stock_bars(
            StockBarsRequest(
                symbol_or_symbols=symbols,
                timeframe=TimeFrame.Day,
                start=datetime.now(timezone.utc) - timedelta(days=10),
            )
        )
        trades = client.get_stock_latest_trade(StockLatestTradeRequest(symbol_or_symbols=symbols))
    except Exception as exc:  # noqa: BLE001 - any failure means we cannot see
        print("regime: price fetch failed: %s" % exc)
        return {s: None for s in symbols}

    today = datetime.now(timezone.utc).date()
    for sym in symbols:
        try:
            # Previous regular session = last daily bar that is not today's.
            closes = [b for b in bars[sym] if b.timestamp.date() < today]
            prev_close = closes[-1].close
            latest = trades[sym].price
            signals[sym] = round((latest / prev_close - 1) * 100, 4)
        except Exception:  # noqa: BLE001 - one absent symbol is not fatal here
            signals[sym] = None
    return signals


def _self_check() -> None:
    calm = {"SPY": 0.10, "GLD": 0.05, "GDX": 0.20, "UUP": 0.02, "TLT": 0.01}
    r = classify(calm)
    assert r["regime"] == "RISK_ON", r
    assert r["risk_budget_usd"] == 10000 and r["min_strike_distance_pct"] == 1.0
    assert r["put_spreads_allowed"] is True

    fear = classify({"SPY": -0.70, "GLD": 0.90, "GDX": 0.60, "UUP": 0.10, "TLT": 0.20})
    assert fear["regime"] == "RISK_OFF", fear
    assert fear["risk_budget_usd"] == 0 and fear["allowed_strategies"] == []

    # Stand-down: blocks put spreads, and stays blocked when re-run on calm data.
    sd = classify({"SPY": -1.40, "GLD": 1.20, "GDX": 0.90, "UUP": 0.10, "TLT": 0.30})
    assert sd["put_spreads_allowed"] is False and sd["stand_down"] is True, sd
    later = classify(calm, prior={"stand_down": True, "regime": sd["regime"]})
    assert later["put_spreads_allowed"] is False, "stand-down must latch for the day"

    # Critical input missing -> HALTED, never a regime.
    halted = classify({"SPY": None, "GLD": 0.4, "GDX": 0.1, "UUP": 0.0, "TLT": 0.0})
    assert halted["operating_state"] == "HALTED" and halted["regime"] is None, halted

    # Secondary input missing -> DEGRADED, still produces a regime, more cautious.
    deg = classify({"SPY": 0.10, "GLD": 0.05, "GDX": None, "UUP": 0.02, "TLT": 0.01})
    assert deg["operating_state"] == "DEGRADED" and deg["regime"] == "NEUTRAL", deg

    # Dollar modifier only ever tightens.
    dollar = classify({"SPY": 0.10, "GLD": 0.60, "GDX": 0.50, "UUP": 0.40, "TLT": 0.0})
    assert dollar["regime"] == "NEUTRAL", dollar
    weak = classify({"SPY": 0.10, "GLD": 0.60, "GDX": 0.50, "UUP": -0.40, "TLT": 0.0})
    assert weak["regime"] == "RISK_ON", weak

    # Divergence downgrades one level.
    div = classify({"SPY": 0.10, "GLD": 0.80, "GDX": -0.10, "UUP": 0.0, "TLT": 0.0})
    assert div["regime"] == "NEUTRAL", div

    # Asymmetric caution: a calmer afternoon does not loosen the morning.
    afternoon = classify(calm, prior={"regime": "RISK_OFF"})
    assert afternoon["regime"] == "RISK_OFF" and afternoon["regime_measured"] == "RISK_ON"

    # Every regime returns a complete, in-band permission block.
    for case in (calm, fear, {"SPY": -0.70, "GLD": 0.90, "GDX": None, "UUP": None, "TLT": None}):
        block = classify(case)
        for field in ("risk_budget_usd", "max_contracts", "min_strike_distance_pct",
                      "max_positions", "allowed_strategies", "put_spreads_allowed", "reason"):
            assert field in block, (field, block)
        assert 0 <= block["risk_budget_usd"] <= 10000
        assert 1.0 <= block["min_strike_distance_pct"] <= 2.5


if __name__ == "__main__":
    _self_check()
    if os.environ.get("ALPACA_API_KEY"):
        print(json.dumps(classify(fetch_signals()), indent=2))
