"""regime.py - today's risk regime, from the gold/macro read.

Spec: docs/regime.md. Gold Rules V2, frozen for validation (see
MIDAS_GATE_GOLD_RULES_V2_VALIDATION_HANDOFF.md). Thresholds here are frozen:
they are validated by backtest.py, not tuned to improve it.

Emits the machine-readable permission block that gates.py turns into limits.

Run `python regime.py` for the self-checks; nothing here touches the account.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

RULES_VERSION = "V2-validation"

# Which inputs we cannot proceed without. TLT is display-only (spec rule 6).
CRITICAL = ("SPY", "GLD")
SECONDARY = ("GDX", "UUP")
SYMBOLS = CRITICAL + SECONDARY + ("TLT",)

# Ordered most permissive first; index is the caution level.
LADDER = ("RISK_ON", "NEUTRAL", "RISK_OFF", "STAND_DOWN")

# STAND_DOWN is a legal state, not a caution notch. Only the stand-down rule
# (or its latch) can reach it - never the divergence/dollar modifiers, and never
# a missing secondary input. A data gap is not a market signal. So modifier-driven
# escalation clamps here, while the full LADDER is still used for the intraday
# one-way comparison, which then orders the stand-down latch for free.
MAX_MODIFIER_LEVEL = LADDER.index("RISK_OFF")

# regime -> permissions. max_contracts is risk_budget_usd // $500, the hard
# per-spread cap in gates.MAX_LOSS_PER_CONTRACT_USD; kept explicit because
# gates.py reads the key.
PERMISSIONS = {
    "RISK_ON": {
        "risk_budget_usd": 2500,
        "max_contracts": 5,
        "min_strike_distance_pct": 1.0,
        "max_positions": 3,
        "allowed_strategies": ["PUT_CREDIT_SPREAD", "IRON_CONDOR"],
    },
    "NEUTRAL": {
        "risk_budget_usd": 1500,
        "max_contracts": 3,
        "min_strike_distance_pct": 1.5,
        "max_positions": 2,
        "allowed_strategies": ["PUT_CREDIT_SPREAD"],
    },
    # Reduced size, still trading. Deliberately NOT equivalent to stand-down.
    "RISK_OFF": {
        "risk_budget_usd": 1000,
        "max_contracts": 2,
        "min_strike_distance_pct": 2.5,
        "max_positions": 1,
        "allowed_strategies": ["PUT_CREDIT_SPREAD"],
    },
    "STAND_DOWN": {
        "risk_budget_usd": 0,
        "max_contracts": 0,
        "min_strike_distance_pct": 2.5,
        "max_positions": 0,
        "allowed_strategies": [],
    },
}


def _more_cautious(regime: str, levels: int = 1) -> str:
    """One (or more) notches toward RISK_OFF. Never into STAND_DOWN, and never
    backwards: a modifier that cannot tighten further must leave the regime
    alone rather than loosening it out of a state it did not set."""
    here = LADDER.index(regime)
    return LADDER[max(here, min(here + levels, MAX_MODIFIER_LEVEL))]


def classify(signals: dict, prior: dict | None = None) -> dict:
    """Gold Rules V2. Pure: no network, no clock, no account.

    `signals` maps symbol -> percentage change vs the previous regular-session
    close, or None when that price could not be read. `prior` is the persisted
    state from earlier the same trading day, for the stand-down latch and the
    asymmetric intraday caution rule.

    Rules are evaluated most-cautious-first; if two overlap the more cautious
    result wins.
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

    # Rule 1 - stand-down. Measured from today's prices only; the latch is
    # applied further down so that `regime_measured` still records what the
    # market actually looked like at this instant.
    latched = bool(prior.get("stand_down"))
    triggered = gld >= 1.00 and spy <= -1.00
    if triggered:
        regime = "STAND_DOWN"
        notes.append("stand-down: GLD %+.2f%% with SPY %+.2f%%" % (gld, spy))
    # Rule 2 - fear rising. Reduced size, not a stand-down.
    elif gld >= 0.75 and spy <= -0.50:
        regime = "RISK_OFF"
        notes.append("fear rising: gold bid while stocks fell")
    else:
        regime = "RISK_ON"
        # Rule 3 - divergence. Gold up, miners not confirming.
        if gdx is not None and gld >= 0.25 and gdx <= 0 and (gld - gdx) >= 0.75:
            regime = _more_cautious(regime)
            notes.append("divergence: GLD-GDX %.2f pp, miners not confirming" % (gld - gdx))
        # Rule 4 - strong dollar. Only ever increases caution, and only while
        # stocks are not clearly positive.
        if uup is not None and uup >= 0.30 and gld >= 0.50 and spy <= 0:
            regime = _more_cautious(regime)
            notes.append("dollar firm with gold bid and stocks soft - caution upgraded")

    # Rule 5 - weak dollar. Explanatory context only. Never cancels a warning
    # and never changes the regime, so it is recorded in every state.
    if uup is not None and uup <= -0.30:
        notes.append("context: dollar weak (UUP %+.2f%%) - no permission change" % uup)

    if degraded:
        regime = _more_cautious(regime)
        notes.append("secondary input(s) missing (%s) - one level more cautious"
                     % ", ".join(degraded))

    # Everything above is this instant's honest read. Record it before any
    # earlier-today state is allowed to override it - the dashboard shows the
    # calmer measurement even when permissions do not follow it.
    measured = regime

    # Rule 1's latch. A stand-down holds for the rest of the trading day; the
    # 13:05 run cannot release it, however calm the afternoon measures.
    stand_down = latched or triggered
    if stand_down and regime != "STAND_DOWN":
        regime = "STAND_DOWN"
        notes.append("stand-down latched earlier today; measured %s" % measured)

    # Asymmetric caution: tighten now, loosen only next trading day (spec).
    held = prior.get("regime")
    if held in LADDER and LADDER.index(held) > LADDER.index(regime):
        regime = held
        notes.append("measured %s; permissions held at %s from earlier today" % (measured, held))
        stand_down = stand_down or regime == "STAND_DOWN"

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
        **PERMISSIONS["STAND_DOWN"],
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
    assert r["risk_budget_usd"] == 2500 and r["max_contracts"] == 5
    assert r["min_strike_distance_pct"] == 1.0 and r["put_spreads_allowed"] is True

    # Fear-only RISK_OFF: reduced size, still trading. NOT a stand-down.
    fear = classify({"SPY": -0.70, "GLD": 0.90, "GDX": 0.60, "UUP": 0.10, "TLT": 0.20})
    assert fear["regime"] == "RISK_OFF", fear
    assert fear["stand_down"] is False and fear["put_spreads_allowed"] is True, fear
    assert fear["risk_budget_usd"] == 1000 and fear["max_contracts"] == 2, fear
    assert fear["allowed_strategies"] == ["PUT_CREDIT_SPREAD"], fear

    # Stand-down is its own state: no risk, no put spreads, latches for the day.
    sd = classify({"SPY": -1.40, "GLD": 1.20, "GDX": 0.90, "UUP": 0.10, "TLT": 0.30})
    assert sd["regime"] == "STAND_DOWN" and sd["stand_down"] is True, sd
    assert sd["risk_budget_usd"] == 0 and sd["put_spreads_allowed"] is False, sd
    assert sd["allowed_strategies"] == [], sd
    later = classify(calm, prior={"stand_down": True, "regime": sd["regime"]})
    assert later["regime"] == "STAND_DOWN" and later["put_spreads_allowed"] is False, later
    assert later["risk_budget_usd"] == 0 and later["stand_down"] is True, later
    # The calmer afternoon is recorded for transparency, just never applied.
    assert later["regime_measured"] == "RISK_ON", later

    # A missing secondary input must not loosen a latched stand-down.
    blind_latch = classify(dict(calm, GDX=None), prior={"stand_down": True})
    assert blind_latch["regime"] == "STAND_DOWN" and blind_latch["risk_budget_usd"] == 0
    assert blind_latch["regime_measured"] == "NEUTRAL", blind_latch

    # RISK_OFF and STAND_DOWN must be machine-distinguishable, not prose.
    assert (fear["regime"], fear["stand_down"]) != (sd["regime"], sd["stand_down"])

    # Critical input missing -> HALTED, never a regime.
    halted = classify({"SPY": None, "GLD": 0.4, "GDX": 0.1, "UUP": 0.0, "TLT": 0.0})
    assert halted["operating_state"] == "HALTED" and halted["regime"] is None, halted

    # Secondary input missing -> DEGRADED, still produces a regime, more cautious.
    deg = classify({"SPY": 0.10, "GLD": 0.05, "GDX": None, "UUP": 0.02, "TLT": 0.01})
    assert deg["operating_state"] == "DEGRADED" and deg["regime"] == "NEUTRAL", deg

    # A data gap must never manufacture a stand-down, even from RISK_OFF.
    blind = classify({"SPY": -0.70, "GLD": 0.90, "GDX": None, "UUP": None, "TLT": None})
    assert blind["regime"] == "RISK_OFF" and blind["stand_down"] is False, blind

    # Strong dollar tightens only while stocks are not clearly positive.
    dollar = classify({"SPY": -0.10, "GLD": 0.60, "GDX": 0.50, "UUP": 0.40, "TLT": 0.0})
    assert dollar["regime"] == "NEUTRAL", dollar
    spy_up = classify({"SPY": 0.40, "GLD": 0.60, "GDX": 0.50, "UUP": 0.40, "TLT": 0.0})
    assert spy_up["regime"] == "RISK_ON", spy_up

    # Weak dollar is context only - it never moves the regime or cancels a warning.
    weak = classify({"SPY": 0.10, "GLD": 0.60, "GDX": 0.50, "UUP": -0.40, "TLT": 0.0})
    assert weak["regime"] == "RISK_ON" and "dollar weak" in weak["reason"], weak
    weak_fear = classify({"SPY": -0.70, "GLD": 0.90, "GDX": 0.60, "UUP": -0.40, "TLT": 0.0})
    assert weak_fear["regime"] == "RISK_OFF" and "dollar weak" in weak_fear["reason"]

    # Divergence needs GLD >= 0.25, not merely positive.
    div = classify({"SPY": 0.10, "GLD": 0.80, "GDX": -0.10, "UUP": 0.0, "TLT": 0.0})
    assert div["regime"] == "NEUTRAL", div
    edge = classify({"SPY": 0.10, "GLD": 0.30, "GDX": -0.50, "UUP": 0.0, "TLT": 0.0})
    assert edge["regime"] == "NEUTRAL", edge
    below = classify({"SPY": 0.10, "GLD": 0.10, "GDX": -0.70, "UUP": 0.0, "TLT": 0.0})
    assert below["regime"] == "RISK_ON", below

    # Modifiers stack but can never reach STAND_DOWN.
    both = classify({"SPY": -0.10, "GLD": 0.80, "GDX": -0.10, "UUP": 0.40, "TLT": 0.0})
    assert both["regime"] == "RISK_OFF" and both["stand_down"] is False, both

    # Asymmetric caution: a calmer afternoon does not loosen the morning.
    afternoon = classify(calm, prior={"regime": "RISK_OFF"})
    assert afternoon["regime"] == "RISK_OFF" and afternoon["regime_measured"] == "RISK_ON"
    assert afternoon["risk_budget_usd"] == 1000

    # Every regime returns a complete, in-band permission block.
    for case in (calm, fear, {"SPY": -0.70, "GLD": 0.90, "GDX": None, "UUP": None, "TLT": None}):
        block = classify(case)
        for field in ("risk_budget_usd", "max_contracts", "min_strike_distance_pct",
                      "max_positions", "allowed_strategies", "put_spreads_allowed", "reason"):
            assert field in block, (field, block)
        assert 0 <= block["risk_budget_usd"] <= 2500
        assert 1.0 <= block["min_strike_distance_pct"] <= 2.5

    # Sizing table matches the frozen V2 spec exactly.
    assert {k: v["risk_budget_usd"] for k, v in PERMISSIONS.items()} == {
        "RISK_ON": 2500, "NEUTRAL": 1500, "RISK_OFF": 1000, "STAND_DOWN": 0}
    for name, perm in PERMISSIONS.items():
        assert perm["max_contracts"] == perm["risk_budget_usd"] // 500, name


if __name__ == "__main__":
    _self_check()
    if os.environ.get("ALPACA_API_KEY"):
        print(json.dumps(classify(fetch_signals()), indent=2))
