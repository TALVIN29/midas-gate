"""backtest.py - same-timestamp validation of the frozen Gold Rules.

Spec: docs/backtest.md, plus the teammate's V2 handoff
(MIDAS_GATE_GOLD_RULES_V2_VALIDATION_HANDOFF.md sections 7 and 8).

This validates the rules; it does not tune them. It imports `regime.classify`
rather than reimplementing it - a backtest that reimplements the rules is
measuring a different system than the one that trades.

Sampling is at the real run times, 09:35 and 13:05 ET, using the live
measurement convention: latest available price / previous regular-session
close - 1. Close-to-close is only a proxy and is not used here.

    python backtest.py --self-test          # no network
    python backtest.py                      # six months, writes backtest_report.md
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

import regime

ET = ZoneInfo("America/New_York")
SAMPLE_TIMES = (("09:35", time(9, 35)), ("13:05", time(13, 5)))

# A price older than this at the sample instant is not "the latest available
# price", it is a stale quote. Live, that symbol would be unreadable; here it
# becomes None and classify() decides whether that is fatal. This is also what
# makes early-close half-days fall out on their own, with no holiday table.
STALE_TOLERANCE = timedelta(minutes=15)

CACHE_DIR = Path("data")
REPORT_PATH = Path("backtest_report.md")

# Markers emitted by regime.classify() into `reason`. Attribution reads these
# rather than recomputing the rules. _self_check pins them, so renaming a note
# in regime.py breaks this file loudly instead of silently zeroing a counter.
MARKERS = {
    "stand_down": "stand-down:",
    "fear": "fear rising:",
    "divergence": "divergence:",
    "strong_dollar": "dollar firm with gold bid",
    "weak_dollar": "dollar weak",
    "degraded": "secondary input(s) missing",
}


# --------------------------------------------------------------------------
# data
# --------------------------------------------------------------------------

def _client():
    from alpaca.data.historical import StockHistoricalDataClient

    if not os.environ.get("ALPACA_API_KEY"):
        # The repo keeps credentials in .env; regime.py reads them from the
        # environment, so load them the same way rather than inventing a second
        # configuration path.
        env = Path(".env")
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return StockHistoricalDataClient(
        os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"]
    )


def _fetch(timeframe, start: date, end: date, tag: str, refresh: bool) -> pd.DataFrame:
    """Bars for every regime symbol, cached. Index: (symbol, UTC timestamp)."""
    from alpaca.data.requests import StockBarsRequest

    CACHE_DIR.mkdir(exist_ok=True)
    path = CACHE_DIR / ("%s_%s_%s.csv" % (tag, start, end))
    if path.exists() and not refresh:
        df = pd.read_csv(path, parse_dates=["timestamp"])
    else:
        print("fetching %s bars %s..%s (SIP)" % (tag, start, end), file=sys.stderr)
        bars = _client().get_stock_bars(StockBarsRequest(
            symbol_or_symbols=list(regime.SYMBOLS),
            timeframe=timeframe,
            start=datetime.combine(start, time(0, 0)),
            end=datetime.combine(end, time(23, 59)),
            # IEX is not usable here: probed six months back it dropped whole
            # stretches of UUP. SIP is the consolidated tape.
            feed="sip",
        ))
        df = bars.df.reset_index()
        df.to_csv(path, index=False)
        print("cached %d bars -> %s" % (len(df), path), file=sys.stderr)

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df.set_index(["symbol", "timestamp"]).sort_index()


def _by_symbol(df: pd.DataFrame) -> dict:
    """Split the MultiIndex frame into one timestamp-indexed frame per symbol."""
    return {sym: df.loc[sym] for sym in df.index.get_level_values(0).unique()}


def price_at(frame: pd.DataFrame, ts: datetime) -> float | None:
    """Close of the last bar at or before `ts`, or None if there is none or it
    is stale. The backtest's stand-in for get_stock_latest_trade()."""
    pos = frame.index.searchsorted(pd.Timestamp(ts).tz_convert("UTC"), side="right") - 1
    if pos < 0:
        return None
    bar_ts = frame.index[pos]
    if pd.Timestamp(ts).tz_convert("UTC") - bar_ts > STALE_TOLERANCE:
        return None
    return float(frame["close"].iloc[pos])


def prev_closes(daily: dict) -> dict:
    """symbol -> {session date: previous regular-session close}."""
    out = {}
    for sym, frame in daily.items():
        dates = [t.tz_convert(ET).date() for t in frame.index]
        closes = frame["close"].tolist()
        out[sym] = {d: closes[i - 1] for i, d in enumerate(dates) if i > 0}
    return out


# --------------------------------------------------------------------------
# replay
# --------------------------------------------------------------------------

def sample(minute: dict, prev: dict, day: date, at: time) -> dict:
    """The `signals` dict classify() expects, measured at one instant."""
    ts = datetime.combine(day, at, tzinfo=ET)
    signals = {}
    for sym in regime.SYMBOLS:
        frame, base = minute.get(sym), prev.get(sym, {}).get(day)
        px = price_at(frame, ts) if frame is not None else None
        signals[sym] = None if px is None or not base else round((px / base - 1) * 100, 4)
    return signals


def replay(minute: dict, prev: dict, sessions: list[date]) -> list[dict]:
    """One record per session: the 09:35 read, then the 13:05 read carrying the
    morning's state forward exactly as run.py threads it through state.json."""
    records = []
    for day in sessions:
        row = {"date": day}
        am = regime.classify(sample(minute, prev, day, SAMPLE_TIMES[0][1]))
        row["09:35"] = am
        pm_signals = sample(minute, prev, day, SAMPLE_TIMES[1][1])
        if pm_signals["SPY"] is None and pm_signals["GLD"] is None:
            # Early close: no 13:05 exists. Never forward-fill a stale price
            # into a regime decision - record the session as morning-only.
            row["13:05"] = None
            row["early_close"] = True
        else:
            row["13:05"] = regime.classify(
                pm_signals, prior={"regime": am["regime"], "stand_down": am["stand_down"]})
            row["early_close"] = False
        records.append(row)
    return records


def fired(block: dict, key: str) -> bool:
    return block is not None and MARKERS[key] in (block.get("reason") or "")


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------

def _impact(minute: dict, daily: dict, records: list[dict]) -> dict:
    """SPY-based proxies for trading impact. There is no fill history and no
    cheap historical option chain, so option-level P&L by regime is out of
    reach; the handoff scopes that section "where supported". What SPY can
    honestly answer is how the tape behaved after each call."""
    spy_min, spy_day = minute.get("SPY"), daily.get("SPY")
    closes = {t.tz_convert(ET).date(): c for t, c in
              zip(spy_day.index, spy_day["close"])} if spy_day is not None else {}
    order = sorted(closes)
    nxt = {d: closes[order[i + 1]] for i, d in enumerate(order) if i + 1 < len(order)}

    per = defaultdict(list)
    for row in records:
        block = row["13:05"] or row["09:35"]
        state = block.get("regime") or block.get("operating_state")
        day = row["date"]
        ts = datetime.combine(day, SAMPLE_TIMES[0][1], tzinfo=ET)
        px = price_at(spy_min, ts) if spy_min is not None else None
        if px is None or day not in closes:
            continue
        # Bounded to this session's regular close - "adverse move after the
        # call" means today, not the rest of the window.
        close_ts = datetime.combine(day, time(16, 0), tzinfo=ET)
        rest = spy_min.loc[pd.Timestamp(ts).tz_convert("UTC"):
                           pd.Timestamp(close_ts).tz_convert("UTC")]
        per[state].append({
            "to_close": (closes[day] / px - 1) * 100,
            "to_next": (nxt[day] / px - 1) * 100 if day in nxt else None,
            "adverse": (float(rest["low"].min()) / px - 1) * 100 if len(rest) else 0.0,
        })
    return per


def _fmt(rows: list[dict], key: str) -> str:
    vals = [r[key] for r in rows if r[key] is not None]
    if not vals:
        return "n/a"
    return "%+.2f%% avg, %+.2f%% worst" % (sum(vals) / len(vals), min(vals))


def report(records: list[dict], impact: dict, start: date, end: date, label: str) -> str:
    n = len(records)
    L = ["# Gold Rules %s - same-timestamp validation" % label, "",
         "Window `%s` .. `%s`, **%d sessions**. Sampled at **09:35 and 13:05 ET** "
         "on Alpaca SIP minute bars, using the live convention "
         "`latest available price / previous regular-session close - 1`. "
         "Rules imported from `regime.py` (`rules_version: %s`), not reimplemented."
         % (start, end, n, regime.RULES_VERSION), ""]

    # --- signal frequency ---
    uniq = {k: set() for k in MARKERS}
    overlap, am_signals, newly_cautious, calmer_latched, early = set(), 0, 0, 0, 0
    for row in records:
        early += bool(row["early_close"])
        for tag, block in (("09:35", row["09:35"]), ("13:05", row["13:05"])):
            if block is None:
                continue
            hits = [k for k in MARKERS if fired(block, k)]
            for k in hits:
                uniq[k].add(row["date"])
            # Only executable rules count as an overlap; weak dollar is context.
            if len([k for k in hits if k not in ("weak_dollar", "degraded")]) >= 2:
                overlap.add(row["date"])
        am, pm = row["09:35"], row["13:05"]
        if am["regime"] not in (None, "RISK_ON"):
            am_signals += 1
        if pm is not None and am["regime"] in regime.LADDER and pm["regime_measured"] in regime.LADDER:
            if regime.LADDER.index(pm["regime_measured"]) > regime.LADDER.index(am["regime"]):
                newly_cautious += 1
            if pm["regime"] != pm["regime_measured"]:
                calmer_latched += 1

    # Fear-only = the fear rule fired on a day that never stood down.
    fear_only = uniq["fear"] - uniq["stand_down"]

    L += ["## Signal frequency", "",
          "| Signal | Unique days |", "|---|---:|",
          "| `STAND_DOWN` (rule 1) | %d |" % len(uniq["stand_down"]),
          "| fear-only `RISK_OFF` (rule 2) | %d |" % len(fear_only),
          "| divergence downgrades (rule 3) | %d |" % len(uniq["divergence"]),
          "| strong-dollar downgrades (rule 4) | %d |" % len(uniq["strong_dollar"]),
          "| weak-dollar notes (context only) | %d |" % len(uniq["weak_dollar"]),
          "| sessions with 2+ executable rules overlapping | %d |" % len(overlap),
          "| degraded (a secondary input unreadable) | %d |" % len(uniq["degraded"]), "",
          "| Intraday | Sessions |", "|---|---:|",
          "| 09:35 reads that were not `RISK_ON` | %d |" % am_signals,
          "| 13:05 measured **more** cautious than 09:35 | %d |" % newly_cautious,
          "| 13:05 measured calmer but stayed latched | %d |" % calmer_latched,
          "| early closes (no 13:05 sample exists) | %d |" % early, ""]

    # --- regime distribution ---
    def dist(which):
        c = Counter()
        for row in records:
            b = row[which] if which != "effective" else (row["13:05"] or row["09:35"])
            if b is None:
                continue
            c[b.get("regime") or b.get("operating_state")] += 1
        return c

    L += ["## Regime distribution", "",
          "`effective` is the state the day actually traded under: the 13:05 read where "
          "one exists, otherwise the morning.", "",
          "| State | 09:35 | 13:05 | effective | % of sessions |", "|---|---:|---:|---:|---:|"]
    a, p, e = dist("09:35"), dist("13:05"), dist("effective")
    for state in list(regime.LADDER) + ["HALTED"]:
        L.append("| `%s` | %d | %d | %d | %.1f%% |"
                 % (state, a[state], p[state], e[state], 100 * e[state] / n if n else 0))
    L.append("")

    # --- trading impact ---
    L += ["## Trading impact (SPY proxies)", "",
          "No fill history and no cheap historical option chain exist for this window, so "
          "option-level P&L by regime is **not** reported - the handoff scopes that "
          "\"where supported\". These are the honest substitutes: how SPY actually behaved "
          "after each call, measured from the 09:35 sample price.", "",
          "| State | days | 09:35 -> same-day close | 09:35 -> next close | max adverse intraday | permitted open risk |",
          "|---|---:|---|---|---|---:|"]
    for state in list(regime.LADDER) + ["HALTED"]:
        rows = impact.get(state, [])
        budget = regime.PERMISSIONS.get(state, {}).get("risk_budget_usd", 0)
        L.append("| `%s` | %d | %s | %s | %s | $%s |"
                 % (state, len(rows), _fmt(rows, "to_close"), _fmt(rows, "to_next"),
                    _fmt(rows, "adverse"), "{:,}".format(budget)))
    L.append("")

    sd_rows = impact.get("STAND_DOWN", [])
    hurt = [r for r in sd_rows if r["to_close"] < 0]
    L += ["**Stand-down days, split by what the tape did next.** A short put spread is hurt "
          "when SPY falls, so:", "",
          "- losing put spreads plausibly avoided: **%d** of %d (SPY fell after the call)"
          % (len(hurt), len(sd_rows)),
          "- profitable opportunities plausibly skipped: **%d** (SPY rose or was flat)"
          % (len(sd_rows) - len(hurt)), ""]

    # --- verdict ---
    def verdict(name, observed, lo, hi):
        mark = "PASS" if lo <= observed <= hi else "**FLAG**"
        return "| %s | %d | %d-%d | %s |" % (name, observed, lo, hi, mark)

    risk_off_days = len(uniq["stand_down"] | uniq["fear"])
    L += ["## Verdict against the handoff's sanity ranges", "",
          "These are validation ranges, not optimisation targets.", "",
          "| Check | Observed | Target | |", "|---|---:|---|---|",
          verdict("unique `STAND_DOWN` days", len(uniq["stand_down"]), 2, 4),
          verdict("fear-only `RISK_OFF` days", len(fear_only), 3, 6),
          verdict("total days at `RISK_OFF` or worse", risk_off_days, 0, 10), "",
          "A **FLAG** is not permission to move a threshold. Per handoff section 12, "
          "return the evidence first; any V3 is documented as "
          "`V2 result -> observed failure -> human-approved amendment`.", "",
          "## Not covered here", "",
          "- **Event-calendar gate** (handoff section 9) is not implemented. The handoff "
          "forbids inventing a blackout window without sign-off, so it awaits a decision "
          "on the window and is deliberately not another regime vote.",
          "- **Option-level P&L, win rate and realised open risk** need fills that do not "
          "exist yet. The SPY proxies above are what this window can honestly support.", ""]

    # --- the days themselves ---
    flagged = [r for r in records
               if (r["13:05"] or r["09:35"]).get("regime") not in ("RISK_ON", None)
               or r["09:35"].get("regime") not in ("RISK_ON", None)]
    L += ["## Every session where something fired", "",
          "| Date | 09:35 | 13:05 | effective | why |", "|---|---|---|---|---|"]
    for row in flagged:
        am, pm = row["09:35"], row["13:05"]
        eff = pm or am
        L.append("| %s | %s | %s | `%s` | %s |"
                 % (row["date"], am.get("regime") or am["operating_state"],
                    (pm.get("regime") or pm["operating_state"]) if pm else "early close",
                    eff.get("regime") or eff["operating_state"], eff["reason"]))
    if not flagged:
        L.append("| - | - | - | - | nothing fired in the window |")
    L.append("")
    return "\n".join(L)


# --------------------------------------------------------------------------

def run(start: date, end: date, label: str, refresh: bool) -> str:
    from alpaca.data.timeframe import TimeFrame

    daily = _by_symbol(_fetch(TimeFrame.Day, start - timedelta(days=15), end, "daily", refresh))
    minute = _by_symbol(_fetch(TimeFrame.Minute, start, end, "minute", refresh))
    prev = prev_closes(daily)
    sessions = sorted(d for d in prev.get("SPY", {}) if start <= d <= end)
    if not sessions:
        raise SystemExit("no sessions in %s..%s" % (start, end))
    records = replay(minute, prev, sessions)
    return report(records, _impact(minute, daily, records), sessions[0], sessions[-1], label)


def _frame(rows: list[tuple[str, float]]) -> pd.DataFrame:
    idx = pd.to_datetime([t for t, _ in rows], utc=True)
    return pd.DataFrame({"close": [c for _, c in rows], "low": [c for _, c in rows]}, index=idx)


def _self_check() -> None:
    # regime.py still emits every marker attribution depends on. If a note is
    # reworded there, this fails rather than silently reporting zero.
    assert MARKERS["stand_down"] in regime.classify(
        {"SPY": -1.4, "GLD": 1.2, "GDX": 0.9, "UUP": 0.1, "TLT": 0.0})["reason"]
    assert MARKERS["fear"] in regime.classify(
        {"SPY": -0.7, "GLD": 0.9, "GDX": 0.6, "UUP": 0.1, "TLT": 0.0})["reason"]
    assert MARKERS["divergence"] in regime.classify(
        {"SPY": 0.1, "GLD": 0.8, "GDX": -0.1, "UUP": 0.0, "TLT": 0.0})["reason"]
    assert MARKERS["strong_dollar"] in regime.classify(
        {"SPY": -0.1, "GLD": 0.6, "GDX": 0.5, "UUP": 0.4, "TLT": 0.0})["reason"]
    assert MARKERS["weak_dollar"] in regime.classify(
        {"SPY": 0.1, "GLD": 0.6, "GDX": 0.5, "UUP": -0.4, "TLT": 0.0})["reason"]
    assert MARKERS["degraded"] in regime.classify(
        {"SPY": 0.1, "GLD": 0.05, "GDX": None, "UUP": 0.02, "TLT": 0.0})["reason"]

    # Sampling takes the last bar at or before the instant, never a later one.
    f = _frame([("2026-03-03 14:33:00Z", 10.0), ("2026-03-03 14:34:00Z", 11.0),
                ("2026-03-03 14:36:00Z", 99.0)])
    ts = datetime(2026, 3, 3, 9, 35, tzinfo=ET)   # 14:35Z
    assert price_at(f, ts) == 11.0, price_at(f, ts)

    # Nothing yet today, and a stale last bar, both read as unavailable.
    assert price_at(f, datetime(2026, 3, 3, 9, 30, tzinfo=ET)) is None
    assert price_at(f, datetime(2026, 3, 3, 13, 5, tzinfo=ET)) is None

    day = date(2026, 3, 3)
    prev = {s: {day: 100.0} for s in regime.SYMBOLS}

    # An early close leaves no 13:05 sample; the morning is not carried forward
    # as if it were an afternoon measurement.
    half = {s: _frame([("2026-03-03 14:34:00Z", 100.0)]) for s in regime.SYMBOLS}
    row = replay(half, prev, [day])[0]
    assert row["early_close"] is True and row["13:05"] is None, row

    # The latch survives the 13:05 read: a stand-down morning stays stood down
    # even when the afternoon measures calm.
    scared = {"SPY": 98.0, "GLD": 101.5, "GDX": 101.0, "UUP": 100.1, "TLT": 100.2}
    full = {s: _frame([("2026-03-03 14:34:00Z", scared[s]),
                       ("2026-03-03 18:04:00Z", 100.05)]) for s in regime.SYMBOLS}
    row = replay(full, prev, [day])[0]
    assert row["09:35"]["regime"] == "STAND_DOWN", row["09:35"]
    assert row["13:05"]["regime"] == "STAND_DOWN", row["13:05"]
    assert row["13:05"]["regime_measured"] == "RISK_ON", row["13:05"]
    assert row["13:05"]["stand_down"] is True and row["13:05"]["risk_budget_usd"] == 0

    # A calm morning does not latch anything.
    calm = {s: _frame([("2026-03-03 14:34:00Z", 100.05),
                       ("2026-03-03 18:04:00Z", 100.05)]) for s in regime.SYMBOLS}
    row = replay(calm, prev, [day])[0]
    assert row["09:35"]["regime"] == "RISK_ON" and row["13:05"]["regime"] == "RISK_ON"

    # The report renders end to end on a real record set.
    text = report(replay(full, prev, [day]), {}, day, day, "V2-selftest")
    assert "STAND_DOWN" in text and "Verdict" in text
    print("backtest self-checks passed")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", type=date.fromisoformat)
    ap.add_argument("--end", type=date.fromisoformat)
    ap.add_argument("--rules", default=regime.RULES_VERSION, help="label recorded in the report")
    ap.add_argument("--refresh", action="store_true", help="ignore the cached bars")
    ap.add_argument("--self-test", action="store_true", help="offline checks only")
    args = ap.parse_args()

    if args.self_test:
        _self_check()
        raise SystemExit(0)

    end = args.end or date.today() - timedelta(days=1)
    start = args.start or end - timedelta(days=183)
    text = run(start, end, args.rules, args.refresh)
    REPORT_PATH.write_text(text, encoding="utf-8")
    print(text)
    print("\nwritten to %s" % REPORT_PATH, file=sys.stderr)
