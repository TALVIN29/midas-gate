# Midas Gate — module documentation

Plain-language specs for every part of the system. Written **before** the code, so
each file below is the contract that the code has to satisfy.

The strategy and the schedule live in [`../PLAN.md`](../PLAN.md). This folder is the
"how it actually works" layer.

---

## The two facts that shape everything

**1. There are only about four trading days.** Aug 29, Sep 2, Sep 3, and Sep 4 up to
roughly 11:00 ET. Labor Day closes Sep 1.

Four days is far too short to bet on a market going up or down and call the result
skill — that is a coin flip. So we do not bet on direction. We **sell options and
collect the premium**, which pays us a little every day simply because time passes.
That works in a flat market, a mildly-up market, and a mildly-down market. It turns
"did we get lucky" into "did we engineer this properly".

**2. Alpaca's free data feed labels its option prices "indicative".** The numbers it
gives for the risk measures (the greeks) are not trustworthy. Paying for the real
feed is $99/month.

So we never let those numbers pick our trades. We choose which contracts to sell by
**how far away the price is from where the market is trading right now**, measured as
a percentage. That number is reliable. We compute the greeks ourselves and show them
on the dashboard as context only — never as an input to a decision.

---

## How the pieces chain together

```
GitHub Actions cron (weekdays, 2 runs a day)
  │
  ├─ 1. regime.py   reads gold-related prices, decides today's mood:
  │                 RISK_ON | NEUTRAL | RISK_OFF, plus how big we may trade
  │
  ├─ 2. gates.py    reads the account, works out the ENVELOPE — the complete list
  │                 of trades that are legal right now. Or refuses to produce one
  │                 at all, if a loss limit has been hit.
  │
  ├─ 3. agent.py    the AI. Receives the envelope. Picks one trade from inside it
  │                 and places it, through Alpaca's MCP server. Writes down why.
  │
  └─ 4. audit.py    checks what actually got filled, confirms it obeyed the
                    envelope, recomputes profit and loss, publishes site/state.json
```

The important design choice: **step 2 runs before step 3.** The AI never gets the
chance to break a risk limit, because by the time it is asked anything, the only
options in front of it are already legal ones. That is a much stronger guarantee than
writing "please do not exceed $500 of risk" in a prompt and hoping.

---

## The files

| Doc | Module | What it does |
|---|---|---|
| [regime.md](regime.md) | `regime.py` | Gold prices in, today's risk mood out |
| [gates.md](gates.md) | `gates.py` | Account state in, list of legal trades out |
| [bs.md](bs.md) | `bs.py` | Our own option maths, for display only |
| [agent.md](agent.md) | `agent.py` | The AI that picks and places the trade |
| [audit.md](audit.md) | `audit.py` | Checks the AI, publishes the results |
| [backtest.md](backtest.md) | `backtest.py` | Historical evidence the strategy works |
| [workflow.md](workflow.md) | `.github/workflows/trade.yml` | The clock that runs it all |
| [dashboard.md](dashboard.md) | `site/` | The public web page |

---

## Glossary

Defined once here, then used freely in the other docs.

| Term | Plain meaning |
|---|---|
| **option** | A contract to buy or sell a stock at a fixed price by a fixed date. You can buy one, or sell one to someone else. |
| **call / put** | A call bets the price goes up. A put bets it goes down. |
| **strike** | The fixed price written into the option contract. |
| **spot** | What the stock is actually trading at right now. |
| **expiry / DTE** | The date the contract dies. DTE = "days to expiry". We use 1–3 DTE — very short-dated. |
| **premium** | The money paid for an option. When we *sell* one, this is money we receive. |
| **credit spread** | We sell one option and buy a cheaper, further-away one at the same time. We keep the difference in premium. The bought one caps our worst case. This is our entire strategy. |
| **defined risk** | Because of that second bought option, the most we can possibly lose on a trade is a known, fixed number. No surprises. |
| **iron condor** | Two credit spreads at once — one above the market, one below. Profits when the price stays in the middle. |
| **OTM** ("out of the money") | The strike is set somewhere the stock would have to move to reach. The further out, the safer and the less we get paid. |
| **theta** | The rate at which an option loses value purely because time passes. When we are the seller, theta is money flowing toward us every day. |
| **the greeks** | A set of numbers (theta, delta, and others) describing how an option's price reacts to things. We compute our own — see [bs.md](bs.md). |
| **the chain** | The full list of every option contract available on a stock for a given expiry. |
| **SPY / GLD / GDX / UUP / TLT** | Tradeable funds. SPY = the US stock market. GLD = gold. GDX = gold miners. UUP = the US dollar. TLT = long-term government bonds. |
| **paper account** | A fake-money Alpaca account with real market prices. Everything here is paper. |
| **MCP** | Model Context Protocol — the standard way an AI is handed a set of tools it can call. Alpaca ship an official MCP server; it is the AI's only route to the market. |
| **cron** | A schedule. "Run this at 09:35 every weekday." |
| **envelope** | Our term: the complete, pre-computed set of trades that are legal at this moment. See [gates.md](gates.md). |
| **fill** | Confirmation that an order actually executed, and at what price. |
| **drawdown** | How far the account is down from its high point. |
