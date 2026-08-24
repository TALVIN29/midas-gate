"""run.py - one scheduled cycle, end to end.

    python run.py --run-id 2026-09-02-1305

Reads persisted state first: if a halt is latched, the run stops before any
model client exists. Then regime -> envelope -> agent -> validator -> order ->
audit -> publish. audit.py always runs, including on halted and no-trade runs,
because every scheduled run belongs in the record.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

import agent
import audit
import gates


def main() -> int:
    run_id = None
    if "--run-id" in sys.argv:
        run_id = sys.argv[sys.argv.index("--run-id") + 1]
    run_id = run_id or datetime.now(gates.ET).strftime("%Y-%m-%d-%H%M")

    previous = {}
    if os.path.exists(audit.STATE_PATH):
        try:
            previous = json.load(open(audit.STATE_PATH))
        except json.JSONDecodeError:
            print("state.json unreadable - treating as empty, not overwriting")

    status = previous.get("status", {})
    if status.get("competition_halt") or status.get("review_required"):
        # Deterministically halted: no MCP, no model, no market interaction.
        print("HALTED (%s) - no agent invocation" % status.get("state_reason", ""))
        record = {"run_id": run_id, "regime": {}, "envelope": {
            "allowed": False, "operating_state": status.get("operating_state", "HALTED"),
            "reason": "LATCHED_HALT", "detail": status.get("state_reason", "")},
            "proposal": {"action": "NONE", "reasoning": status.get("state_reason", "")}}
        state = audit.build_state(record, {"equity": previous.get("pnl", {}).get(
            "account_value", gates.COMPETITION_START_EQUITY)},
            previous.get("positions", []), previous=previous)
        print("published %s" % audit.publish(state))
        return 0

    mcp = agent.MCP()
    try:
        record = agent.run(run_id=run_id, mcp=mcp)
        account = mcp.call("get_account_info")
        positions = mcp.call("get_all_positions")
        positions = positions if isinstance(positions, list) else positions.get("result", [])
        spot = agent._spot(mcp.call("get_stock_latest_quote", symbols="SPY"))
    finally:
        mcp.close()

    state = audit.build_state(record, account, positions, previous=previous,
                             spot_at_fill=spot, now=datetime.now(timezone.utc))
    path = audit.publish(state)
    run_entry = state["runs"][0]
    print("AUDIT=%s outcome=%s state=%s pnl=%+.2f -> %s"
          % (run_entry["audit_result"], run_entry["outcome_class"],
             state["status"]["operating_state"], state["pnl"]["total_pnl"], path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
