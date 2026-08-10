"""Event-driven stage aliases — legacy tick loop still names these phase0–phase3."""

from __future__ import annotations

# Advisor / SWARM session (Explorer, Verifier, compile leaf contract inputs)
ADVISOR_SESSION = "phase0"

# Work cycle: select ready node → Maker → Checker → Gate
WORK_CYCLE = "phase1"

# Post-Gate: repair feedback, veto, memory phase3 (not a fixed global phase boundary)
POST_GATE = "phase2"

# Tick export: projections, Σ refine staging, quota hydration
TICK_EXPORT = "phase3"

# Legacy names retained for log grep / dashboard compatibility
PHASE0 = ADVISOR_SESSION
PHASE1 = WORK_CYCLE
PHASE2 = POST_GATE
PHASE3 = TICK_EXPORT
