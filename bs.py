"""bs.py - Black-Scholes greeks, computed locally, for DISPLAY ONLY.

Spec: docs/bs.md. Alpaca's free feed is labelled "indicative"; it does return
greeks, but they are modelled numbers on a feed the vendor will not call
authoritative. So we compute our own and show them as context.

These numbers never select a trade. They are not in the regime block, not in
the envelope, not in the pre-trade validator, and not in any audit check -
strike selection is percentage distance from spot, a direct measurement.

Run `python bs.py` for the self-checks.
"""

from __future__ import annotations

import math

# ASSUMPTION: short-term Treasury rate, hardcoded. Over a 1-3 day contract the
# rate is worth fractions of a cent, and fetching it would add a network
# dependency to a file that has none.
RISK_FREE_RATE = 0.043


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def greeks(S: float, K: float, T: float, sigma: float, r: float = RISK_FREE_RATE,
           option_type: str = "put") -> dict:
    """Price and greeks for one European option. T in years, sigma annualised.

    theta is per day. An expired contract returns its value at expiry rather
    than raising - a display calculator must never take down the audit.
    """
    if option_type not in ("call", "put"):
        raise ValueError("option_type must be 'call' or 'put'")
    if sigma <= 0:
        raise ValueError("volatility must be positive - there is no sensible answer")

    if T <= 0:
        intrinsic = max(S - K, 0.0) if option_type == "call" else max(K - S, 0.0)
        return {"price": intrinsic, "delta": 0.0, "gamma": 0.0, "theta": 0.0,
                "vega": 0.0, "note": "expired"}

    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    discount = math.exp(-r * T)
    common_theta = -(S * _norm_pdf(d1) * sigma) / (2 * math.sqrt(T))

    if option_type == "call":
        price = S * _norm_cdf(d1) - K * discount * _norm_cdf(d2)
        delta = _norm_cdf(d1)
        theta = common_theta - r * K * discount * _norm_cdf(d2)
    else:
        price = K * discount * _norm_cdf(-d2) - S * _norm_cdf(-d1)
        delta = _norm_cdf(d1) - 1.0
        theta = common_theta + r * K * discount * _norm_cdf(-d2)

    return {
        "price": price,
        "delta": delta,
        "gamma": _norm_pdf(d1) / (S * sigma * math.sqrt(T)),
        "theta": theta / 365.0,          # per day, as displayed
        "vega": S * _norm_pdf(d1) * math.sqrt(T) / 100.0,  # per 1 vol point
    }


def spread_theta_per_day(short: dict, long: dict, contracts: int = 1) -> float:
    """Net daily time decay for a credit spread, in dollars, in our favour.

    We are short the near leg, so its decay flows toward us.
    """
    return (-short["theta"] + long["theta"]) * 100 * contracts


def _self_check() -> None:
    # The textbook case: every options text and online calculator agrees on this.
    call = greeks(S=100, K=100, T=1.0, sigma=0.20, r=0.05, option_type="call")
    assert abs(call["price"] - 10.45) < 0.01, call["price"]

    # Put-call parity: C - P == S - K*exp(-rT). Catches sign errors, which are
    # the most common mistake in this kind of code.
    put = greeks(S=100, K=100, T=1.0, sigma=0.20, r=0.05, option_type="put")
    parity = call["price"] - put["price"]
    assert abs(parity - (100 - 100 * math.exp(-0.05))) < 1e-6, parity

    # Delta ranges.
    assert 0.0 < call["delta"] < 1.0, call["delta"]
    assert -1.0 < put["delta"] < 0.0, put["delta"]

    # Both contracts lose value as time passes.
    assert call["theta"] < 0 and put["theta"] < 0

    # Expired contract returns intrinsic value, does not raise.
    exp_put = greeks(S=100, K=110, T=-0.01, sigma=0.2, option_type="put")
    assert exp_put["price"] == 10 and exp_put["note"] == "expired"
    assert greeks(S=100, K=90, T=0, sigma=0.2, option_type="put")["price"] == 0

    # Nonsense volatility is refused rather than answered.
    for bad in (0.0, -0.2):
        try:
            greeks(S=100, K=100, T=0.1, sigma=bad)
        except ValueError:
            pass
        else:
            raise AssertionError("sigma=%s should raise" % bad)

    # A realistic 2-DTE SPY put spread: decay should be positive for us.
    T = 2 / 365
    short_leg = greeks(S=764.43, K=752, T=T, sigma=0.17, option_type="put")
    long_leg = greeks(S=764.43, K=747, T=T, sigma=0.17, option_type="put")
    assert short_leg["price"] > long_leg["price"] > 0
    assert spread_theta_per_day(short_leg, long_leg) > 0


if __name__ == "__main__":
    _self_check()
    T = 2 / 365
    short_leg = greeks(S=764.43, K=752, T=T, sigma=0.17, option_type="put")
    long_leg = greeks(S=764.43, K=747, T=T, sigma=0.17, option_type="put")
    print("SPY 764.43, 752/747 put spread, 2 DTE, sigma 0.17")
    print("  short 752: price %.2f delta %+.3f theta %+.3f"
          % (short_leg["price"], short_leg["delta"], short_leg["theta"]))
    print("  long  747: price %.2f delta %+.3f theta %+.3f"
          % (long_leg["price"], long_leg["delta"], long_leg["theta"]))
    print("  time decay working for us: $%.2f/day per contract"
          % spread_theta_per_day(short_leg, long_leg))
